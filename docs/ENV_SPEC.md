# RL Environment Specification

> Commit: 5a5def9 (dev) | Updated: 2026-04-12

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
| Score point | +10.0 | Agent scores |
| Concede point | -10.0 | Opponent scores |
| Win game | +20.0 | Agent reaches MAX_SCORE(15) |
| Lose game | -20.0 | Opponent reaches MAX_SCORE(15) |
| Ball touch | +3.0 | Agent hits ball (vy-flip detection) |
| Net crossing | +1.0 | Ball crosses from agent side to opponent side |
| Approach ball | +0.05 | Agent moves closer to ball (ball on own side) |
| Ready position | +0.01 | Agent near court center (ball on opponent side) |

Max single-step reward: ~34.06 (score + win + touch + crossing + approach + ready)
Min single-step reward: -30.0 (concede + lose)

## Breaking Changes from Previous Version

| Item | Before | After |
|------|--------|-------|
| Observation shape | (12,) | (18,) |
| Action count | 6 | 12 |
| Ball touch reward | +1.0 | +3.0 |
| Net crossing reward | +0.5 | +1.0 |
| Approach reward | +0.02 | +0.05 |
| Time penalty | -0.005/frame | Removed |
| Court control | +0.01/frame | Removed (replaced by ready position) |

Existing trained models are incompatible (observation/action shape mismatch). Retraining from scratch required.
