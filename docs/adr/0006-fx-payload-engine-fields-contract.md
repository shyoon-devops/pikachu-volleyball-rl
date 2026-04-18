# ADR-0006: Engine FX and freeze-frame fields — WS payload contract

- **Status**: Accepted
- **Date**: 2026-04-12
- **Archive**: `docs/reports/notices/NOTICE-ENGINE-FIELDS-ON-DEV.md`, `docs/reports/notices/NOTICE-FX-PAYLOAD-READY.md`

## Context

The designer's D11-D15 CSS overlays (dive trail, punch ring, power ring, post-score freeze flash) depended on engine state that wasn't exposed on the WS frame payload. The physics port landed the raw fields on `dev`, but without a single source-of-truth document FE could not safely read them and BE could not reason about replay back-compat. Two NOTICE files were emitted in parallel covering the same contract from BE-producer and FE-consumer angles — this ADR merges them into one.

## Decision

The following fields are now **part of the stable WS frame contract** and reused by replay frames:

**`frame.ball.*`**
- `is_power_hit` (bool) — one-frame rising edge on power-hit collision.
- `punch_effect_x / _y` (int) — effect centre in canvas pixels.
- `punch_effect_radius` (int) — starts at `BALL_RADIUS (20)`, engine decays −2/frame to 0.

**`frame.*`**
- `is_round_over` (bool) — true for the entire freeze window.
- `post_score_freeze_frames` (int) — countdown starting at `POST_SCORE_FREEZE_FRAMES (20)`; reaches 0 → engine serves next ball.

**Back-compat**: `replay_service._backfill_frame` fills legacy msgpack replays with `(0, False)` defaults so old recordings still load.

**FE integration map**: rising-edge detection for D13 punch ring (radius transitions `0 → >0`), radius-driven fade for ring opacity, `is_power_hit` rising-edge → D12 power spark, `post_score_freeze_frames > 0` → D15 scoreboard flash class. Full trigger/action mapping lives in the archived `NOTICE-FX-PAYLOAD-READY.md`.

## Consequences

- FE overlays D11-D15 can consume the WS feed directly; no further BE changes required.
- Any future FX must be added via new named fields, not by re-purposing existing ones (e.g. don't overload `punch_effect_radius` for unrelated effects).
- Replay viewer stays forward- and backward-compatible across versions because `_backfill_frame` is the single compat shim.
- Post-score freeze behaviour (the 15-point invisibility bug) is fixed by the same contract — FE draws the frozen frame as normal, no special client logic.
