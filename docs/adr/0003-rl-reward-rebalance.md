# ADR-0003: RL reward rebalance — terminal-dominant shaping

- **Status**: Accepted
- **Date**: 2026-04-12
- **Archive**: `docs/reports/notices/NOTICE-REWARD-REBALANCE.md`
- **Related**: PR #40, commit `0f32235e`

## Context

500k-step training runs produced low win rates. Root cause: over a 3,000-step episode, cumulative shaping reward (approach + ready-position + touches) reached the same magnitude as the single `±20` terminal win/loss signal. The policy gradient could not distinguish *winning* from *staying alive and wandering*. This is the classic shaping-farming pathology.

## Decision

Rebalance so **terminal swing dominates** the per-episode shaping budget:

| Signal | Old | New | Rationale |
|--------|----:|----:|-----------|
| Game win / loss | ±20 | **±50** | Terminal swing 100 now > max shaping budget (~+120 → cut below) |
| Approach ball | 0.05/f | **0.02/f** | Prevent shaping farming |
| Ready position | 0.01/f | **0.005/f** | Same |
| Stall penalty | -0.03/f | **-0.05/f** | Dead-rally cost stronger |
| Rally timeout | -5.0 | **-12.0** | Must exceed single concede (-10) |
| Offensive pressure (NEW) | — | **+0.02/f** | Ball on opponent's side + `vx > 0`, distance-decayed |

Touch 1st/2nd/3rd+ (`+3/+1/-2`), net-crossing (`+2`), score/concede (`±10`) unchanged — the f8ea6126 anti-toss work is preserved.

## Consequences

- **All prior checkpoints are invalidated** — the reward scale change makes old value functions meaningless. Trainer must restart from scratch.
- Recommended diagnostics during retraining: `info["consecutive_touches"]` distribution (toss-loop regression), `info["stalled_out"]` ratio, episode-length distribution.
- Optional reward-component logging (decompose `_compute_reward` into a component dict) left as a future improvement — useful if balance regresses again.
- Baseline target: `bot_level=1`, 500k or 1M steps, compare win rate against the pre-rebalance floor.
