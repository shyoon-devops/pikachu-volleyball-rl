"""Pikachu Volleyball game engine — pure Python port of physics.js.

Physics ported frame-accurately from the original game source
(gorisanson/pikachu-volleyball: src/resources/js/physics.js, MIT-licensed).
Function-level comments reference the original JS function name.

This module implements ONLY the physics engine equivalent of physics.js.
The pikavolley.js state machine (intro / menu / startOfNewGame / round /
gameEnd / afterEndOfRound etc.) is layered on top via this module's scoring
wrapper and is being progressively aligned with the original — see commit
`port(view): gameEnd 211f intro 복귀 플로우`.

Design notes:
  * Back-compat flags (``PlayerState.is_jumping`` etc.) are kept as derived
    views of ``PlayerState.state`` so existing consumers (bot.py, env.py)
    keep working. New code should read ``state`` directly.
  * Stochastic decisions (the original's ``rand() % 3`` zero-velocity
    tiebreak in ball-player collision; ``rand() % 5`` computer boldness)
    go through ``self._rand`` so the whole engine can be seeded for
    deterministic golden tests.
  * Integer ops use ``_trunc_div`` where the original JS used ``(a / b) | 0``;
    Python ``//`` floors toward ``-inf`` and diverges on negatives.
"""

from __future__ import annotations

import random
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

# Matches INFINITE_LOOP_LIMIT in physics.js — safety cap on the two
# trajectory-simulation loops (expected-landing-point and its power-hit
# variant). The original JS has the same cap for the same reason.
INFINITE_LOOP_LIMIT: int = 1000


def _trunc_div(a: int | float, b: int | float) -> int:
    """JS-style truncating integer division matching ``(a / b) | 0``.

    Python ``//`` floors (``-5 // 2 == -3``); the original JS bitwise ``| 0``
    truncates toward zero (``(-5 / 2) | 0 == -2``). Several physics paths
    (``fine_rotation`` advance, ball-player collision base vx, expected-
    landing-point trajectory) need the truncating semantics to produce the
    same frame sequence as the original.
    """
    return int(a / b)


@dataclass
class PlayerState:
    """Port of physics.js ``Player``.

    Internal source of truth is ``state`` (0-6, matches original Player.state
    at offset 0xC0). Back-compat boolean flags (``is_jumping``, ``is_diving``,
    ``is_power_hitting``, ``lying_down_duration``) are kept in sync via
    :meth:`sync_derived_flags` and exist solely so bot.py / env.py and older
    tests can keep reading the engine without a breaking API change.
    """

    x: int
    y: int
    vx: int = 0
    vy: int = 0
    # 0: normal, 1: jumping, 2: jumping_and_power_hitting, 3: diving,
    # 4: lying_down_after_diving, 5: win, 6: lost — matches physics.js
    # Player.state at 0xC0 exactly.
    state: int = 0
    frame_number: int = 0
    delay_before_next_frame: int = 0
    normal_status_arm_swing_direction: int = 1
    # Original ``lyingDownDurationLeft`` at 0xB8. Sentinel value ``-1`` means
    # "not lying down"; on dive-landing it is set to 3 and decremented each
    # frame; when it drops below ``-1`` the state transitions back to 0.
    lying_down_duration_left: int = -1
    diving_direction: int = 0
    # Original ``isCollisionWithBallHappened`` at 0xBC. Prevents collision
    # from re-firing while the ball is still inside the 32px box; cleared
    # when the ball exits the box.
    is_collision_with_ball_happened: bool = False
    is_winner: bool = False
    game_ended: bool = False
    # Built-in-AI knobs. Our L1-L5 bot (backend/game/bot.py) is an external
    # policy and does not consult these, but they are populated at
    # round-start for 1:1 fidelity with the original.
    computer_boldness: int = 0
    computer_where_to_stand_by: int = 0
    # ── Back-compat derived views (see sync_derived_flags). ──
    is_jumping: bool = False
    is_diving: bool = False
    is_power_hitting: bool = False
    lying_down_duration: int = 0

    def sync_derived_flags(self) -> None:
        """Keep ``is_*`` / ``lying_down_duration`` in sync with ``state``."""
        self.is_jumping = self.state in (1, 2)
        self.is_diving = self.state == 3
        self.is_power_hitting = self.state == 2
        # Legacy "remaining frames" view: the old direct-field semantics
        # counted 3→2→1→0 and treated >0 as "still down". The original
        # ``lyingDownDurationLeft`` counts one beyond that (3→2→1→0→-1,
        # then state=0 on the next decrement), so the legacy view clips
        # negatives to 0 and otherwise mirrors lying_down_duration_left.
        if self.state == 4:
            self.lying_down_duration = max(0, self.lying_down_duration_left)
        else:
            self.lying_down_duration = 0


@dataclass
class BallState:
    """Port of physics.js ``Ball``.

    All sprite-adjacent fields (``fine_rotation``, ``punch_effect_*``,
    ``previous_*``) are carried on the state so renderers stay stateless.
    """

    x: int
    y: int
    vx: int = 0
    vy: int = 0
    # Sprite-frame index (0-5). Derived from fine_rotation on each ball-world
    # update. NOTE: the pre-port engine exposed ``rotation`` as degrees
    # (0-360); the port switches to the original 0-5 sprite-frame semantics.
    rotation: int = 0
    # Original ``fineRotation`` at 0x48. Advanced by ``(vx / 2) | 0`` per
    # frame and wrapped to [0, 50]. When pinned at 50 the "hyper ball glitch"
    # fires in the original (sprite 5 drawn continuously). We replicate the
    # wrap but without the glitch path.
    fine_rotation: int = 0
    punch_effect_x: int = 0
    punch_effect_y: int = 0
    punch_effect_radius: int = 0
    # Trail-effect anchors (physics.js:402-405). Updated every world step
    # regardless of whether the ball touches the ground.
    previous_x: int = 0
    previous_y: int = 0
    previous_previous_x: int = 0
    previous_previous_y: int = 0
    # Ball's expected landing x — recomputed after every ball-player collision
    # (physics.js:730) so the built-in AI and any external consumer share the
    # same "where will this end up" prediction the engine itself uses.
    expected_landing_point_x: int = 0
    # True on the frame of a power-hit collision; drives the hyper-ball /
    # trail sprite (original view.js:513). Cleared on any non-power collision.
    is_power_hit: bool = False
    # Original stereo-sound flags (fired on event; FE clears on consume).
    sound_power_hit: bool = False
    sound_ball_touches_ground: bool = False


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
    # against infinite self-toss rallies — see ``PikachuVolleyball.step``.
    # Resets to 0 on net crossing and at round start.
    frames_since_net_crossing: int = 0
    # True when this round ended because ``frames_since_net_crossing`` exceeded
    # ``PikachuVolleyball.RALLY_MAX_FRAMES`` (and NOT because the ball
    # grounded). The concede is awarded to the side currently holding the
    # ball. Consumers can distinguish timeout concedes via this flag.
    round_ended_by_timeout: bool = False
    # Port of pikavolley.js ``gameEnded``. Flips to True the frame MAX_SCORE
    # is reached and stays True; subsequent ``step()`` calls continue to run
    # physics (ball can bounce, players move into win/lose poses) but
    # scoring is gated so no further points are awarded. See the view-port
    # commit message for the full state-machine mapping.
    is_game_ended: bool = False
    # Frames elapsed since ``is_game_ended`` was set. Port of pikavolley.js
    # ``frameCounter`` for the ``gameEnd`` state. When it reaches
    # ``PikachuVolleyball.GAME_END_FRAMES`` the engine freezes state
    # permanently (equivalent to the original returning to the intro).
    game_end_frame_counter: int = 0


class PlayerInput(NamedTuple):
    x_dir: int  # -1, 0, 1
    y_dir: int  # -1, 0, 1
    power_hit: bool


class PikachuVolleyball:
    """Deterministic Pikachu Volleyball engine — port of physics.js."""

    # Safety valve: force-end the round if the ball hasn't crossed the net
    # for this many consecutive frames. Prevents infinite self-toss loops.
    # NOT in the original — added here because non-interactive play (RL
    # training, replays, headless bot-vs-bot) has no user available to
    # forfeit the round.
    RALLY_MAX_FRAMES: int = 600

    # Duration of the ``gameEnd`` state (port of pikavolley.js
    # ``frameTotal.gameEnd``). After MAX_SCORE is reached physics continues
    # running for this many frames so winner/loser poses play out; the
    # engine then freezes state permanently (original: returns to intro).
    GAME_END_FRAMES: int = 211

    def __init__(self, *, seed: int | None = None) -> None:
        """Create a new engine instance.

        seed: optional seed for the engine's internal RNG. All stochastic
            physics decisions (``rand() % 3`` in ball-player collision,
            ``rand() % 5`` boldness) go through it so golden-scenario tests
            can reproduce identical frame sequences across runs.
        """
        self._rng: random.Random = random.Random(seed)
        self._state: GameState = self._create_initial_state()
        self._prev_ball_x: float = float(self._state.ball.x)

    # ------------------------------------------------------------------
    # RNG — matches rand.js semantics: integer in [0, 32767].
    # ------------------------------------------------------------------
    def _rand(self) -> int:
        """Port of ``rand()`` in rand.js. Returns int in [0, 32767]."""
        return self._rng.randint(0, 32767)

    def _create_initial_state(self, serving_player: int = 1) -> GameState:
        # physics.js: player1.x = 36, player2.x = GROUND_WIDTH - 36 (= 396)
        p1 = PlayerState(x=PLAYER_INIT_X_P1, y=PLAYER_GROUND_Y)
        p2 = PlayerState(x=PLAYER_INIT_X_P2, y=PLAYER_GROUND_Y)
        # Original ``computerBoldness = _rand() % 5`` on every round start.
        p1.computer_boldness = self._rand() % 5
        p2.computer_boldness = self._rand() % 5
        p1.sync_derived_flags()
        p2.sync_derived_flags()
        # physics.js: ball.x = 56 (p1 serve) or 376, y = 0, vy = 1
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
        """Advance one frame. Order matches physics.js ``physicsEngine`` (FUN_00403dd0).

        1. ``processCollisionBetweenBallAndWorldAndSetBallPosition`` — ball
           boundary / ceiling / net / ground, then move + gravity last.
        2. ``processPlayerMovementAndSetPlayerPosition`` for both players.
        3. ``isCollisionBetweenBallAndPlayerHappened`` +
           ``processCollisionBetweenBallAndPlayer`` for both players.

        After the original-faithful update, one extension runs:
          * Rally-timeout safety valve (not in original).

        Game-end flow (port of pikavolley.js ``round`` + ``gameEnd``):
          * When a player's score reaches MAX_SCORE, ``is_game_ended`` is set
            and ``game_end_frame_counter`` starts counting. Physics continues
            running for the next ``GAME_END_FRAMES`` calls — the ball can
            bounce, players transition into their win (state=5) or lose
            (state=6) pose — but scoring is gated so no further points are
            awarded. Once the counter hits ``GAME_END_FRAMES`` the engine
            freezes state permanently (equivalent to the original returning
            to ``intro``). Consumer loops should exit when
            ``is_game_ended and game_end_frame_counter >= GAME_END_FRAMES``.
        """
        state = self._state

        # Decay the graphic punch-effect radius every frame (mirrors
        # view.js:502-507 where the client decrements by 2 per render tick).
        # Centralising the shrink in the engine keeps FE renderers stateless.
        if state.ball.punch_effect_radius > 0:
            state.ball.punch_effect_radius = max(
                0, state.ball.punch_effect_radius - 2
            )

        # Match-over guard. Once the 211-frame gameEnd window has fully
        # elapsed the engine refuses to advance physics — this preserves
        # the final scene and makes repeated step() calls a no-op (same
        # effective contract as the original returning to ``intro``).
        if (
            state.is_game_ended
            and state.game_end_frame_counter >= self.GAME_END_FRAMES
        ):
            state.is_round_over = True
            return state

        if state.is_game_ended:
            # gameEnd window — tick the counter, keep ``is_round_over`` set,
            # and let physics run normally below. Scoring is gated by the
            # ``grounded and not is_game_ended`` branch.
            state.game_end_frame_counter += 1
        else:
            # Live round — clear per-frame round flags.
            state.is_round_over = False
            state.round_ended_by_timeout = False

        state.frame += 1
        prev_ball_x = self._prev_ball_x

        grounded = self._update_ball_and_world(state.ball)
        if grounded and not state.is_game_ended:
            self._handle_scoring(state)
            self._prev_ball_x = float(self._state.ball.x)
            return self._state

        self._update_player(
            state.player1, p1_input, is_player2=False,
            ball=state.ball, other=state.player2,
        )
        self._update_player(
            state.player2, p2_input, is_player2=True,
            ball=state.ball, other=state.player1,
        )

        self._check_ball_player_collision(state.ball, state.player1, p1_input)
        self._check_ball_player_collision(state.ball, state.player2, p2_input)

        # Net-crossing counter + rally-timeout safety valve (extensions —
        # not in original). Gated on ``not is_game_ended`` so the gameEnd
        # window can't force-concede a phantom timeout point.
        if not state.is_game_ended:
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
                self._prev_ball_x = float(self._state.ball.x)
                return self._state
            self._prev_ball_x = now_ball_x
        else:
            self._prev_ball_x = float(state.ball.x)
        return state

    # ==================================================================
    # Physics subroutines — 1:1 port of physics.js.
    # ==================================================================

    def _update_ball_and_world(self, ball: BallState) -> bool:
        """Port of ``processCollisionBetweenBallAndWorldAndSetBallPosition``.

        Returns True if the ball touched the ground this frame. Order and
        integer-truncation behavior match physics.js:398-486 exactly,
        including the documented right-wall asymmetry (``> GROUND_WIDTH``,
        not ``> GROUND_WIDTH - BALL_RADIUS``) and the ``fine_rotation``
        advance that produces the hyper-ball sprite glitch at fine==50.
        """
        # Save trail positions (physics.js:402-405).
        ball.previous_previous_x = ball.previous_x
        ball.previous_previous_y = ball.previous_y
        ball.previous_x = ball.x
        ball.previous_y = ball.y

        # fine_rotation advance — matches physics.js:408-421 with JS-trunc.
        future_fine_rotation = ball.fine_rotation + _trunc_div(ball.vx, 2)
        if future_fine_rotation < 0:
            future_fine_rotation += 50
        elif future_fine_rotation > 50:
            future_fine_rotation -= 50
        ball.fine_rotation = future_fine_rotation
        ball.rotation = _trunc_div(ball.fine_rotation, 10)

        future_x = ball.x + ball.vx
        # Left-right world bounds — original is asymmetric on purpose.
        if future_x < BALL_RADIUS or future_x > GROUND_WIDTH:
            ball.vx = -ball.vx

        future_y = ball.y + ball.vy
        # Ceiling — if ball would go above top, force downward.
        if future_y < 0:
            ball.vy = 1

        # Net collision — top of pillar vs side of pillar.
        if (
            abs(ball.x - NET_PILLAR_X) < NET_PILLAR_HALF_WIDTH
            and ball.y > NET_PILLAR_TOP_Y
        ):
            if ball.y <= NET_PILLAR_TOP_BOTTOM_Y:
                if ball.vy > 0:
                    ball.vy = -ball.vy
            else:
                if ball.x < NET_PILLAR_X:
                    ball.vx = -abs(ball.vx)
                else:
                    ball.vx = abs(ball.vx)

        future_y = ball.y + ball.vy
        if future_y > BALL_GROUND_Y:
            ball.sound_ball_touches_ground = True
            ball.vy = -ball.vy
            ball.punch_effect_x = ball.x
            ball.y = BALL_GROUND_Y
            ball.punch_effect_radius = BALL_RADIUS
            ball.punch_effect_y = BALL_GROUND_Y + BALL_RADIUS
            return True

        ball.y = future_y
        ball.x = ball.x + ball.vx
        ball.vy += GRAVITY
        return False

    def _update_player(
        self,
        player: PlayerState,
        inp: PlayerInput,
        *,
        is_player2: bool,
        ball: BallState,
        other: PlayerState,
    ) -> None:
        """Port of ``processPlayerMovementAndSetPlayerPosition`` (physics.js:496-649).

        Uses ``player.state`` (0-6) as the source of truth. The derived
        ``is_jumping`` / ``is_diving`` / ``is_power_hitting`` / legacy
        ``lying_down_duration`` flags are resynced at the end via
        :meth:`PlayerState.sync_derived_flags` for consumers that haven't
        migrated to ``state``.

        Note: the original calls ``letComputerDecideUserInput`` here when
        ``player.isComputer``. We omit that branch — L1-L5 bot is an
        external policy, so inputs are always provided by the caller.
        """
        # state === 4 (lying down) — frozen; decrement and maybe exit.
        if player.state == 4:
            player.lying_down_duration_left -= 1
            if player.lying_down_duration_left < -1:
                player.state = 0
            player.sync_derived_flags()
            return

        # Horizontal velocity — matches physics.js:516-524.
        player_velocity_x = 0
        if player.state < 5:
            if player.state < 3:
                player_velocity_x = inp.x_dir * PLAYER_SPEED
            else:
                # state == 3 (diving) — x driven by diving_direction.
                player_velocity_x = player.diving_direction * PLAYER_DIVE_SPEED

        player.vx = player_velocity_x
        future_player_x = player.x + player_velocity_x
        player.x = future_player_x

        # Court-half clamp (physics.js:530-544).
        if not is_player2:
            if future_player_x < PLAYER_HALF_LENGTH:
                player.x = PLAYER_HALF_LENGTH
            elif future_player_x > NET_PILLAR_X - PLAYER_HALF_LENGTH:
                player.x = NET_PILLAR_X - PLAYER_HALF_LENGTH
        else:
            if future_player_x < NET_PILLAR_X + PLAYER_HALF_LENGTH:
                player.x = NET_PILLAR_X + PLAYER_HALF_LENGTH
            elif future_player_x > GROUND_WIDTH - PLAYER_HALF_LENGTH:
                player.x = GROUND_WIDTH - PLAYER_HALF_LENGTH

        # Jump — only from state < 3 at grounded y with up input.
        if (
            player.state < 3
            and inp.y_dir == -1
            and player.y == PLAYER_GROUND_Y
        ):
            player.vy = PLAYER_JUMP_VELOCITY
            player.state = 1
            player.frame_number = 0

        # Gravity + landing — unconditional y advance (physics.js:562-579).
        future_player_y = player.y + player.vy
        player.y = future_player_y
        if future_player_y < PLAYER_GROUND_Y:
            player.vy += GRAVITY
        elif future_player_y > PLAYER_GROUND_Y:
            # Landing — snap to ground and clear vy.
            player.vy = 0
            player.y = PLAYER_GROUND_Y
            player.frame_number = 0
            if player.state == 3:
                # Diving → lying down.
                player.state = 4
                player.frame_number = 0
                player.lying_down_duration_left = LYING_DOWN_DURATION
            else:
                player.state = 0

        # Power-hit / dive trigger (physics.js:581-604).
        if inp.power_hit:
            if player.state == 1:
                # Jumping → power hit.
                player.delay_before_next_frame = 5
                player.frame_number = 0
                player.state = 2
            elif player.state == 0 and inp.x_dir != 0:
                # Grounded + horizontal input → dive.
                player.state = 3
                player.frame_number = 0
                player.diving_direction = inp.x_dir
                player.vy = PLAYER_DIVE_VELOCITY

        # Animation frame_number updates (physics.js:606-631). Only state=2
        # affects physics (the power-hit dwell window within which a ball
        # collision is treated as a power hit); other branches are purely
        # render-state but we mirror them for 1:1 fidelity.
        if player.state == 1:
            player.frame_number = (player.frame_number + 1) % 3
        elif player.state == 2:
            if player.delay_before_next_frame < 1:
                player.frame_number += 1
                if player.frame_number > 4:
                    player.frame_number = 0
                    player.state = 1
            else:
                player.delay_before_next_frame -= 1
        elif player.state == 0:
            player.delay_before_next_frame += 1
            if player.delay_before_next_frame > 3:
                player.delay_before_next_frame = 0
                future_frame_number = (
                    player.frame_number + player.normal_status_arm_swing_direction
                )
                if future_frame_number < 0 or future_frame_number > 4:
                    player.normal_status_arm_swing_direction = (
                        -player.normal_status_arm_swing_direction
                    )
                player.frame_number = (
                    player.frame_number + player.normal_status_arm_swing_direction
                )

        # Game-end win/lose-pose transitions and their frame advance.
        if player.game_ended:
            if player.state == 0:
                if player.is_winner:
                    player.state = 5
                else:
                    player.state = 6
                player.delay_before_next_frame = 0
                player.frame_number = 0
            self._process_game_end_frame_for(player)

        player.sync_derived_flags()

    @staticmethod
    def _process_game_end_frame_for(player: PlayerState) -> None:
        """Port of ``processGameEndFrameFor`` (physics.js:656-664).

        Advances ``frame_number`` up to 4 with a 4-frame dwell between
        increments. Used for the winner/loser victory/defeat motions after
        the match has ended.
        """
        if player.game_ended and player.frame_number < 4:
            player.delay_before_next_frame += 1
            if player.delay_before_next_frame > 4:
                player.delay_before_next_frame = 0
                player.frame_number += 1

    def _check_ball_player_collision(
        self, ball: BallState, player: PlayerState, inp: PlayerInput
    ) -> None:
        """Port of ``isCollisionBetweenBallAndPlayerHappened`` +
        ``processCollisionBetweenBallAndPlayer`` (physics.js:381-731).

        Detection distance: 32px (PLAYER_HALF_LENGTH) on both axes. Uses
        the ``is_collision_with_ball_happened`` gate so tangential /
        slow-moving balls that stay in the box across frames only trigger
        a single collision.
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
            return
        player.is_collision_with_ball_happened = True

        # Base horizontal velocity — physics.js:688-699 with JS-trunc.
        if ball.x < player.x:
            ball.vx = -_trunc_div(abs(dx_signed), 3)
        elif ball.x > player.x:
            ball.vx = _trunc_div(abs(dx_signed), 3)
        # else: vx unchanged from its prior value at this point — the
        # zero-check below handles the "exactly aligned" case.
        if ball.vx == 0:
            # Original: ``(rand() % 3) - 1`` → -1, 0, or 1.
            ball.vx = (self._rand() % 3) - 1

        # Base vertical velocity — reflect and clamp magnitude to 15.
        ball_abs_vy = abs(ball.vy)
        ball.vy = -ball_abs_vy
        if ball_abs_vy < BALL_MIN_REFLECT_VY_ABS:
            ball.vy = -BALL_MIN_REFLECT_VY_ABS

        # Power-hit branch — triggered by state == 2 (the dwell window
        # started when the player pressed power_hit while jumping).
        if player.state == 2:
            x_magnitude = (abs(inp.x_dir) + 1) * 10
            if ball.x < NET_PILLAR_X:
                ball.vx = x_magnitude
            else:
                ball.vx = -x_magnitude
            ball.punch_effect_x = ball.x
            ball.punch_effect_y = ball.y
            # Original: ``vy = |vy| * yDirection * 2``. If y_dir == 0 this
            # zeros vy (flat drive).
            ball.vy = abs(ball.vy) * inp.y_dir * 2
            ball.punch_effect_radius = BALL_RADIUS
            ball.sound_power_hit = True
            ball.is_power_hit = True
        else:
            ball.is_power_hit = False

        self._calculate_expected_landing_point_x(ball)

    def _calculate_expected_landing_point_x(self, ball: BallState) -> None:
        """Port of ``calculateExpectedLandingPointXFor`` (physics.js:738-788).

        Simulates the ball trajectory on a copy until it would touch the
        ground (or ``INFINITE_LOOP_LIMIT`` is hit as a safety cap), then
        writes the final x to ``ball.expected_landing_point_x``. This is
        a read-only prediction — the real ball is not mutated.
        """
        bx = ball.x
        by = ball.y
        bvx = ball.vx
        bvy = ball.vy
        loop_counter = 0
        while True:
            loop_counter += 1
            future_bx = bvx + bx
            if future_bx < BALL_RADIUS or future_bx > GROUND_WIDTH:
                bvx = -bvx
            if by + bvy < 0:
                bvy = 1

            if (
                abs(bx - NET_PILLAR_X) < NET_PILLAR_HALF_WIDTH
                and by > NET_PILLAR_TOP_Y
            ):
                # Note: original uses ``<`` here (not ``<=``) — documented
                # upstream as a likely mistake by the original author, but
                # mirroring for frame-accurate reproduction.
                if by < NET_PILLAR_TOP_BOTTOM_Y:
                    if bvy > 0:
                        bvy = -bvy
                else:
                    if bx < NET_PILLAR_X:
                        bvx = -abs(bvx)
                    else:
                        bvx = abs(bvx)

            by = by + bvy
            if by > BALL_GROUND_Y or loop_counter >= INFINITE_LOOP_LIMIT:
                break
            bx = bx + bvx
            bvy += 1
        ball.expected_landing_point_x = bx

    # ==================================================================
    # Scoring wrapper — NOT in physics.js (original defers to pikavolley.js).
    # Mirrors pikavolley.js:368-400 (score bookkeeping) and the gameEnd
    # transition on MAX_SCORE.
    # ==================================================================

    def _handle_scoring(self, state: GameState) -> None:
        ball = state.ball
        state.is_round_over = True
        if ball.x < NET_PILLAR_X:
            state.score2 += 1
            state.serving_player = 2
        else:
            state.score1 += 1
            state.serving_player = 1

        # Game-end transition — port of pikavolley.js:377-383 / 387-393.
        # When a player reaches MAX_SCORE we flip the gameEnd flags on both
        # sides and DO NOT swap in a new serving state — the ball stays
        # where it grounded and physics continues running through the next
        # GAME_END_FRAMES calls so winner/loser poses play out.
        if state.score1 >= MAX_SCORE or state.score2 >= MAX_SCORE:
            state.is_game_ended = True
            state.game_end_frame_counter = 0
            p1_won = state.score1 >= MAX_SCORE
            state.player1.is_winner = p1_won
            state.player2.is_winner = not p1_won
            state.player1.game_ended = True
            state.player2.game_ended = True
            return

        # Mid-match — swap to fresh serving state. Consumers see
        # ``is_round_over=True`` on this frame and a reset ball on the next
        # step() call. Replaces the old post-score freeze path.
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

        Concede goes to the side currently holding the ball.
        ``round_ended_by_timeout`` is set so RL / UI can distinguish from
        a grounded-ball concede. If the concede wins the match, the
        gameEnd path is entered just like a normal ground-touch score.
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

        if state.score1 >= MAX_SCORE or state.score2 >= MAX_SCORE:
            state.is_game_ended = True
            state.game_end_frame_counter = 0
            p1_won = state.score1 >= MAX_SCORE
            state.player1.is_winner = p1_won
            state.player2.is_winner = not p1_won
            state.player1.game_ended = True
            state.player2.game_ended = True
            return

        serving = state.serving_player
        s1, s2, frame = state.score1, state.score2, state.frame
        new = self._create_initial_state(serving_player=serving)
        new.score1 = s1
        new.score2 = s2
        new.frame = frame
        new.is_round_over = True
        new.round_ended_by_timeout = True
        self._state = new
