"""Pikachu Volleyball game engine — pure Python, no I/O."""

from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple

from backend.game.constants import (
    BALL_GROUND_Y,
    BALL_INIT_Y_VELOCITY,
    BALL_RADIUS,
    GRAVITY,
    GROUND_WIDTH,
    NET_PILLAR_HALF_WIDTH,
    NET_PILLAR_TOP_Y,
    NET_PILLAR_X,
    PLAYER_GROUND_Y,
    PLAYER_HALF_LENGTH,
    PLAYER_JUMP_VELOCITY,
    PLAYER_SPEED,
    MAX_SCORE,
)


@dataclass
class PlayerState:
    x: int
    y: int
    vx: int = 0
    vy: int = 0
    is_jumping: bool = False
    is_diving: bool = False
    is_power_hitting: bool = False
    lying_down_duration: int = 0


@dataclass
class BallState:
    x: int
    y: int
    vx: int = 0
    vy: int = 0
    rotation: int = 0
    punch_effect_x: int = 0
    punch_effect_y: int = 0


@dataclass
class GameState:
    player1: PlayerState
    player2: PlayerState
    ball: BallState
    score1: int = 0
    score2: int = 0
    serving_player: int = 1
    is_round_over: bool = False
    frame: int = 0


class PlayerInput(NamedTuple):
    x_dir: int  # -1, 0, 1
    y_dir: int  # -1, 0, 1
    power_hit: bool


class PikachuVolleyball:
    """Deterministic Pikachu Volleyball game engine."""

    def __init__(self) -> None:
        self._state: GameState = self._create_initial_state()

    def _create_initial_state(self, serving_player: int = 1) -> GameState:
        p1 = PlayerState(x=108, y=PLAYER_GROUND_Y)
        p2 = PlayerState(x=324, y=PLAYER_GROUND_Y)
        if serving_player == 1:
            ball = BallState(x=108, y=100, vy=BALL_INIT_Y_VELOCITY)
        else:
            ball = BallState(x=324, y=100, vy=BALL_INIT_Y_VELOCITY)
        return GameState(
            player1=p1,
            player2=p2,
            ball=ball,
            serving_player=serving_player,
        )

    def reset(self) -> GameState:
        self._state = self._create_initial_state()
        return self._state

    def step(self, p1_input: PlayerInput, p2_input: PlayerInput) -> GameState:
        state = self._state
        state.is_round_over = False
        state.frame += 1

        self._update_player(state.player1, p1_input, is_player2=False)
        self._update_player(state.player2, p2_input, is_player2=True)
        self._update_ball(state)

        # Check scoring before collisions — if ball hit ground, round is over
        if self._check_scoring(state):
            return state

        self._check_ball_player_collision(state.ball, state.player1, p1_input)
        self._check_ball_player_collision(state.ball, state.player2, p2_input)
        self._check_ball_net_collision(state.ball)

        return state

    def _update_player(
        self, player: PlayerState, inp: PlayerInput, *, is_player2: bool
    ) -> None:
        if player.lying_down_duration > 0:
            player.lying_down_duration -= 1
            if player.lying_down_duration <= 0:
                player.lying_down_duration = 0
            return

        # Horizontal movement
        if not player.is_jumping and not player.is_diving:
            player.vx = inp.x_dir * PLAYER_SPEED
        player.x += player.vx

        # Clamp to court half
        if is_player2:
            left_bound = NET_PILLAR_X + NET_PILLAR_HALF_WIDTH + PLAYER_HALF_LENGTH
            right_bound = GROUND_WIDTH - PLAYER_HALF_LENGTH
            player.x = max(left_bound, min(player.x, right_bound))
        else:
            left_bound = PLAYER_HALF_LENGTH
            right_bound = NET_PILLAR_X - NET_PILLAR_HALF_WIDTH - PLAYER_HALF_LENGTH
            player.x = max(left_bound, min(player.x, right_bound))

        # Jump
        if not player.is_jumping and not player.is_diving and inp.y_dir == -1:
            player.vy = PLAYER_JUMP_VELOCITY
            player.is_jumping = True

        # Apply gravity when airborne
        if player.is_jumping or player.is_diving:
            player.vy += GRAVITY
            player.y += player.vy
            if player.y >= PLAYER_GROUND_Y:
                player.y = PLAYER_GROUND_Y
                player.vy = 0
                player.vx = 0
                player.is_jumping = False
                if player.is_diving:
                    player.is_diving = False
                    player.lying_down_duration = 30

        # Power hit state
        player.is_power_hitting = inp.power_hit and player.is_jumping

    def _update_ball(self, state: GameState) -> None:
        ball = state.ball
        ball.vy += GRAVITY
        ball.x += ball.vx + ball.punch_effect_x
        ball.y += ball.vy + ball.punch_effect_y

        # Decay punch effect
        if ball.punch_effect_x != 0:
            ball.punch_effect_x = int(ball.punch_effect_x * 0.7)
        if ball.punch_effect_y != 0:
            ball.punch_effect_y = int(ball.punch_effect_y * 0.7)

        # Horizontal boundary
        if ball.x <= BALL_RADIUS:
            ball.x = BALL_RADIUS
            ball.vx = abs(ball.vx)
        elif ball.x >= GROUND_WIDTH - BALL_RADIUS:
            ball.x = GROUND_WIDTH - BALL_RADIUS
            ball.vx = -abs(ball.vx)

        ball.rotation = (ball.rotation + ball.vx) % 360

    def _check_ball_player_collision(
        self, ball: BallState, player: PlayerState, inp: PlayerInput
    ) -> None:
        dx = abs(ball.x - player.x)
        dy = abs(ball.y - player.y)

        collision_dist = PLAYER_HALF_LENGTH + BALL_RADIUS
        if dx <= collision_dist and dy <= collision_dist:
            # Direction from player to ball
            dir_x = 1 if ball.x >= player.x else -1

            # Base collision response
            ball.vx = (dx // 3) * dir_x if dx > 0 else dir_x * 2
            ball.vy = min(ball.vy, -15)

            # Power hit
            if player.is_power_hitting or inp.power_hit:
                x_component = abs(inp.x_dir) + 1
                ball.vx = x_component * 10 * dir_x
                ball.vy = max(abs(ball.vy), 15) * (inp.y_dir if inp.y_dir != 0 else -1) * 2
                ball.punch_effect_x = ball.vx // 2
                ball.punch_effect_y = ball.vy // 4

            # Push ball out of player
            if dy <= collision_dist:
                ball.y = player.y - collision_dist - 1

    def _check_ball_net_collision(self, ball: BallState) -> None:
        if (
            abs(ball.x - NET_PILLAR_X) < NET_PILLAR_HALF_WIDTH + BALL_RADIUS
            and ball.y > NET_PILLAR_TOP_Y - BALL_RADIUS
        ):
            # Determine bounce direction based on velocity (moving into net)
            if ball.vx > 0:
                # Moving right → bounce left
                ball.x = NET_PILLAR_X - NET_PILLAR_HALF_WIDTH - BALL_RADIUS
                ball.vx = -abs(ball.vx)
            elif ball.vx < 0:
                # Moving left → bounce right
                ball.x = NET_PILLAR_X + NET_PILLAR_HALF_WIDTH + BALL_RADIUS
                ball.vx = abs(ball.vx)
            else:
                # No horizontal movement — push based on position
                if ball.x < NET_PILLAR_X:
                    ball.x = NET_PILLAR_X - NET_PILLAR_HALF_WIDTH - BALL_RADIUS
                else:
                    ball.x = NET_PILLAR_X + NET_PILLAR_HALF_WIDTH + BALL_RADIUS

            # Top collision
            if ball.y < NET_PILLAR_TOP_Y:
                ball.y = NET_PILLAR_TOP_Y - BALL_RADIUS
                ball.vy = -abs(ball.vy)

    def _check_scoring(self, state: GameState) -> bool:
        ball = state.ball
        if ball.y >= BALL_GROUND_Y:
            state.is_round_over = True
            if ball.x < NET_PILLAR_X:
                state.score2 += 1
                state.serving_player = 2
            else:
                state.score1 += 1
                state.serving_player = 1

            # Reset for next round if game not over
            if state.score1 < MAX_SCORE and state.score2 < MAX_SCORE:
                serving = state.serving_player
                s1, s2, frame = state.score1, state.score2, state.frame
                new = self._create_initial_state(serving_player=serving)
                new.score1 = s1
                new.score2 = s2
                new.frame = frame
                new.is_round_over = True
                self._state = new
            return True
        return False
