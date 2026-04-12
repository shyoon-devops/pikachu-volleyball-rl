"""Rule-based bot for Pikachu Volleyball — Levels 1-5."""

from __future__ import annotations

import random
from dataclasses import dataclass

from backend.game.constants import (
    BALL_GROUND_Y,
    GRAVITY,
    GROUND_WIDTH,
    NET_PILLAR_HALF_WIDTH,
    NET_PILLAR_X,
    PLAYER_GROUND_Y,
    PLAYER_HALF_LENGTH,
    PLAYER_SPEED,
)
from backend.game.engine import GameState, PlayerInput


@dataclass(frozen=True)
class BotParams:
    reaction_delay: int
    prediction_error: float        # σ of gaussian noise on intercept target_x
    miss_probability: float        # chance of a pure noop
    move_range: float              # fraction of half-court the bot will range
    jump_timing_error: int         # mean offset added to jump threshold
    # ── new stochastic knobs (hotfix: break repetitive play patterns) ──
    jump_jitter: int               # per-frame uniform jitter on jump threshold
    angle_variance: float          # prob. of non-default power-hit angle
    hesitation_rate: float         # prob. of a movement hesitation (x_dir=0)
    trajectory_noise_scale: float  # extra noise scaled by frames-to-intercept


# Tuned so L5 retains a distinct skill edge but is no longer perfectly
# deterministic: every level now has non-zero variance on every knob, so
# no two games play out frame-identically even with the same RNG seed if
# external entropy (e.g., env.reset) varies.
BOT_PARAMS: dict[int, BotParams] = {
    1: BotParams(reaction_delay=8, prediction_error=0.4,  miss_probability=0.15,
                 move_range=0.6,  jump_timing_error=4,
                 jump_jitter=3, angle_variance=0.4, hesitation_rate=0.12,
                 trajectory_noise_scale=0.25),
    2: BotParams(reaction_delay=5, prediction_error=0.25, miss_probability=0.08,
                 move_range=0.75, jump_timing_error=3,
                 jump_jitter=2, angle_variance=0.3, hesitation_rate=0.08,
                 trajectory_noise_scale=0.18),
    3: BotParams(reaction_delay=3, prediction_error=0.15, miss_probability=0.04,
                 move_range=0.85, jump_timing_error=2,
                 jump_jitter=2, angle_variance=0.22, hesitation_rate=0.05,
                 trajectory_noise_scale=0.12),
    4: BotParams(reaction_delay=1, prediction_error=0.08, miss_probability=0.01,
                 move_range=0.95, jump_timing_error=1,
                 jump_jitter=1, angle_variance=0.14, hesitation_rate=0.02,
                 trajectory_noise_scale=0.07),
    5: BotParams(reaction_delay=0, prediction_error=0.03, miss_probability=0.0,
                 move_range=1.0,  jump_timing_error=0,
                 jump_jitter=1, angle_variance=0.08, hesitation_rate=0.01,
                 trajectory_noise_scale=0.04),
}


class RuleBasedBot:
    """Rule-based Pikachu Volleyball bot with configurable difficulty."""

    def __init__(self, level: int = 1) -> None:
        if level not in BOT_PARAMS:
            raise ValueError(f"Level must be 1-5, got {level}")
        self.level = level
        self.params = BOT_PARAMS[level]
        self._delay_counter: int = 0

    def get_action(self, state: GameState, *, is_player2: bool) -> PlayerInput:
        params = self.params

        # Miss probability — return no-op
        if random.random() < params.miss_probability:
            return PlayerInput(x_dir=0, y_dir=0, power_hit=False)

        # Reaction delay — skip first N frames each round
        if state.is_round_over:
            self._delay_counter = 0
        self._delay_counter += 1
        if self._delay_counter <= params.reaction_delay:
            return PlayerInput(x_dir=0, y_dir=0, power_hit=False)

        player = state.player2 if is_player2 else state.player1
        ball = state.ball

        # Predict ball intercept point (and keep frames-to-intercept for
        # distance-scaled noise below).
        target_x, frames_to_intercept = self._predict_intercept_x(state, is_player2)

        # Add prediction error noise — base + trajectory-distance-scaled.
        # Farther predictions (longer lookahead) get more uncertainty,
        # which breaks up the "same seed → same trajectory" feel.
        if params.prediction_error > 0:
            base_sigma = params.prediction_error * 50
            dist_sigma = params.trajectory_noise_scale * frames_to_intercept
            target_x += random.gauss(0, base_sigma + dist_sigma)

        # Position offset: stand slightly toward own wall so the ball
        # goes toward the opponent on collision (dx in collision gives vx).
        offset = PLAYER_HALF_LENGTH * 0.8
        if is_player2:
            target_x += offset  # shift right → ball goes left
        else:
            target_x -= offset  # shift left → ball goes right

        # Clamp to player's court side within move_range
        if is_player2:
            court_min = NET_PILLAR_X + NET_PILLAR_HALF_WIDTH + PLAYER_HALF_LENGTH
            court_max = GROUND_WIDTH - PLAYER_HALF_LENGTH
        else:
            court_min = PLAYER_HALF_LENGTH
            court_max = NET_PILLAR_X - NET_PILLAR_HALF_WIDTH - PLAYER_HALF_LENGTH

        court_center = (court_min + court_max) / 2
        court_half = (court_max - court_min) / 2
        max_move = court_half * params.move_range
        target_x = max(court_center - max_move, min(target_x, court_center + max_move))

        # Horizontal movement toward target (with occasional hesitation so
        # the bot doesn't track like a railgun).
        dx = target_x - player.x
        if abs(dx) > PLAYER_SPEED:
            x_dir = 1 if dx > 0 else -1
        else:
            x_dir = 0
        if params.hesitation_rate > 0 and random.random() < params.hesitation_rate:
            x_dir = 0

        # Jump decision — threshold gets a fresh uniform jitter each frame
        # so repeated identical game states don't always trigger jumps on
        # the same frame.
        y_dir = 0
        ball_on_my_side = (
            (is_player2 and ball.x >= NET_PILLAR_X)
            or (not is_player2 and ball.x <= NET_PILLAR_X)
        )
        ball_dist_x = abs(ball.x - player.x)

        if not player.is_jumping and ball_on_my_side:
            frames_to_ground = self._frames_to_y(
                ball.y, ball.vy, PLAYER_GROUND_Y - PLAYER_HALF_LENGTH
            )
            jump_threshold = 20 + params.jump_timing_error * 3
            if params.jump_jitter > 0:
                jump_threshold += random.randint(-params.jump_jitter, params.jump_jitter)
            if frames_to_ground <= jump_threshold and ball_dist_x < PLAYER_HALF_LENGTH * 5:
                y_dir = -1

        # Power hit — when jumping and ball is close. Instead of always
        # aiming straight at the opponent, randomize attack angle
        # (steep smash / flat drive / cross-court).
        power_hit = False
        if player.is_jumping:
            collision_dist = PLAYER_HALF_LENGTH + 20
            if (
                ball_dist_x < collision_dist * 2
                and abs(ball.y - player.y) < collision_dist * 2
            ):
                power_probability = max(0.2, self.level / 5.0)
                if random.random() < power_probability:
                    power_hit = True
                    # Default attack direction points at opponent.
                    default_x_dir = -1 if is_player2 else 1
                    x_dir = default_x_dir
                    # Angle variance: with p=angle_variance, pick a different
                    # angle (0 = straight down smash, or flipped for cross-court).
                    if random.random() < params.angle_variance:
                        x_dir = random.choice([0, default_x_dir, -default_x_dir])
                    # Y-direction variance: random.choice of 0 (flat) or -1
                    # (lob) alongside the default 0, so `vy = |vy| * y_dir * 2`
                    # in the engine produces different attack trajectories.
                    if random.random() < params.angle_variance:
                        y_dir = random.choice([-1, 0, 0])  # bias toward 0

        return PlayerInput(x_dir=x_dir, y_dir=y_dir, power_hit=power_hit)

    def _predict_intercept_x(
        self, state: GameState, is_player2: bool
    ) -> tuple[float, int]:
        """Predict where to stand to intercept the ball.

        Returns (intercept_x, frames_simulated). `frames_simulated` is used
        by the caller to scale prediction noise — longer lookaheads get
        proportionally more uncertainty.
        """
        ball = state.ball

        bx, by = float(ball.x), float(ball.y)
        bvx, bvy = float(ball.vx), float(ball.vy)

        # Simulate ball trajectory
        best_x = bx
        frames = 0
        for i in range(120):
            bvy += GRAVITY
            bx += bvx
            by += bvy
            frames = i + 1

            # Wall bounces
            if bx <= 20:
                bx = 20
                bvx = abs(bvx)
            elif bx >= GROUND_WIDTH - 20:
                bx = GROUND_WIDTH - 20
                bvx = -abs(bvx)

            # Net collision
            if abs(bx - NET_PILLAR_X) < NET_PILLAR_HALF_WIDTH + 20 and by > 156:
                if bvx > 0:
                    bvx = -abs(bvx)
                elif bvx < 0:
                    bvx = abs(bvx)

            # Check if ball is on my side and at reachable height
            on_my_side = (is_player2 and bx >= NET_PILLAR_X) or (not is_player2 and bx <= NET_PILLAR_X)
            if on_my_side and by >= PLAYER_GROUND_Y - 100:
                best_x = bx
                break

            if by >= BALL_GROUND_Y:
                best_x = bx
                break

        return best_x, frames

    def _frames_to_y(self, y: float, vy: float, target_y: float) -> int:
        """Estimate frames until ball reaches target_y."""
        for i in range(200):
            vy += GRAVITY
            y += vy
            if y >= target_y:
                return i + 1
        return 200
