# API Reference — changes in v1.0.0

> **Baseline**: v0.2.5 (`cd1e6a39`)
> **Target**: v1.0.0 (`547ff663`)
> **Scope**: Changes to REST + WS + MongoDB schemas since v0.2.5

This document captures every API surface change that landed in the v1.0.0 cycle. Full endpoint list is served live from `/docs` (FastAPI OpenAPI) on any running backend. Authoritative source-of-truth for field shapes is `backend/app/models/*.py` and `backend/app/api/*.py`.

## 1. New REST Endpoints

### Training runs aggregation

`GET /api/training/runs` (BE-T4 + BE-T10)
— List training runs aggregated by title. Each entry carries hyperparam snapshot (10 fields) + game/eval counts + latest timestamps. Powers the `/runs` top-level list.

- Response shape: `list[RunEntry]` with `title`, `experiment_id`, `started_at`, `last_seen_at`, `games_count`, `evaluations_count`, `hyperparams: {lr, gamma, clip_range, batch_size, n_envs, n_epochs, n_steps, total_timesteps, ent_coef, gae_lambda}`, `bot_level`

`GET /api/training/runs/{title}` (BE-T4)
— Single run detail. Same shape as list entries plus `games: [GameRecord]` and `evaluations: [EvaluationRecord]`.

### Training titles autocomplete

`GET /api/training/titles`
— Recent-first distinct list of titles seen in MongoDB. Powers HyperparamForm autocomplete.

### Metrics timeseries

`GET /api/training/timeseries` (superseded v0.2.5's `/metrics/timeseries` — moved to `/training/timeseries` for consistency)
— Returns `{step, value, timestamp}` points. Default limit 10000 (was 1000 in v0.2.5).

### Evaluation

`POST /api/evaluation/run` (202 Accepted)
— Kick off async evaluation job. Returns `{job_id, status: "queued"}`. Non-blocking.

`GET /api/evaluation/status/{job_id}`
— Poll job status. States: `queued | running | succeeded | failed`. On success includes `result: EvaluationRecord`; on failure includes `error`.

`GET /api/evaluation/results`
— Historical evaluation results with backfilled `title` for legacy records (BE-T12).

### Evaluation persistence (PR #44)

`POST /api/evaluations`
— Insert a new evaluation record. Returns `{id, inserted_at}`.

`GET /api/evaluations` (list)
— Filterable: `?model_path=`, `?bot_level=`, `?limit=`. Sort: newest first.

`GET /api/evaluations/{record_id}`
— Single record by id.

`GET /api/evaluations/checkpoints`
— Distinct `checkpoint_label` values across stored evaluations.

`GET /api/evaluations/timeseries`
— Time-series points for a given metric across (model_path, bot_level) keys. Includes `training_step` + `checkpoint_label` for x-axis annotation.

### Models management

`GET /api/models`
— List models. New in v1.0: `?title=<slug>` filter + enriched fields (size, last_modified, associated `experiment_id`).

`DELETE /api/models` (BE-T9)
— Bulk delete with `{paths: [str], confirm: true}` body. **Active-run protection**: returns 409 Conflict if any target is the currently training model.

## 2. Changed REST Endpoints

### Preserved with field additions

`GET /api/games`
— Response `GameRecord[]` now includes `env_id`, `title`, `episode` fields (see §5). Legacy records missing these fields are still returned with `null` values.

`GET /api/training/status`
— Unchanged shape, but `bot_level`/`experiment_id`/`started_at` fields (added in v0.2.4) remain stable contracts.

### Timeout changes

`POST /api/evaluation/run`
— nginx `proxy_read_timeout` extended (`56d7473b`) because long evaluations could exceed the default. Now uses async pattern so timeout pressure is reduced.

### Rate limit changes

All `/api/*` endpoints
— Rate limiter now honors `X-Forwarded-For` header (`6c1baaea`). Normal SPA burst traffic (`/history`, `/runs` navigation) no longer triggers 429. Burst size enlarged for SPA (`7ab12372`).

## 3. New WebSocket Events

All events emit from `/ws` channel, serialized with serialize-once fan-out.

### `training:game_end` (BE-T7)

Fires after every `GameRecord` insert. FE prepends into live history without a full refresh.

```ts
{
  type: "training:game_end",
  data: GameRecord  // includes env_id, title, episode, rally_count
}
```

### `training:env_frame`

Per-env frame broadcast for batch tabs multi-env live view.

```ts
{
  type: "training:env_frame",
  data: {
    env_id: string,    // "0".."7" or "demo"
    frame: FrameState  // same shape as training:frame
  }
}
```

### Existing events — field additions

`training:frame` — `FrameState.players[i]` now includes:
- `diving_direction: -1 | 0 | 1` (`4a57ddb9`) — FE renders state 3/4 pose flip
- `state: 0..4` — player state machine index (0=idle, 1=normal, 2=jumping, 3=diving, 4=grounded)
- `is_winner: boolean` — only set during `game_ended` freeze window

`training:frame` — `FrameState.ball` now includes:
- `punch_effect_x`, `punch_effect_y`, `punch_effect_radius` (`982e3a80` + `743dc8ae`) — ground/power-hit white ring, server-authoritative
- `is_power_hit: boolean` (v0.2.4) — hyper-ball trail flag

`training:frame` — `FrameState.sfx` (new, `a5cd5df0`):
- Per-frame SFX flags as booleans: `{ball_hit, ball_net, ball_ground, punch, pi_pikachu}` (5 flags; `pi` and `pikachu` dropped from scope)

`training:game_end` — data includes `game_ended: boolean` and `winpose_frame` index during gameEnd freeze

### WS runtime validation (A6)

Training WS messages are validated at FE runtime via zod (`daf38ad9`). Failed parse is **log-only** — the message is still dispatched to preserve liveness. The validator shape lives in `frontend/src/ws/schemas.ts` with a discriminated union on `type`.

## 4. MongoDB Schema Changes

### `games` collection — added fields

```python
class GameRecord(BaseModel):
    # existing: id, game_id, experiment_id, timestamp, bot_level,
    #           score1, score2, winner, duration_frames, rally_count

    # v1.0.0 additions:
    env_id: str | None = None       # "0".."7" or "demo"; legacy → None
    title: str | None                # ≤60 chars; legacy → None  (BE-T1)
    episode: int | None              # ≥0; legacy → None  (BE-T6)
```

Indexes (BE-T3):
- Compound `(title, timestamp desc)` for /runs filter + recent-first
- Existing `(experiment_id, timestamp)` retained

### `evaluations` collection — added fields

```python
class EvaluationCreate(BaseModel):
    # existing: model_path, bot_level, n_games, win_rate, avg_score,
    #           avg_opponent_score, avg_rally_length, avg_episode_length,
    #           timestamp, dominance_score, checkpoint_label, training_step

    # v1.0.0 additions:
    title: str | None                # BE-T11
    experiment_id: str | None        # BE-T11 — backfill via /api/evaluation/results (BE-T12)
```

### Migration

Legacy docs without `title`/`experiment_id`/`episode` are backward-compatible — all new fields are `Optional` with `None` default. One-shot batch update:

```bash
docker compose exec backend python -m backend.scripts.migrate_games_bot_level --mode=title-backfill
```

Read path also auto-injects `title` when responding from `/api/evaluation/results` (BE-T12, `9fc59022`).

## 5. Breaking Changes

### URL routes

- `/history` and `/evaluation` (top-level FE routes) removed — replaced by `/runs` with `?tab=overview|games|evaluation`
- External bookmarks to the old paths will 404; redirect candidate for v1.0.1 hotfix
- Internal FE router changes only — no backend route names removed

### Response shape additions

- `GameRecord` and `EvaluationRecord` gained optional fields. No field was renamed or removed. Downstream consumers that do strict schema validation should add the new fields as optional on their end

### Known inconsistency

- `?tab=evaluation` vs `?tab=eval` URL query token inconsistency — known issue for v1.0.1 hotfix. Canonicalize to `?tab=evaluation` + add `eval → evaluation` redirect

## 6. Deprecations

Deprecated in v1.0.0 — **will be removed in v2.x**:

- FE top-level routes `/history`, `/evaluation` — use `/runs?tab=games|evaluation`
- FE component `TrainingRunDetail` — replaced by `UnifiedRunDetail` (already deleted in A4 dead-code sweep, `31b30301`)
- FE API exports `getGame` and `getMetricsHistory` — unused (already deleted `5a0f0aca`)
- Helper `PikaAudio.__resetPikaAudioForTests` — unused (deleted `464f2fa6`)
- BE route arg `seen_traversal_or_invalid` in `delete_models` — unused flag (deleted `70ae1162`)

## 7. Security-relevant changes

- **Bulk delete active-run protection** (`dc80b557`) — `DELETE /api/models` returns 409 if any target path is the currently training model
- **Rate limit XFF honor** (`6c1baaea`) — prevents shared-NAT false-429 against normal users
- **WS runtime validation via zod** (`daf38ad9`) — server shape changes are detected and logged client-side rather than silently corrupting UI
- **No new authentication surface** — all APIs continue to run behind the existing nginx proxy; auth is deferred to v2.x (no change from v0.2.5)

## References

- `backend/app/api/routes.py` — main REST handlers
- `backend/app/api/evaluations.py` — `/evaluations` CRUD
- `backend/app/models/schemas.py` — GameRecord + related
- `backend/app/models/evaluation.py` — EvaluationCreate + EvaluationRecord
- `backend/app/ws/handlers.py` — WebSocket dispatch
- `frontend/src/ws/schemas.ts` — zod validation schema (A6)
- [CHANGELOG.md § 1.0.0](../CHANGELOG.md#100---2026-04-19)
- [RELEASE-NOTES-v1.0.0.md](RELEASE-NOTES-v1.0.0.md)
