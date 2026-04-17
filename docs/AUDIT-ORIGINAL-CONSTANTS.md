# Audit — Original Constants Inventory (gorisanson/pikachu-volleyball)

Source clone: `/tmp/pikachu-original/` (commit at clone time, 2026-04-13).
Audit window: 2026-04-18.

This document is the authoritative inventory of every numeric / enum
constant used by the original physics engine and game-loop controller.
The cross-walk to our Python port lives in
`AUDIT-PORT-DIFF.md`; the state-machine cross-walk lives in
`AUDIT-STATE-MACHINE-DIFF.md`.

Constants are listed in the order they appear in the source.

---

## `src/resources/js/physics.js`

### Top-of-file `const` declarations

| Line | Name | Value | Notes |
|---:|---|---:|---|
| 33 | `GROUND_WIDTH` | 432 | game-court width in px |
| 35 | `GROUND_HALF_WIDTH` | 216 | derived `(GROUND_WIDTH / 2) \| 0`; also = net pillar x |
| 37 | `PLAYER_LENGTH` | 64 | bounding box edge length |
| 39 | `PLAYER_HALF_LENGTH` | 32 | derived `(PLAYER_LENGTH / 2) \| 0`; collision half-extent |
| 41 | `PLAYER_TOUCHING_GROUND_Y_COORD` | 244 | player y when feet on ground |
| 43 | `BALL_RADIUS` | 20 | ball half-width / collision radius |
| 45 | `BALL_TOUCHING_GROUND_Y_COORD` | 252 | ball y when bottom touches ground |
| 47 | `NET_PILLAR_HALF_WIDTH` | 25 | physics-only net half-width (not sprite width) |
| 49 | `NET_PILLAR_TOP_TOP_Y_COORD` | 176 | net top edge |
| 51 | `NET_PILLAR_TOP_BOTTOM_Y_COORD` | 192 | net top-block bottom edge |
| 64 | `INFINITE_LOOP_LIMIT` | 1000 | safety cap on expected-landing-point trajectory loops |

### `Player` initial / per-round values

| Line | Field | Value | Notes |
|---:|---|---:|---|
| 174 | `Player.x` (P1) | 36 | initial / round-reset x |
| 176 | `Player.x` (P2) | `GROUND_WIDTH - 36` = 396 | mirror |
| 179 | `Player.y` | 244 | = `PLAYER_TOUCHING_GROUND_Y_COORD` |
| 181 | `Player.yVelocity` | 0 | round reset |
| 192 | `Player.state` | 0 | normal idle (see state enum below) |
| 194 | `Player.frameNumber` | 0 | sprite frame index |
| 196 | `Player.normalStatusArmSwingDirection` | 1 | arm-swing animation direction |
| 198 | `Player.delayBeforeNextFrame` | 0 | sprite-frame dwell counter |
| 213 | `Player.computerBoldness` | `rand() % 5` | 0-4, set every round |
| 138 | `Player.divingDirection` | 0 | -1/0/+1 |
| 140 | `Player.lyingDownDurationLeft` | -1 | "not lying down" sentinel |
| 142 | `Player.isWinner` | false | flipped on game-end |
| 144 | `Player.gameEnded` | false | flipped on game-end |
| 153 | `Player.computerWhereToStandBy` | 0 | AI standby flag (0 / 1) |

### `Ball` initial / per-round values

| Line | Field | Value | Notes |
|---:|---|---:|---|
| 275 | `Ball.x` (P1 serve) | 56 | |
| 277 | `Ball.x` (P2 serve) | `GROUND_WIDTH - 56` = 376 | |
| 280 | `Ball.y` | 0 | top of court |
| 282 | `Ball.xVelocity` | 0 | |
| 284 | `Ball.yVelocity` | 1 | initial drop |
| 286 | `Ball.punchEffectRadius` | 0 | |
| 288 | `Ball.isPowerHit` | false | |
| 234 | `Ball.expectedLandingPointX` | 0 | recomputed every collision |
| 240 | `Ball.rotation` | 0 | sprite frame 0-5 |
| 242 | `Ball.fineRotation` | 0 | wraps in [0, 50] |
| 244-255 | trail / punch markers | 0 | `previousX/Y`, `previousPreviousX/Y`, `punchEffectX/Y` |

### `Player.state` enum (physics.js:186-191)

| Value | Meaning |
|---:|---|
| 0 | normal |
| 1 | jumping |
| 2 | jumping_and_power_hitting |
| 3 | diving |
| 4 | lying_down_after_diving |
| 5 | win |
| 6 | lost |

### Per-frame numeric thresholds

| Line | Where | Value | Meaning |
|---:|---|---:|---|
| 416 | `processCollisionBetweenBallAndWorldAndSetBallPosition` | 50 | `fineRotation` wrap modulus |
| 421 | same | 10 | `fineRotation / 10` → sprite frame 0-5 |
| 519 | `processPlayerMovementAndSetPlayerPosition` | 6 | x speed multiplier (`xDirection * 6`) |
| 522 | same | 8 | dive x speed multiplier (`divingDirection * 8`) |
| 552 | same | -16 | jump initial y velocity |
| 575 | same | 3 | `lyingDownDurationLeft` set on dive landing |
| 585 | same | 5 | `delayBeforeNextFrame` set on power-hit (state=2 dwell) |
| 596 | same | 0 | `frameNumber` reset on dive trigger |
| 598 | same | -5 | dive initial y velocity |
| 607 | same | 3 | jumping anim cycle modulus (`(frameNumber + 1) % 3`) |
| 611 | same | 4 | state==2 anim max frame (`> 4` resets to 0 + state=1) |
| 620 | same | 3 | state==0 anim dwell (`delayBeforeNextFrame > 3`) |
| 622-624 | same | 0, 4 | state==0 arm-swing range |
| 657 | `processGameEndFrameFor` | 4 | gameEnd anim max frame (`< 4`) |
| 659 | same | 4 | gameEnd anim dwell (`> 4`) |
| 691, 693 | `processCollisionBetweenBallAndPlayer` | 3 | ball vx divisor (`abs(dx) / 3 \| 0`) |
| 698 | same | 3 | zero-vx tiebreak modulus (`rand() % 3 - 1`) |
| 705 | same | 15 | min reflect vy magnitude (`if abs(vy) < 15: vy = -15`) |
| 711-713 | same | 10 | power-hit x magnitude (`(\|xDir\|+1) * 10`) |
| 718 | same | 2 | power-hit y multiplier (`abs(vy) * yDir * 2`) |

### `letComputerDecideUserInput` (built-in AI) — magic numbers

| Line | Threshold | Value |
|---:|---|---:|
| 810 | `abs(ball.x - player.x) > 100` | 100 |
| 811 | `abs(ball.xVelocity) < boldness + 5` | +5 |
| 822 | `(GROUND_HALF_WIDTH / 2) \| 0` | 108 |
| 828 | `abs(virtualX - player.x) > boldness + 8` | +8 |
| 835 | `rand() % 20 === 0` | 20 |
| 836, 909, 930 | `rand() % 2` | 2 |
| 841 | `abs(ball.xVelocity) < boldness + 3` | +3 |
| 842 | `abs(ball.x - player.x) < PLAYER_HALF_LENGTH` | 32 |
| 843, 844 | `ball.y > -36`, `ball.y < 10 * boldness + 84` | -36, +84, ×10 |
| 856 | `abs(ball.x - player.x) > boldness * 5 + PLAYER_LENGTH` | ×5, +64 |
| 859 | `ball.y > 174` | 174 |
| 870, 877 | `abs(ball.x - player.x) > 8`, `< 48` | 8, 48 |
| 887 | `abs(otherPlayer.x - player.x) < 80` | 80 |
| 922, 943 | `abs(landing - otherPlayer.x) > PLAYER_LENGTH` | 64 |

These are AI-only and our L1-L5 bot is an external policy that ignores
them — listed for inventory completeness only.

---

## `src/resources/js/pikavolley.js`

### Class fields (constructor)

| Line | Field | Value | Notes |
|---:|---|---:|---|
| 54 | `normalFPS` | 25 | game loop tick rate |
| 56 | `slowMotionFPS` | 5 | slow-motion physics rate |
| 59 | `SLOW_MOTION_FRAMES_NUM` | 6 | physics frames during slow-mo window |
| 71 | `winningScore` | 15 | match-win score |
| 81 | `frameCounter` | 0 | per-state frame counter |

### `frameTotal` (pikavolley.js:83-91)

| Key | Value | Meaning |
|---|---:|---|
| `intro` | 165 | intro screen duration |
| `afterMenuSelection` | 15 | post-menu fade-out |
| `beforeStartOfNewGame` | 15 | pre-game delay |
| `startOfNewGame` | 71 | game-start banner |
| `afterEndOfRound` | 5 | post-round fade-out |
| `beforeStartOfNextRound` | 30 | next-round READY ramp |
| `gameEnd` | 211 | win/lose pose window |

### `noInputFrameTotal` (pikavolley.js:96-98)

| Key | Value | Meaning |
|---|---:|---|
| `menu` | 225 | menu auto-advance to demo (AI vs AI) |

### Other gameplay magic numbers

| Line | Where | Value | Meaning |
|---:|---|---:|---|
| 195 | `menu` | 71 | early skip-to-end-of-banner threshold |
| 199 | same | 71 | input-recognition threshold |
| 359 | `round` (gameEnd skip) | 70 | post-power-hit early-skip threshold during gameEnd |
| 397 | `round` (slow-mo arm) | `SLOW_MOTION_FRAMES_NUM` | slow-mo set on score |
| 405, 416, 440 | various | `1 / 16` | per-frame fade-alpha delta |
| 443 | `beforeStartOfNextRound` | 5 | `frameCounter % 5 === 0` → toggle READY message |
| 128 | `gameLoop` | `Math.round(normalFPS / slowMotionFPS)` = 5 | physics-skip ratio during slow-mo |

---

## `src/resources/js/rand.js`

| Line | Function | Range |
|---:|---|---|
| 24-29 | `rand()` | `Math.floor(32768 * Math.random())` → `[0, 32767]` |

---

**End of inventory.**
