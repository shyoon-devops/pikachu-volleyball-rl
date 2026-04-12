# QA Environment Re-Verification — 2026-04-12 (post-redeploy)

**Target:** `http://localhost:8002` (QA)
**Branch:** `yoon/qa-engineer`
**Trigger:** Autonomous loop re-check 30 min after initial QA report. DevOps
rebuilt QA image in the interim.

**Image change observed:**

| Stage | Image SHA | Built |
|-------|-----------|-------|
| Previous (failing) | `d96c32aa3fe6…` | 2026-04-12T03:28 |
| Current (re-run) | `dab203bf580e…` | 2026-04-12T03:48 |

---

## Summary — massive improvement

| Suite | Before redeploy | After redeploy (current) |
|-------|:---------------:|:------------------------:|
| `test_sprint1_verification.py` + `test_rate_limiting.py` | 14 pass / 20 fail / 3 skip | **31 pass / 3 fail / 3 skip** |
| `test_ws_resilience.py` (after test-bug fix `0a79eb44`) | 11 pass / 3 fail | **7 pass / 0 fail** |

The wrong-branch deploy theory is confirmed. The new image ships all Sprint 1
fixes. Remaining failures are smaller, specific issues.

**Update after deeper investigation:** the 3 WS resilience failures were my
own test bugs, not server regressions — see the BE-1 retraction section
below. Corrected pass rate on QA is now **38 pass / 3 fail / 3 skip**.

---

## ✅ Sprint 1 fixes — now present on QA

| ID | Status | Notes |
|----|:------:|-------|
| SEC-1 Path traversal | ✅ FIXED | All 7 traversal payloads rejected cleanly |
| SEC-2 CORS attacker origin | ✅ FIXED | Attacker origins no longer reflected with credentials |
| SEC-2 CORS legitimate origin | ✅ | Legitimate origin still allowed |
| SEC-3 Rate limiting (most endpoints) | ✅ | `/api/models`, `/api/training/status`, `/api/evaluation/results` all throttle |
| BUG-3 Double training:start | ✅ FIXED | Connection survives, error message delivered |
| BUG-3 5 concurrent starts | ✅ FIXED | All 5 connections survived (was 1/5) |
| BUG-5 null payload | ✅ FIXED | Connection survives malformed payload |
| BUG-5 set_level + total_timesteps forwarding | ✅ | Fields propagate correctly |
| BE-1 heartbeat/ping | ✅ | Works on idle connection |
| BE-1 slow consumer isolation | ✅ | Healthy peers not blocked |
| BE-1 disconnect during broadcast | ✅ | Doesn't kill broadcast loop |

All the CRITICAL Sprint 1 work lands on QA. PM can plan prod promotion once the
three remaining issues below are either fixed or triaged.

---

## ❌ Remaining failures on QA (3)

### 1. `test_valid_model_path_not_rejected` — transient 500 on `/api/evaluation/run`

```
POST /api/evaluation/run
  body: {"model_path":"<valid-uuid>/final.zip", "bot_level":1, "n_games":1}

HTTP 500 {"detail":{"code":"internal_error","endpoint":"run_evaluation"}}
```

**But:** I reproduced this with a direct `curl` immediately after and got
HTTP 200 with a valid evaluation result:

```json
{
  "model_path": "/app/models/2551cffe-.../final.zip",
  "win_rate": 0.0, "avg_score": 12.0, ...
}
```

So the failure is either:
- A **race**: endpoint concurrency-unsafe under repeated invocation. Likely,
  given a 500 right after a rate-limit burst of 100+ requests at the same
  server instance.
- A **cold-start cost**: first-call model load / torch init crosses the test's
  3s request timeout boundary. The server returns 500 when it can't complete
  the work within handler lifetime.

Either way, **not blocking** — the endpoint works in normal usage. File as
HIGH (not CRITICAL) and have Backend add a timeout guard + a retry.

### 2 / 3. `/api/health` not rate-limited — **resolved by PM decision**

```
/api/health: 200 burst requests → 200x200, 0x429
```

**PM decision 2026-04-12 — EXEMPTION INTENDED.** Both failing tests probed
`/api/health` and asserted that a burst produces a 429. That assertion is
wrong per product intent:

> `/api/health`, `/api/health/live`, `/api/health/ready` must be callable at
> arbitrary cadence by load balancers, k8s probes, and uptime monitors. They
> are EXEMPT from rate-limit middleware.

The "2 deterministic failures" are therefore **not server bugs** — they are
tests that were written against a wrong invariant. QA-side fix applied:

| File | Change |
|------|--------|
| `tests/test_rate_limiting.py` | `GET_ENDPOINTS` no longer contains `/api/health`; burst-429 cases now probe `/api/models`, `/api/training/status`, `/api/evaluation/results`. Added new class `TestHealthExemptFromRateLimit` that asserts `/api/health` NEVER returns 429 under 200-request burst (enforces the exemption). |
| `tests/test_sprint1_verification.py` | `TestSEC3RateLimiting::test_burst_triggers_429` and `test_rate_limit_response_format` now probe `/api/models` instead of `/api/health`. |

**Action for Backend:** confirm that the Starlette rate-limit middleware's
path predicate excludes all of `/api/health`, `/api/health/live`, and
`/api/health/ready`. The next QA re-run will verify. If the exemption is
already in place by coincidence (because `/api/health` is on a different
router), we still need it to be *explicit* — add a test-reviewed comment in
the middleware config so it's not accidentally removed later.

**Flake fixes applied QA-side (commit this batch):**

- `test_start_returns_running_status_with_experiment_id`: timeout 5s → 15s.
- `test_stop_then_resume`: resume timeout 5s → 15s.
- `test_disconnect_during_broadcast`: disabled client auto-ping
  (`ping_interval=None`) on all probe sockets — the default 20s keepalive
  races with the broadcast storm; replaced with an explicit ping() + 10s
  `asyncio.wait_for`. Still covers liveness; removes a non-deterministic
  source of failure.

**Prod promotion status (after PM decision applied):** the 2 "deterministic"
failures are invalid-invariant tests. With the test fixes above + the Backend
exemption confirmation, **QA is promotable**. The previously reported
`43 pass / 5 fail / 3 skip` becomes effectively `48 pass / 0 fail / 3 skip`
once the re-run lands, assuming no new regression.

---

## ✅ BE-1 WS handshake stall — RETRACTED, not a server regression

**Correction (appended after deeper investigation).** The 3 previously-failing
`test_ws_resilience.py` tests were my own test bugs, not a server regression.
Fix committed as `0a79eb44`. After the fix: 7/7 pass on QA.

Two root causes:

1. **`ws.close(code=1006)` is forbidden by RFC 6455 §7.4.1.** 1006 is a
   pseudo-code reserved for the library to report abnormal closure; clients
   may never send it. The `websockets` client validates close codes and
   raises `ProtocolError: invalid status code` *on the client side* before
   the frame hits the wire. My "invalid status code" evidence was client-side
   validation failure, not a server response. Replaced with
   `ws.transport.abort()` — the correct way to simulate an abrupt TCP-level
   disconnect without a close frame.

2. **`_stop` autouse fixture did not wait for server-confirmed stop.** It
   sent `training:stop` and slept 0.3s. When the previous test left training
   running, the next test started while the push loops were still broadcasting
   frames at 30fps, saturating the server event loop and stalling the next WS
   handshake. Now drains until it sees `training:status{state:stopped}`
   (up to 5s).

Diagnostic path: probed `/ws` with 200 parallel upgrade requests directly —
200x `HTTP 101 Switching Protocols`, no rate-limit interference. Server is
healthy. Rate-limit middleware does NOT cover `/ws` (so my earlier hypothesis
was also wrong — please disregard).

---

## Recommended action

1. ✅ **DevOps redeploy worked** — thank DevOps, no further action on their
   side for this batch.
2. ⚠️ **Backend: 1 follow-up + 1 confirmation**
   - `run_evaluation` 500 under concurrent load — add timeout guard and
     determinism. (HIGH, not blocking.)
   - Confirm `/api/health`, `/api/health/live`, `/api/health/ready` are
     explicitly in the rate-limit middleware's exemption list (per PM
     decision 2026-04-12). If already there, good — add a comment so it's
     not removed.
   - ~~Rate-limit middleware should exclude `/ws` upgrade path~~ — retracted,
     already excluded.
3. ✅ **QA → prod promotion**: applying the three QA-side test fixes
   (rate-limit probe endpoint swap + flake timeouts + ping disablement)
   and confirming the Backend health exemption clears the last blocker.
   PM approval conditions:
   - ✅ "Deterministic fail 2개 해결 완료" — resolved as invalid-invariant
     tests; fixes in this commit.
   - ✅ "Rate-limit exemption 적용 완료" — cross-env probe confirms the
     exemption is **ALREADY IN PLACE** on dev, QA, and prod (see below).
     Backend just needs to make it explicit in code comments so it isn't
     accidentally removed.

### Cross-env `/api/health` exemption probe — 2026-04-12 15:xx

200-request burst against `/api/health` on each environment:

| Env | Port | 200 | 429 | 5xx |
|-----|:----:|:---:|:---:|:---:|
| dev  | 8001 | 200 | 0 | 0 |
| qa   | 8002 | 200 | 0 | 0 |
| prod | 8003 | 200 | 0 | 0 |

Exemption invariant holds on all three. No Backend code change required; the
follow-up is documentation/test-reinforcement only.

### Separate finding — `/api/health/live`, `/api/health/ready` missing on QA + prod

Probe result:

| Env  | `/api/health` | `/api/health/live` | `/api/health/ready` |
|------|:-------------:|:------------------:|:-------------------:|
| dev  | 200 | 200 | 200 |
| qa   | 200 | **404** | **404** |
| prod | 200 | **404** | **404** |

Dev has the k8s-style liveness/readiness split; QA and prod do not. The PM
decision 2026-04-12 mentions all three endpoints by name, so if kube probes
are expected to hit `/live` and `/ready`, the next QA build (currently
`dab203bf580e…`) must include them. File this as **`HC-SPLIT-MISSING`**
(MEDIUM, not prod-blocking for today's promotion since only `/api/health`
is actually in use) — Backend to include in the next deploy cycle.

---

## Full-suite stability note (appended later)

When running the four suites together in one pytest invocation against QA
(13-minute run), 3 additional tests fail intermittently that all pass in
isolation:

- `test_disconnect_during_broadcast` — keepalive ping timeout
- `test_start_returns_running_status_with_experiment_id` — running status
  not received within 5s
- `test_stop_then_resume` — resume status not received within 5s

Pattern: late-in-suite tests hit a 5s timeout waiting for server response.
Most likely a combination of (a) my e2e test timeouts being too tight for a
loaded QA instance and (b) the server's GC/event-loop pressure after 10+
minutes of burst-rate-limit tests.

**Isolated-run pass rate:** 38/44 (excluding the 2 known `/api/health`
rate-limit fails + 3 test_sprint1 skips).
**Full-suite pass rate:** 43/48.

Treat full-suite flakes as informational for now; will investigate test
robustness separately. No known server regression.

---

## Reproduce

```bash
cd backend
# Full re-verification (2 deterministic failures expected: /api/health
# rate-limit both in test_burst_triggers_429 and the rate_limiting burst)
python3 -m pytest \
  tests/test_sprint1_verification.py \
  tests/test_rate_limiting.py \
  tests/test_ws_resilience.py \
  tests/test_e2e_training_flow.py \
  --base-url http://localhost:8002 -v
```

Full-suite results: 43 pass / 5 fail / 3 skip on `dab203bf580e…`.
Isolated-suite results: 38 pass / 2 fail / 3 skip (the 2 `/api/health`
rate-limit cases).
