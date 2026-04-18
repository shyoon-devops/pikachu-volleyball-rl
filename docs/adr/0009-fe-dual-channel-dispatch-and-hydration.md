# ADR-0009: FE dispatches commands on both WS + REST, and hydrates state on mount / reconnect

- **Status**: Accepted
- **Date**: 2026-04-12
- **Archives**: `docs/reports/notices/NOTICE-FRONTEND-BUTTON-SYNC.md`, `docs/reports/notices/NOTICE-FRONTEND-METRICS-HYDRATION.md`, `docs/reports/notices/NOTICE-FRONTEND-STATUS-SYNC.md`

## Context

User-reported CRITICAL bugs on dev clustered around four symptoms: (1) Stop/Pause buttons appeared dead, (2) refresh replaced a live-looking metrics chart with a *different* smoothed curve, (3) refresh during a running session rendered a Start button (no Stop), (4) bot-level buttons didn't reflect selection. Root causes split three ways:

- **Command dispatch**: all UI actions went through WS. If the WS path missed a message (reconnect race, server-side drop) the command was lost.
- **Status hydration**: `useTrainingState` hard-coded initial status to `stopped`; WS `training:status` broadcasts only on *change*, so a refresh into a running session saw no broadcast and stayed stuck at `stopped`.
- **Metrics hydration**: the live WS feed and the REST `GET /api/training/metrics/aggregate` endpoint returned *different Y values by design* — live is raw snapshots, REST is `AVG(...)` over 1-minute `$dateTrunc` buckets. Same `(step, metric)` → two different numbers. User saw a chart "change" on every refresh.

## Decision

Unify FE state management around three rules:

1. **Dual-channel command dispatch**: `useTrainingState.send()` fires **both** the WS message and an idempotent REST call (`POST /api/training/stop|pause|resume`, `PATCH /api/training/level`). Either side landing is enough. REST failures are swallowed; the WS path + optimistic UI update keep the user in sync.
2. **Status hydration**: on mount and on every WS `connected` transition, call `GET /api/training/status` once and apply it. This solves the "Start button on refresh of a running session" regression.
3. **Metrics hydration parity**: do not mix raw-snapshot data with server-side `AVG()` buckets in the same chart series. Either the aggregate endpoint returns raw snapshots (no `$group`), or the FE plots hydrated history separately from live-feed tail. Matching the two axes requires both sources to use the same granularity and the same `since=` window semantics.

## Consequences

- WS remains the authoritative real-time channel; REST becomes the redundant path + hydration surface. No single-point-of-failure for UI commands.
- Producers must guarantee REST handlers are **idempotent** — replaying a `POST /api/training/stop` on an already-stopped run must not error.
- Any new command added to the UI inherits the dual-channel contract; adding it only to WS is a regression waiting to happen.
- The metrics endpoint requires a follow-up: keep a `raw=true` query flag or split into `/metrics/live` + `/metrics/bucketed` so FE can pick explicitly. Tracking separately.
