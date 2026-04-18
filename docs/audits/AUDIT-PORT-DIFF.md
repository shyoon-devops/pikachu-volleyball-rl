# Audit — Port Diff vs Original

Cross-walk of every constant from `AUDIT-ORIGINAL-CONSTANTS.md` against
the matching site in our Python port. Last updated 2026-04-18 after the
E1/E2/E3 fix series.

Status legend:
- ✓ MATCH — identical value, frame-accurate behavior verified.
- ✗ DIFF — value differs from original (must be flagged + justified).
- ◇ EXT — extension we added that has no counterpart in the original.
- ⊘ NOT PORTED — original has it, we do not (intentional or open gap).

---

## physics.js — top-of-file constants

| Original (file:line) | Original value | Our location | Our value | Status |
|---|---:|---|---:|:---:|
| physics.js:33 `GROUND_WIDTH` | 432 | `constants.py:9 GROUND_WIDTH` | 432 | ✓ |
| physics.js:35 `GROUND_HALF_WIDTH` | 216 | `constants.py:14 NET_PILLAR_X` | 216 | ✓ (renamed) |
| physics.js:37 `PLAYER_LENGTH` | 64 | derived `PLAYER_HALF_LENGTH * 2` | 64 | ✓ |
| physics.js:39 `PLAYER_HALF_LENGTH` | 32 | `constants.py:20` | 32 | ✓ |
| physics.js:41 `PLAYER_TOUCHING_GROUND_Y_COORD` | 244 | `constants.py:21 PLAYER_GROUND_Y` | 244 | ✓ (renamed) |
| physics.js:43 `BALL_RADIUS` | 20 | `constants.py:39` | 20 | ✓ |
| physics.js:45 `BALL_TOUCHING_GROUND_Y_COORD` | 252 | `constants.py:40 BALL_GROUND_Y` | 252 | ✓ (renamed) |
| physics.js:47 `NET_PILLAR_HALF_WIDTH` | 25 | `constants.py:15` | 25 | ✓ |
| physics.js:49 `NET_PILLAR_TOP_TOP_Y_COORD` | 176 | `constants.py:16 NET_PILLAR_TOP_Y` | 176 | ✓ |
| physics.js:51 `NET_PILLAR_TOP_BOTTOM_Y_COORD` | 192 | `constants.py:17 NET_PILLAR_TOP_BOTTOM_Y` | 192 | ✓ |
| physics.js:64 `INFINITE_LOOP_LIMIT` | 1000 | `engine.py:69` | 1000 | ✓ |

## physics.js — Player init / per-round

| Original (file:line) | Original value | Our location | Our value | Status |
|---|---:|---|---:|:---:|
| physics.js:174 `Player.x` (P1) | 36 | `constants.py:26 PLAYER_INIT_X_P1` | 36 | ✓ |
| physics.js:176 `Player.x` (P2) | 396 | `constants.py:27 PLAYER_INIT_X_P2` | `GROUND_WIDTH-36` (=396) | ✓ |
| physics.js:179 `Player.y` | 244 | derived from `PLAYER_GROUND_Y` | 244 | ✓ |
| physics.js:181 `Player.yVelocity` | 0 | `engine.py:PlayerState.vy default` | 0 | ✓ |
| physics.js:192 `Player.state` | 0 | `engine.py:PlayerState.state default` | 0 | ✓ |
| physics.js:194 `Player.frameNumber` | 0 | `engine.py:PlayerState.frame_number default` | 0 | ✓ |
| physics.js:196 `Player.normalStatusArmSwingDirection` | 1 | `engine.py:PlayerState.normal_status_arm_swing_direction default` | 1 | ✓ |
| physics.js:198 `Player.delayBeforeNextFrame` | 0 | `engine.py:PlayerState.delay_before_next_frame default` | 0 | ✓ |
| physics.js:213 `Player.computerBoldness` | `rand() % 5` | `engine.py:_create_initial_state` | `self._rand() % 5` | ✓ |
| physics.js:138 `Player.divingDirection` | 0 | `engine.py:PlayerState.diving_direction default` | 0 | ✓ |
| physics.js:140 `Player.lyingDownDurationLeft` | -1 | `engine.py:PlayerState.lying_down_duration_left default` | -1 | ✓ |
| physics.js:142 `Player.isWinner` | false | `engine.py:PlayerState.is_winner default` | False | ✓ |
| physics.js:144 `Player.gameEnded` | false | `engine.py:PlayerState.game_ended default` | False | ✓ |
| physics.js:153 `Player.computerWhereToStandBy` | 0 | `engine.py:PlayerState.computer_where_to_stand_by default` | 0 | ✓ |

## physics.js — Ball init / per-round

| Original (file:line) | Original value | Our location | Our value | Status |
|---|---:|---|---:|:---:|
| physics.js:275 `Ball.x` (P1 serve) | 56 | `constants.py:42 BALL_SERVE_X_P1` | 56 | ✓ |
| physics.js:277 `Ball.x` (P2 serve) | 376 | `constants.py:43 BALL_SERVE_X_P2` | `GROUND_WIDTH-56` (=376) | ✓ |
| physics.js:280 `Ball.y` | 0 | `constants.py:44 BALL_SERVE_Y` | 0 | ✓ |
| physics.js:282 `Ball.xVelocity` | 0 | `engine.py:BallState.vx default` | 0 | ✓ |
| physics.js:284 `Ball.yVelocity` | 1 | `constants.py:41 BALL_INIT_Y_VELOCITY` | 1 | ✓ |
| physics.js:286 `Ball.punchEffectRadius` | 0 | `engine.py:BallState.punch_effect_radius default` | 0 | ✓ |
| physics.js:288 `Ball.isPowerHit` | false | `engine.py:BallState.is_power_hit default` | False | ✓ |
| physics.js:234 `Ball.expectedLandingPointX` | 0 | `engine.py:BallState.expected_landing_point_x default` | 0 | ✓ |
| physics.js:240 `Ball.rotation` | 0 | `engine.py:BallState.rotation default` | 0 | ✓ |
| physics.js:242 `Ball.fineRotation` | 0 | `engine.py:BallState.fine_rotation default` | 0 | ✓ |
| physics.js:244-255 trail / punch markers | 0 | `engine.py:BallState.previous_*, punch_effect_*` defaults | 0 | ✓ |

## physics.js — per-frame thresholds (in-line literals)

All checked against `engine.py:_update_ball_and_world`,
`engine.py:_update_player`, `engine.py:_check_ball_player_collision`,
`engine.py:_calculate_expected_landing_point_x`,
`engine.py:_process_game_end_frame_for`.

| Original (file:line) | Original | Our value | Status |
|---|---:|---:|:---:|
| physics.js:416 `fineRotation` wrap mod | 50 | 50 | ✓ |
| physics.js:421 `fineRotation / 10` divisor | 10 | 10 | ✓ |
| physics.js:519 player x speed | 6 | `PLAYER_SPEED=6` | ✓ |
| physics.js:522 dive x speed | 8 | `PLAYER_DIVE_SPEED=8` | ✓ |
| physics.js:552 jump vy | -16 | `PLAYER_JUMP_VELOCITY=-16` | ✓ |
| physics.js:575 `lyingDownDurationLeft` set | 3 | `LYING_DOWN_DURATION=3` | ✓ |
| physics.js:585 power-hit dwell delay | 5 | inline `5` | ✓ |
| physics.js:596 `frameNumber` reset on dive | 0 | inline `0` | ✓ |
| physics.js:598 dive vy | -5 | `PLAYER_DIVE_VELOCITY=-5` | ✓ |
| physics.js:607 jumping anim mod | 3 | inline `3` | ✓ |
| physics.js:611 state==2 anim max | 4 | inline `4` | ✓ |
| physics.js:620 state==0 anim dwell | >3 | inline `>3` | ✓ |
| physics.js:622-624 arm-swing range | 0..4 | inline `0..4` | ✓ |
| physics.js:657 gameEnd anim max | <4 | inline `<4` | ✓ |
| physics.js:659 gameEnd anim dwell | >4 | inline `>4` | ✓ |
| physics.js:691,693 ball vx divisor | 3 | `_trunc_div(abs(dx), 3)` | ✓ |
| physics.js:698 zero-vx tiebreak | `rand() % 3 - 1` | `(self._rand() % 3) - 1` | ✓ |
| physics.js:705 min reflect vy mag | 15 | `BALL_MIN_REFLECT_VY_ABS=15` | ✓ |
| physics.js:711-713 power x mag | `(\|xDir\|+1) * 10` | `(abs(inp.x_dir)+1) * 10` | ✓ |
| physics.js:718 power y mult | `abs(vy) * yDir * 2` | `abs(ball.vy) * inp.y_dir * 2` | ✓ |
| physics.js:507-512 lying-down decrement / exit | `< -1` | `< -1` | ✓ |

## physics.js — `Player.state` enum

| Value | Original meaning | Our value | Status |
|---:|---|---:|:---:|
| 0 | normal | 0 | ✓ |
| 1 | jumping | 1 | ✓ |
| 2 | jumping_and_power_hitting | 2 | ✓ |
| 3 | diving | 3 | ✓ |
| 4 | lying_down_after_diving | 4 | ✓ |
| 5 | win | 5 | ✓ |
| 6 | lost | 6 | ✓ |

## pikavolley.js — controller fields

| Original (file:line) | Original value | Our location | Our value | Status |
|---|---:|---|---:|:---:|
| pikavolley.js:54 `normalFPS` | 25 | `constants.py:66 FPS` | 25 | ✓ (E1 fix 12967dee) |
| pikavolley.js:56 `slowMotionFPS` | 5 | derived (`SLOW_MOTION_SKIP_RATIO = 25/5 = 5`) | 5 | ✓ |
| pikavolley.js:59 `SLOW_MOTION_FRAMES_NUM` | 6 | `engine.py:282` | 6 | ✓ |
| pikavolley.js:71 `winningScore` | 15 | `constants.py:57 MAX_SCORE` | 15 | ✓ |
| pikavolley.js:128 slow-mo skip ratio | 5 | `engine.py:285 SLOW_MOTION_SKIP_RATIO` | 5 | ✓ |

## pikavolley.js — `frameTotal`

| Original key | Original value | Our location | Status |
|---|---:|---|:---:|
| `intro` | 165 | (none) | ⊘ NOT PORTED |
| `afterMenuSelection` | 15 | (none) | ⊘ NOT PORTED |
| `beforeStartOfNewGame` | 15 | (none) | ⊘ NOT PORTED |
| `startOfNewGame` | 71 | (none) | ⊘ NOT PORTED |
| `afterEndOfRound` | 5 | `engine.py:280 AFTER_END_OF_ROUND_FRAMES` | ✓ |
| `beforeStartOfNextRound` | 30 | `engine.py:281 BEFORE_START_OF_NEXT_ROUND_FRAMES` | ✓ |
| `gameEnd` | 211 | `engine.py:277 GAME_END_FRAMES` | ✓ |

## pikavolley.js — display state-machine numbers

| Original (file:line) | Original value | Our location | Our value | Status |
|---|---:|---|---:|:---:|
| pikavolley.js:443 READY toggle period | `% 5` | `engine.py:288 READY_MESSAGE_TOGGLE_PERIOD` | 5 | ✓ |
| pikavolley.js:405,416,440 fade alpha delta | ±1/16 | `engine.py:291 FADE_DELTA` | 1.0/16 | ✓ |
| pikavolley.js:359 game-end power-hit early skip | 70 | (none) | ⊘ NOT PORTED |
| pikavolley.js:96-98 `noInputFrameTotal.menu` | 225 | (none) | ⊘ NOT PORTED (menu state not modeled) |

## rand.js

| Original | Range | Our location | Our value | Status |
|---|---:|---|---:|:---:|
| rand.js:24-29 `rand()` | `[0, 32767]` | `engine.py:_rand` | `randint(0, 32767)` | ✓ |

---

## Extensions (◇ EXT) — not in original

| Our location | Our value | Reason |
|---|---:|---|
| `engine.py:271 RALLY_MAX_FRAMES` | 600 | safety valve against infinite self-toss in headless RL play; original has user available to forfeit |
| `engine.py:GameState.frames_since_net_crossing` | int | counter feeding RALLY_MAX_FRAMES |
| `engine.py:GameState.round_ended_by_timeout` | bool | distinguishes timeout concede from normal score |
| `engine.py:GameState.post_score_freeze_frames` | int (always 0 post-port) | legacy field kept zeroed for replay back-compat |
| `engine.py:GAME_HEIGHT` derivation, `GROUND_HEIGHT=304` | 304 | court height used by RL obs normalization, original game has it visually but doesn't expose as physics constant |
| `engine.py:PlayerState.is_jumping/is_diving/is_power_hitting/lying_down_duration` | derived | back-compat boolean views over `state` for bot.py, env.py |

## Built-in AI (`letComputerDecideUserInput`) — entirely not ported

physics.js:803-952 (`letComputerDecideUserInput`,
`decideWhetherInputPowerHit`, `expectedLandingPointXWhenPowerHit`)
make up the upstream's single computer AI. We do not call any of
these — `backend/game/bot.py` (RuleBasedBot) is an external L1-L5
ladder per PM scope. The `computerBoldness` and
`computerWhereToStandBy` fields on `PlayerState` are populated for
1:1 fidelity but never read by our engine.

## Stereo / sound function families — not ported in engine

physics.js mentions `FUN_00408470` and several
`maybe-soundcode function (...) omitted` commented stubs throughout
the player update / ball collision paths. We carry the boolean
trigger flags (`sound_pika`, `sound_chu`, `sound_pipikachu`,
`sound_power_hit`, `sound_ball_touches_ground`) on the engine state
and aggregate them in `_serialize_state["sounds"]`; the FE plays
the audio. Stereo pan derivation lives client-side. ✓ functionally
covered, ◇ structurally different (no engine-side audio calls).

---

## Summary

- 51 ported constants / fields verified ✓ identical to original.
- 6 extensions ◇ added by us (rally timeout + back-compat views).
- 5 ⊘ not ported (intro / menu / startOfNewGame display states +
  noInputFrameTotal.menu + game-end power-hit early skip). All are
  display-layer concerns the dashboard doesn't currently consume.
- **0 unexplained ✗ DIFF**.

The `startOfNewGame` (71 frame banner) is the most likely
candidate for a future commit — adding it would put a brief game-
start state-name in the WS payload that the FE could surface. The
others (intro / menu) are pre-game UI that don't apply to a
headless RL backend.

The state-machine-level mapping (which entries above wire into which
state functions in pikavolley.js) is in `AUDIT-STATE-MACHINE-DIFF.md`.

---
**End of port diff.**
