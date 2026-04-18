# Audit — State-Machine Cross-Walk

The original game has two parallel state machines:

1. `pikavolley.js` controller states — game-loop-level
   (intro/menu/round/gameEnd…). Each is a function the loop calls
   once per frame.
2. `physics.js` `Player.state` — per-player physics state (0-6).

This document cross-walks every transition in both layers against our
Python port and flags any drift. Companion docs:
`AUDIT-ORIGINAL-CONSTANTS.md`, `AUDIT-PORT-DIFF.md`.

---

## Layer 1: pikavolley.js controller state machine

### State graph (original)

```
intro (165f) ──pwr/timeout──▶ menu (≤225f auto)
                                    │
                                    ▼
                             afterMenuSelection (15f)
                                    │
                                    ▼
                             beforeStartOfNewGame (15f)
                                    │
                                    ▼
                             startOfNewGame (71f) ──▶ round
                                                       │ ┌──────────────┐
                                                       │ │              │
                                                       │ ▼              │
                                                       ▼ slow-mo (6 physics ticks at 1/5)
                                                       │ │              │
                          ╔═══ score, mid-match ════════│═┤              │
                          ║                              │              │
                          ▼                              │              │
                   afterEndOfRound (5f fade out)         │              │
                          │                              │              │
                          ▼                              │              │
                   beforeStartOfNextRound (30f ramp,     │              │
                       READY blink every 5f) ────────────│──────────────┘
                                                          │
                          ╔═══ score, MAX_SCORE ══════════│
                          ║
                          ▼
                       gameEnd (211f) ──▶ intro
```

### Our port (display mode only — `display_state_machine=True`)

```
                       (engine starts in 'round')
                                    │
                                    ▼
                                 round
                                    │ ┌──────────────┐
                                    │ │              │
                                    ▼ │              │
                         (mid-score) slow-mo (6 physics × 5 skip)
                                    │ │              │
                                    ▼ │              │
                            afterEndOfRound (5f fade-out, no physics)
                                    │ │              │
                                    ▼ │              │
                       beforeStartOfNextRound (30f, READY blink every 5f, no physics)
                                    │              ──┘
                                    │
                       ╔══(MAX_SCORE)══╗
                                    ▼
                                 gameEnd (211f, physics keeps running, players state=5/6)
                                    │
                                    ▼
                           (state pinned, no further transitions)
```

### Transition cross-walk

| Original transition (pikavolley.js) | Ported behavior (engine.py) | Status |
|---|---|:---:|
| `intro` (165f) → `menu` | not ported (engine starts in `round`) | ⊘ |
| `menu` selection → `afterMenuSelection` | not ported | ⊘ |
| `afterMenuSelection` (15f fade-out) → `beforeStartOfNewGame` | not ported | ⊘ |
| `beforeStartOfNewGame` (15f) → `startOfNewGame` | not ported | ⊘ |
| `startOfNewGame` (71f banner) → `round` | not ported | ⊘ |
| `round` runs `physics.runEngineForNextFrame` every frame (line 346) | `engine.step()` runs physics same way | ✓ |
| `round` mid-match score → `slowMotionFramesLeft = 6`, `roundEnded = true`, stays in `round` (lines 396-400) | `_handle_scoring` arms `slow_motion_frames_left = 6` in display mode | ✓ |
| `gameLoop` slow-motion: `slowMotionNumOfSkippedFrames % 5 !== 0` skips physics (lines 124-135) | `step()` slow-motion block: `slow_motion_skip_counter % 5 != 0` returns early | ✓ |
| Slow-mo expiry + `roundEnded` → fade += 1/16, `state = afterEndOfRound` (lines 402-408) | post-physics block in `step()` flips `state_name='afterEndOfRound'` and ticks fade once | ✓ |
| `afterEndOfRound` (5f, fade += 1/16) → `beforeStartOfNextRound` (lines 411-422) | `_tick_after_end_of_round` matches frame-by-frame | ✓ |
| `beforeStartOfNextRound` frame 0: fade → 1.0, init players + ball (lines 429-437) | `_tick_before_start_of_next_round` frame 0 sets fade=1.0, replaces player1/player2/ball | ✓ |
| `beforeStartOfNextRound` per-frame: fade −= 1/16, blink READY at `% 5` (lines 439-444) | `_tick_before_start_of_next_round` matches | ✓ |
| `beforeStartOfNextRound` (30f) → `round` (lines 447-453) | matches: state_name='round', flags reset, frames_since_net_crossing=0 | ✓ |
| `round` MAX_SCORE → `gameEnded=true`, isWinner/isLoser flagged on both players (lines 377-393) | `_handle_scoring` sets `is_game_ended=True`, `player.is_winner` / `player.game_ended` on both | ✓ |
| `round` during gameEnded: `drawGameEndMessage`, `frameCounter++`, exit at `>=211` or `>=70 + powerHit` (lines 354-366) | `step()` increments `game_end_frame_counter`; match-over guard returns at `>= GAME_END_FRAMES`. **Power-hit early-skip (70f) NOT ported** — minor display-only escape hatch | ⊘ (early-skip only) |
| `gameEnd` exit → `state = intro` | engine pins state forever (no intro to return to in headless) | ✓ (functionally equivalent) |

### Display-state-machine subtotal

- 8 transitions ✓ ported and verified.
- 5 transitions ⊘ not ported (all are pre-`round` UI states the
  headless engine doesn't expose).
- 1 partial ⊘ (game-end power-hit early-skip — purely a UX escape).
- 0 ✗ unexplained drift.

---

## Layer 2: physics.js `Player.state` transitions

### State enum (recap)

```
0 = normal idle
1 = jumping
2 = jumping_and_power_hitting
3 = diving
4 = lying_down_after_diving
5 = win pose
6 = lose pose
```

### Transition cross-walk

| Trigger | Original (physics.js) | Our port (engine.py) | Status |
|---|---|---|:---:|
| `state=4` lying-down decrement / exit | lines 507-512: `lyingDownDurationLeft += -1`; `if < -1 → state=0` | lines 681-687 (post-game-end-NOOP-guard): identical decrement + same `< -1` exit | ✓ |
| `state<3 && yDir==-1 && y==ground` → `state=1` (jump) | lines 547-558: vy=-16, state=1, frameNumber=0 | lines 718-722: same vy/state/frame transition | ✓ |
| `state=3` lands → `state=4`, ldl=3 | lines 571-575: triggered in gravity-branch `else if (futurePlayerY > ground)` | lines 738-741: same trigger and same field sets | ✓ |
| `state=1 && powerHit` → `state=2`, delay=5, frame=0 | lines 581-587 | lines 751-754: identical | ✓ |
| `state=0 && powerHit && xDir!=0` → `state=3`, vy=-5, divingDirection=xDir | lines 593-603 | lines 755-759: identical | ✓ |
| `state=1` per-frame anim: `frameNumber = (frameNumber+1) % 3` | lines 606-607 | lines 776-777: identical | ✓ |
| `state=2` per-frame anim: delay tick, `frameNumber+=1`, `>4 → state=1, frame=0` | lines 608-617 | lines 778-784: identical | ✓ |
| `state=0` per-frame anim: dwell 3, arm-swing in [0..4] | lines 618-631 | lines 785-797: identical | ✓ |
| `gameEnded && state==0` → state=5 (winner) or 6 (loser), frame=0, delay=0 | lines 633-647 | lines 800-808: identical, plus calls `_process_game_end_frame_for` | ✓ |
| `processGameEndFrameFor`: if `frameNumber<4`, dwell 4, frame+=1 | lines 656-663 | `_process_game_end_frame_for` (engine.py): identical | ✓ |
| **NEW (E3 2026-04-18)** game-ended input neutralization | NOT in original (UI-driven games naturally don't spam input post-game-end; built-in AI happens to settle to NOOP) | engine.py top of `_update_player`: `if player.game_ended: inp = NOOP` | ◇ EXT (intentional, see E3 commit message) |

### Per-player-state subtotal

- 10 transitions ✓ ported and verified frame-accurate.
- 1 ◇ extension (E3 input neutralization — necessary for symmetric
  behavior across bot vs RL agent control sources, original doesn't
  need it because all upstream input sources are well-behaved).
- 0 ✗ unexplained drift.

---

## Cross-cutting: `physicsEngine` ordering (FUN_00403dd0)

physics.js:303-371 fixes the per-frame execution order:

1. `processCollisionBetweenBallAndWorldAndSetBallPosition` (line 305)
2. For each player: `calculateExpectedLandingPointXFor` + `processPlayerMovementAndSetPlayerPosition` (lines 309-330)
3. For each player: `isCollisionBetweenBallAndPlayerHappened` + (if first frame in box) `processCollisionBetweenBallAndPlayer` (lines 337-364)

Our `engine.step()` runs the same sequence in the same order (with
the slow-motion skip and game-end input neutralization layered on
top). ✓ MATCH.

---

## Summary

| Layer | ✓ ported | ◇ extension | ⊘ not ported | ✗ unexplained |
|---|---:|---:|---:|---:|
| pikavolley.js controller transitions | 8 | 0 | 6 | 0 |
| physics.js `Player.state` transitions | 10 | 1 | 0 | 0 |
| `physicsEngine` ordering | 1 | 0 | 0 | 0 |
| **Total** | **19** | **1** | **6** | **0** |

All 6 ⊘ entries are pre-`round` UI states (intro / menu /
afterMenuSelection / beforeStartOfNewGame / startOfNewGame) plus the
gameEnd power-hit early-skip — none impact gameplay frame fidelity
once the engine enters the `round` state.

The single ◇ extension (E3 input neutralization) is necessary
because our engine has heterogeneous input sources (RL agent +
RuleBasedBot + future human) where the original only had built-in
AI + keyboard, both of which naturally became no-op during gameEnd.

---
**End of state-machine diff.**
