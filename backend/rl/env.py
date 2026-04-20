"""Gymnasium environment for Pikachu Volleyball RL training."""

from __future__ import annotations

from typing import Any

import numpy as np

import gymnasium
from gymnasium import spaces

from backend.rl.opponent import FixedBotProvider, OpponentProvider
from backend.rl.reward_potential import (
    BuiltinLinearPotential,
    PotentialFn,
)

# Boundary-contract enum: must match the BE/FE validator values 1:1.
# Any drift raises ValueError at env construction; the three
# implementations are wired via ``_reward_impls`` dispatch so
# extending the set is a single-line change to both the tuple and
# the dispatch table.
VALID_REWARD_MODELS: tuple[str, ...] = (
    "shaped_v1",
    "sparse_v1",
    "learned_shaped_v1",
)
from backend.game.constants import (
    BALL_RADIUS,
    GROUND_HEIGHT,
    GROUND_WIDTH,
    MAX_SCORE,
    NET_PILLAR_TOP_Y,
    NET_PILLAR_X,
    PLAYER_HALF_LENGTH,
)
from backend.game.engine import GameState, PikachuVolleyball, PlayerInput


def _match_state_name(state: GameState) -> str:
    """Short label for the match-level state consumers render as a tag.

    Distinguishes the three user-visible macro-states:
      * "ended"   — match is over (a side reached MAX_SCORE)
      * "scoring" — grounded-ball / freeze frame between rallies
      * "live"    — rally in progress

    We avoid leaking the per-player ``state`` field (0-6) because those
    are render-only animation frames; FE doesn't need them.
    """
    if getattr(state, "is_game_ended", False):
        return "ended"
    if getattr(state, "is_round_over", False):
        return "scoring"
    return "live"

# Action mapping: 12 actions covering (x_dir, y_dir, power_hit) combos
# 0=noop, 1=left, 2=right, 3=jump, 4=left+jump, 5=right+jump,
# 6=power, 7=left+power, 8=right+power,
# 9=jump+power, 10=left+jump+power, 11=right+jump+power
ACTION_MAP: dict[int, PlayerInput] = {
    0: PlayerInput(x_dir=0, y_dir=0, power_hit=False),
    1: PlayerInput(x_dir=-1, y_dir=0, power_hit=False),
    2: PlayerInput(x_dir=1, y_dir=0, power_hit=False),
    3: PlayerInput(x_dir=0, y_dir=-1, power_hit=False),
    4: PlayerInput(x_dir=-1, y_dir=-1, power_hit=False),
    5: PlayerInput(x_dir=1, y_dir=-1, power_hit=False),
    6: PlayerInput(x_dir=0, y_dir=0, power_hit=True),
    7: PlayerInput(x_dir=-1, y_dir=0, power_hit=True),
    8: PlayerInput(x_dir=1, y_dir=0, power_hit=True),
    9: PlayerInput(x_dir=0, y_dir=-1, power_hit=True),
    10: PlayerInput(x_dir=-1, y_dir=-1, power_hit=True),
    11: PlayerInput(x_dir=1, y_dir=-1, power_hit=True),
}


class PikachuVolleyballEnv(gymnasium.Env):
    """Pikachu Volleyball as a Gymnasium environment.

    Player 1 (left) is the RL agent. Player 2 (right) is the rule-based bot.
    """

    metadata: dict[str, Any] = {"render_modes": []}

    def __init__(
        self,
        bot_level: int = 1,
        max_steps: int = 3000,
        *,
        opponent_provider: OpponentProvider | None = None,
        env_index: int = 0,
        reward_model: str = "shaped_v1",
        potential_fn: PotentialFn | None = None,
        gamma: float = 0.99,
    ) -> None:
        super().__init__()
        if reward_model not in VALID_REWARD_MODELS:
            raise ValueError(
                f"reward_model must be one of "
                f"{sorted(VALID_REWARD_MODELS)}, got {reward_model!r}"
            )
        self.bot_level = bot_level
        self.max_steps = max_steps
        self.env_index = int(env_index)
        # Boundary-contract enum; unknown values rejected above.
        self.reward_model: str = reward_model
        # Learned-shaping scaffold (ADR 0015). Only consulted when
        # reward_model == 'learned_shaped_v1'; left None for the
        # shaped_v1 / sparse_v1 paths to make the cold-start cost
        # explicit in a debugger. For the learned path, the caller
        # can inject a trained PotentialFn; the placeholder below
        # returns Φ ≡ 0 so shaping collapses to zero and the path
        # behaves like sparse_v1 until IRL training lands.
        self._potential_fn: PotentialFn | None = (
            potential_fn
            if potential_fn is not None
            else (
                BuiltinLinearPotential.zeros()
                if reward_model == "learned_shaped_v1"
                else None
            )
        )
        # Discount used for the Ng-Harada-Russell shaping delta.
        # Matches the PPO default (also 0.99 in DEFAULT_HYPERPARAMS).
        self._shaping_gamma: float = float(gamma)
        # Previous-frame potential cached across step() calls. Reset
        # to 0.0 on env.reset(). For the zeros-placeholder potential
        # this stays 0.0, making the shaping term identically 0.
        self._prev_potential_value: float = 0.0

        # Opponent provider wiring (v2.x Sprint-1 self-play league).
        # When a provider is passed in explicitly, it takes precedence —
        # typical for the self-play-league trainer path where the trainer
        # owns a shared PFSPProvider. When left None (the legacy and
        # bot_ladder path), we fall back to a FixedBotProvider built from
        # ``bot_level`` so existing callers keep working unchanged. See
        # docs/adr/0014-self-play-league.md §3.
        self._opponent_provider: OpponentProvider = (
            opponent_provider
            if opponent_provider is not None
            else FixedBotProvider(level=bot_level)
        )

        self.observation_space = spaces.Box(
            low=-1.0, high=1.0, shape=(18,), dtype=np.float32
        )
        self.action_space = spaces.Discrete(12)

        # The port(view) commit dropped the engine's post-score freeze.
        # Mid-match scoring now immediately swaps to a fresh serving state,
        # which is exactly the behavior the RL env previously opted into
        # via `post_score_freeze=False`. The engine enters a 211-frame
        # gameEnd window at MAX_SCORE, but the env terminates on MAX_SCORE
        # before that window is entered so the RL agent never sees no-op
        # game-end frames.
        self._game = PikachuVolleyball()
        # Bot reference is rebound on every reset() so provider sampling
        # runs once per match (matching the pre-league per-episode
        # RuleBasedBot construction pattern).
        self._bot = self._opponent_provider.get_opponent(self.env_index)
        self._steps = 0
        self._prev_score1 = 0
        self._prev_score2 = 0
        self._prev_ball_x = 0.0
        self._prev_ball_y = 0.0
        self._prev_ball_vy = 0.0
        self._prev_p1_x = 0.0
        self._consecutive_touches = 0
        self._frames_since_crossing = 0
        # Per-match net-crossing counter (rally_count in the GameRecord).
        # Increments on any net crossing (either direction) and resets on
        # reset() — matches the definition the offline evaluator uses
        # (rl/evaluator.py:82-85) so /api/games and avg_rally_length are
        # comparable. The BE-A2 drain_pending_results hook reads it at
        # game-end and ships the total in the result dict.
        self._rally_count: int = 0
        self._prev_ball_side_right: bool = False
        # Finished matches queued for the trainer-thread drain hook
        # (BE-A2). Each entry is a plain dict matching the producer
        # contract expected by handlers.results_push_loop.
        self._pending_results: list[dict[str, Any]] = []

    def reset(
        self,
        *,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[np.ndarray, dict[str, Any]]:
        super().reset(seed=seed, options=options)
        # Port commit `port(view): gameEnd 211f` dropped the engine's
        # post-score freeze. Mid-match scoring now immediately swaps to a
        # fresh serving state, which is exactly the behavior the RL env
        # previously opted into via `post_score_freeze=False`. The engine
        # enters a 211-frame gameEnd window at MAX_SCORE, but the env
        # terminates on MAX_SCORE before that window is entered.
        self._game = PikachuVolleyball()
        # Pull a fresh opponent for the new match. The FixedBotProvider
        # path returns a new RuleBasedBot(level=bot_level) — same
        # behavior as the pre-league direct construction. The PFSP
        # path samples from the league pool.
        self._bot = self._opponent_provider.get_opponent(self.env_index)
        state = self._game.reset()
        self._steps = 0
        self._prev_score1 = 0
        self._prev_score2 = 0
        self._prev_ball_x = float(state.ball.x)
        self._prev_ball_y = float(state.ball.y)
        self._prev_ball_vy = float(state.ball.vy)
        self._prev_p1_x = float(state.player1.x)
        self._consecutive_touches = 0
        self._frames_since_crossing = 0
        # rally_count and ball-side tracker reset together; pending
        # results intentionally survive reset so the trainer-side drain
        # can still collect a game that ended on the last step of the
        # prior episode (VecEnv auto-reset races with env_method).
        self._rally_count = 0
        self._prev_ball_side_right = state.ball.x > NET_PILLAR_X
        # Shaping cache (learned_shaped_v1 only). Fresh match means no
        # prior potential — seed to 0 so the very first step's shaping
        # delta is ``γ·Φ(s') − 0``. With the zeros placeholder this is
        # identically 0.0; with a trained Φ it's the first transition's
        # legitimate shaping contribution.
        self._prev_potential_value = 0.0
        return self._get_obs(state), {}

    def step(
        self, action: int
    ) -> tuple[np.ndarray, float, bool, bool, dict[str, Any]]:
        self._steps += 1

        p1_input = ACTION_MAP[int(action)]

        # Auto power-hit: if jumping and ball is close, force power_hit
        state = self._game._state
        p1 = state.player1
        ball = state.ball
        if p1.is_jumping and not p1_input.power_hit:
            dist_x = abs(ball.x - p1.x)
            dist_y = abs(ball.y - p1.y)
            if dist_x < 60 and dist_y < 60:
                p1_input = PlayerInput(
                    x_dir=p1_input.x_dir,
                    y_dir=p1_input.y_dir,
                    power_hit=True,
                )

        p2_input = self._bot.get_action(state, is_player2=True)
        new_state = self._game.step(p1_input, p2_input)

        obs = self._get_obs(new_state)
        reward = self._compute_reward(new_state)
        terminated = new_state.score1 >= MAX_SCORE or new_state.score2 >= MAX_SCORE
        truncated = self._steps >= self.max_steps

        # Force-truncate with large penalty if rally stalls too long
        # (agent looping self-tosses without sending ball over net).
        # Two signals converge here:
        #   1. env-local `_frames_since_crossing` — counts shaping frames
        #      for the reward signal; truncates the episode early to avoid
        #      reward-farming inside stalled rallies.
        #   2. engine-level `round_ended_by_timeout` — the game engine
        #      force-ended the round itself via its RALLY_MAX_FRAMES safety
        #      valve (added in this hotfix). Guarantees no infinite rally
        #      can wedge the match, even outside RL.
        engine_timeout = getattr(new_state, "round_ended_by_timeout", False)
        stalled_out = (
            self._frames_since_crossing >= self._RALLY_MAX_FRAMES
            or engine_timeout
        )
        if stalled_out and not terminated:
            reward += self._RALLY_TIMEOUT_PENALTY
            truncated = True

        # Net-crossing rally counter — both directions count (matches the
        # offline evaluator so /api/games rally_count matches eval avg).
        ball_side_right = new_state.ball.x > NET_PILLAR_X
        if ball_side_right != self._prev_ball_side_right:
            self._rally_count += 1
        self._prev_ball_side_right = ball_side_right

        # BE-A2: terminal game result snapshot. Only on natural ``terminated``
        # (a side reached MAX_SCORE). Truncation (max_steps, stall penalty)
        # is NOT a completed match and must not be saved — otherwise the
        # Recent Games list would fill with abandoned episodes. The drain
        # hook on the trainer thread picks these up.
        if terminated and not truncated:
            winner = 1 if new_state.score1 >= MAX_SCORE else 2
            self._pending_results.append({
                "score1": int(new_state.score1),
                "score2": int(new_state.score2),
                "winner": winner,
                "duration_frames": int(new_state.frame),
                "rally_count": int(self._rally_count),
            })
            # League provider sees the match outcome so it can update
            # Elo against the sampled opponent. FixedBotProvider's
            # default on_match_end is a no-op — zero cost for the
            # legacy path. PFSPProvider forwards to its rating_store.
            self._opponent_provider.on_match_end(
                env_index=self.env_index,
                opponent=self._bot,
                winner=winner,
                score1=int(new_state.score1),
                score2=int(new_state.score2),
            )

        self._prev_score1 = new_state.score1
        self._prev_score2 = new_state.score2
        self._prev_ball_x = float(new_state.ball.x)
        self._prev_ball_y = float(new_state.ball.y)
        self._prev_ball_vy = float(new_state.ball.vy)
        self._prev_p1_x = float(new_state.player1.x)

        info: dict[str, Any] = {
            "score1": new_state.score1,
            "score2": new_state.score2,
            "frame": new_state.frame,
            "stalled_out": stalled_out,
            "engine_rally_timeout": engine_timeout,
            "consecutive_touches": self._consecutive_touches,
        }

        return obs, reward, terminated, truncated, info

    def drain_pending_results(self) -> list[dict[str, Any]]:
        """Pop completed-match dicts queued by ``step`` (BE-A2).

        Called via ``VecEnv.env_method`` from the EnvResultCallback so
        each parallel env's terminated matches can be flushed to Mongo.
        Returns a shallow copy of the internal list and clears it in one
        step so a concurrent callback tick on the same env cannot
        double-save.
        """
        results = list(self._pending_results)
        self._pending_results.clear()
        return results

    def get_frame_snapshot(self) -> dict[str, Any]:
        """Return a serialized picture of this env's current game state.

        Called from the training thread's callback via ``VecEnv.env_method``
        so a SubprocVecEnv can fan the snapshot out across process
        boundaries — the return value must therefore be a plain dict of
        primitives (no engine objects, no numpy arrays). Reuses the
        ``_serialize_state`` helper that already powers the demo game's
        WS frames so both channels produce the same schema.

        Returns the same dict the demo callback emits, plus a
        ``state_name`` and ``score`` convenience pair so consumers don't
        have to re-derive them.
        """
        # Lazy import — avoids an import cycle (rl.callbacks imports
        # backend.game.engine which imports backend.game.constants, and
        # rl.env is pulled from several test paths that shouldn't need
        # SB3 on the path).
        from backend.rl.callbacks import _serialize_state

        state = self._game._state
        payload = _serialize_state(state)
        payload["score"] = [int(state.score1), int(state.score2)]
        payload["state_name"] = _match_state_name(state)
        return payload

    def _get_obs(self, state: Any) -> np.ndarray:
        """Normalize game state to [-1, 1] observation vector (18 floats).

        Layout:
          [0-4]   Player 1: x, y, vx, vy, airborne_state
          [5-7]   Player 2: x, y, vy
          [8-11]  Ball: x, y, vx, vy
          [12-13] Ball trajectory delta: dx, dy
          [14-15] Ball-agent relationship: relative_x, ball_side
          [16-17] Game state: score_diff, serving
        """
        w = float(GROUND_WIDTH)
        h = float(GROUND_HEIGHT)
        max_v = 20.0

        # Player airborne state: jumping=1, diving=-1, grounded=0
        if state.player1.is_jumping:
            p1_air = 1.0
        elif state.player1.is_diving:
            p1_air = -1.0
        else:
            p1_air = 0.0

        obs = np.array(
            [
                # Player 1 (agent) — 5 values
                state.player1.x / w * 2 - 1,
                state.player1.y / h * 2 - 1,
                np.clip(state.player1.vx / max_v, -1, 1),
                np.clip(state.player1.vy / max_v, -1, 1),
                p1_air,
                # Player 2 (opponent) — 3 values
                state.player2.x / w * 2 - 1,
                state.player2.y / h * 2 - 1,
                np.clip(state.player2.vy / max_v, -1, 1),
                # Ball — 4 values
                state.ball.x / w * 2 - 1,
                state.ball.y / h * 2 - 1,
                np.clip(state.ball.vx / max_v, -1, 1),
                np.clip(state.ball.vy / max_v, -1, 1),
                # Ball trajectory delta — 2 values
                np.clip(
                    (float(state.ball.x) - self._prev_ball_x) / max_v, -1, 1
                ),
                np.clip(
                    (float(state.ball.y) - self._prev_ball_y) / max_v, -1, 1
                ),
                # Ball-agent relationship — 2 values
                np.clip(
                    (float(state.ball.x) - float(state.player1.x)) / w, -1, 1
                ),
                1.0 if state.ball.x <= NET_PILLAR_X else -1.0,
                # Game state — 2 values
                np.clip((state.score1 - state.score2) / MAX_SCORE, -1, 1),
                1.0 if state.serving_player == 1 else -1.0,
            ],
            dtype=np.float32,
        )
        return np.clip(obs, -1.0, 1.0)

    # Reward weights — tuned for 500K+ step PPO convergence.
    # Philosophy: terminal rewards should dominate cumulative shaping over a
    # full 15-point match, so the agent optimizes for winning rather than for
    # harvesting small shaping signals.
    #
    # Rough per-game budget (illustrative, bot-level 1):
    #   - Terminal game bonus: ±50 (was ±20 — too small vs 15×10 point reward)
    #   - Net scoring:         ±10 per point (kept)
    #   - Touch + crossing:    ~+5 per winning rally, ~-2 per toss-loop
    #   - Shaping (approach + ready + offensive-pressure): capped ~+0.04/frame
    #     A full 3000-step episode can accumulate at most ~120 shaping reward,
    #     which is now less than a single terminal swing (+50 − (−50) = 100).
    _GAME_WIN_REWARD = 50.0           # was 20.0 — terminal must dominate shaping
    _GAME_LOSS_REWARD = -50.0         # was -20.0
    _SCORE_REWARD = 10.0              # kept — per-point scoring signal
    _CONCEDE_REWARD = -10.0
    _TOUCH_REWARD_FIRST = 3.0
    _TOUCH_REWARD_SECOND = 1.0
    _TOUCH_PENALTY_EXCESS = -2.0
    _NET_CROSSING_REWARD = 2.0
    _STALL_THRESHOLD = 300
    _STALL_PENALTY_PER_FRAME = -0.05  # was -0.03 — more bite on dead rallies
    _RALLY_MAX_FRAMES = 600           # hard termination threshold
    _RALLY_TIMEOUT_PENALTY = -12.0    # was -5.0 — must outweigh a single concede
    _APPROACH_REWARD = 0.02           # was 0.05 — halved (reduce shaping bias)
    _READY_REWARD = 0.005             # was 0.01 — halved
    _OFFENSIVE_PRESSURE_REWARD = 0.02 # NEW: reward attacking ball near net / opp side

    def _compute_reward(self, state: Any) -> float:
        """Dispatch reward computation to the configured ``reward_model``.

        The enum-to-impl mapping is intentionally a single branch so
        unknown values are impossible at call time (validated at
        __init__). Each impl is isolated in its own method to keep
        the call-path for shaped_v1 bit-identical to the pre-ADR-0015
        monolith — see ``_compute_reward_shaped_v1`` for the fixed
        accumulation order that the parity test pins.
        """
        if self.reward_model == "shaped_v1":
            return self._compute_reward_shaped_v1(state)
        if self.reward_model == "sparse_v1":
            return self._compute_reward_sparse_v1(state)
        if self.reward_model == "learned_shaped_v1":
            return self._compute_reward_learned_shaped_v1(state)
        # Defensive — the __init__ validator should have caught this,
        # but guard against in-place self.reward_model mutation by
        # external code that bypasses the constructor.
        raise ValueError(
            f"unknown reward_model {self.reward_model!r} at dispatch; "
            f"expected one of {sorted(VALID_REWARD_MODELS)}"
        )

    def _compute_reward_shaped_v1(self, state: Any) -> float:
        """v1.0.0 shaped reward — 9-term hand-tuned shaping.

        The body is the original pre-ADR-0015 ``_compute_reward``
        verbatim; keeping the helper call order fixed is what lets
        ``test_reward_model_shaped_v1_parity.py`` assert bit-identical
        float sums against a reference trajectory.

        Reward hierarchy (largest to smallest):
          1. Game outcome:       win +50 / loss -50  (terminal, dominates shaping)
          2. Scoring:            score +10 / concede -10
          3. Rally timeout:      -12 if rally stalls past _RALLY_MAX_FRAMES
          4. Ball touch:         +3.0 first, +1.0 second, -2.0 for 3rd+ (per rally)
          5. Net crossing:       +2.0 when ball sent to opp court (resets touch count)
          6. Approach ball:      +0.02/frame when moving toward ball on own side
          7. Offensive pressure: +0.02/frame when ball is high+near net on opp side
          8. Ready position:     +0.005/frame near center when ball on opp side
          9. Stall penalty:      -0.05/frame after 300 frames without net crossing
        """
        reward = 0.0
        counter_reset_this_frame = False

        # --- PRIMARY: scoring events ---
        score_delta, score_reset = self._score_reward(state)
        reward += score_delta
        counter_reset_this_frame = counter_reset_this_frame or score_reset
        reward += self._game_outcome_reward(state)

        # --- AUX 1: ball touch with diminishing returns ---
        reward += self._touch_reward(state)

        # --- AUX 2: net crossing (strengthened, resets touch counter) ---
        crossing_delta, crossing_reset = self._net_crossing_reward(state)
        reward += crossing_delta
        counter_reset_this_frame = counter_reset_this_frame or crossing_reset

        # --- AUX 3: stall penalty ---
        reward += self._stall_penalty(state, counter_reset_this_frame)

        # --- AUX 4: approach ball (gradient for early training) ---
        reward += self._approach_reward(state)

        # --- AUX 5: offensive pressure ---
        reward += self._offensive_pressure_reward(state)

        # --- AUX 6: ready position (defensive positioning) ---
        reward += self._ready_position_reward(state)

        return float(reward)

    def _compute_reward_sparse_v1(self, state: Any) -> float:
        """Terminal-only reward — ADR 0015 §2 option A.

        Returns ``_SCORE_REWARD`` / ``_CONCEDE_REWARD`` on per-point
        scoring events and ``_GAME_{WIN,LOSS}_REWARD`` on the final
        point. No per-frame shaping: the farming loops #6 (approach),
        #7 (offensive pressure), #8 (ready position) contribute
        exactly 0.0 per step.

        The helpers ``_score_reward``, ``_net_crossing_reward``, and
        ``_stall_penalty`` are still invoked for their counter-update
        side-effects — ``step()`` downstream reads
        ``_frames_since_crossing`` to drive the rally-timeout
        truncation, and that tick must still happen even when we're
        dropping the shaping penalty. The shaping delta returned by
        ``_stall_penalty`` is discarded; ``_net_crossing_reward``'s
        +2 bonus is discarded; ``_touch_reward`` is skipped entirely
        (its only mutation is ``_consecutive_touches`` which scoring
        helpers reset on their own).
        """
        score_delta, score_reset = self._score_reward(state)
        _crossing_delta, crossing_reset = self._net_crossing_reward(state)
        # Tick the rally-timeout counter. Discard the penalty — sparse
        # rewards do not shape per-frame. Counter mutation is still
        # required so step() can truncate stalled rallies.
        self._stall_penalty(state, score_reset or crossing_reset)

        reward = 0.0
        reward += score_delta
        reward += self._game_outcome_reward(state)
        return float(reward)

    def _compute_reward_learned_shaped_v1(self, state: Any) -> float:
        """Sparse terminal + potential-based shaping — ADR 0015 §2 option B.

        ``F(s, a, s') = γ·Φ(s') − Φ(s)`` per Ng-Harada-Russell (1999).
        Optimal policy is identical to ``sparse_v1`` by the
        policy-invariance theorem; shaping only densifies the gradient.

        During Sprint 2 the default ``_potential_fn`` is
        ``BuiltinLinearPotential.zeros()`` — Φ ≡ 0 on every obs → the
        shaping delta is 0.0 on every transition → this method returns
        exactly the same number as ``sparse_v1``. That's the intentional
        placeholder: the scaffold wire is live, ready for an IRL-trained
        ``PotentialFn`` to drop in without touching this method.
        """
        sparse = self._compute_reward_sparse_v1(state)
        if self._potential_fn is None:
            # Defensive — __init__ guarantees a potential for this
            # enum, but if someone mutated the attribute in-place the
            # shaping delta must degrade gracefully to zero rather
            # than crash training.
            return float(sparse)
        curr_obs = self._get_obs(state)
        phi_curr = float(self._potential_fn.phi(curr_obs))
        shaping_delta = self._shaping_gamma * phi_curr - self._prev_potential_value
        self._prev_potential_value = phi_curr
        return float(sparse + shaping_delta)

    # ------------------------------------------------------------------
    # Reward helpers (A1 refactor) — each returns its delta only. Main
    # ``_compute_reward`` sums in a fixed order so float accumulation is
    # byte-identical to the pre-refactor monolith. Pure helpers (no state
    # mutation) are extracted first; mutation-carrying ones follow.
    # ------------------------------------------------------------------
    def _stall_penalty(self, state: Any, counter_reset_this_frame: bool) -> float:
        """Per-frame penalty when the rally has stalled past the threshold.
        Mutates ``_frames_since_crossing`` (increment only; resets happen
        inside the score / net-crossing helpers).

        Gate: ``not is_round_over`` AND ``not counter_reset_this_frame``.
        The counter tracks "frames since the last meaningful event"; on
        any frame where a score, concede, or net-crossing fired the
        counter was already zeroed by that helper, so we must NOT
        increment it here — otherwise the threshold comparison would
        slip by one frame.

        Returns ``_STALL_PENALTY_PER_FRAME`` only once the counter
        CROSSES ``_STALL_THRESHOLD`` (strictly greater). Pre-threshold
        frames return 0.0 even though the counter still ticks.
        """
        if state.is_round_over or counter_reset_this_frame:
            return 0.0
        self._frames_since_crossing += 1
        if self._frames_since_crossing > self._STALL_THRESHOLD:
            return self._STALL_PENALTY_PER_FRAME
        return 0.0

    def _touch_reward(self, state: Any) -> float:
        """Diminishing-returns bonus for agent touching the ball.
        Mutates ``_consecutive_touches`` only (not frames_since_crossing).

        Touch detection uses the engine's post-collision velocity clamp:
        the engine sets ``ball.vy <= -15`` on a player collision, and
        we see the previous frame's ``_prev_ball_vy >= 0`` (ball was
        falling or level) paired with ``ball.vy <= -14`` (reflected
        upward past the clamp floor) to detect exactly one edge per
        collision. A 3× collision_dist x-proximity gate keeps the signal
        pinned to player 1 (the agent) vs. player 2 (bot).

        First touch of a rally: +_TOUCH_REWARD_FIRST. Second: +_TOUCH_
        REWARD_SECOND. Third+ (``else``): +_TOUCH_PENALTY_EXCESS — a
        NEGATIVE constant, intentionally punishing self-toss loops.
        """
        ball = state.ball
        p1 = state.player1
        collision_dist = PLAYER_HALF_LENGTH + BALL_RADIUS
        if self._prev_ball_vy >= 0 and ball.vy <= -14:
            if abs(ball.x - p1.x) < collision_dist * 3:
                self._consecutive_touches += 1
                if self._consecutive_touches == 1:
                    return self._TOUCH_REWARD_FIRST
                if self._consecutive_touches == 2:
                    return self._TOUCH_REWARD_SECOND
                return self._TOUCH_PENALTY_EXCESS
        return 0.0

    def _score_reward(self, state: Any) -> tuple[float, bool]:
        """Per-point scoring reward. Mutates ``_consecutive_touches`` and
        ``_frames_since_crossing`` on either a score or a concede.

        Returns ``(reward_delta, did_reset_counters)``. Both branches
        fire independently (double-counting a simultaneous score + concede
        has never been observed but the pre-refactor code allowed it, so
        the two ``if`` blocks stay independent rather than ``elif``).
        Float-accumulation order matches the inline version:
        ``_SCORE_REWARD`` first, then ``_CONCEDE_REWARD``.
        """
        scored = state.score1 - self._prev_score1
        conceded = state.score2 - self._prev_score2
        delta = 0.0
        reset = False
        if scored > 0:
            delta += self._SCORE_REWARD
            self._consecutive_touches = 0
            self._frames_since_crossing = 0
            reset = True
        if conceded > 0:
            delta += self._CONCEDE_REWARD
            self._consecutive_touches = 0
            self._frames_since_crossing = 0
            reset = True
        return delta, reset

    def _net_crossing_reward(self, state: Any) -> tuple[float, bool]:
        """Ball-over-the-net bonus. Mutates ``_consecutive_touches``
        and ``_frames_since_crossing`` when the crossing is detected.

        Returns ``(reward_delta, did_reset_counters)``. Caller OR's the
        flag into ``counter_reset_this_frame`` so the stall penalty
        knows to skip incrementing this frame. A crossing is counted
        left→right with positive vx (``ball.x > NET_PILLAR_X`` now,
        ``self._prev_ball_x <= NET_PILLAR_X`` previously, ``ball.vx > 0``).
        The ``ball.vx > 0`` gate rules out ball-bounces-off-net-pillar
        false positives where the ball briefly crosses then reverses.
        """
        ball = state.ball
        prev_on_p1_side = self._prev_ball_x <= NET_PILLAR_X
        now_on_p2_side = ball.x > NET_PILLAR_X
        if prev_on_p1_side and now_on_p2_side and ball.vx > 0:
            self._consecutive_touches = 0
            self._frames_since_crossing = 0
            return self._NET_CROSSING_REWARD, True
        return 0.0, False

    def _ready_position_reward(self, state: Any) -> float:
        """Defensive positioning bonus: stand near center while the ball
        is on the opponent's side. Pure — no state mutation.

        Ready-x is half the court (``NET_PILLAR_X * 0.5``); the reward
        decays linearly from full at ready-x to zero at either wall.
        ``max(0.0, ...)`` guards against the (impossible under clamp)
        case of ``dist_from_ready > max_dist``.
        """
        ball = state.ball
        p1 = state.player1
        if ball.x > NET_PILLAR_X and not state.is_round_over:
            ready_x = NET_PILLAR_X * 0.5
            dist_from_ready = abs(float(p1.x) - ready_x)
            max_dist = NET_PILLAR_X * 0.5
            return self._READY_REWARD * max(0.0, 1.0 - dist_from_ready / max_dist)
        return 0.0

    def _offensive_pressure_reward(self, state: Any) -> float:
        """Distance-weighted bonus when the ball is over the opponent's
        half, above the net, and still moving forward. Pure — no state
        mutation.

        Gated by ``not is_round_over`` so scoring frames don't double-
        count. Depth factor decays linearly from 1.0 at the net pillar
        to 0.0 at the far wall, so the reward is strongest in the
        attacking zone (near the opponent's net).
        """
        ball = state.ball
        if (
            ball.x > NET_PILLAR_X
            and ball.y < NET_PILLAR_TOP_Y  # above the net height
            and ball.vx > 0  # moving into opponent's court
            and not state.is_round_over
        ):
            opp_half = float(GROUND_WIDTH - NET_PILLAR_X)
            ball_depth = float(ball.x - NET_PILLAR_X)
            depth_factor = max(0.0, 1.0 - ball_depth / opp_half)
            return self._OFFENSIVE_PRESSURE_REWARD * depth_factor
        return 0.0

    def _approach_reward(self, state: Any) -> float:
        """Gradient shaping when the agent moves toward the ball on its own
        court half. Pure — no state mutation.

        Gated by ``not is_round_over`` so scoring-freeze frames don't
        double-count, and by ``ball.x <= NET_PILLAR_X`` so the signal
        applies only while the ball is defendable. The previous-frame
        distances are taken from ``self._prev_ball_x`` / ``self._prev_p1_x``
        (set at the end of ``step``) so approach is measured as
        "got closer vs. last frame".
        """
        ball = state.ball
        p1 = state.player1
        if ball.x <= NET_PILLAR_X and not state.is_round_over:
            prev_dist = abs(self._prev_ball_x - self._prev_p1_x)
            curr_dist = abs(float(ball.x) - float(p1.x))
            if curr_dist < prev_dist:
                return self._APPROACH_REWARD
        return 0.0

    def _game_outcome_reward(self, state: Any) -> float:
        """Terminal win / loss bonus. Pure — no state mutation.

        Returns ``+_GAME_WIN_REWARD`` when p1 reached MAX_SCORE,
        ``+_GAME_LOSS_REWARD`` when p2 did (note: the loss constant is
        a NEGATIVE number, so adding it subtracts). Exactly one branch
        fires per call — ``score1 >= MAX_SCORE`` takes priority if both
        somehow reached MAX at once, matching the pre-refactor
        if/elif chain.
        """
        if state.score1 >= MAX_SCORE:
            return self._GAME_WIN_REWARD
        if state.score2 >= MAX_SCORE:
            return self._GAME_LOSS_REWARD
        return 0.0
