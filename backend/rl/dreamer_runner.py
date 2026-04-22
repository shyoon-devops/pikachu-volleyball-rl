"""Vendored Dreamer V3 — minimal, SB3-compatible adapter.

ADR 0018 §5 intended to pin ``NM512/dreamerv3-torch`` by git+SHA,
but that repo has no setup.py / pyproject.toml — not a pip library
(2026-04-22). No PyTorch Dreamer V3 ships on PyPI (Hafner's 1.5.0
is TF/JAX). Vendoring in-tree is the only path that respects the
ADR's PyTorch-stack decision. The skeleton has correct three-phase
structure (env interaction → world-model train → AC imagine)
WITHOUT the full Hafner 2023 niceties (KL-balance schedule, symlog
reward, two-hot encoding, prior ensembles) — those ship v3.x; S5
is opt-in + experimental per ADR 0018 §8. API matches SB3 shape
so ``trainer.py`` + ``LoadedPolicyBot`` dispatch on algorithm alone.
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
from stable_baselines3.common.logger import Logger


# ADR 0018 §7 — pinned defaults, NOT WS-surfaced. Reduced sizes vs
# Hafner 2023 defaults so CPU smoke tests run in under a minute;
# production GPU runs override via the factory's kwargs.
DREAMER_DEFAULT_KWARGS: dict[str, Any] = {
    # latent: 32 axes × 32 classes = 1024-d; train_every in env steps.
    "rssm_hidden_size": 512, "latent_dim": 32, "latent_axes": 32,
    "world_model_lr": 1e-4, "actor_lr": 3e-5, "critic_lr": 3e-5,
    "imagine_horizon": 15, "batch_size": 16, "sequence_length": 64,
    "replay_capacity": 1_000_000, "train_every": 16,
    "discount": 0.99, "kl_scale": 1.0, "free_bits": 1.0,
}


@dataclass
class _Step:
    """One (obs, action, reward, done) transition in the replay buffer."""
    obs: np.ndarray
    action: int
    reward: float
    done: bool


def _mlp(in_dim: int, hidden: int, out_dim: int) -> nn.Sequential:
    return nn.Sequential(
        nn.Linear(in_dim, hidden), nn.SiLU(),
        nn.Linear(hidden, out_dim),
    )


class _SequenceReplayBuffer:
    """Trajectory replay. ``n_streams`` supports one open episode
    per VecEnv sub-env so parallel trajectories don't splice into
    a single sequence. Each stream closes to the shared
    completed-pool on its own ``done``."""

    def __init__(self, capacity: int, n_streams: int = 1) -> None:
        self.capacity = capacity
        self.n_streams = max(1, int(n_streams))
        self._episodes: deque[list[_Step]] = deque()
        self._currents: list[list[_Step]] = [[] for _ in range(self.n_streams)]
        self._total_steps = 0

    def add(self, step: _Step, env_idx: int = 0) -> None:
        cur = self._currents[env_idx]
        cur.append(step)
        self._total_steps += 1
        if step.done:
            self._episodes.append(cur)
            self._currents[env_idx] = []
        while self._total_steps > self.capacity and self._episodes:
            self._total_steps -= len(self._episodes.popleft())

    def __len__(self) -> int:
        return self._total_steps

    def sample(
        self, batch_size: int, seq_len: int, obs_dim: int
    ) -> tuple[th.Tensor, th.Tensor, th.Tensor, th.Tensor] | None:
        # Include in-progress streams so CPU-smoke runs can train
        # before the first episode closes.
        pool = list(self._episodes)
        for cur in self._currents:
            if cur and len(cur) >= seq_len:
                pool.append(cur)
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
        self.prior_head = _mlp(hidden, hidden, latent_flat)
        self.post_head = _mlp(hidden * 2, hidden, latent_flat)
        self.action_dim = action_dim

    def _one_hot_latent(self, logits: th.Tensor) -> tuple[th.Tensor, th.Tensor]:
        """Straight-through categorical sample per latent axis.
        Returns (one-hot sample, log-softmax logits for KL)."""
        shape = (*logits.shape[:-1], self.latent_axes, self.latent_dim)
        logits = logits.view(*shape)
        probs = F.softmax(logits, dim=-1)
        log_probs = F.log_softmax(logits, dim=-1)
        sample = F.one_hot(
            th.distributions.Categorical(probs=probs).sample(),
            num_classes=self.latent_dim,
        ).float()
        # Straight-through: discrete sample + gradient through probs.
        sample = sample + probs - probs.detach()
        flat_shape = (*logits.shape[:-2], self.latent_axes * self.latent_dim)
        return sample.view(*flat_shape), log_probs

    def initial_state(self, batch_size: int, device: th.device) -> th.Tensor:
        return th.zeros(batch_size, self.hidden, device=device)

    def observe(
        self, obs_seq: th.Tensor, action_seq: th.Tensor,
    ) -> dict[str, th.Tensor]:
        """Posterior pass over a (B, T, obs_dim) sequence — returns
        intermediate tensors the world-model loss needs."""
        B, T, _ = obs_seq.shape
        device = obs_seq.device
        embeds = self.embed(obs_seq)
        action_onehot = F.one_hot(action_seq, self.action_dim).float()
        h = self.initial_state(B, device)
        latent = th.zeros(B, self.latent_axes * self.latent_dim, device=device)
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
        h_new = self.cell(th.cat([latent, action_onehot], dim=-1), h)
        latent_new, _ = self._one_hot_latent(self.prior_head(h_new))
        return h_new, latent_new


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
        # Peel VecEnv to get single-env spaces.
        base_env = env.envs[0] if hasattr(env, "envs") else env
        obs_space = base_env.observation_space
        act_space = base_env.action_space
        assert isinstance(obs_space, spaces.Box), (
            f"requires Box obs; got {type(obs_space).__name__}"
        )
        assert isinstance(act_space, spaces.Discrete), (
            f"requires Discrete action; got {type(act_space).__name__}"
        )

        self.env = env
        self.obs_dim = int(np.prod(obs_space.shape))
        self.action_dim = int(act_space.n)
        self.verbose = verbose
        # VecEnv n_envs — trainer builds SubprocVecEnv n_envs=8 for
        # every algo. Per-env action + n_streams buffer fix the
        # n_envs>1 crash from the 2026-04-22 QA regression.
        self.num_envs = int(getattr(env, "num_envs", 1))
        # SB3 BaseAlgorithm interface surface — callbacks read these
        # via ``self.model.<attr>``. bench-B 2026-04-23 crashed on
        # ``training_env`` (→ ``model.get_env()``) in EnvFrameCallback
        # / EnvResultCallback. Mirror BaseAlgorithm so stock SB3
        # callbacks work with no special-casing. VecNormalize isn't
        # used in this pipeline → explicit None keeps callbacks that
        # check the SB3 eval-path attr from AttributeError-ing.
        self.observation_space = obs_space
        self.action_space = act_space
        self._vec_normalize_env = None

        cfg = {**DREAMER_DEFAULT_KWARGS, **dreamer_kwargs}
        self.cfg = cfg
        self.device = th.device("cuda" if device == "auto" and th.cuda.is_available() else (device if device != "auto" else "cpu"))

        hidden = int(cfg["rssm_hidden_size"])
        latent_flat = int(cfg["latent_dim"]) * int(cfg["latent_axes"])

        self.rssm = _RSSM(
            self.obs_dim, self.action_dim, hidden,
            int(cfg["latent_dim"]), int(cfg["latent_axes"]),
        ).to(self.device)
        self.decoder = _DecoderHead(hidden, self.obs_dim, latent_flat).to(self.device)
        self.actor = _ActorHead(hidden, latent_flat, self.action_dim).to(self.device)
        self.critic = _CriticHead(hidden, latent_flat).to(self.device)

        self.wm_params = list(self.rssm.parameters()) + list(self.decoder.parameters())
        self.opt_wm = th.optim.Adam(self.wm_params, lr=float(cfg["world_model_lr"]))
        self.opt_actor = th.optim.Adam(self.actor.parameters(), lr=float(cfg["actor_lr"]))
        self.opt_critic = th.optim.Adam(self.critic.parameters(), lr=float(cfg["critic_lr"]))

        self.buffer = _SequenceReplayBuffer(
            int(cfg["replay_capacity"]), n_streams=self.num_envs,
        )
        self._n_updates = 0
        self.num_timesteps = 0
        # SB3 callbacks read ``self.model.logger.name_to_value`` — an
        # empty Logger is all we need as a record sink.
        self.logger = Logger(folder=None, output_formats=[])
        if seed is not None:
            th.manual_seed(seed)
            np.random.seed(seed)

    # Phase 1 — env interaction
    def _collect_step(self, obs: np.ndarray) -> np.ndarray:
        """Per-env actor pass → VecEnv.step → per-stream replay.

        QA 2026-04-22: ``env.step(np.array([action]))`` (length-1)
        vs n_envs=8 VecEnv crashed. Fix: per-env forwards building a
        ``(n_envs,)`` action array, each sub-env routes into its own
        replay stream. Independent forwards (not batched) — RSSM
        posterior init is (1, H), batch-rewrite deferred to v3.x.
        """
        if obs.ndim == 1:
            obs = obs.reshape(1, -1)
        n_envs = obs.shape[0]

        actions = np.zeros(n_envs, dtype=np.int64)
        with th.no_grad():
            for i in range(n_envs):
                obs_t = th.from_numpy(obs[i]).float().unsqueeze(0).to(self.device)
                h = self.rssm.initial_state(1, self.device)
                emb = self.rssm.embed(obs_t)
                latent, _ = self.rssm._one_hot_latent(
                    self.rssm.post_head(th.cat([h, emb], dim=-1))
                )
                logits = self.actor(h, latent)
                actions[i] = int(
                    th.distributions.Categorical(logits=logits).sample().item()
                )

        # VecEnv.step → 4-tuple (obs, rew, done, info); newer
        # Gymnasium's 5-tuple term/trunc gets normalised by
        # DummyVecEnv / SubprocVecEnv but handle both.
        stepped = self.env.step(actions)
        if len(stepped) == 4:
            new_obs, rew, done, _info = stepped
        else:
            new_obs, rew, term, trunc, _info = stepped
            done = term | trunc
        for i in range(n_envs):
            self.buffer.add(
                _Step(
                    obs=obs[i].astype(np.float32).copy(),
                    action=int(actions[i]),
                    reward=float(rew[i]),
                    done=bool(done[i]),
                ),
                env_idx=i,
            )
        return new_obs

    # Phase 2 — world-model train
    def _train_world_model(self) -> dict[str, float]:
        batch = self.buffer.sample(
            int(self.cfg["batch_size"]), int(self.cfg["sequence_length"]), self.obs_dim,
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

        # KL with free-bits: sum over classes → per-axis KL, clamp
        # at free_bits, mean.
        post_probs = post_lp.exp()
        kl_per_axis = (post_probs * (post_lp - prior_lp.detach())).sum(dim=-1)
        kl = kl_per_axis.clamp(min=float(self.cfg["free_bits"])).mean()

        wm_loss = obs_loss + rew_loss + cont_loss + float(self.cfg["kl_scale"]) * kl
        self.opt_wm.zero_grad()
        wm_loss.backward()
        th.nn.utils.clip_grad_norm_(self.wm_params, 100.0)
        self.opt_wm.step()

        self._last_trace = (h.detach(), latent.detach())
        return {
            "wm_loss": float(wm_loss.item()),
            "obs_loss": float(obs_loss.item()),
            "rew_loss": float(rew_loss.item()),
            "kl": float(kl.item()),
        }

    # Phase 3 — actor-critic imagine-train
    def _train_actor_critic(self) -> dict[str, float]:
        if not hasattr(self, "_last_trace"):
            return {"actor_loss": float("nan"), "critic_loss": float("nan")}
        h_seed, latent_seed = self._last_trace
        # Flatten batch × time as the rollout starting points.
        h = h_seed.reshape(-1, h_seed.shape[-1])
        latent = latent_seed.reshape(-1, latent_seed.shape[-1])

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

    # Public SB3-compatible API
    def learn(
        self,
        total_timesteps: int,
        callback: Any = None,
        progress_bar: bool = False,
    ) -> "DreamerAgent":
        """Three-phase loop; ``total_timesteps`` in env-step units
        (each ``_collect_step`` consumes ``num_envs`` steps). SB3
        ``BaseCallback`` protocol wired: init → training_start →
        on_step per _collect_step → training_end. QA bench-B
        2026-04-23 hit dispatch-missing bug."""
        obs = self.env.reset()
        if isinstance(obs, tuple):  # gymnasium new API
            obs = obs[0]
        # BaseCallback handshake — CallbackList forwards to each child.
        if callback is not None:
            callback.init_callback(self)
            callback.on_training_start(locals(), globals())

        train_every = int(self.cfg["train_every"])
        seq_len = int(self.cfg["sequence_length"])
        steps_since_train = 0
        collected = 0
        early_stop = False
        while collected < total_timesteps and not early_stop:
            obs = self._collect_step(obs)
            self.num_timesteps += self.num_envs
            collected += self.num_envs
            steps_since_train += self.num_envs
            if steps_since_train >= train_every and len(self.buffer) >= seq_len:
                self._train_world_model()
                self._train_actor_critic()
                self._n_updates += 1
                steps_since_train = 0
            # on_step fires once per _collect_step; False → abort.
            if callback is not None and callback.on_step() is False:
                early_stop = True
        if callback is not None:
            callback.on_training_end()
        return self

    def predict(
        self,
        observation: np.ndarray,
        state: Any = None,
        episode_start: Any = None,
        deterministic: bool = True,
    ) -> tuple[np.ndarray, Any]:
        """SB3-shaped predict. ``state`` / ``episode_start`` ignored
        — skeleton resets posterior per-call. Matches BaseAlgorithm
        contract for Discrete: single obs ``(obs_dim,)`` → 0-d int
        (``int(action)`` works — bench-B 2026-04-23 crashed here
        when we returned ``(1,)``), batched ``(B, obs_dim)`` →
        ``(B,)``. Deterministic mode argmaxes the categorical latent
        so repeated calls on the same obs give identical actions
        (LoadedPolicyBot + demo-game rollouts rely on this)."""
        obs_arr = np.asarray(observation)
        single = obs_arr.ndim == 1
        obs_t = th.from_numpy(obs_arr).float().to(self.device)
        if single:
            obs_t = obs_t.unsqueeze(0)
        with th.no_grad():
            B = obs_t.shape[0]
            h = self.rssm.initial_state(B, self.device)
            emb = self.rssm.embed(obs_t)
            post_logits = self.rssm.post_head(th.cat([h, emb], dim=-1))
            if deterministic:
                # Argmax-one-hot per axis — reproducible.
                grid = post_logits.view(B, self.rssm.latent_axes, self.rssm.latent_dim)
                idx = th.argmax(grid, dim=-1)
                latent = F.one_hot(idx, self.rssm.latent_dim).float().view(B, -1)
            else:
                latent, _ = self.rssm._one_hot_latent(post_logits)
            logits = self.actor(h, latent)
            a = th.argmax(logits, dim=-1) if deterministic else (
                th.distributions.Categorical(logits=logits).sample()
            )
        actions = a.cpu().numpy().astype(np.int64)
        # SB3 contract: collapse batch axis for single-obs inputs so
        # ``int(action)`` works at the callsite (LiveFrameCallback,
        # ACTION_MAP lookup, LoadedPolicyBot).
        if single:
            actions = actions.squeeze(0)
        return actions, state

    def save(self, path: str | Path) -> None:
        """Zip wrapping a ``data.pt`` torch dump. Matches SB3's
        model.zip layout closely enough that checkpoint listing +
        slug-prefixed filenames keep working."""
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
        # weights_only=False: payload has cfg dict + state_dicts; our
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

    def get_env(self) -> Any:
        """BaseAlgorithm.get_env mirror — SB3 callbacks read
        ``self.training_env`` via ``self.model.get_env()``. Returns
        the VecEnv (or None if we ever null it out)."""
        return self.env

    # Entropy-like API for parity with SB3 when callbacks poke it.
    def set_training_mode(self, mode: bool) -> None:
        self.rssm.train(mode)
        self.decoder.train(mode)
        self.actor.train(mode)
        self.critic.train(mode)
