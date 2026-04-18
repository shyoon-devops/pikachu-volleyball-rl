# NOTICE: Frontend Metrics Hydration Stopgap

**Date:** 2026-04-12
**Owner:** FE (yoon)
**Severity:** P0 user-visible bug → stopgap shipped; full fix requires BE cooperation.
**Tracking doc:** companion to `docs/NOTICE-FRONTEND-BUTTON-SYNC.md` (dual-channel dispatch).

---

## User-reported bug

> "학습 그래프를 새로고침하면 이전 그래프와 **다른** 그래프가 보인다."

On page refresh, the metrics chart briefly showed a smoothed curve that did
*not* match the live curve it had shown moments earlier. Same experiment,
same timesteps, different Y values.

## Root cause

Two sources feed the same `metrics[]` array that drives the chart:

| Source | Endpoint | Granularity | X axis |
|--------|----------|-------------|--------|
| Live   | WS `training:metrics` | per-snapshot (every `log_interval` timesteps) | actual `step` |
| Hydrate on mount | REST `GET /api/training/metrics/aggregate` | **1-minute wall-clock buckets, AVG()** | bucket's `step_max` |

Live WS emits every raw snapshot reward/loss. The aggregate endpoint runs a
Mongo `$dateTrunc` + `$group` with `AVG(mean_reward, win_rate, policy_loss,
value_loss)` over 1-minute wall-clock windows and plots each bucket against
its `step_max`. For the same `(step, metric)` pair, the two sources return
**different Y values by design** — one is a snapshot, the other is the
average of all snapshots inside the enclosing minute.

Additional contributors:
- Default `since=now-6h` on the aggregate endpoint silently caps history.
- No `experiment_id` filter → cross-experiment bleed if the DB has prior runs.
- `episode` field is not preserved through aggregate.
- 10-second `@cache_ttl` on the REST response further desyncs from live.
- No dedup/sort merge on the client — hydrate + live were naively concatenated.

## Stopgap shipped (this commit)

`frontend/src/hooks/useTrainingState.ts`:
- **Removed the `getMetricsHistory()` call from the mount-seed effect.**
- Kept `getRecentGames()` and `getCurrentFrame()` hydration untouched
  (those endpoints return raw data, no divergence risk).
- Left a large `TODO(FE)` block + import placeholder comment explaining
  exactly how to re-enable hydration once the BE lands the correct
  endpoint.

User-visible effect:
- After refresh, the chart starts **empty**, then fills in from the WS as
  new snapshots stream. No more "different data after refresh" illusion.
- Downside: the first few seconds after refresh show an empty chart. This
  is the accepted tradeoff until BE lands `/timeseries` — a lying chart is
  worse than a briefly-empty one.

Tests:
- `useTrainingState.test.tsx` now asserts `GET /api/training/metrics/aggregate`
  is **not** called on mount, and `metrics-count` stays at `0` before WS
  arrives.

## Required BE change — `GET /api/training/timeseries`

Per API spec v0.2.4 (PM-approved Option A). The endpoint must return raw
per-snapshot points so the seed matches the live resolution 1:1:

```
GET /api/training/timeseries?experiment_id=<id>&since_step=<n>&limit=<n>
→ 200 { points: [{ step, episode, mean_reward, win_rate, policy_loss, value_loss, timestamp }, ...] }
```

Requirements from FE:
1. Source is the **raw snapshots collection** (same docs WS `metrics_push_loop` writes), not the aggregate bucket.
2. Plot axis is `step`, not `timestamp` — must match WS exactly.
3. Filterable by `experiment_id` (or defaults to "current running experiment" — BE to decide).
4. `since_step` for incremental backfill after reconnect.
5. No hard `since=6h` cap. If a limit is needed, bound by `limit` (point count), not wall-clock.
6. No `@cache_ttl` — or at most 1s, since this is for page restore.
7. `snake_case` payload, FE will `snakeToCamel` as usual.

## Re-enable plan on the FE

Once BE deploys `/timeseries` and confirms the payload matches the live
WS snapshots 1:1, FE will:

1. Replace the commented-out import with `getTimeseries(experimentId, sinceStep)`.
2. Add a dedup + step-sort merge so seed + live join cleanly:
   ```ts
   setMetrics(prev => {
     const byStep = new Map<number, TrainingMetrics>()
     for (const m of history) byStep.set(m.step, m)
     for (const m of prev) byStep.set(m.step, m)  // live wins on collision
     return [...byStep.values()]
       .sort((a, b) => a.step - b.step)
       .slice(-MAX_METRICS_POINTS)
   })
   ```
3. Keep `experiment_id` in sync with `status.experimentId` from `training:status`.
4. Re-enable the hydration test in `useTrainingState.test.tsx` asserting
   dedup + order on a mixed seed+live stream.

## Why not just keep the aggregate endpoint around?

The aggregate endpoint is still useful for the Evaluation panel's
long-range summary chart (different surface, explicitly labeled as a
rollup). We're not deleting it — just not using it for the live training
chart where it pretends to be the same data source.

## Contacts

- FE: yoon
- BE counterpart: backend-engineer (ping for `/timeseries` rollout ETA)
- PM: approved Option A 2026-04-12
