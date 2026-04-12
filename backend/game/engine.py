"""Pikachu Volleyball game engine — pure Python, no I/O.

Physics ported from the original game source
(gorisanson/pikachu-volleyball: src/resources/js/physics.js).
Function-level comments reference the original JS function name.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple

from backend.game.constants import (
    BALL_GROUND_Y,
    BALL_INIT_Y_VELOCITY,
    BALL_MIN_REFLECT_VY_ABS,
    BALL_PLAYER_COLLISION_DIST,
    BALL_RADIUS,
    BALL_SERVE_X_P1,
    BALL_SERVE_X_P2,
    BALL_SERVE_Y,
    GRAVITY,
    GROUND_WIDTH,
    LYING_DOWN_DURATION,
    MAX_SCORE,
    NET_PILLAR_HALF_WIDTH,
    NET_PILLAR_TOP_BOTTOM_Y,
    NET_PILLAR_TOP_Y,
    NET_PILLAR_X,
    PLAYER_DIVE_SPEED,
    PLAYER_DIVE_VELOCITY,
    PLAYER_GROUND_Y,
    PLAYER_HALF_LENGTH,
    PLAYER_INIT_X_P1,
    PLAYER_INIT_X_P2,
    PLAYER_JUMP_VELOCITY,
    PLAYER_SPEED,
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
    diving_direction: int = 0  # -1 left, 0 none, 1 right
    # Per original physics.js (Player.isCollisionWithBallHappened, 0xBC):
    # Prevents collision from re-firing while the ball is still within the
    # 32px box across frames. Cleared when the ball leaves the box.
    is_collision_with_ball_happened: bool = False


@dataclass
class BallState:
    x: int
    y: int
    vx: int = 0
    vy: int = 0
    rotation: int = 0
    # punch_effect_x/y are graphic markers only (per original).
    # They are NOT added to position — ball movement uses (vx, vy) only.
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
    # Frames since the ball last crossed the net. Used as a safety valve
    # against infinite self-toss rallies — see `PikachuVolleyball.step`.
    # Resets to 0 on net crossing and at round start.
    frames_since_net_crossing: int = 0
    # True when this round ended because `frames_since_net_crossing` exceeded
    # `PikachuVolleyball.RALLY_MAX_FRAMES` (and NOT because the ball grounded).
    # The concede is awarded to the side currently holding the ball. Consumers
    # can distinguish timeout concedes from normal concedes via this flag.
    round_ended_by_timeout: bool = False


class PlayerInput(NamedTuple):
    x_dir: int  # -1, 0, 1
    y_dir: int  # -1, 0, 1
    power_hit: bool


class PikachuVolleyball:
    """Deterministic Pikachu Volleyball engine, port of original physics.js."""

    # Safety valve: force-end the round if the ball hasn't crossed the net
    # for this many consecutive frames. Prevents infinite self-toss loops
    # from wedging the match (e.g., a weak RL policy bouncing the ball to
    # itself forever on its own court). NOT present in the original game —
    # added here because non-interactive play (RL training, replays,
    # headless bot-vs-bot) has no user available to forfeit the round.
    RALLY_MAX_FRAMES: int = 600

    def __init__(self) -> None:
        self._state: GameState = self._create_initial_state()
        self._prev_ball_x: float = float(self._state.ball.x)

    def _create_initial_state(self, serving_player: int = 1) -> GameState:
        # Original: player1.x = 36, player2.x = GROUND_WIDTH - 36 (= 396)
        p1 = PlayerState(x=PLAYER_INIT_X_P1, y=PLAYER_GROUND_Y)
        p2 = PlayerState(x=PLAYER_INIT_X_P2, y=PLAYER_GROUND_Y)
        # Original: ball.x = 56 (p1 serve) or GROUND_WIDTH - 56 = 376, y = 0, vy = 1
        if serving_player == 1:
            ball = BallState(x=BALL_SERVE_X_P1, y=BALL_SERVE_Y, vy=BALL_INIT_Y_VELOCITY)
        else:
            ball = BallState(x=BALL_SERVE_X_P2, y=BALL_SERVE_Y, vy=BALL_INIT_Y_VELOCITY)
        return GameState(
            player1=p1,
            player2=p2,
            ball=ball,
            serving_player=serving_player,
        )

    def reset(self) -> GameState:
        self._state = self._create_initial_state()
        self._prev_ball_x = float(self._state.ball.x)
        return self._state

    def step(self, p1_input: PlayerInput, p2_input: PlayerInput) -> GameState:
        """Advance one frame.

        Order matches original physicsEngine (FUN_00403dd0):
          1. processCollisionBetweenBallAndWorldAndSetBallPosition (FUN_00402dc0)
             — ball boundary / ceiling / net / ground, then move + gravity last.
          2. processPlayerMovementAndSetPlayerPosition for both players (FUN_00401fc0).
          3. isCollisionBetweenBallAndPlayerHappened + processCollisionBetweenBallAndPlayer
             — detect and set ball velocity for next frame.

        After the original-faithful update, one extension runs:
          4. Rally-timeout safety valve (not in original). If the ball has
             not crossed the net for RALLY_MAX_FRAMES frames, force-end the
             round; the side currently holding the ball concedes the point.
        """
        state = self._state
        state.is_round_over = False
        state.round_ended_by_timeout = False
        state.frame += 1
        prev_ball_x = self._prev_ball_x

        grounded = self._update_ball_and_world(state.ball)
        if grounded:
            self._handle_scoring(state)
            # GameState may have been replaced by a fresh serving state.
            self._prev_ball_x = float(self._state.ball.x)
            return self._state

        self._update_player(state.player1, p1_input, is_player2=False)
        self._update_player(state.player2, p2_input, is_player2=True)

        self._check_ball_player_collision(state.ball, state.player1, p1_input)
        self._check_ball_player_collision(state.ball, state.player2, p2_input)

        # Rotation (graphic) — original uses fineRotation; we approximate with degrees
        state.ball.rotation = (state.ball.rotation + state.ball.vx) % 360

        # Net-crossing counter (extension — safety valve, not in original).
        now_ball_x = float(state.ball.x)
        crossed = (
            (prev_ball_x <= NET_PILLAR_X < now_ball_x)
            or (prev_ball_x >= NET_PILLAR_X > now_ball_x)
        )
        if crossed:
            state.frames_since_net_crossing = 0
        else:
            state.frames_since_net_crossing += 1

        if state.frames_since_net_crossing >= self.RALLY_MAX_FRAMES:
            self._handle_rally_timeout(state)
            # _handle_rally_timeout may swap in a fresh serving state.
            self._prev_ball_x = float(self._state.ball.x)
            return self._state

        self._prev_ball_x = now_ball_x
        return state

    # ------------------------------------------------------------------
    # Ball world update — port of processCollisionBetweenBallAndWorldAndSetBallPosition
    # ------------------------------------------------------------------
    def _update_ball_and_world(self, ball: BallState) -> bool:
        """Handle ball world collisions and move the ball.

        Returns True if the ball touched the ground this frame.
        Mirrors the original function exactly, including its known asymmetry
        for the right wall (futureBallX > GROUND_WIDTH, not GROUND_WIDTH - BALL_RADIUS).
        """
        future_x = ball.x + ball.vx
        # Left-right world bounds — original is asymmetric on purpose.
        # Known quirk documented in original source.
        if future_x < BALL_RADIUS or future_x > GROUND_WIDTH:
            ball.vx = -ball.vx

        future_y = ball.y + ball.vy
        # Ceiling — if ball would go above top of world, force downward.
        if future_y < 0:
            ball.vy = 1

        # Net collision — original splits top-of-pillar vs side-of-pillar.
        if (
            abs(ball.x - NET_PILLAR_X) < NET_PILLAR_HALF_WIDTH
            and ball.y > NET_PILLAR_TOP_Y
        ):
            if ball.y <= NET_PILLAR_TOP_BOTTOM_Y:
                # On top of net pillar — bounce up if moving down.
                if ball.vy > 0:
                    ball.vy = -ball.vy
            else:
                # Side of net pillar — reflect horizontally away from net.
                if ball.x < NET_PILLAR_X:
                    ball.vx = -abs(ball.vx)
                else:
                    ball.vx = abs(ball.vx)

        future_y = ball.y + ball.vy
        if future_y > BALL_GROUND_Y:
            # Ball touches ground — bounce + record punch-effect markers.
            ball.vy = -ball.vy
            ball.punch_effect_x = ball.x
            ball.y = BALL_GROUND_Y
            ball.punch_effect_y = BALL_GROUND_Y + BALL_RADIUS
            return True

        # Move + gravity applied LAST (matches original ordering).
        ball.y = future_y
        ball.x = ball.x + ball.vx
        ball.vy += GRAVITY
        return False

    # ------------------------------------------------------------------
    # Player update — port of processPlayerMovementAndSetPlayerPosition
    # ------------------------------------------------------------------
    def _update_player(
        self, player: PlayerState, inp: PlayerInput, *, is_player2: bool
    ) -> None:
        # Lying down after dive — frozen for LYING_DOWN_DURATION frames.
        if player.lying_down_duration > 0:
            player.lying_down_duration -= 1
            if player.lying_down_duration <= 0:
                player.lying_down_duration = 0
            return

        # Horizontal velocity
        if player.is_diving:
            vel_x = player.diving_direction * PLAYER_DIVE_SPEED
        else:
            vel_x = inp.x_dir * PLAYER_SPEED
        player.vx = vel_x
        player.x += vel_x

        # Clamp to court half — original allows up to GROUND_HALF_WIDTH ± PLAYER_HALF_LENGTH.
        if is_player2:
            left_bound = NET_PILLAR_X + PLAYER_HALF_LENGTH
            right_bound = GROUND_WIDTH - PLAYER_HALF_LENGTH
        else:
            left_bound = PLAYER_HALF_LENGTH
            right_bound = NET_PILLAR_X - PLAYER_HALF_LENGTH
        player.x = max(left_bound, min(player.x, right_bound))

        # Jump — only when grounded and not diving.
        if (
            not player.is_jumping
            and not player.is_diving
            and inp.y_dir == -1
            and player.y == PLAYER_GROUND_Y
        ):
            player.vy = PLAYER_JUMP_VELOCITY
            player.is_jumping = True

        # Gravity + landing
        if player.is_jumping or player.is_diving:
            player.y += player.vy
            if player.y < PLAYER_GROUND_Y:
                player.vy += GRAVITY
            elif player.y >= PLAYER_GROUND_Y:
                player.y = PLAYER_GROUND_Y
                player.vy = 0
                if player.is_diving:
                    player.is_diving = False
                    player.diving_direction = 0
                    player.lying_down_duration = LYING_DOWN_DURATION
                player.is_jumping = False

        # Dive trigger — power hit while grounded + xDir != 0 starts a dive.
        if (
            inp.power_hit
            and not player.is_jumping
            and not player.is_diving
            and player.y == PLAYER_GROUND_Y
            and inp.x_dir != 0
        ):
            player.is_diving = True
            player.diving_direction = inp.x_dir
            player.vy = PLAYER_DIVE_VELOCITY

        # Power-hit flag (true when jumping + power_hit pressed).
        player.is_power_hitting = inp.power_hit and player.is_jumping

    # ------------------------------------------------------------------
    # Ball-player collision — port of
    # isCollisionBetweenBallAndPlayerHappened + processCollisionBetweenBallAndPlayer
    # ------------------------------------------------------------------
    def _check_ball_player_collision(
        self, ball: BallState, player: PlayerState, inp: PlayerInput
    ) -> None:
        """Detect collision and set ball velocity for next frame.

        Detection distance matches original exactly: PLAYER_HALF_LENGTH (32px)
        on both x and y axes. Collision does NOT move the ball; it only updates
        (vx, vy) which take effect on the next _update_ball_and_world call.

        Per original (physicsEngine, FUN_00403dd0): if the ball stays within
        the 32px box across multiple frames, the collision is only processed
        on the FIRST frame. The flag resets when the ball exits the box.
        Without this gate, a slowly moving / tangential ball would retrigger
        the velocity reflection every frame and produce chaotic physics.
        """
        dx_signed = ball.x - player.x
        dy_signed = ball.y - player.y
        in_box = (
            abs(dx_signed) <= BALL_PLAYER_COLLISION_DIST
            and abs(dy_signed) <= BALL_PLAYER_COLLISION_DIST
        )
        if not in_box:
            player.is_collision_with_ball_happened = False
            return
        if player.is_collision_with_ball_happened:
            # Still in the box from a prior collision — don't re-fire.
            return
        player.is_collision_with_ball_happened = True

        # Base horizontal velocity — signed integer division by 3.
        if dx_signed < 0:
            ball.vx = -(abs(dx_signed) // 3)
        elif dx_signed > 0:
            ball.vx = abs(dx_signed) // 3
        else:
            # Original picks rand() % 3 - 1 (= -1/0/1); we pick 0 for determinism.
            ball.vx = 0

        # Base vertical velocity — reflect and clamp magnitude to 15.
        # Original: vy = -|vy|; if |vy| < 15 then vy = -15.
        abs_vy = abs(ball.vy)
        ball.vy = -abs_vy if abs_vy >= BALL_MIN_REFLECT_VY_ABS else -BALL_MIN_REFLECT_VY_ABS

        # Power hit — overrides vx/vy. Direction determined by which half of
        # the court the ball is in, NOT by player side.
        if inp.power_hit and player.is_jumping:
            x_magnitude = (abs(inp.x_dir) + 1) * 10
            if ball.x < NET_PILLAR_X:
                ball.vx = x_magnitude
            else:
                ball.vx = -x_magnitude
            # Original: vy = |vy| * yDirection * 2. If yDir == 0 this zeros vy.
            ball.vy = abs(ball.vy) * inp.y_dir * 2
            # Record graphic markers only — do NOT add to position.
            ball.punch_effect_x = ball.x
            ball.punch_effect_y = ball.y

    # ------------------------------------------------------------------
    # Scoring — not in original engine (it returns isBallTouchingGround
    # and caller handles scoring). Preserved from our earlier implementation.
    # ------------------------------------------------------------------
    def _handle_scoring(self, state: GameState) -> None:
        ball = state.ball
        state.is_round_over = True
        if ball.x < NET_PILLAR_X:
            state.score2 += 1
            state.serving_player = 2
        else:
            state.score1 += 1
            state.serving_player = 1

        if state.score1 < MAX_SCORE and state.score2 < MAX_SCORE:
            serving = state.serving_player
            s1, s2, frame = state.score1, state.score2, state.frame
            new = self._create_initial_state(serving_player=serving)
            new.score1 = s1
            new.score2 = s2
            new.frame = frame
            new.is_round_over = True
            self._state = new

    def _handle_rally_timeout(self, state: GameState) -> None:
        """Force-end the round when the rally stalls past RALLY_MAX_FRAMES.

        Concede goes to the side currently holding the ball (ball.x side).
        Matches `_handle_scoring` semantics so downstream consumers treat a
        timeout like a grounded-ball concede, except `round_ended_by_timeout`
        is set so RL / UI layers can distinguish the two.
        """
        ball = state.ball
        state.is_round_over = True
        state.round_ended_by_timeout = True
        if ball.x < NET_PILLAR_X:
            state.score2 += 1
            state.serving_player = 2
        else:
            state.score1 += 1
            state.serving_player = 1

        if state.score1 < MAX_SCORE and state.score2 < MAX_SCORE:
            serving = state.serving_player
            s1, s2, frame = state.score1, state.score2, state.frame
            new = self._create_initial_state(serving_player=serving)
            new.score1 = s1
            new.score2 = s2
            new.frame = frame
            new.is_round_over = True
            new.round_ended_by_timeout = True
            self._state = new
