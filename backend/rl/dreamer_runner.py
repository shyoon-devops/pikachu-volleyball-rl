"""Vendored Dreamer V3 — minimal, SB3-compatible adapter.

ADR 0018 §5 intended to pin ``NM512/dreamerv3-torch`` by git+SHA.
Verification (2026-04-22): that repo has **no setup.py / pyproject.toml**
— it's a research script for ``python dreamer.py``, not a pip
library. No PyTorch Dreamer V3 package ships on PyPI (only Hafner's
TF/JAX ``dreamerv3`` v1.5.0, which would drag JAX into our image).
Vendoring in-tree is the only path that respects the ADR's "keep
the PyTorch stack" decision.

This is a compact Dreamer V3 **skeleton** — correct three-phase
structure (env interaction → world-model train → AC imagine) on
real tensors, but WITHOUT the full Hafner 2023 engineering
niceties (KL-balance schedule, symlog reward head, two-hot
encoding, prior ensembles). Those ship with the v3.x parity
follow-up; the algorithm is opt-in + **experimental** per ADR
0018 §8 exactly to create room for that swap without breaking the
boundary contract.

API delivered: ``DreamerAgent(env, ...)`` constructs on any
Gymnasium (Box obs, Discrete action) env; ``.learn(total_timesteps)``
runs the three phases; ``.predict(obs, deterministic)`` matches
SB3's predict contract so ``LoadedPolicyBot`` doesn't need a
separate code path; ``.save`` / ``.load`` round-trip a zip
wrapping a torch state-dict (same container convention as SB3 so
``{slug}__{exp8}__final.zip`` keeps working).
"""

from __future__ import annotations

import io
import zipfile
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch as th
import torch.nn as nn
import torch.nn.functional as F
from gymnasium import spaces


# ADR 0018 §7 — pinned defaults, NOT WS-surfaced. Reduced sizes vs
# Hafner 2023 defaults so CPU smoke tests run in under a minute;
# production GPU runs override via the factory's kwargs.
DREAMER_DEFAULT_KWARGS: dict[str, Any] = {
    "rssm_hidden_size": 512,
    "latent_dim": 32,           # categorical classes per axis
    "latent_axes": 32,          # number of categorical axes (32×32 = 1024-d latent)
    "world_model_lr": 1e-4,
    "actor_lr": 3e-5,
    "critic_lr": 3e-5,
    "imagine_horizon": 15,
    "batch_size": 16,
    "sequence_length": 64,
    "replay_capacity": 1_000_000,
    "train_every": 16,          # env steps per gradient step
    "discount": 0.99,
    "kl_scale": 1.0,
    "free_bits": 1.0,           # minimum KL per-axis (nats)
}


@dataclass
class _Step:
    """One (obs, action, reward, done) transition in the replay buffer."""
    obs: np.ndarray
    action: int
    reward: float
    done: bool


class _SequenceReplayBuffer:
    """Trajectory replay — Dreamer trains on sub-sequences, not
    single transitions. ``sample`` returns contiguous slices from
    episodes that are at least ``seq_len`` long (falling back to
    the open episode if no completed one qualifies yet)."""

    def __init__(self, capacity: int) -> None:
        self.capacity = capacity
        self._episodes: deque[list[_Step]] = deque()
        self._current: list[_Step] = []
        self._total_steps = 0

    def add(self, step: _Step) -> None:
        self._current.append(step)
        self._total_steps += 1
        if step.done:
            self._episodes.append(self._current)
            self._current = []
        while self._total_steps > self.capacity and self._episodes:
            self._total_steps -= len(self._episodes.popleft())

    def __len__(self) -> int:
        return self._total_steps

    def sample(
        self, batch_size: int, seq_len: int, obs_dim: int
    ) -> tuple[th.Tensor, th.Tensor, th.Tensor, th.Tensor] | None:
        pool = list(self._episodes)
        if self._current and len(self._current) >= seq_len:
            pool.append(self._current)
        pool = [ep for ep in pool if len(ep) >= seq_len]
        if not pool:
            return None
        obs = np.zeros((batch_size, seq_len, obs_dim), dtype=np.float32)
        act = np.zeros((batch_size, seq_len), dtype=np.int64)
        rew = np.zeros((batch_size, seq_len), dtype=np.float32)
        done = np.zeros((batch_size, seq_len), dtype=np.float32)
        rng = np.random.default_rng()
        for i in range(batch_size):
            ep = pool[rng.integers(0, len(pool))]
            start = rng.integers(0, len(ep) - seq_len + 1)
            for t in range(seq_len):
                s = ep[start + t]
                obs[i, t], act[i, t], rew[i, t], done[i, t] = (
                    s.obs, s.action, s.reward, float(s.done)
                )
        return (th.from_numpy(obs), th.from_numpy(act),
                th.from_numpy(rew), th.from_numpy(done))


class _RSSM(nn.Module):
    """Recurrent state-space model — deterministic GRU state +
    categorical stochastic latent. Dreamer V3 §3.1."""

    def __init__(
        self, obs_dim: int, action_dim: int, hidden: int,
        latent_dim: int, latent_axes: int,
    ) -> None:
        super().__init__()
        self.hidden = hidden
        self.latent_dim = latent_dim
        self.latent_axes = latent_axes
        latent_flat = latent_dim * latent_axes

        self.embed = nn.Sequential(
            nn.Linear(obs_dim, hidden), nn.SiLU(),
            nn.Linear(hidden, hidden), nn.SiLU(),
        )
        self.cell = nn.GRUCell(latent_flat + action_dim, hidden)
        self.prior_head = nn.Sequential(
            nn.Linear(hidden, hidden), nn.SiLU(),
            nn.Linear(hidden, latent_flat),
        )
        self.post_head = nn.Sequential(
            nn.Linear(hidden * 2, hidden), nn.SiLU(),
            nn.Linear(hidden, latent_flat),
        )
        self.action_dim = action_dim

    def _one_hot_latent(self, logits: th.Tensor) -> tuple[th.Tensor, th.Tensor]:
        """Straight-through categorical sample along each latent axis.

        Returns (sample, log_prob_grid) where sample is one-hot per
        axis, log_prob_grid is log-softmax(logits) for the KL term.
        """
        shape = (*logits.shape[:-1], self.latent_axes, self.latent_dim)
        logits = logits.view(*shape)
        probs = F.softmax(logits, dim=-1)
        log_probs = F.log_softmax(logits, dim=-1)
        # Straight-through: sample discrete but pass gradient through probs.
        sample = F.one_hot(
            th.distributions.Categorical(probs=probs).sample(),
            num_classes=self.latent_dim,
        ).float()
        sample = sample + probs - probs.detach()
        flat_shape = (*logits.shape[:-2], self.latent_axes * self.latent_dim)
        return sample.view(*flat_shape), log_probs

    def initial_state(self, batch_size: int, device: th.device) -> th.Tensor:
        return th.zeros(batch_size, self.hidden, device=device)

    def observe(
        self,
        obs_seq: th.Tensor,     # (B, T, obs_dim)
        action_seq: th.Tensor,  # (B, T) int64
    ) -> dict[str, th.Tensor]:
        """Run the posterior pass over a sequence, returning all the
        intermediate tensors the world-model loss needs."""
        B, T, _ = obs_seq.shape
        device = obs_seq.device
        embeds = self.embed(obs_seq)                       # (B, T, H)
        action_onehot = F.one_hot(action_seq, self.action_dim).float()

        h = self.initial_state(B, device)
        latent = th.zeros(
            B, self.latent_axes * self.latent_dim, device=device
        )
        h_list, prior_lp_list, post_lp_list, latent_list = [], [], [], []
        for t in range(T):
            cell_in = th.cat([latent, action_onehot[:, t]], dim=-1)
            h = self.cell(cell_in, h)
            prior_logits = self.prior_head(h)
            post_logits = self.post_head(th.cat([h, embeds[:, t]], dim=-1))
            latent, post_lp = self._one_hot_latent(post_logits)
            _, prior_lp = self._one_hot_latent(prior_logits)
            h_list.append(h)
            prior_lp_list.append(prior_lp)
            post_lp_list.append(post_lp)
            latent_list.append(latent)
        return {
            "h": th.stack(h_list, dim=1),
            "latent": th.stack(latent_list, dim=1),
            "prior_log_prob": th.stack(prior_lp_list, dim=1),
            "post_log_prob": th.stack(post_lp_list, dim=1),
        }

    def imagine_step(
        self, h: th.Tensor, latent: th.Tensor, action_onehot: th.Tensor,
    ) -> tuple[th.Tensor, th.Tensor]:
        """One rollout step using the PRIOR only — no obs visible."""
        cell_in = th.cat([latent, action_onehot], dim=-1)
        h_new = self.cell(cell_in, h)
        prior_logits = self.prior_head(h_new)
        latent_new, _ = self._one_hot_latent(prior_logits)
        return h_new, latent_new


def _mlp(in_dim: int, hidden: int, out_dim: int) -> nn.Sequential:
    return nn.Sequential(
        nn.Linear(in_dim, hidden), nn.SiLU(),
        nn.Linear(hidden, out_dim),
    )


class _DecoderHead(nn.Module):
    """Three heads from feat=(h, z): obs reconstruction, reward, continue."""

    def __init__(self, hidden: int, obs_dim: int, latent_flat: int) -> None:
        super().__init__()
        feat = hidden + latent_flat
        self.obs = _mlp(feat, hidden, obs_dim)
        self.reward = _mlp(feat, hidden, 1)
        self.cont = _mlp(feat, hidden, 1)

    def forward(
        self, h: th.Tensor, latent: th.Tensor,
    ) -> tuple[th.Tensor, th.Tensor, th.Tensor]:
        feat = th.cat([h, latent], dim=-1)
        return self.obs(feat), self.reward(feat).squeeze(-1), self.cont(feat).squeeze(-1)


class _ActorHead(nn.Module):
    """Categorical actor over |A|."""

    def __init__(self, hidden: int, latent_flat: int, action_dim: int) -> None:
        super().__init__()
        self.net = _mlp(hidden + latent_flat, hidden, action_dim)

    def forward(self, h: th.Tensor, latent: th.Tensor) -> th.Tensor:
        return self.net(th.cat([h, latent], dim=-1))


class _CriticHead(nn.Module):
    """V(h, z) → scalar return estimate."""

    def __init__(self, hidden: int, latent_flat: int) -> None:
        super().__init__()
        self.net = _mlp(hidden + latent_flat, hidden, 1)

    def forward(self, h: th.Tensor, latent: th.Tensor) -> th.Tensor:
        return self.net(th.cat([h, latent], dim=-1)).squeeze(-1)


class DreamerAgent:
    """SB3-compatible adapter around a minimal Dreamer V3 world model.

    The trainer treats every algorithm the same way — construct,
    call ``.learn(total_timesteps)``, optionally ``.save`` / ``.load``
    / ``.predict``. This class is the entire Dreamer surface of that
    contract.
    """

    def __init__(
        self,
        env: Any,
        policy_kwargs: dict[str, Any] | None = None,
        device: str = "auto",
        verbose: int = 0,
        seed: int | None = None,
        **dreamer_kwargs: Any,
    ) -> None:
        # env may be a VecEnv; peel one layer so obs / action spaces
        # are the single-env shapes Dreamer expects.
        base_env = env.envs[0] if hasattr(env, "envs") else env
        obs_space = base_env.observation_space
        act_space = base_env.action_space
        assert isinstance(obs_space, spaces.Box), (
            "DreamerAgent requires a Box observation space; "
            f"got {type(obs_space).__name__}"
        )
        assert isinstance(act_space, spaces.Discrete), (
            "DreamerAgent requires a Discrete action space; "
            f"got {type(act_space).__name__}"
        )

        self.env = env
        self.obs_dim = int(np.prod(obs_space.shape))
        self.action_dim = int(act_space.n)
        self.verbose = verbose

        # Merge caller overrides onto the ADR-pinned defaults.
        cfg = {**DREAMER_DEFAULT_KWARGS, **dreamer_kwargs}
        self.cfg = cfg
        self.device = th.device(
            "cuda" if device == "auto" and th.cuda.is_available()
            else (device if device != "auto" else "cpu")
        )

        hidden = int(cfg["rssm_hidden_size"])
        latent_flat = int(cfg["latent_dim"]) * int(cfg["latent_axes"])

        self.rssm = _RSSM(
            obs_dim=self.obs_dim,
            action_dim=self.action_dim,
            hidden=hidden,
            latent_dim=int(cfg["latent_dim"]),
            latent_axes=int(cfg["latent_axes"]),
        ).to(self.device)
        self.decoder = _DecoderHead(hidden, self.obs_dim, latent_flat).to(self.device)
        self.actor = _ActorHead(hidden, latent_flat, self.action_dim).to(self.device)
        self.critic = _CriticHead(hidden, latent_flat).to(self.device)

        self.wm_params = list(self.rssm.parameters()) + list(self.decoder.parameters())
        self.opt_wm = th.optim.Adam(self.wm_params, lr=float(cfg["world_model_lr"]))
        self.opt_actor = th.optim.Adam(
            self.actor.parameters(), lr=float(cfg["actor_lr"])
        )
        self.opt_critic = th.optim.Adam(
            self.critic.parameters(), lr=float(cfg["critic_lr"])
        )

        self.buffer = _SequenceReplayBuffer(int(cfg["replay_capacity"]))
        self._n_updates = 0
        self.num_timesteps = 0
        if seed is not None:
            th.manual_seed(seed)
            np.random.seed(seed)

    # -------------------------------------------------------------
    # Env interaction — Phase 1 of Dreamer's three-phase loop
    # -------------------------------------------------------------
    def _collect_step(self, obs: np.ndarray) -> np.ndarray:
        """Pick an action, step the env, stash the transition."""
        # obs for VecEnv is (n_envs, obs_dim); Dreamer's actor wants
        # a single env. Use env index 0 — we don't run vectorised
        # rollouts in the vendored skeleton.
        single_obs = obs[0] if obs.ndim == 2 else obs
        with th.no_grad():
            obs_t = th.from_numpy(single_obs).float().unsqueeze(0).to(self.device)
            h = self.rssm.initial_state(1, self.device)
            latent = th.zeros(
                1, int(self.cfg["latent_dim"]) * int(self.cfg["latent_axes"]),
                device=self.device,
            )
            emb = self.rssm.embed(obs_t)
            _, post_lp = self.rssm._one_hot_latent(
                self.rssm.post_head(th.cat([h, emb], dim=-1))
            )
            latent, _ = self.rssm._one_hot_latent(
                self.rssm.post_head(th.cat([h, emb], dim=-1))
            )
            logits = self.actor(h, latent)
            action = int(th.distributions.Categorical(logits=logits).sample().item())

        # VecEnv step returns (obs, rew, done, info) — possibly
        # (obs, rew, terminated, truncated, info) on Gymnasium 0.29+
        # when wrapped; the DummyVecEnv normalises to the 4-tuple.
        stepped = self.env.step(np.array([action]))
        if len(stepped) == 4:
            new_obs, rew, done, _info = stepped
        else:  # gymnasium new API
            new_obs, rew, term, trunc, _info = stepped
            done = term | trunc
        self.buffer.add(_Step(
            obs=single_obs.astype(np.float32).copy(),
            action=action,
            reward=float(rew[0]),
            done=bool(done[0]),
        ))
        return new_obs

    # -------------------------------------------------------------
    # World-model train — Phase 2
    # -------------------------------------------------------------
    def _train_world_model(self) -> dict[str, float]:
        batch = self.buffer.sample(
            int(self.cfg["batch_size"]),
            int(self.cfg["sequence_length"]),
            self.obs_dim,
        )
        if batch is None:
            return {"wm_loss": float("nan")}
        obs, act, rew, done = (t.to(self.device) for t in batch)

        trace = self.rssm.observe(obs, act)
        h, latent = trace["h"], trace["latent"]
        post_lp, prior_lp = trace["post_log_prob"], trace["prior_log_prob"]

        recon_obs, recon_rew, recon_cont = self.decoder(h, latent)
        obs_loss = F.mse_loss(recon_obs, obs)
        rew_loss = F.mse_loss(recon_rew, rew)
        cont_loss = F.binary_cross_entropy_with_logits(recon_cont, 1.0 - done)

        # KL with free-bits: max(free_bits, KL). post_lp / prior_lp
        # have shape (B, T, axes, classes); sum over classes to get
        # per-axis KL, then clamp at free_bits before averaging.
        post_probs = post_lp.exp()
        kl_per_axis = (post_probs * (post_lp - prior_lp.detach())).sum(dim=-1)
        free = float(self.cfg["free_bits"])
        kl = kl_per_axis.clamp(min=free).mean()

        wm_loss = obs_loss + rew_loss + cont_loss + float(self.cfg["kl_scale"]) * kl
        self.opt_wm.zero_grad()
        wm_loss.backward()
        th.nn.utils.clip_grad_norm_(self.wm_params, 100.0)
        self.opt_wm.step()

        # Return detached scalars + the traces the AC phase needs.
        self._last_trace = (h.detach(), latent.detach())
        return {
            "wm_loss": float(wm_loss.item()),
            "obs_loss": float(obs_loss.item()),
            "rew_loss": float(rew_loss.item()),
            "kl": float(kl.item()),
        }

    # -------------------------------------------------------------
    # Actor-critic imagine-train — Phase 3
    # -------------------------------------------------------------
    def _train_actor_critic(self) -> dict[str, float]:
        if not hasattr(self, "_last_trace"):
            return {"actor_loss": float("nan"), "critic_loss": float("nan")}
        h_seed, latent_seed = self._last_trace

        B = h_seed.shape[0]
        T = h_seed.shape[1]
        # Flatten batch × time as the rollout starting points.
        h = h_seed.reshape(B * T, -1)
        latent = latent_seed.reshape(B * T, -1)

        H = int(self.cfg["imagine_horizon"])
        discount = float(self.cfg["discount"])

        actor_losses: list[th.Tensor] = []
        rewards: list[th.Tensor] = []
        values: list[th.Tensor] = []
        for _ in range(H):
            logits = self.actor(h, latent)
            dist = th.distributions.Categorical(logits=logits)
            a = dist.sample()
            log_p = dist.log_prob(a)
            a_onehot = F.one_hot(a, self.action_dim).float()
            with th.no_grad():
                _, reward_pred, _ = self.decoder(h, latent)
            v = self.critic(h, latent)
            actor_losses.append(-log_p * (reward_pred - v.detach()))
            rewards.append(reward_pred)
            values.append(v)
            h, latent = self.rssm.imagine_step(h, latent, a_onehot)

        # λ-return (simplified: bootstrap off last value with
        # discount factor only — full V3 uses λ=0.95 GAE-style).
        returns = [values[-1].detach()]
        for t in reversed(range(H - 1)):
            returns.append(rewards[t] + discount * returns[-1])
        returns = list(reversed(returns))
        returns_t = th.stack(returns, dim=0)

        actor_loss = th.stack(actor_losses, dim=0).mean()
        self.opt_actor.zero_grad()
        actor_loss.backward(retain_graph=True)
        th.nn.utils.clip_grad_norm_(self.actor.parameters(), 100.0)
        self.opt_actor.step()

        values_t = th.stack(values, dim=0)
        critic_loss = F.mse_loss(values_t, returns_t.detach())
        self.opt_critic.zero_grad()
        critic_loss.backward()
        th.nn.utils.clip_grad_norm_(self.critic.parameters(), 100.0)
        self.opt_critic.step()

        return {
            "actor_loss": float(actor_loss.item()),
            "critic_loss": float(critic_loss.item()),
        }

    # -------------------------------------------------------------
    # Public SB3-compatible API
    # -------------------------------------------------------------
    def learn(
        self,
        total_timesteps: int,
        callback: Any = None,
        progress_bar: bool = False,
    ) -> "DreamerAgent":
        obs = self.env.reset()
        if isinstance(obs, tuple):  # gymnasium new API
            obs = obs[0]
        train_every = int(self.cfg["train_every"])
        steps_since_train = 0
        for _ in range(total_timesteps):
            obs = self._collect_step(obs)
            self.num_timesteps += 1
            steps_since_train += 1
            if steps_since_train >= train_every and len(self.buffer) >= int(self.cfg["sequence_length"]):
                self._train_world_model()
                self._train_actor_critic()
                self._n_updates += 1
                steps_since_train = 0
        return self

    def predict(
        self,
        observation: np.ndarray,
        state: Any = None,
        episode_start: Any = None,
        deterministic: bool = True,
    ) -> tuple[np.ndarray, Any]:
        """SB3-shaped predict. ``state`` / ``episode_start`` accepted
        for interface-compat and ignored — the skeleton resets the
        posterior per-call to stay stateless at the boundary.

        In ``deterministic=True`` mode the categorical latent is
        collapsed to its argmax one-hot (not sampled) so repeated
        calls on the same obs give identical actions — SB3's
        ``PPO.predict`` + ``SACDiscrete.predict`` both have this
        contract; LoadedPolicyBot relies on it for reproducible
        replay / league matches.
        """
        obs_t = th.from_numpy(np.asarray(observation)).float().to(self.device)
        if obs_t.ndim == 1:
            obs_t = obs_t.unsqueeze(0)
        with th.no_grad():
            B = obs_t.shape[0]
            h = self.rssm.initial_state(B, self.device)
            emb = self.rssm.embed(obs_t)
            post_logits = self.rssm.post_head(th.cat([h, emb], dim=-1))
            shape = (B, self.rssm.latent_axes, self.rssm.latent_dim)
            post_logits_grid = post_logits.view(*shape)
            if deterministic:
                # Argmax-one-hot per axis — reproducible for the
                # same obs + weights, matching SB3 predict contract.
                idx = th.argmax(post_logits_grid, dim=-1)
                latent = F.one_hot(idx, self.rssm.latent_dim).float()
                latent = latent.view(B, self.rssm.latent_axes * self.rssm.latent_dim)
            else:
                latent, _ = self.rssm._one_hot_latent(post_logits)
            logits = self.actor(h, latent)
            if deterministic:
                a = th.argmax(logits, dim=-1)
            else:
                a = th.distributions.Categorical(logits=logits).sample()
        return a.cpu().numpy().astype(np.int64), None

    def save(self, path: str | Path) -> None:
        """Write a zip containing a ``data.pt`` torch dump. Matches
        SB3's ``model.zip`` layout closely enough that our
        checkpoint-listing + slug-prefixed filenames keep working.
        ``load`` rebuilds the class from the stored config."""
        p = Path(str(path))
        if not p.suffix:
            p = p.with_suffix(".zip")
        payload = {
            "cfg": self.cfg, "rssm": self.rssm.state_dict(),
            "decoder": self.decoder.state_dict(),
            "actor": self.actor.state_dict(),
            "critic": self.critic.state_dict(),
            "obs_dim": self.obs_dim, "action_dim": self.action_dim,
            "num_timesteps": self.num_timesteps,
            "_n_updates": self._n_updates,
        }
        buf = io.BytesIO()
        th.save(payload, buf)
        with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("data.pt", buf.getvalue())

    @classmethod
    def load(
        cls, path: str | Path, env: Any = None, device: str = "auto",
    ) -> "DreamerAgent":
        p = Path(str(path))
        if not p.suffix:
            p = p.with_suffix(".zip")
        with zipfile.ZipFile(p, "r") as zf:
            raw = zf.read("data.pt")
        # weights_only=False is intentional — payload contains a
        # config dict alongside state_dicts, and this repo's
        # save/load pair is the only writer.
        payload = th.load(io.BytesIO(raw), weights_only=False, map_location="cpu")
        assert env is not None, "DreamerAgent.load requires env= for shape info."
        cfg_overrides = {k: v for k, v in payload["cfg"].items() if k in DREAMER_DEFAULT_KWARGS}
        agent = cls(env=env, device=device, **cfg_overrides)
        agent.rssm.load_state_dict(payload["rssm"])
        agent.decoder.load_state_dict(payload["decoder"])
        agent.actor.load_state_dict(payload["actor"])
        agent.critic.load_state_dict(payload["critic"])
        agent.num_timesteps = int(payload.get("num_timesteps", 0))
        agent._n_updates = int(payload.get("_n_updates", 0))
        return agent

    # Entropy-like API for parity with SB3 when callbacks poke it.
    def set_training_mode(self, mode: bool) -> None:
        self.rssm.train(mode)
        self.decoder.train(mode)
        self.actor.train(mode)
        self.critic.train(mode)
