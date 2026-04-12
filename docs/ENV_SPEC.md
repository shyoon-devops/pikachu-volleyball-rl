# RL Environment Specification

> Updated: 2026-04-12 (anti-toss-loop reward shaping)

## Observation Space

`Box(low=-1.0, high=1.0, shape=(18,), dtype=float32)`

| Index | Field | Description | Range |
|-------|-------|-------------|-------|
| 0 | player1.x | Agent horizontal position (normalized) | [-1, 1] |
| 1 | player1.y | Agent vertical position (normalized) | [-1, 1] |
| 2 | player1.vx | Agent horizontal velocity | [-1, 1] |
| 3 | player1.vy | Agent vertical velocity | [-1, 1] |
| 4 | player1.airborne | Jumping=1, Diving=-1, Grounded=0 | {-1, 0, 1} |
| 5 | player2.x | Opponent horizontal position | [-1, 1] |
| 6 | player2.y | Opponent vertical position | [-1, 1] |
| 7 | player2.vy | Opponent vertical velocity | [-1, 1] |
| 8 | ball.x | Ball horizontal position | [-1, 1] |
| 9 | ball.y | Ball vertical position | [-1, 1] |
| 10 | ball.vx | Ball horizontal velocity | [-1, 1] |
| 11 | ball.vy | Ball vertical velocity | [-1, 1] |
| 12 | ball.dx | Ball x-delta from previous frame | [-1, 1] |
| 13 | ball.dy | Ball y-delta from previous frame | [-1, 1] |
| 14 | ball_rel_x | Ball x relative to agent (ball.x - p1.x) | [-1, 1] |
| 15 | ball_side | Ball on agent's side=1, opponent's side=-1 | {-1, 1} |
| 16 | score_diff | (score1 - score2) / MAX_SCORE | [-1, 1] |
| 17 | serving | Agent serving=1, Opponent serving=-1 | {-1, 1} |

Normalization: positions by GROUND_WIDTH(432)/GROUND_HEIGHT(304), velocities clamped to max_v=20.

## Action Space

`Discrete(12)`

| Action | x_dir | y_dir | power_hit | Effect |
|--------|-------|-------|-----------|--------|
| 0 | 0 | 0 | False | Noop |
| 1 | -1 | 0 | False | Move left |
| 2 | 1 | 0 | False | Move right |
| 3 | 0 | -1 | False | Jump |
| 4 | -1 | -1 | False | Jump left |
| 5 | 1 | -1 | False | Jump right |
| 6 | 0 | 0 | True | Power (no effect on ground) |
| 7 | -1 | 0 | True | Dive left |
| 8 | 1 | 0 | True | Dive right |
| 9 | 0 | -1 | True | Jump + power hit |
| 10 | -1 | -1 | True | Jump left + power hit |
| 11 | 1 | -1 | True | Jump right + power hit |

Auto power-hit: when agent is jumping and ball is within 60px, power_hit is forced True regardless of action.

## Reward Structure

| Signal | Value | Trigger |
|--------|-------|---------|
| Score point | +10.0 | Agent scores (resets touch/stall counters) |
| Concede point | -10.0 | Opponent scores (resets counters) |
| Win game | +20.0 | Agent reaches MAX_SCORE(15) |
| Lose game | -20.0 | Opponent reaches MAX_SCORE(15) |
| Ball touch (1st) | +3.0 | First agent touch since last net crossing |
| Ball touch (2nd) | +1.0 | Second consecutive touch on own side |
| Ball touch (3rd+) | -2.0 | 3+ consecutive touches — anti-toss-loop penalty |
| Net crossing | +2.0 | Ball crosses from agent side to opp side (resets counters) |
| Stall penalty | -0.03/frame | After 300 frames without net crossing |
| Rally timeout | -5.0 | After 600 frames without crossing → truncate episode |
| Approach ball | +0.05 | Agent moves closer to ball (ball on own side) |
| Ready position | +0.01 | Agent near court center (ball on opponent side) |

Max single-step reward: ~35.06 (score + win + touch + crossing + approach + ready)
Min single-step reward: -35.0 (concede + lose + rally_timeout)

## Anti-Toss-Loop Behavior

To prevent the agent from learning infinite self-toss exploits (repeatedly
touching the ball on its own side without sending it across the net), the
environment tracks `_consecutive_touches` and `_frames_since_crossing`:

- **Touch counter** increments on each agent ball-touch. Reward decays:
  +3.0 → +1.0 → -2.0 for 3rd and further touches in the same rally.
- **Net crossing** resets the touch counter and gives +2.0 (strengthened from
  +1.0) to strongly incentivize actually playing the point.
- **Stall timer** counts frames since last net crossing. Beyond 300 frames,
  a per-frame penalty accumulates. Beyond 600 frames, the episode is
  truncated with a -5.0 terminal penalty.
- Counters reset on: score point, concede, net crossing, env.reset().

The `info` dict returned by `step()` exposes `consecutive_touches` and
`stalled_out` for monitoring.

## Breaking Changes from Previous Version

| Item | Before | After |
|------|--------|-------|
| Observation shape | (12,) | (18,) |
| Action count | 6 | 12 |
| Ball touch reward | +1.0 | +3.0 / +1.0 / -2.0 (by consecutive count) |
| Net crossing reward | +0.5 | +2.0 |
| Approach reward | +0.02 | +0.05 |
| Time penalty | -0.005/frame | Removed |
| Court control | +0.01/frame | Removed (replaced by ready position) |
| Stall penalty | (none) | -0.03/frame after 300 frames |
| Rally timeout | (none) | Truncate + -5.0 after 600 frames |

Existing trained models are incompatible (observation/action shape mismatch). Retraining from scratch required.

## Changelog

- 2026-04-12: Anti-toss-loop reward shaping. Diminishing touch reward for
  consecutive same-side touches, strengthened net crossing to +2.0, added
  stall penalty (-0.03/frame after 300) and rally timeout (-5.0 + truncate
  at 600). Fixes agent learning to self-toss indefinitely without sending
  ball across the net.
- 2026-04-12 (earlier): Expanded observation (12→18), action (6→12),
  strengthened primary reward signals.
