"""Game constants for Pikachu Volleyball.

Values are matched against the original game source
(gorisanson/pikachu-volleyball: src/resources/js/physics.js).
Any divergence from the original must be intentional and documented.
"""

# Court dimensions — original: GROUND_WIDTH=432, GROUND_HEIGHT=304
GROUND_WIDTH: int = 432
GROUND_HEIGHT: int = 304

# Net — original: NET_PILLAR_HALF_WIDTH=25, NET_PILLAR_TOP_TOP/BOTTOM=176/192
# NET_PILLAR_X equals GROUND_HALF_WIDTH=(GROUND_WIDTH/2)|0=216 in original.
NET_PILLAR_X: int = 216
NET_PILLAR_HALF_WIDTH: int = 25
NET_PILLAR_TOP_Y: int = 176  # original: NET_PILLAR_TOP_TOP_Y_COORD
NET_PILLAR_TOP_BOTTOM_Y: int = 192  # original: NET_PILLAR_TOP_BOTTOM_Y_COORD

# Player — original: PLAYER_LENGTH=64 (half=32), PLAYER_TOUCHING_GROUND_Y=244
PLAYER_HALF_LENGTH: int = 32
PLAYER_GROUND_Y: int = 244
PLAYER_SPEED: int = 6  # original: xDirection * 6
PLAYER_DIVE_SPEED: int = 8  # original: divingDirection * 8
PLAYER_JUMP_VELOCITY: int = -16  # original: -16 on jump
PLAYER_DIVE_VELOCITY: int = -5  # original: yVelocity = -5 on dive start
PLAYER_INIT_X_P1: int = 36  # original: player1.x = 36
PLAYER_INIT_X_P2: int = GROUND_WIDTH - 36  # original: 396

# Lying-down after dive landing. Set on the landing frame (player.state
# 3 → 4), then decremented by 1 each frame the player is in state==4;
# state transitions back to 0 the frame the counter falls below -1. So
# total time stuck in state=4 is exactly 5 frames (3 → 2 → 1 → 0 → -1,
# then -2 triggers the state=0 transition). Matches the literal value
# at physics.js:575 ``player.lyingDownDurationLeft = 3``; see also the
# decrement / exit branch at physics.js:507-512.
LYING_DOWN_DURATION: int = 3

# Ball — original: BALL_RADIUS=20, BALL_TOUCHING_GROUND_Y=252
BALL_RADIUS: int = 20
BALL_GROUND_Y: int = 252
BALL_INIT_Y_VELOCITY: int = 1  # original: ball.yVelocity = 1 at serve
BALL_SERVE_X_P1: int = 56  # original: ball.x = 56 on player1 serve
BALL_SERVE_X_P2: int = GROUND_WIDTH - 56  # original: 376 on player2 serve
BALL_SERVE_Y: int = 0  # original: ball.y = 0 at serve

# Physics — per-frame gravity step (yVelocity += 1)
GRAVITY: int = 1

# Collision thresholds derived from original physics
# Ball-player collision: |ball.x - player.x| <= 32 AND |ball.y - player.y| <= 32
# (original uses PLAYER_HALF_LENGTH, NOT PLAYER_HALF_LENGTH + BALL_RADIUS)
BALL_PLAYER_COLLISION_DIST: int = PLAYER_HALF_LENGTH
# Minimum reflected-vy magnitude after a non-power-hit collision
BALL_MIN_REFLECT_VY_ABS: int = 15

# Game rules
MAX_SCORE: int = 15
# Canonical engine tick rate. One ``PikachuVolleyball.step()`` call advances
# the physics by exactly one game frame; this constant declares how many of
# those frames make up one real-time second so consumers (FE replay player,
# WS frame emitter, dashboard interpolator) can convert tick counts to
# milliseconds correctly. Matches pikavolley.js:53 ``this.normalFPS = 25``.
# Pre-2026-04-18 this was 30 — that 17% mismatch made dive/jump/lying-down
# durations and the slow-motion window all play back faster than the
# original.
FPS: int = 25
