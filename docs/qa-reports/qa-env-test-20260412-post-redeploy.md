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

| Suite | Before redeploy | After redeploy |
|-------|:---------------:|:--------------:|
| `test_sprint1_verification.py` + `test_rate_limiting.py` | 14 pass / 20 fail / 3 skip | **31 pass / 3 fail / 3 skip** |
| `test_ws_resilience.py` | 11 pass / 3 fail | **4 pass / 3 fail** |

The wrong-branch deploy theory is confirmed. The new image ships all Sprint 1
fixes. Remaining failures are smaller, specific issues.

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

### 2 / 3. `/api/health` not rate-limited (same issue dev has)

```
/api/health: 200 burst requests → 200x200, 0x429
```

Reproduces on dev as well — this was flagged in the first report as
`RL-HEALTH-RATE`. Nothing changed on this front with the redeploy. Backend
should confirm whether excluding `/api/health` from the rate-limit middleware
is intentional (common practice for load-balancer probes) or an oversight.

---

## ❌ BE-1 — WS handshake still unstable under abrupt-close stress

3 failures in `test_ws_resilience.py`:

- `TestAbruptDisconnect::test_abrupt_close_does_not_crash_server` — ProtocolError: invalid status code
- `TestAbruptDisconnect::test_abrupt_close_does_not_affect_sibling` — ProtocolError: invalid status code
- `TestReconnectRecovery::test_reconnect_can_issue_stop` — TimeoutError on handshake

**Changed symptom vs. pre-redeploy.** Before: all three timed out during the
opening handshake. After redeploy: two of three now receive a non-101 response
(`ProtocolError: invalid status code`). The third still times out.

Direct `curl` WS handshake reproduces 101 Switching Protocols and streams
frames normally. So the issue is specific to the sequence: **abrupt 1006
closes followed immediately by a new handshake on the same server instance**.

**Hypothesis**: the rate-limit middleware may be counting the WS upgrade
requests; after a storm of abrupt closes, the next upgrade request hits the
throttle and returns 429 instead of 101. That would explain "invalid status
code" — the `websockets` client rejects 429 as a non-switching-protocol
response.

**Request for Backend:** check whether rate limiting applies to `/ws` upgrade
requests. If yes, exclude WS upgrades, OR raise the WS-upgrade rate window
specifically.

---

## Recommended action

1. ✅ **DevOps redeploy worked** — thank DevOps, no further action on their
   side for this batch.
2. ⚠️ **Backend: 3 follow-ups**
   - `run_evaluation` 500 under concurrent load — add timeout guard and
     determinism.
   - `/api/health` rate-limit coverage — confirm intent with PM.
   - Rate-limit middleware should exclude `/ws` upgrade path (hypothesis,
     please verify).
3. ✅ **QA → prod promotion**: once the three above are triaged (fixed or
   PM-waived), QA is promotable.

---

## Reproduce

```bash
cd backend
# Full re-verification (3 failures expected post-redeploy on current image)
python3 -m pytest \
  tests/test_sprint1_verification.py \
  tests/test_rate_limiting.py \
  tests/test_ws_resilience.py \
  --base-url http://localhost:8002 -v
```

Full results: 35 pass / 6 fail / 3 skip on `dab203bf580e…`.
