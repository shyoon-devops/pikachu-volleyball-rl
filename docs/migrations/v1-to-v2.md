# Migration guide — v1.0.0 → v2.0.0

> **Status**: Default-safe. Skipping the optional backfill scripts keeps v1 behavior intact.
> **Breaking changes**: None. All new fields default to v1 values.

## Summary

v2.0.0 adds five selectors to the training pipeline (Opponent mode, reward model, policy type, algorithm, sampling strategy). Every selector defaults to the v1 behavior:

| Field | v1 implicit value | v2.0 default | Location |
|-------|-------------------|--------------|----------|
| `training_mode` | `rule_ladder` | `rule_ladder` | `training:start` payload, run record |
| `opponent_sampling` | `uniform` | `uniform` | `training:start`, run record |
| `reward_model` | shaped (9-term) | `shaped_v1` | `training:start`, run record |
| `policy_type` | MLP | `mlp_v1` | `training:start`, run record |
| `algorithm` | PPO | `ppo` | `training:start`, run record |

An existing v1 run that is loaded into v2 gets None/undefined for these fields; the dashboard treats that as equivalent to the defaults above (renders a dash in chips, falls back to v1 semantics when replaying).

## 1. Existing run records — backfill (optional)

The v2 dashboard shows algorithm / reward_model / policy_type chips on the run list and drill-down. For pre-v2 runs, those chips render as `—`. If you want a clean view with explicit defaults backfilled:

```bash
docker compose exec backend python -m backend.scripts.migrate_games_bot_level \
  --mode=v1-to-v2-defaults
```

This script sets `reward_model=shaped_v1`, `policy_type=mlp_v1`, `algorithm=ppo`, `training_mode=rule_ladder` on every run document that has `None` for those fields. Idempotent — safe to re-run.

## 2. League pool seed (optional, recommended)

To populate the self-play league with your existing v1 PPO checkpoints so they're available as sampled opponents:

```bash
docker compose exec backend python -m backend.scripts.seed_league_from_v1_models
```

What it does:
- Scans `models/<experiment_id>/*.zip`
- Inserts each as a `LeagueCheckpoint` with `source="v1_legacy"`, `elo=1000.0` (unranked seed)
- Unconditionally inserts anchor rows: L1=600, L3=900, L5=1200 (never rated, absolute corridor)
- Writes to both `models/league/manifest.json` and MongoDB `league_checkpoints`

First self-play training run after seeding will start ranking the v1_legacy entries based on actual match outcomes.

## 3. WebSocket payload compatibility

No WS event names changed. New fields are additive:

- `training:start` — v2 adds `training_mode`, `opponent_sampling`, `reward_model`, `policy_type`, `algorithm`. All optional; v1 clients emitting `training:start` without them continue to work (BE defaults each).
- `training:update_start` / `training:update_end` — new events for PPO gradient phase overlay. Not emitted by v1 backends. v2 FE has a heuristic fallback (frame-stall detection) so mixed v1-BE / v2-FE still renders correctly.
- `training:league_update` — new event broadcast during self-play. v1 FE ignores unknown event types safely.

## 4. Checkpoint compatibility

| Saved in | Loadable in PPO | Loadable in SAC | Loadable in Dreamer V3 |
|----------|:---------------:|:---------------:|:----------------------:|
| PPO + MLP | ✅ | ❌ arch mismatch | ❌ different format |
| PPO + LSTM (v2 S3) | ❌ arch mismatch | ❌ | ❌ |
| SAC (v2 S4) | ❌ | ✅ | ❌ |
| Dreamer V3 (v2 S5) | ❌ different format | ❌ | ✅ |

Implications:
- Your existing v1 PPO/MLP checkpoints continue to work in v2 PPO runs unchanged
- Migrating a specific run from PPO → SAC (or → Dreamer) is a fresh-start train, not a transfer
- League pool entries record their `source` so the dashboard can render the lineage badge correctly

## 5. Breaking changes

**None.** This migration has no required steps.

If you do run the backfill scripts in §1-2, they're idempotent and safe. If you skip them, your dashboard simply shows `—` chips for pre-v2 runs and an empty league pool until your first self-play run seeds it naturally.

## References

- [docs/release-notes/RELEASE-NOTES-v2.0.md](../release-notes/RELEASE-NOTES-v2.0.md)
- [docs/retrospective/v2.x-retrospective.md](../retrospective/v2.x-retrospective.md)
- [ADR-0014 self-play league](../adr/0014-self-play-league.md) — migration §8 details
- Backfill scripts: `backend/scripts/migrate_games_bot_level.py`, `backend/scripts/seed_league_from_v1_models.py`
