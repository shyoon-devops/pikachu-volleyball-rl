# QA Re-Verification — 2026-04-12 (post dev→QA promotion)

**Target:** `http://localhost:8002` (QA) / `http://192.168.0.248:3001/` (QA frontend)
**Branch:** `yoon/qa-engineer`
**Trigger:** DevOps promoted 12 commits from `github/dev` → `github/qa`; full
re-verify requested by PM, confirmed by PM's direct `curl` of the new frontend
bundle.

**Promotion commits included (via `git log github/qa..github/dev`):**
- `38e29bdd fix(middleware): exempt metrics + health probes from rate limiter`
- `9f050c87 fix(ui): remove duplicate Start button, unify training controls`
- `b0d0aaee fix: port game engine faithfully to gorisanson/pikachu-volleyball`
- `e5d765a0 fix: gate ball-player collision with isCollisionWithBallHappened`
- `fb1f5e64 perf(ws): parallel broadcast with serialize-once fan-out (BE-6)`
- `ee7a6c0b perf(db): declare hot-path MongoDB indexes at startup (BE-5)`
- `407876ca feat: time-series endpoint for evaluation metrics`
- `f10b6c25 feat(replay): keyboard scrubbing`
- `76005f52 feat: evaluation history persistence + CRUD`
- `3cdef948 feat(design): D6-D10 training progress / tooltip / fullscreen`
- `265e3c30 feat(ui): global ConnectionIndicator pill`
- `0f32235e feat(rl): rebalance reward weights`

---

## Overall verdict — ❌ **prod 승격 불가**

**Backend suite: 40 pass / 9 fail / 2 skip** (pre-promotion: 48/0/3 → regression 9건)

Training-start WS broadcast is broken (100% reproducible in two consecutive clean
runs) and net-collision physics regressed. PM's live-UI observation (Start
button stays enabled, status badge shows "stopped" while training thread is
actually running) is explained perfectly by the broken broadcast path.

---

## Deployment application — all ✅

| Item | Pre-promotion | Post-promotion | Result |
|------|:-------------:|:--------------:|:------:|
| Backend image SHA | `dab203bf…` | `0cf25d36…` | ✅ rebuilt |
| Frontend bundle | `index-we-0u1Nl.js` (839,199 B) | `index-D3bB_L7S.js` (839,305 B) | ✅ rebuilt |
| Duplicate Start button | `Start`×1 + `Start Training`×1 | `Start`×1 only | ✅ unified |
| `/api/health` rate-limit exemption | 0×429 (already exempt) | 200×200 / 0×429 | ✅ preserved |
| `/api/metrics` rate-limit exemption | 80×429 under 100-burst | 100×200 / 0×429 | ✅ **newly applied** (PM decision 2026-04-12) |
| Infinite-toss (ball-player collision) | — | 5/5 physics PASS | ✅ fixed |

---

## Blocker #1 — training:status WS broadcast broken (CRITICAL)

**100% reproducible across two clean full-suite runs.**

| Test | Error |
|------|-------|
| `test_sprint1_verification::test_start_uses_provided_bot_level` | No `training:status` response to start |
| `test_sprint1_verification::test_total_timesteps_forwarded` | No `training:status` response |
| `test_e2e_training_flow::test_start_returns_running_status_with_experiment_id` | No `training:status(running)` within 15s after start |
| `test_e2e_training_flow::test_stop_then_resume` | `training:resume` did not produce running status within 15s |

**PM's live observation matches exactly:**
> "학습은 진행중인데 여전히 start버튼이 활성화되고 있다 그치? 상태 배지도 stopped로 떠있고"

Training thread starts on the backend, but `training:status(running)` is never
received by the websocket client → UI keeps Start button enabled and the
status badge stays on "stopped".

**1순위 원인:** `fb1f5e64 perf(ws): parallel broadcast with serialize-once
fan-out (BE-6)` — fan-out 최적화가 `training:status` / `training:metrics`
메시지를 소실하는 것으로 추정. `asyncio.gather(..., return_exceptions=True)`
로 전환하면서 발생한 브로드캐스트 경로 회귀.

**Action:** Backend team urgent investigation. Revert or fix BE-6 before
re-promotion.

---

## Blocker #2 — net collision physics regressed

```
FAILED tests/test_engine.py::TestBallNetCollision::test_ball_vx_reverses_on_net_collision
  ball at x=221 (net center x≈216), vx=5 (expected ≤0)
  is_round_over=False
```

Ball reaches the net but `vx` does not reverse — ball can pass through or get
stuck on the net.

**1순위 원인:** `b0d0aaee fix: port game engine faithfully to
gorisanson/pikachu-volleyball` — faithful-port commit likely changed net
collision gating logic along with ball-player gating.

**Action:** Backend team confirm net-collision branch in ported engine; add
regression test once fix lands.

---

## Secondary regressions (server saturation during suite)

| Test | Error | Interpretation |
|------|-------|----------------|
| `test_ws_resilience::test_disconnect_during_broadcast` | `InvalidMessage: did not receive a valid HTTP response` | WS handshake failed mid-suite — server CPU/task saturation |
| `test_burst_200_requests_any_endpoint_triggers_429[/api/models]` | 0×200, 0×429, 0×5xx | All 200 concurrent requests timed out |
| `test_burst_200_requests_any_endpoint_triggers_429[/api/training/status]` | same | same |
| `test_burst_200_requests_any_endpoint_triggers_429[/api/evaluation/results]` | same | same |
| `test_health_endpoint_never_throttled[/api/health]` | 0/200 success | `/api/health` unresponsive mid-suite |

**Key evidence that the server itself is OK at low load:**
- Post-suite manual 50-burst `/api/health`: 50×200 / 0×429 / 0×5xx ✅
- Post-suite manual 200-burst `/api/health`: 200×200 ✅
- Post-suite manual 100-burst `/api/metrics`: 100×200 ✅
- Container state: `RestartCount=0`, `OOMKilled=false`, `StartedAt` unchanged

**Interpretation:** These five failures are not independent bugs — they are
symptoms of the BE-6 broadcast fan-out (and possibly BE-5 startup-index
declaration) causing task/thread saturation under sustained suite pressure.
Fixing Blocker #1 is expected to clear most or all of these.

**Production risk:** When multiple dashboard clients connect + training runs
+ evaluation polling happens concurrently, the same saturation is likely to
manifest.

---

## What works (✅)

- All 4 SEC tests (CORS, rate-limiting, path-traversal)
- All 3 BUG3 double-start tests
- 4/5 BE1 heartbeat tests (only `disconnect_during_broadcast` fails, likely
  suite-saturation)
- All 7 WS resilience tests (abrupt disconnect, reconnect, malformed input)
- 5/7 e2e training-lifecycle tests (stop, status, set_level, metrics_stream,
  broadcast_reaches_second_client — the last two passed in clean run, failed
  in earlier dirty run, consistent with suite-saturation interference)
- All 10 rate-limiting tests at low/normal load
- All 5 engine-physics tests except the net-collision one
- `/api/health` and `/api/metrics` rate-limit exemption (PM decision applied)
- Duplicate Start button removed, infinite toss fixed

---

## Recommended next steps

1. **Backend — urgent:**
   - Investigate `fb1f5e64` (BE-6 parallel broadcast); verify
     `training:status` still reaches all subscribers, even when 1+ subscribers
     disconnect mid-fanout.
   - Investigate `b0d0aaee` net-collision branch in `backend/game/engine.py`.
2. **DevOps — after backend fix:**
   - Rebuild QA with fixed backend.
   - Signal QA engineer for re-verification.
3. **QA — after re-verify:**
   - Full suite must return 48+ pass / 0 fail.
   - Add explicit net-collision scenario test to `test_game_scenarios.py` to
     prevent regression.
4. **PM:**
   - Hold prod promotion until Blocker #1 + #2 cleared and re-verify passes.

---

## Appendix — exact fail list (clean re-run)

```
FAILED tests/test_sprint1_verification.py::TestBUG5FieldMismatch::test_start_uses_provided_bot_level
FAILED tests/test_sprint1_verification.py::TestBUG5FieldMismatch::test_total_timesteps_forwarded
FAILED tests/test_sprint1_verification.py::TestBE1Heartbeat::test_disconnect_during_broadcast
FAILED tests/test_rate_limiting.py::TestBurstRateLimit::test_burst_200_requests_any_endpoint_triggers_429[/api/models]
FAILED tests/test_rate_limiting.py::TestBurstRateLimit::test_burst_200_requests_any_endpoint_triggers_429[/api/training/status]
FAILED tests/test_rate_limiting.py::TestBurstRateLimit::test_burst_200_requests_any_endpoint_triggers_429[/api/evaluation/results]
FAILED tests/test_rate_limiting.py::TestHealthExemptFromRateLimit::test_health_endpoint_never_throttled[/api/health]
FAILED tests/test_e2e_training_flow.py::TestTrainingLifecycle::test_start_returns_running_status_with_experiment_id
FAILED tests/test_e2e_training_flow.py::TestTrainingLifecycle::test_stop_then_resume
FAILED tests/test_engine.py::TestBallNetCollision::test_ball_vx_reverses_on_net_collision  [separate from 4-suite run]

9 failed (4-suite) + 1 failed (engine-physics) / 40+ passed / 2 skipped
4-suite: 532.06s (0:08:52)
```

Verification script: `scripts/qa_reverify_post_promotion.sh`
Raw log: `/tmp/qa_reverify_*.log`
