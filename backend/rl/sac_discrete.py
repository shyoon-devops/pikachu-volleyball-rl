"""Vendored SAC-Discrete (Christodoulou 2019) on the SB3 off-policy base.

ADR 0017 §2/§7: stock SB3 ``SAC`` accepts only Box action spaces, and
sb3-contrib 2.8.0 does not ship a discrete variant. The Pikachu
Volleyball env is ``Discrete(12)`` by construction (physics.js port),
and per ADR §2 we chose (A) "keep discrete" over (B) "re-map to
continuous" — so we vendor the Christodoulou 2019 adaptation here
rather than cascade engine changes.

Christodoulou adapts the SAC objective for a discrete action set:

  Actor:  π(a|s) = Categorical(logits(s))
  Critic: Q_i(s) : R^|A|          (twin, i ∈ {1,2})

  Actor loss:     L_π  = E_s [ Σ_a π(a|s) · (α log π(a|s) − Q_min(s,a)) ]
  Critic loss_i:  L_Qi = E_{s,a} [ (Q_i(s,a) − y)^2 ]
         y      = r + γ(1−d) Σ_a' π(a'|s') · (Q̄_min(s',a') − α log π(a'|s'))
  Entropy tune:   L_α  = − Σ_a π(a|s) · (log π(a|s) + H̄)

where ``H̄ = -log(1/|A|) · target_entropy_scale`` (Christodoulou §3.1;
we follow the published 0.98 scale default).

Scope: this is a deliberately compact implementation — the core
algorithm fits inside SB3's ``OffPolicyAlgorithm`` lifecycle so that
replay buffers, logging, callbacks, VecEnv handling, `.learn()`,
`.save()`, `.load()`, `.predict()`, and checkpoint round-tripping all
come for free. What we own here is the policy module and the
``train()`` step. Correctness is smoke-tested (ADR §6 success gates
are training-quality, not unit); wider parity work ships in a
follow-up once the algorithm is exercised on real runs.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import torch as th
import torch.nn as nn
import torch.nn.functional as F
from gymnasium import spaces
from stable_baselines3.common.buffers import ReplayBuffer
from stable_baselines3.common.off_policy_algorithm import OffPolicyAlgorithm
from stable_baselines3.common.policies import BasePolicy
from stable_baselines3.common.torch_layers import create_mlp
from stable_baselines3.common.type_aliases import Schedule
from stable_baselines3.common.utils import polyak_update


DEFAULT_NET_ARCH: list[int] = [256, 256]
# Christodoulou §3.1: target entropy for discrete SAC. Scale * log(|A|)
# so α tracks a fraction of the maximum-entropy policy. 0.98 matches
# the published implementations; set once here so the factory doesn't
# surface it on WS payload (ADR §5).
TARGET_ENTROPY_SCALE: float = 0.98


class _DiscreteActor(nn.Module):
    """Categorical policy over a Discrete action space.

    Layout mirrors SB3's ``Actor`` for continuous SAC — a shared MLP
    trunk then a linear head — so checkpoint loads + parameter counts
    stay legible. Unlike continuous SAC the head produces logits
    (``action_dim`` outputs), not a (mean, log_std) pair.
    """

    def __init__(
        self,
        observation_space: spaces.Space,
        action_space: spaces.Discrete,
        net_arch: list[int],
    ) -> None:
        super().__init__()
        assert isinstance(action_space, spaces.Discrete), (
            "SACDiscrete requires a Discrete action space; "
            f"got {type(action_space).__name__}"
        )
        obs_dim = int(np.prod(observation_space.shape))
        self.action_dim: int = int(action_space.n)
        # ``create_mlp`` returns a list of layers without a final
        # activation — we append a logits head explicitly so the
        # output reads as "pre-softmax" end-to-end.
        trunk = create_mlp(obs_dim, -1, net_arch, activation_fn=nn.ReLU)
        self.trunk = nn.Sequential(*trunk)
        self.logits_head = nn.Linear(net_arch[-1], self.action_dim)

    def _logits(self, obs: th.Tensor) -> th.Tensor:
        return self.logits_head(self.trunk(obs))

    def forward(self, obs: th.Tensor) -> th.Tensor:
        """Return the action distribution's logits for ``obs``.

        Left as raw logits so the caller (``train`` loss or
        ``_predict``) can decide between softmax (policy prob) and
        log-softmax (entropy) without redoing the forward pass.
        """
        return self._logits(obs)

    def action_log_prob(
        self, obs: th.Tensor
    ) -> tuple[th.Tensor, th.Tensor, th.Tensor]:
        """Return (sampled_action, all_action_probs, all_log_probs).

        SAC-Discrete's actor loss uses the **full-expectation form**
        over actions — every loss term sums across the action set
        weighted by π(a|s). We return the full prob vector + log
        vector rather than a single (action, log_prob) pair so the
        train loop can compute Σ_a π(a|s) · (·) without a second
        forward.
        """
        logits = self._logits(obs)
        probs = F.softmax(logits, dim=-1)
        # log(softmax) is numerically safer than log(probs + ε) when
        # some classes get near-zero probability — use the fused op.
        log_probs = F.log_softmax(logits, dim=-1)
        action = th.distributions.Categorical(probs=probs).sample()
        return action, probs, log_probs

    def _predict(self, obs: th.Tensor, deterministic: bool = False) -> th.Tensor:
        logits = self._logits(obs)
        if deterministic:
            return th.argmax(logits, dim=-1)
        probs = F.softmax(logits, dim=-1)
        return th.distributions.Categorical(probs=probs).sample()


class _DiscreteCritic(nn.Module):
    """Twin Q-network — each head takes **obs only** and emits a
    Q-value per action (shape ``[B, |A|]``).

    The continuous-SAC shape ``Q(obs, action) → scalar`` requires
    action-conditioned forwards; for a discrete action set we read
    off Q(s, a) via ``Q(s)[a]``, which collapses the critic backward
    pass. Same trick Christodoulou uses; it's also the conventional
    DQN head.
    """

    def __init__(
        self,
        observation_space: spaces.Space,
        action_space: spaces.Discrete,
        net_arch: list[int],
        n_critics: int = 2,
    ) -> None:
        super().__init__()
        obs_dim = int(np.prod(observation_space.shape))
        action_dim = int(action_space.n)
        self.n_critics = n_critics
        self.q_nets: nn.ModuleList = nn.ModuleList()
        for _ in range(n_critics):
            # action_dim outputs — one Q per discrete action.
            net = create_mlp(obs_dim, action_dim, net_arch, activation_fn=nn.ReLU)
            self.q_nets.append(nn.Sequential(*net))

    def forward(self, obs: th.Tensor) -> tuple[th.Tensor, ...]:
        return tuple(q(obs) for q in self.q_nets)


class SACDiscretePolicy(BasePolicy):
    """Thin wrapper that owns the actor + twin critics + target pair.

    Mirrors the SB3 SAC policy contract so ``OffPolicyAlgorithm``
    boilerplate (learning rate scheduling, predict routing, save /
    load indexing) keeps working.
    """

    # Policy registry key — the trainer addresses it via the string
    # "MlpPolicy" so pre-S4 PPO callsites can remain a no-op literal.
    actor: _DiscreteActor
    critic: _DiscreteCritic
    critic_target: _DiscreteCritic

    def __init__(
        self,
        observation_space: spaces.Space,
        action_space: spaces.Space,
        lr_schedule: Schedule,
        net_arch: list[int] | None = None,
        n_critics: int = 2,
    ) -> None:
        super().__init__(
            observation_space=observation_space,
            action_space=action_space,
            squash_output=False,
        )
        self.net_arch = net_arch if net_arch is not None else list(DEFAULT_NET_ARCH)
        self.n_critics = n_critics
        self._build(lr_schedule)

    def _build(self, lr_schedule: Schedule) -> None:
        self.actor = _DiscreteActor(
            self.observation_space, self.action_space, self.net_arch
        )
        self.critic = _DiscreteCritic(
            self.observation_space, self.action_space, self.net_arch, self.n_critics
        )
        # Target critic shares architecture + initial weights. SB3
        # convention: target has no independent optimizer and is
        # updated via ``polyak_update`` in ``train``.
        self.critic_target = _DiscreteCritic(
            self.observation_space, self.action_space, self.net_arch, self.n_critics
        )
        self.critic_target.load_state_dict(self.critic.state_dict())
        # Disable grad on the target — we only soft-update it.
        for p in self.critic_target.parameters():
            p.requires_grad_(False)

        # Separate optimizers for actor / critic (Christodoulou §3.2).
        # Initial LR from the schedule at t=1.0; OffPolicyAlgorithm
        # reschedules both each train call via the algorithm's
        # ``_update_learning_rate`` hook.
        initial_lr = lr_schedule(1.0)
        self.actor.optimizer = th.optim.Adam(
            self.actor.parameters(), lr=initial_lr
        )
        self.critic.optimizer = th.optim.Adam(
            self.critic.parameters(), lr=initial_lr
        )

    def _predict(self, observation: th.Tensor, deterministic: bool = False) -> th.Tensor:
        return self.actor._predict(observation, deterministic=deterministic)

    def forward(self, obs: th.Tensor, deterministic: bool = False) -> th.Tensor:
        return self._predict(obs, deterministic=deterministic)


class SACDiscrete(OffPolicyAlgorithm):
    """Soft Actor-Critic for a Discrete action space.

    API surface intentionally matches SB3's ``SAC`` — the policy
    factory can swap one for the other on the ``algorithm`` axis
    without the trainer caring which class it's holding.

    The algorithm owns the replay buffer lifecycle via
    ``OffPolicyAlgorithm``. ``train`` implements one gradient-step
    over (critic, actor, α). ``_setup_model`` hooks the policy and
    the entropy-coefficient machinery.
    """

    # OffPolicyAlgorithm needs these class-level descriptors so the
    # predict / save / load routing understands our policy key.
    policy_aliases = {"MlpPolicy": SACDiscretePolicy}

    def __init__(
        self,
        policy: str | type[SACDiscretePolicy],
        env: Any,
        learning_rate: float = 3e-4,
        buffer_size: int = 1_000_000,
        learning_starts: int = 10_000,
        batch_size: int = 256,
        tau: float = 0.005,
        gamma: float = 0.99,
        train_freq: int = 1,
        gradient_steps: int = 1,
        ent_coef: str | float = "auto",
        target_update_interval: int = 1,
        target_entropy: str | float = "auto",
        policy_kwargs: dict[str, Any] | None = None,
        verbose: int = 0,
        device: str = "auto",
        seed: int | None = None,
        _init_setup_model: bool = True,
    ) -> None:
        super().__init__(
            policy=policy,
            env=env,
            learning_rate=learning_rate,
            buffer_size=buffer_size,
            learning_starts=learning_starts,
            batch_size=batch_size,
            tau=tau,
            gamma=gamma,
            train_freq=train_freq,
            gradient_steps=gradient_steps,
            action_noise=None,
            replay_buffer_class=ReplayBuffer,
            policy_kwargs=policy_kwargs,
            verbose=verbose,
            device=device,
            seed=seed,
            sde_support=False,
            supported_action_spaces=(spaces.Discrete,),
            support_multi_env=True,
        )
        self.target_entropy_spec = target_entropy
        self.ent_coef_spec = ent_coef
        self.target_update_interval = target_update_interval
        self.log_ent_coef: th.Tensor | None = None
        self.ent_coef_optimizer: th.optim.Optimizer | None = None
        self.ent_coef_tensor: th.Tensor | None = None

        if _init_setup_model:
            self._setup_model()

    def _setup_model(self) -> None:
        super()._setup_model()
        self._create_aliases()

        # Target entropy: by convention for discrete SAC this is
        # a fraction of the max-entropy value log(|A|) rather than
        # the continuous-SAC default of -|A|. Christodoulou §3.1.
        if self.target_entropy_spec == "auto":
            assert isinstance(self.action_space, spaces.Discrete)
            self.target_entropy = float(
                -np.log(1.0 / self.action_space.n) * TARGET_ENTROPY_SCALE
            )
        else:
            self.target_entropy = float(self.target_entropy_spec)

        # α auto-tune: parameterize log(α) directly so optimization
        # stays positive-valued. Same pattern as SB3 SAC.
        if isinstance(self.ent_coef_spec, str) and self.ent_coef_spec.startswith("auto"):
            init_value = 1.0
            if "_" in self.ent_coef_spec:
                init_value = float(self.ent_coef_spec.split("_")[1])
                assert init_value > 0.0, "initial ent_coef must be > 0"
            self.log_ent_coef = th.log(
                th.ones(1, device=self.device) * init_value
            ).requires_grad_(True)
            self.ent_coef_optimizer = th.optim.Adam(
                [self.log_ent_coef], lr=self.lr_schedule(1.0)
            )
        else:
            # Fixed α. Stored as a buffer so .to(device) moves it.
            self.ent_coef_tensor = th.tensor(
                float(self.ent_coef_spec), device=self.device
            )

    def _create_aliases(self) -> None:
        self.actor = self.policy.actor
        self.critic = self.policy.critic
        self.critic_target = self.policy.critic_target

    def train(self, gradient_steps: int, batch_size: int = 64) -> None:
        self.policy.set_training_mode(True)
        optimizers = [self.actor.optimizer, self.critic.optimizer]
        if self.ent_coef_optimizer is not None:
            optimizers.append(self.ent_coef_optimizer)
        self._update_learning_rate(optimizers)

        ent_coefs: list[float] = []
        actor_losses: list[float] = []
        critic_losses: list[float] = []

        for _ in range(gradient_steps):
            batch = self.replay_buffer.sample(
                batch_size, env=self._vec_normalize_env
            )
            # Actions come back as ``[B, 1]`` int64 from the replay
            # buffer for Discrete spaces; collapse to ``[B]`` for
            # gather / index use.
            actions = batch.actions.long().flatten()

            # -- critic update -----------------------------------
            with th.no_grad():
                # Full-expectation target: Σ_a' π(a'|s') · (min Q̄ − α log π)
                _, next_probs, next_log_probs = self.actor.action_log_prob(
                    batch.next_observations
                )
                next_q_values = th.stack(
                    self.critic_target(batch.next_observations), dim=0
                )
                next_q_values, _ = th.min(next_q_values, dim=0)
                ent_coef = self._resolve_ent_coef().detach()
                target_v = (
                    next_probs * (next_q_values - ent_coef * next_log_probs)
                ).sum(dim=1, keepdim=True)
                target_q = batch.rewards + (1 - batch.dones) * self.gamma * target_v

            current_q_values = self.critic(batch.observations)
            # Q(s, a): gather the action-taken column from each
            # critic, then mean-squared-error against the shared
            # target — SAC's twin-critic loss is **not** min-pooled
            # at the critic forward, only at the target.
            critic_loss = 0.0
            for q in current_q_values:
                q_taken = q.gather(1, actions.unsqueeze(-1))
                critic_loss = critic_loss + F.mse_loss(q_taken, target_q)
            critic_loss = critic_loss / len(current_q_values)
            critic_losses.append(float(critic_loss.item()))

            self.critic.optimizer.zero_grad()
            critic_loss.backward()
            self.critic.optimizer.step()

            # -- actor update ------------------------------------
            _, probs, log_probs = self.actor.action_log_prob(batch.observations)
            with th.no_grad():
                q_values = th.stack(self.critic(batch.observations), dim=0)
                q_values, _ = th.min(q_values, dim=0)
            ent_coef = self._resolve_ent_coef()
            # Full-expectation actor loss — Σ_a π(a|s) · (α log π − Q).
            actor_loss = (probs * (ent_coef.detach() * log_probs - q_values)).sum(
                dim=1
            ).mean()
            actor_losses.append(float(actor_loss.item()))

            self.actor.optimizer.zero_grad()
            actor_loss.backward()
            self.actor.optimizer.step()

            # -- entropy coefficient update ----------------------
            if self.ent_coef_optimizer is not None and self.log_ent_coef is not None:
                # Entropy of the categorical = -Σ π log π; target is
                # positive so the sign convention here matches SB3
                # continuous SAC.
                entropy = -(probs.detach() * log_probs.detach()).sum(dim=1)
                ent_coef_loss = -(
                    self.log_ent_coef * (self.target_entropy - entropy)
                ).mean()
                self.ent_coef_optimizer.zero_grad()
                ent_coef_loss.backward()
                self.ent_coef_optimizer.step()
            ent_coefs.append(float(self._resolve_ent_coef().detach().item()))

            # -- target soft-update ------------------------------
            if self._n_updates % self.target_update_interval == 0:
                polyak_update(
                    self.critic.parameters(),
                    self.critic_target.parameters(),
                    self.tau,
                )
            self._n_updates += 1

        self.logger.record("train/n_updates", self._n_updates, exclude="tensorboard")
        if actor_losses:
            self.logger.record("train/actor_loss", float(np.mean(actor_losses)))
            self.logger.record("train/critic_loss", float(np.mean(critic_losses)))
            self.logger.record("train/ent_coef", float(np.mean(ent_coefs)))

    def _resolve_ent_coef(self) -> th.Tensor:
        if self.log_ent_coef is not None:
            return th.exp(self.log_ent_coef)
        assert self.ent_coef_tensor is not None
        return self.ent_coef_tensor

    def _excluded_save_params(self) -> list[str]:
        # SB3 save pickles the algorithm minus these fields. Carry
        # through the defaults plus our alias attributes so a
        # reload rebuilds them via ``_create_aliases``.
        return [*super()._excluded_save_params(), "actor", "critic", "critic_target"]

    def _get_torch_save_params(self) -> tuple[list[str], list[str]]:
        state_dicts = ["policy", "actor.optimizer", "critic.optimizer"]
        saved_tensors: list[str] = []
        if self.ent_coef_optimizer is not None:
            state_dicts.append("ent_coef_optimizer")
            saved_tensors.append("log_ent_coef")
        return state_dicts, saved_tensors
