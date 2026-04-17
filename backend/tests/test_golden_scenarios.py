"""Golden-scenario regression tests for the ported physics engine.

Ten deterministic scenarios covering the core physics paths that
``port(physics)`` and ``port(view)`` touched. Each test seeds the
engine explicitly and pins frame-level ball/player state so any
future drift away from the current port (whether accidental or from
intentional tuning without intent to change the physics) is caught
loudly.

Scenarios
---------
1. Serve trajectory — ball leaves (56, 0) at vy=1, falls under gravity.
2. Player-ball collision — grounded player reflects a falling ball.
3. Power-hit smash — jumping player + power_hit drives the ball.
4. Dive trigger — grounded + power_hit + x_dir → state=3.
5. Dive landing → lying down — state=3 at ground → state=4.
6. Net pillar — top of pillar flips vy.
7. Net pillar — side of pillar reflects vx (ball on left).
8. Ceiling — ball at y<0 gets vy forced to 1.
9. Ground scoring — ball on p1 side grounds → p2 scores + serve swap.
10. Game end at MAX_SCORE — is_game_ended, 211f counter, no further scoring.

These tests are "golden" in the regression sense: the current port is
the source of truth for the pinned values. They do not attempt to
prove frame-accuracy against the upstream JS — that would require a
running JS harness we don't have. See ATTRIBUTION.md for the full
provenance chain.
"""

from __future__ import annotations

import pytest

from backend.game.constants import (
    BALL_GROUND_Y,
    BALL_RADIUS,
    BALL_SERVE_X_P1,
    BALL_SERVE_Y,
    MAX_SCORE,
    NET_PILLAR_HALF_WIDTH,
    NET_PILLAR_TOP_BOTTOM_Y,
    NET_PILLAR_TOP_Y,
    NET_PILLAR_X,
    PLAYER_GROUND_Y,
    PLAYER_HALF_LENGTH,
    PLAYER_INIT_X_P1,
)
from backend.game.engine import (
    BallState,
    GameState,
    PikachuVolleyball,
    PlayerInput,
    PlayerState,
)

NOOP = PlayerInput(x_dir=0, y_dir=0, power_hit=False)


# ── 1. Serve trajectory ──────────────────────────────────────────────────────


def test_serve_trajectory_first_five_frames_are_pinned() -> None:
    """Initial serve: ball drops from (56, 0) with vy=1, gravity += 1/frame.

    Golden pin: the first five frame positions and velocities are
    deterministic integer sequences from the physics port. If any
    future change shifts serve initial vy / gravity / rotation the
    whole sequence will visibly move and this test will light up.
    """
    game = PikachuVolleyball(seed=0)
    state = game.reset()

    # Frame 0 (after reset) — fresh serving state.
    assert state.ball.x == BALL_SERVE_X_P1
    assert state.ball.y == BALL_SERVE_Y
    assert state.ball.vy == 1
    assert state.ball.vx == 0

    # Advance 5 frames with no input. Ball should fall with vy
    # accumulating by +1/frame, x unchanged (vx=0).
    positions: list[tuple[int, int, int, int]] = []
    for _ in range(5):
        s = game.step(NOOP, NOOP)
        positions.append((s.ball.x, s.ball.y, s.ball.vx, s.ball.vy))

    # y advance: 0→1→3→6→10→15; vy advance: 1→2→3→4→5→6.
    # (ball.y starts at 0, then += vy, then vy += 1.)
    assert positions == [
        (56, 1, 0, 2),
        (56, 3, 0, 3),
        (56, 6, 0, 4),
        (56, 10, 0, 5),
        (56, 15, 0, 6),
    ]


# ── 2. Player-ball collision ─────────────────────────────────────────────────


def test_grounded_player_reflects_falling_ball_with_min_vy_15() -> None:
    """Ball falling onto a grounded, centred player: vx≈0 tiebreak, vy→-15.

    Port semantics: when |vy| < 15 the post-collision vy magnitude is
    clamped to 15 (physics.js:704-706). With the ball directly over
    the player vx falls through the zero-tiebreak rand()%3-1 path; we
    seed the engine so the rand value is reproducible.
    """
    game = PikachuVolleyball(seed=12345)
    game.reset()
    # Place ball exactly over player1 at a low descending vy.
    game._state.ball.x = game._state.player1.x
    game._state.ball.y = game._state.player1.y - PLAYER_HALF_LENGTH + 4
    game._state.ball.vx = 0
    game._state.ball.vy = 4

    state = game.step(NOOP, NOOP)

    # Post-collision: vy is clamped to -15 (minimum reflect magnitude).
    assert state.ball.vy == -15
    # vx comes from (rand() % 3) - 1 ∈ {-1, 0, 1}; seed makes it deterministic.
    assert state.ball.vx in {-1, 0, 1}
    # Expected-landing-point recomputed by collision path.
    assert state.ball.expected_landing_point_x != 0


# ── 3. Power-hit smash ───────────────────────────────────────────────────────


def test_power_hit_in_air_drives_ball_at_20_horizontal() -> None:
    """Jumping + power_hit + x_dir=1 on p1 side → ball.vx = +20.

    Formula from physics.js:710-714: ``x_magnitude = (|xDir|+1)*10 = 20``,
    sign = +1 when ball on left half, -1 when on right half. Power hit
    also sets punch_effect_radius to BALL_RADIUS and is_power_hit=True.
    """
    game = PikachuVolleyball(seed=0)
    game.reset()
    # state=1 (jumping) so power_hit input transitions state 1→2 in
    # _update_player, matching the port's state-dwell semantics.
    game._state.player1.state = 1
    game._state.player1.sync_derived_flags()
    game._state.player1.y = PLAYER_GROUND_Y - 40
    game._state.ball.x = game._state.player1.x
    game._state.ball.y = game._state.player1.y
    game._state.ball.vx = 0
    game._state.ball.vy = 3

    state = game.step(PlayerInput(x_dir=1, y_dir=-1, power_hit=True), NOOP)

    # Ball is on p1 side (left of net), so power-hit drives it right.
    assert state.ball.vx == 20
    # y_dir = -1 with |vy|=15 → vy = 15 * -1 * 2 = -30 (upward smash).
    assert state.ball.vy == -30
    assert state.ball.punch_effect_radius == BALL_RADIUS
    assert state.ball.is_power_hit is True


# ── 4. Dive trigger ──────────────────────────────────────────────────────────


def test_dive_triggers_from_grounded_power_hit_with_x_direction() -> None:
    """state==0 on ground + power_hit + x_dir!=0 → state=3 (dive).

    physics.js:593-603 — power_hit while grounded and walking starts a
    dive with the chosen direction and vy=-5 (short hop).
    """
    game = PikachuVolleyball(seed=0)
    game.reset()
    state = game.step(PlayerInput(x_dir=1, y_dir=0, power_hit=True), NOOP)

    assert state.player1.state == 3
    assert state.player1.diving_direction == 1
    assert state.player1.is_diving is True  # back-compat view still True


# ── 5. Dive landing → lying down ─────────────────────────────────────────────


def test_diving_player_lands_and_enters_lying_down_state() -> None:
    """state=3 at PLAYER_GROUND_Y → state=4, lying_down_duration_left=3.

    physics.js:571-575 — landing from a dive transitions to state=4
    and seeds the lying-down countdown to LYING_DOWN_DURATION (3).
    """
    game = PikachuVolleyball(seed=0)
    game.reset()
    game._state.player1.state = 3
    game._state.player1.diving_direction = 1
    game._state.player1.y = PLAYER_GROUND_Y - 3
    game._state.player1.vy = 10

    state = game.step(NOOP, NOOP)

    assert state.player1.state == 4
    assert state.player1.lying_down_duration_left == 3
    # Back-compat view.
    assert state.player1.lying_down_duration == 3
    assert state.player1.is_diving is False


# ── 6. Net pillar top ────────────────────────────────────────────────────────


def test_net_pillar_top_flips_descending_vy() -> None:
    """Ball at the top of the net pillar with vy>0 bounces straight up.

    physics.js:447-454 — top-of-pillar reflection only flips vy when
    it's positive; an ascending ball passes through undisturbed.
    """
    game = PikachuVolleyball(seed=0)
    game.reset()
    game._state.ball.x = NET_PILLAR_X
    # y in (NET_PILLAR_TOP_Y, NET_PILLAR_TOP_BOTTOM_Y] = (176, 192].
    game._state.ball.y = NET_PILLAR_TOP_Y + 4
    game._state.ball.vx = 0
    game._state.ball.vy = 5

    state = game.step(NOOP, NOOP)

    assert state.ball.vy < 0  # flipped to ascending


# ── 7. Net pillar side ───────────────────────────────────────────────────────


def test_net_pillar_side_reflects_ball_on_left_half() -> None:
    """Ball pressed into the left side of the net pillar gets vx forced -|vx|.

    physics.js:455-460 — side-of-pillar reflection forces vx magnitude
    in the away-from-net direction regardless of prior sign.
    """
    game = PikachuVolleyball(seed=0)
    game.reset()
    # Inside the pillar band (y > NET_PILLAR_TOP_BOTTOM_Y), on left side.
    game._state.ball.x = NET_PILLAR_X - NET_PILLAR_HALF_WIDTH + 1
    game._state.ball.y = NET_PILLAR_TOP_BOTTOM_Y + 5
    game._state.ball.vx = 10  # moving right into the pillar
    game._state.ball.vy = 0

    state = game.step(NOOP, NOOP)

    assert state.ball.vx == -abs(state.ball.vx)  # forced back toward left


# ── 8. Ceiling clamp ─────────────────────────────────────────────────────────


def test_ceiling_forces_vy_to_one() -> None:
    """Ball that would pass above y=0 gets vy=1 (physics.js:442-444)."""
    game = PikachuVolleyball(seed=0)
    game.reset()
    game._state.ball.x = 100
    game._state.ball.y = 2
    game._state.ball.vx = 0
    game._state.ball.vy = -5  # would overshoot to y=-3

    state = game.step(NOOP, NOOP)

    # Ball still descending post-step because vy was forced to 1 and
    # then advanced by gravity.
    assert state.ball.vy > 0


# ── 9. Ground scoring + serve swap ───────────────────────────────────────────


def test_ground_on_p1_side_swaps_to_p2_serve() -> None:
    """Mid-match grounded ball on p1 side → p2 scores + p2 serves.

    Port(view) dropped the 20-frame freeze, so the returned state is
    already the fresh serving state (ball at p2 serve position).
    """
    game = PikachuVolleyball(seed=0)
    game.reset()
    game._state.ball.x = NET_PILLAR_X - 50  # p1 side
    game._state.ball.y = BALL_GROUND_Y - 1
    game._state.ball.vy = 10

    state = game.step(NOOP, NOOP)

    assert state.score2 == 1
    assert state.score1 == 0
    assert state.serving_player == 2
    assert state.is_round_over is True
    # Swap happened on the same frame.
    assert state.ball.y < BALL_GROUND_Y


# ── 10. Game end at MAX_SCORE ────────────────────────────────────────────────


def test_max_score_triggers_gameend_211f_and_no_further_scoring() -> None:
    """Match-winning ground touch: is_game_ended=True, 211f counter.

    Port(view): physics continues for GAME_END_FRAMES, scoring is gated
    off so repeat groundings don't add points, then state freezes.
    """
    game = PikachuVolleyball(seed=0)
    game.reset()
    game._state.score1 = MAX_SCORE - 1
    # Force grounding on p2 side to give p1 the winning point.
    game._state.ball.x = NET_PILLAR_X + 50
    game._state.ball.y = BALL_GROUND_Y - 1
    game._state.ball.vy = 10

    # Scoring frame — enters gameEnd.
    state = game.step(NOOP, NOOP)
    assert state.score1 == MAX_SCORE
    assert state.is_game_ended is True
    assert state.game_end_frame_counter == 0
    assert state.player1.is_winner is True
    assert state.player1.game_ended is True

    # Run out the full gameEnd window. Counter advances, score locked.
    for _ in range(game.GAME_END_FRAMES):
        # Repeatedly force the ball back to ground — scoring must stay
        # gated for the entire window.
        game._state.ball.y = BALL_GROUND_Y - 1
        game._state.ball.vy = 10
        state = game.step(NOOP, NOOP)
        assert state.score1 == MAX_SCORE

    # Past the window — repeated step() is a no-op.
    pinned_counter = state.game_end_frame_counter
    for _ in range(5):
        state = game.step(NOOP, NOOP)
        assert state.game_end_frame_counter == pinned_counter


# ── Meta: determinism ────────────────────────────────────────────────────────


@pytest.mark.parametrize("seed", [0, 1, 42, 12345])
def test_same_seed_same_input_produces_identical_trajectory(seed: int) -> None:
    """Golden determinism: two engines with the same seed and the same
    input sequence must produce byte-identical ball/player trajectories
    for at least the first 100 frames.

    This is the core invariant the golden scenarios rely on. Any future
    non-determinism introduced via a system-random call in the physics
    path would fail here.
    """
    def _run(seed: int) -> list[tuple[int, int, int, int, int]]:
        g = PikachuVolleyball(seed=seed)
        g.reset()
        trail: list[tuple[int, int, int, int, int]] = []
        for i in range(100):
            # Tiny deterministic input sequence to drive state changes.
            p1 = PlayerInput(
                x_dir=(1 if i % 7 == 0 else 0),
                y_dir=(-1 if i % 11 == 0 else 0),
                power_hit=(i % 13 == 0),
            )
            s = g.step(p1, NOOP)
            trail.append(
                (s.ball.x, s.ball.y, s.ball.vx, s.ball.vy, s.player1.state)
            )
        return trail

    assert _run(seed) == _run(seed)
