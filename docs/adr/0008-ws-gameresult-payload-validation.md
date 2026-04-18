# ADR-0008: Validate `game:result` WS payloads against the full `GameRecord` schema

- **Status**: Accepted
- **Date**: 2026-04-12
- **Severity**: MEDIUM (user-visible; FE shipped defensive fallback)
- **Archive**: `docs/reports/notices/NOTICE-BE-GAMERESULT-MISSING-FIELDS.md`

## Context

Dashboard "Recent Games" rendered bot-level cells as a bare `"L"` (no number). Trace: the training-loop callback enqueued a dict missing `bot_level`, `experiment_id`, and `rally_count`. The broadcast path constructed a validated `GameRecord` locally — but then broadcast the **raw, unvalidated** dict (`manager.broadcast({..., "payload": data})`) to FE. `.get(..., default)` fallbacks silently swallowed the missing fields, so consumers saw `bot_level = 1` but the FE correctly detected `undefined` and rendered only the `L` prefix. The validated `GameRecord` was built but not used.

## Decision

Two-part fix:

1. **Producer side** (`backend/rl/callbacks.py`): the enqueued dict must carry `experiment_id`, `bot_level`, and `rally_count`. These are known at enqueue time — no excuse to omit them.
2. **WS broadcast side** (`backend/app/ws/handlers.py`): broadcast the serialised `GameRecord`, not the raw dict. Shape: `await manager.broadcast({"type": "game:result", "payload": record.model_dump()})`. Any future missing field fails Pydantic validation and logs loudly instead of silently defaulting.

Remove all `.get(field, default)` fallbacks in the `GameRecord` construction path for required fields — required means required.

## Consequences

- FE can now trust `game:result.payload` matches the `GameRecord` Pydantic schema; defensive `??` fallbacks for `bot_level` / `rally_count` can be removed after verification.
- Any callback that enqueues incomplete results will throw at validation instead of polluting the WS feed with ghosts.
- This is the pattern for *all* WS payloads: validate on producer, serialise the validated model, never broadcast raw dicts. Other handlers should be audited against this rule in a follow-up.
