# NOTICE — Frontend Button Sync (API spec v0.2.4 integration)

**Audience:** Backend engineer, DevOps, PM
**From:** Frontend engineer (`yoon/frontend-engineer`)
**Date:** 2026-04-12

## Summary

User-reported critical bugs on dev (`http://192.168.0.248:3000/`):

1. **Stop** button doesn't reflect in UI
2. **Pause** button doesn't do anything
3. **Refresh wipes graph + recent games** (seeded from empty state)
4. **Bot Level** buttons don't indicate the current selection, clicks feel dead

Frontend fix landed on `yoon/frontend-engineer` → `dev` with the commit
`fix(ui): optimistic Stop/Pause/level + REST hydration for graphs/games (CRITICAL)`.

## What the frontend now does

### Dual-channel command dispatch

`useTrainingState.send()` fires **both** the REST command and the WS
message, so whichever path is live lands the command. Each backend
handler is idempotent on training state.

| UI action | WS message | REST call (new) |
|-----------|------------|-----------------|
| Stop click | `training:stop` | `POST /api/training/stop` |
| Pause click | `training:pause` | `POST /api/training/pause` |
| Resume click | `training:resume` | `POST /api/training/resume` |
| Bot level click | `training:set_level` | `PATCH /api/training/level` |

REST failures (404 before deploy, 5xx) are caught and swallowed — the
WS path plus the optimistic UI update keep the user in sync. **No user-
visible error is raised** if REST 404s.

### Optimistic UI

The moment a button is clicked, local state flips:

- Stop → `state: 'stopped'`
- Pause → `state: 'paused'`
- Resume → `state: 'running'`
- Level N → `botLevel: N`

Backend's echoed `training:status` broadcast (when it arrives) reconciles
the optimistic value with the authoritative state.

### REST hydration on mount

| Endpoint | Purpose |
|----------|---------|
| `GET /api/training/status` | Header + primary CTA (Start/Stop/Pause) reflects reality after refresh |
| `GET /api/training/metrics/aggregate?bucket=1m` | Seeds MetricsChart so graph isn't empty after refresh |
| `GET /api/games?limit=20` | Seeds "Recent Games" panel |
| `GET /api/training/current_frame` | Seeds GameCanvas (pikachu/ball/score) so canvas isn't blank after refresh |

All four are best-effort. Failures are silent — WS takes over as soon
as it connects.

### Reconnect re-sync

On every WS reconnect (`connectionState → 'connected'`), we re-fetch
`/api/training/status` because WS broadcasts `training:status` only on
state change. Without the re-probe, a mid-session reconnect could leave
the UI stuck on stale state.

## What we need from Backend (API spec v0.2.4)

These are the new endpoints the frontend now calls. Until they land,
the WS handlers keep the primary functionality working (except
`training:pause`, which has no WS handler either).

### HIGH priority

1. **`POST /api/training/stop`** — execute stop (204 on success)
2. **`POST /api/training/pause`** — execute pause (204 on success). *Also*
   add the corresponding WS `training:pause` handler — currently there
   is none, so the pause intent is literally a no-op on the backend
   today. The frontend optimistic 'paused' state is **cosmetic** until
   one of the two handlers ships.
3. **`POST /api/training/resume`** — execute resume (204 on success)
4. **`PATCH /api/training/level`** — body `{level: 1-5}`, response `{level}`
5. **`GET /api/training/status` response must include `bot_level`** so
   the active L1-L5 indicator is correct on first paint (currently the
   highlight only appears after the user clicks; a refresh resets it).

### MEDIUM priority

6. **`GET /api/training/current_frame`** — returns the latest game
   frame (same shape as WS `training:frame` payload) or 404/null when
   training isn't running. Frontend fetches on mount to restore the
   game canvas immediately after refresh instead of waiting for the
   first WS frame (~30ms).

## What we need from DevOps

After BE lands the new endpoints **and** this FE branch merges to
`dev`: rebuild + redeploy `dev` so the four bugs can be re-verified
end-to-end.

Current FE fix already works partially without the new REST endpoints:

- Stop/Pause/Resume/Level now update the UI instantly (optimistic)
- Refresh restores status, graph, recent games, **and** the game canvas
  (once BE `current_frame` ships — otherwise canvas is blank until first
  WS frame)
- Bot Level highlights the clicked level (optimistic); the *persistent*
  highlight after refresh waits on BE adding `bot_level` to
  `/api/training/status`

## Rollback

If the dual-channel dispatch surprises the backend (e.g., BE executes a
command twice because both WS and REST fire), revert
`frontend/src/hooks/useTrainingState.ts` `send()` to the WS-only
version — the optimistic UI and REST hydration stay intact; only the
command-dispatch path regresses.

## Related files

- `frontend/src/hooks/useTrainingState.ts` — `send()` wrapper + REST hydration effects
- `frontend/src/lib/api.ts` — new `stopTraining`, `pauseTraining`,
  `resumeTraining`, `patchTrainingLevel`, `getCurrentFrame`,
  `getRecentGames`, `getMetricsHistory`
- `frontend/src/components/dashboard/TrainingControls.tsx` — bot level
  active-state CSS/aria wiring
- `frontend/src/hooks/useTrainingState.test.tsx` — 16 tests covering
  REST sync, hydration, optimistic dispatch, graceful fallback,
  current_frame hydration
- `frontend/src/components/dashboard/TrainingControls.test.tsx` —
  active-state indicator tests
