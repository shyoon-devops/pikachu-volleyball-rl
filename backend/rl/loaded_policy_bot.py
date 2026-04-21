"""Loaded-policy opponent bot for self-play league.

A ``LoadedPolicyBot`` wraps an SB3 ``PPO.load()`` snapshot behind the
same ``get_action(state, is_player2)`` signature as
:class:`backend.game.bot.RuleBasedBot`, so the env's per-frame code
swaps between rule-based and learned opponents with zero branching.

Side symmetry: our agent policies are trained as player 1 exclusively
(left side). When a loaded policy plays as player 2 in the env, we
mirror the observation across the net before inference and mirror the
returned action's ``x_dir`` on the way out. The mirror is centred on
``GROUND_WIDTH / 2 == NET_PILLAR_X``; y, vy and jump / power flags are
unchanged. See ``docs/adr/0014-self-play-league.md`` §3 for the
integration design.

SB3 is imported lazily inside ``_load`` so test doubles can substitute
a policy callable without dragging stable-baselines3 into every env
import (parity test, etc.).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Protocol

import numpy as np

from backend.game.constants import (
    GROUND_HEIGHT,
    GROUND_WIDTH,
    MAX_SCORE,
    NET_PILLAR_X,
)
from backend.game.engine import GameState, PlayerInput
from backend.rl.env import ACTION_MAP


class _PolicyLike(Protocol):
    """Subset of SB3's model surface we actually call.

    Both PPO (mlp_v1) and RecurrentPPO (lstm_v1) satisfy this — PPO
    ignores ``state`` / ``episode_start`` and just returns ``(action,
    None)``, RecurrentPPO threads state through. Tests can inject a
    plain callable-wrapped stub that returns ``(action, state)``.
    """

    def predict(
        self,
        observation: np.ndarray,
        state: Any = None,
        episode_start: Any = None,
        *,
        deterministic: bool = True,
    ) -> tuple[np.ndarray, Any]: ...


def _action_mirror_x_dir(action: int) -> int:
    """Flip the x_dir component of an ACTION_MAP action.

    Actions come in pairs around the x-axis: 1↔2, 4↔5, 7↔8, 10↔11.
    Actions with ``x_dir == 0`` (0, 3, 6, 9) map to themselves.
    """
    pairs = {1: 2, 2: 1, 4: 5, 5: 4, 7: 8, 8: 7, 10: 11, 11: 10}
    return pairs.get(action, action)


class LoadedPolicyBot:
    """Opponent bot wrapping an SB3 policy checkpoint.

    Parameters
    ----------
    model_path: path to a ``.zip`` SB3 checkpoint.
    checkpoint_id: identifier used by the rating store; matches the
        filename stem by convention but the caller owns the naming.
    deterministic: forwarded to ``policy.predict``; defaults to True
        because league matches want reproducible opponents.
    rating: initial Elo surfaced on the object so samplers can bias
        on-construction without round-tripping through the rating
        store.
    policy_loader: optional override returning an object implementing
        :class:`_PolicyLike`. Tests pass a stub here to avoid SB3.
    """

    def __init__(
        self,
        model_path: str | Path,
        checkpoint_id: str,
        *,
        deterministic: bool = True,
        rating: float = 1000.0,
        policy_loader: Callable[[str | Path], _PolicyLike] | None = None,
        policy_type: str = "mlp_v1",
        algorithm: str = "ppo",
    ) -> None:
        self.model_path: Path = Path(model_path)
        self.checkpoint_id: str = str(checkpoint_id)
        # Also exposed as ``.id`` for rating-store identity — matches
        # the Opponent protocol's entry-id key used by PFSPProvider.
        self.id: str = self.checkpoint_id
        self.deterministic: bool = bool(deterministic)
        self.rating: float = float(rating)
        # ADR 0016: dispatch PPO.load vs RecurrentPPO.load on this
        # field. Pre-Sprint-3 checkpoints backfill to ``"mlp_v1"`` at
        # the repository layer (see §9 migration).
        self.policy_type: str = str(policy_type)
        # ADR 0017: algorithm axis. Pre-S4 checkpoints backfill to
        # ``"ppo"``; SAC checkpoints dispatch to ``SACDiscrete.load``
        # instead (replay buffers are not cross-portable, see §9).
        self.algorithm: str = str(algorithm)
        self._policy: _PolicyLike | None = None
        self._policy_loader = policy_loader
        # Ball-trajectory delta observation expects the previous frame's
        # ball position; track it locally so the bot owns its own short
        # history (the env's _prev_ball_x is the agent's history, not
        # ours).
        self._prev_ball_x: float = float(GROUND_WIDTH) / 2.0
        self._prev_ball_y: float = 0.0
        # LSTM recurrent state (hidden, cell) tuple, threaded across
        # ``predict`` calls within a single match. ``None`` means "new
        # episode / first call" — SB3's RecurrentPPO.predict treats
        # that as a hidden-state reset. For mlp_v1 the policy ignores
        # this slot entirely, so the extra attribute is cheap.
        self._lstm_state: Any = None
        # Set on the first predict() after a reset so sb3-contrib's
        # predict() routes through its episode-start branch exactly
        # once. Flips False on the second call.
        self._episode_starts: np.ndarray = np.array([True], dtype=bool)

    # ------------------------------------------------------------------
    # Lazy policy load
    # ------------------------------------------------------------------
    def _load(self) -> _PolicyLike:
        if self._policy is not None:
            return self._policy
        if self._policy_loader is not None:
            self._policy = self._policy_loader(self.model_path)
            return self._policy
        # Default: real SB3 load. Imported lazily so modules that just
        # want the mirroring helpers (or tests using a stub loader)
        # don't pay the SB3 import cost.
        #
        # ADR 0016 + 0017: cross-arch + cross-algo load is blocked.
        # Loading a PPO checkpoint as Recurrent/SAC (or vice versa)
        # hits a layer-shape or buffer-format mismatch at unpickle.
        # The repository backfill stamps (algorithm, policy_type) on
        # every pool entry so dispatch is always correct.
        if self.algorithm == "sac":
            # SAC-Discrete has no recurrent variant (ADR 0017 §4),
            # so policy_type is ignored on this branch — any SAC
            # checkpoint loads via SACDiscrete regardless of the
            # stored policy_type tag.
            from backend.rl.sac_discrete import SACDiscrete  # noqa: PLC0415

            self._policy = SACDiscrete.load(str(self.model_path))
        elif self.policy_type == "lstm_v1":
            from sb3_contrib import RecurrentPPO  # noqa: PLC0415

            self._policy = RecurrentPPO.load(str(self.model_path))
        else:
            from stable_baselines3 import PPO  # noqa: PLC0415

            self._policy = PPO.load(str(self.model_path))
        return self._policy

    # ------------------------------------------------------------------
    # Observation builder — port of PikachuVolleyballEnv._get_obs with
    # optional side-mirror for the player-2 case.
    # ------------------------------------------------------------------
    def _build_obs(self, state: GameState, *, mirror: bool) -> np.ndarray:
        w = float(GROUND_WIDTH)
        h = float(GROUND_HEIGHT)
        max_v = 20.0

        # Pick the policy's "self" and "opponent" views. When mirroring,
        # the learner sees player2 as its own player and the current
        # player1 as the opponent — all x coords flipped around the net
        # so the policy's trained "left side is me" assumption holds.
        # y and vy are NEVER mirrored — the net is only a horizontal
        # symmetry axis. prev_ball_y gets the same treatment as
        # prev_ball_x (own local variable) to keep the field layout
        # symmetric and prevent a future refactor from accidentally
        # mirroring it by analogy.
        prev_ball_y = self._prev_ball_y
        if mirror:
            me = state.player2
            opp = state.player1
            ball_x = float(GROUND_WIDTH) - float(state.ball.x)
            ball_vx = -float(state.ball.vx)
            prev_ball_x = float(GROUND_WIDTH) - self._prev_ball_x
            me_x = float(GROUND_WIDTH) - float(me.x)
            opp_x = float(GROUND_WIDTH) - float(opp.x)
            me_vx = -float(me.vx)
            score_diff = state.score2 - state.score1
            serving_me = state.serving_player == 2
        else:
            me = state.player1
            opp = state.player2
            ball_x = float(state.ball.x)
            ball_vx = float(state.ball.vx)
            prev_ball_x = self._prev_ball_x
            me_x = float(me.x)
            opp_x = float(opp.x)
            me_vx = float(me.vx)
            score_diff = state.score1 - state.score2
            serving_me = state.serving_player == 1

        if me.is_jumping:
            me_air = 1.0
        elif me.is_diving:
            me_air = -1.0
        else:
            me_air = 0.0

        obs = np.array(
            [
                me_x / w * 2 - 1,
                me.y / h * 2 - 1,
                np.clip(me_vx / max_v, -1, 1),
                np.clip(me.vy / max_v, -1, 1),
                me_air,
                # Opponent view is (x, y, vy) — opp.vx intentionally
                # omitted to match the env obs layout docstring at
                # PikachuVolleyballEnv._get_obs (docstring line 275).
                opp_x / w * 2 - 1,
                opp.y / h * 2 - 1,
                np.clip(opp.vy / max_v, -1, 1),
                ball_x / w * 2 - 1,
                state.ball.y / h * 2 - 1,
                np.clip(ball_vx / max_v, -1, 1),
                np.clip(state.ball.vy / max_v, -1, 1),
                np.clip((ball_x - prev_ball_x) / max_v, -1, 1),
                np.clip(
                    (float(state.ball.y) - prev_ball_y) / max_v, -1, 1
                ),
                np.clip((ball_x - me_x) / w, -1, 1),
                # ball_side: 1.0 if ball is on "my" half (i.e. left half
                # of the mirrored frame), -1.0 otherwise.
                1.0 if ball_x <= NET_PILLAR_X else -1.0,
                np.clip(score_diff / MAX_SCORE, -1, 1),
                1.0 if serving_me else -1.0,
            ],
            dtype=np.float32,
        )
        return np.clip(obs, -1.0, 1.0)

    # ------------------------------------------------------------------
    # Opponent protocol
    # ------------------------------------------------------------------
    def get_action(
        self, state: GameState, *, is_player2: bool
    ) -> PlayerInput:
        policy = self._load()
        obs = self._build_obs(state, mirror=is_player2)
        if self.policy_type == "lstm_v1":
            # RecurrentPPO.predict threads (hidden, cell) across calls.
            # ``state`` is None on the first call / after reset —
            # sb3-contrib treats that identically to a zeroed hidden
            # state. ``episode_start`` must be True on exactly the
            # first tick of each episode so the buffer resets; we flip
            # it False immediately after.
            action_arr, new_state = policy.predict(
                obs,
                state=self._lstm_state,
                episode_start=self._episode_starts,
                deterministic=self.deterministic,
            )
            self._lstm_state = new_state
            # After the first call of a match, every subsequent tick is
            # mid-episode as far as the policy is concerned — only
            # ``reset_history`` can flip this back.
            if self._episode_starts.any():
                self._episode_starts = np.array([False], dtype=bool)
        else:
            action_arr, _ = policy.predict(
                obs, deterministic=self.deterministic
            )
        # SB3 predict returns either a scalar or a length-1 array; coerce
        # to int either way so ACTION_MAP lookup is safe.
        try:
            action = int(action_arr.item())
        except AttributeError:
            action = int(action_arr)
        if is_player2:
            action = _action_mirror_x_dir(action)
        # Update our own ball-history AFTER building obs so the next
        # call sees a correct delta. Use the un-mirrored ball.x as the
        # stored value; the mirror is re-applied each call from the
        # raw state.
        self._prev_ball_x = float(state.ball.x)
        self._prev_ball_y = float(state.ball.y)
        return ACTION_MAP[action]

    def reset_history(self) -> None:
        """Clear the per-match ball-delta history. Call from provider
        on a new match if you want strict determinism.

        Also zeroes LSTM recurrent state (ADR 0016 §7) so an lstm_v1
        opponent starts each match with a fresh hidden/cell pair —
        otherwise carrying state across a match boundary would leak
        the previous rally's intent estimate into a new match.
        """
        self._prev_ball_x = float(GROUND_WIDTH) / 2.0
        self._prev_ball_y = 0.0
        self._lstm_state = None
        self._episode_starts = np.array([True], dtype=bool)
