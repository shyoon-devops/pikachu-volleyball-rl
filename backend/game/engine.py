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
    # punch_effect_x/y/radius are graphic markers only (per original).
    # They are NOT added to position — ball movement uses (vx, vy) only.
    # Radius is SET to BALL_RADIUS on each trigger (ground touch or
    # power-hit collision) and decays by 2 per frame thereafter, matching
    # the original's render-loop shrink (view.js:502-507). Shrinking is
    # centralised in the engine so FE renderers just draw whatever
    # radius the server reports and don't need their own animation state.
    punch_effect_x: int = 0
    punch_effect_y: int = 0
    punch_effect_radius: int = 0
    # True on frames where the most recent ball–player collision was a
    # power hit (player was jumping + power_hit pressed). Drives the
    # hyper-ball / trail sprite effect in the original view.js:513 and
    # is the single-frame signal FE needs to render "강타" visually.
    # Semantics match original physics.js: set true in the power-hit
    # branch of processCollisionBetweenBallAndPlayer, set false in any
    # other collision. Persists between collisions until flipped.
    is_power_hit: bool = False


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
    # Countdown of remaining "freeze" frames after a scoring event. While
    # this is > 0 the engine holds the grounded-ball state unchanged so that
    # viewers (and replay FE) get to see the final scoring moment. Expires
    # into a fresh serving state, or stays at 0 when the match has ended.
    # Mirrors the original game's slow-motion + fade-out pause after each
    # round (pikavolley.js: SLOW_MOTION_FRAMES_NUM + afterEndOfRound).
    post_score_freeze_frames: int = 0


class PlayerInput(NamedTuple):
    x_dir: int  # -1, 0, 1
    y_dir: int  # -1, 0, 1
    power_hit: bool


class PikachuVolleyball:
    """Deterministic Pikachu Volleyball game engine."""

    # Safety valve: force-end the round if the ball hasn't crossed the net
    # for this many consecutive frames. Prevents infinite self-toss loops
    # from wedging the match (e.g., a weak RL policy bouncing the ball to
    # itself forever on its own court). NOT present in the original game —
    # added here because non-interactive play (RL training, replays,
    # headless bot-vs-bot) has no user available to forfeit the round.
    RALLY_MAX_FRAMES: int = 600

    # Freeze-frame duration after a scoring event. The grounded ball state
    # is held for this many frames so viewers can see the scoring moment
    # (the user-reported "14→15 득점 순간 안 보이는" bug). ~0.33s at 60fps,
    # roughly matches the original game's SLOW_MOTION_FRAMES_NUM (6 slow
    # frames ≈ 14 real frames) + afterEndOfRound (5 frames) combined pause.
    POST_SCORE_FREEZE_FRAMES: int = 20

    def __init__(self, *, post_score_freeze: bool = True) -> None:
        """Create a new engine instance.

        post_score_freeze: when True (default), every scoring event triggers
            a POST_SCORE_FREEZE_FRAMES-long hold of the grounded-ball state
            before the next serve. Disable for RL training where the agent
            shouldn't waste steps on no-op frames; the training env uses
            `post_score_freeze=False` to keep legacy immediate-reset
            behavior. Headless replay rendering, human/bot playback, and
            the diagnostic script leave it enabled.
        """
        self._post_score_freeze: bool = post_score_freeze
        self._state: GameState = self._create_initial_state()
        self._prev_ball_x: float = float(self._state.ball.x)

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

        Post-score freeze (when enabled): if the previous frame ended the
        round, subsequent calls tick down `post_score_freeze_frames` without
        advancing physics. When the counter reaches zero the engine either
        swaps in a fresh serving state (match ongoing) or holds the final
        state forever (match ended — score already at MAX_SCORE).
        """
        state = self._state

        # Decay the graphic punch-effect radius every frame (mirrors
        # view.js:502-507 in the original where the client decremented by
        # 2 per render tick). Centralising the shrink in the engine keeps
        # FE renderers stateless for this effect. Match-over guard below
        # returns early — the decay still runs so any lingering punch
        # effect from the final ground touch fades cleanly.
        if state.ball.punch_effect_radius > 0:
            state.ball.punch_effect_radius = max(
                0, state.ball.punch_effect_radius - 2
            )

        # Match-over guard. Once either player has reached MAX_SCORE the
        # engine refuses to advance physics — this preserves the final
        # grounded-ball scene for the replay viewer and makes repeated
        # step() calls after termination a no-op (same contract the
        # original game enforces via its `gameEnd` state).
        if state.score1 >= MAX_SCORE or state.score2 >= MAX_SCORE:
            state.is_round_over = True
            return state

        # Freeze-frame pass-through. Runs BEFORE the per-frame clearing of
        # round-over flags so viewers see `is_round_over=True` for the whole
        # freeze window. Physics / inputs are intentionally ignored; the
        # grounded ball position stays pinned until the hold ends.
        if state.post_score_freeze_frames > 0:
            state.post_score_freeze_frames -= 1
            state.frame += 1
            if (
                state.post_score_freeze_frames == 0
                and state.score1 < MAX_SCORE
                and state.score2 < MAX_SCORE
            ):
                serving = state.serving_player
                s1, s2, frame = state.score1, state.score2, state.frame
                new = self._create_initial_state(serving_player=serving)
                new.score1 = s1
                new.score2 = s2
                new.frame = frame
                # new.is_round_over / round_ended_by_timeout default to False.
                self._state = new
                self._prev_ball_x = float(new.ball.x)
                return new
            return state

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
        self._update_ball(state)

        # Check scoring before collisions — if ball hit ground, round is over
        if self._check_scoring(state):
            return state

        self._check_ball_player_collision(state.ball, state.player1, p1_input)
        self._check_ball_player_collision(state.ball, state.player2, p2_input)
        self._check_ball_net_collision(state.ball)

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
            # Matches original physics.js:472-478: radius starts at
            # BALL_RADIUS; FE / engine shrink decays it back to 0.
            ball.vy = -ball.vy
            ball.punch_effect_x = ball.x
            ball.y = BALL_GROUND_Y
            ball.punch_effect_y = BALL_GROUND_Y + BALL_RADIUS
            ball.punch_effect_radius = BALL_RADIUS
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
                ball.vx = -x_magnitude
            # Original: vy = |vy| * yDirection * 2. If yDir == 0 this zeros vy.
            ball.vy = abs(ball.vy) * inp.y_dir * 2
            # Record graphic markers only — do NOT add to position.
            # Matches physics.js:715-719 — the white radial "smash" ring
            # is triggered at BALL_RADIUS and decays each frame.
            ball.punch_effect_x = ball.x
            ball.punch_effect_y = ball.y
            ball.punch_effect_radius = BALL_RADIUS
            # Flag this collision as a power hit so FE can render the
            # hyper-ball / trail sprite (original view.js:513).
            ball.is_power_hit = True
        else:
            # Non-power collision — clear the flag so the trail stops
            # (original physics.js:727).
            ball.is_power_hit = False

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

        if self._post_score_freeze:
            # Freeze-frame path: hold the grounded-ball state for
            # POST_SCORE_FREEZE_FRAMES. The next-serve swap happens in
            # step() when the counter expires (or never, if the match
            # just ended). Do NOT swap _state here.
            state.post_score_freeze_frames = self.POST_SCORE_FREEZE_FRAMES
            return

        # Legacy immediate-reset path (RL training env opts out of freeze
        # so the agent isn't forced to no-op during the hold).
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

        if self._post_score_freeze:
            # See _handle_scoring for rationale. The freeze pass-through
            # in step() will preserve `round_ended_by_timeout=True` for the
            # whole hold, then swap in a fresh serving state on expiry.
            state.post_score_freeze_frames = self.POST_SCORE_FREEZE_FRAMES
            return

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
