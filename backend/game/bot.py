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
    prediction_error: float
    miss_probability: float
    move_range: float
    jump_timing_error: int


BOT_PARAMS: dict[int, BotParams] = {
    1: BotParams(reaction_delay=8, prediction_error=0.4, miss_probability=0.15, move_range=0.6, jump_timing_error=4),
    2: BotParams(reaction_delay=5, prediction_error=0.25, miss_probability=0.08, move_range=0.75, jump_timing_error=3),
    3: BotParams(reaction_delay=3, prediction_error=0.15, miss_probability=0.04, move_range=0.85, jump_timing_error=2),
    4: BotParams(reaction_delay=1, prediction_error=0.05, miss_probability=0.01, move_range=0.95, jump_timing_error=1),
    5: BotParams(reaction_delay=0, prediction_error=0.0, miss_probability=0.0, move_range=1.0, jump_timing_error=0),
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

        # Predict ball intercept point
        target_x = self._predict_intercept_x(state, is_player2)

        # Add prediction error noise
        if params.prediction_error > 0:
            noise = random.gauss(0, params.prediction_error * 50)
            target_x += noise

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

        # Horizontal movement toward target
        dx = target_x - player.x
        if abs(dx) > PLAYER_SPEED:
            x_dir = 1 if dx > 0 else -1
        else:
            x_dir = 0

        # Jump decision
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
            if frames_to_ground <= jump_threshold and ball_dist_x < PLAYER_HALF_LENGTH * 5:
                y_dir = -1

        # Power hit — when jumping and ball is close, aim toward opponent
        power_hit = False
        if player.is_jumping:
            collision_dist = PLAYER_HALF_LENGTH + 20
            if (
                ball_dist_x < collision_dist * 2
                and abs(ball.y - player.y) < collision_dist * 2
            ):
                power_probability = self.level / 5.0
                if random.random() < power_probability:
                    power_hit = True
                    x_dir = -1 if is_player2 else 1  # aim toward opponent

        return PlayerInput(x_dir=x_dir, y_dir=y_dir, power_hit=power_hit)

    def _predict_intercept_x(self, state: GameState, is_player2: bool) -> float:
        """Predict where to stand to intercept the ball."""
        ball = state.ball

        bx, by = float(ball.x), float(ball.y)
        bvx, bvy = float(ball.vx), float(ball.vy)

        # Simulate ball trajectory
        best_x = bx
        for _ in range(120):
            bvy += GRAVITY
            bx += bvx
            by += bvy

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

        return best_x

    def _frames_to_y(self, y: float, vy: float, target_y: float) -> int:
        """Estimate frames until ball reaches target_y."""
        for i in range(200):
            vy += GRAVITY
            y += vy
            if y >= target_y:
                return i + 1
        return 200
