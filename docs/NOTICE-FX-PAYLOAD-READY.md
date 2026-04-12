# Notice to Frontend/Backend: FX payload fields now live

**From:** AI Engineer (backend/game, backend/rl/callbacks)
**To:** Frontend (GameCanvas integration), Backend (WS handlers)
**Status:** Unblocks designer's D11-D13 / D15 CSS overlays
**Related commits (merged to `dev` at `8aee452e`):**
- `6ff911d9` — post-score freeze-frame (fixes 14→15 invisibility)
- `982e3a80` — `ball.punch_effect_x/y/radius` (white radial ring)
- D11-D13 overlays at `34137663`, D15 flash at `5f0b0cd7` (already on dev)

---

## What changed in the WS frame payload

Every `training:frame` and every replay frame now carries these fields.
Defaults are back-filled by `replay_service._backfill_frame` for old
msgpack replays, so loading historical replays won't crash.

### `ball.*`

| Field | Type | Meaning | Trigger |
|---|---|---|---|
| `is_power_hit` | bool | Ball is in a power-hit trajectory | Set true for one frame on power-hit collision; cleared on next collision |
| `punch_effect_x` | int | Effect centre x (pixels) | Ground touch OR power-hit collision |
| `punch_effect_y` | int | Effect centre y (pixels) | Same |
| `punch_effect_radius` | int | Effect current radius (pixels, decays -2/frame) | `= BALL_RADIUS (20)` on trigger; engine decays toward 0 |

### top-level frame

| Field | Type | Meaning | Trigger |
|---|---|---|---|
| `is_round_over` | bool | Round ended (score just happened OR rally timed out) | Stays true for entire freeze window |
| `post_score_freeze_frames` | int | Countdown: frames remaining in the post-score hold | Starts at 20 (`POST_SCORE_FREEZE_FRAMES`), decays to 0; when 0, engine serves new ball |

---

## FE integration map — WS payload → designer CSS class

The designer's D11-D13 / D15 CSS lives in `frontend/src/components/game/GameCanvas.css`.
Nothing is wired to the WS feed yet. Here is the integration contract
FE owns:

### D13 — punch ring (ball ground-touch OR power-hit landing)

- **Trigger:** `frame.ball.punch_effect_radius > 0` AND previous frame's radius was `0`
  (rising edge — avoids re-spawning rings on the decay frames).
- **Action:** spawn `.punch-ring-layer > .punch-ring` with CSS vars
  `--px = frame.ball.punch_effect_x`, `--py = frame.ball.punch_effect_y`.
  Optionally spawn `.punch-ring--secondary` (80ms lag) for the 2-wave look.
- **Lifetime:** 450ms CSS animation; relies on `animationend` for cleanup.
- **Do NOT** read the engine's radius decay directly — the 450ms CSS is
  the authoritative visual; the engine's 10-frame decay is there only so
  replay viewers without JS still see the marker.

### D12 — power-hit flash/bolt

- **Trigger:** `frame.ball.is_power_hit === true` AND previous frame was `false`
  (rising edge).
- **Action:** spawn `.power-hit-flash` + `.power-hit-bolt` (angle from ball velocity
  `atan2(ball.vy, ball.vx)` → `--bolt-angle` in deg). Add
  `.game-canvas--power-hit` for the 85ms shake class.
- `.game-canvas--hyper` stays on while `is_power_hit === true`.

### D11 — dive trail / landing dust

- **Trigger:** `frame.player{1,2}.is_diving === true` AND previous frame `false`.
- **Action:** spawn `.dive-trail` + `.dive-streak` with `--dive-dir = ±1`
  (player's facing direction). On landing (diving → false), spawn
  `.dive-landing-dust`.
- Optional `.player-diving-halo` while `is_diving` is true.

### D15 — score freeze scoreboard flash

- **Trigger:** `frame.is_round_over === true` AND previous frame was `false`
  (rising edge — fires exactly once per scoring event).
- **Action:** add CSS class `.scoreboard--freeze-flash` to the scoreboard
  container for the duration of the freeze window. Use
  `frame.post_score_freeze_frames / POST_SCORE_FREEZE_FRAMES` (20) to drive
  any progress-based visual (fade-in, etc.).
- **Remove** the class when `frame.is_round_over === false`.

---

## Backend WS handler — nothing to change

`_serialize_state` (`backend/rl/callbacks.py:294-348`) already emits all
fields. `handlers.frames_push_loop` wraps the dict as
`{"type": "training:frame", "payload": ...}` — no shape change needed.

---

## Replay back-compat

`replay_service._backfill_frame` (`backend/app/services/replay_service.py:71-82`)
defaults missing `punch_effect_*` and `post_score_freeze_frames` /
`is_round_over` to zero/false. Old msgpack replays from before these
commits decode without KeyError and play back without FX (correct — they
were recorded without the events).

---

## Testing

- Engine-side pinned by `TestPostScoreFreeze` (6 tests) + `TestPunchEffectRadius`
  (5 tests) in `backend/tests/test_engine.py`.
- Serialize-keys pinned by `test_serialize_state_has_all_keys` in
  `backend/tests/test_coverage_gaps.py`.
- Replay back-fill exercised indirectly; FE should add a
  playwright/Vitest test that loads a legacy replay fixture and asserts
  no render crash.

---

## Questions / owner

Ping AI Engineer (`yoon/ai-engineer`) if you see:
- Radius rising edge not firing (engine issue, not FE).
- `is_round_over` or `post_score_freeze_frames` missing from a frame
  (could be an old msgpack without back-fill in the viewer path).
- RL training step count stalls during scoring (freeze pass-through
  should NOT affect training — env passes `post_score_freeze=False`).
