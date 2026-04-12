# QA Environment Test Run — 2026-04-12

**Target:** `http://localhost:8002` (QA)
**Branch:** `yoon/qa-engineer`
**Run trigger:** Autonomous loop (task #32) — full QA suite execution
**Suites run:**

- `tests/test_sprint1_verification.py` — Sprint 1 fix verification
- `tests/test_rate_limiting.py` — rate limit coverage
- `tests/test_e2e_training_flow.py` — full training lifecycle
- `tests/test_ws_resilience.py` — WebSocket disconnect/reconnect

---

## Summary

| Suite | Total | Pass | Fail | Skip |
|-------|-------|-----:|-----:|-----:|
| `test_sprint1_verification.py` | 30 | 11 | 16 | 3 |
| `test_rate_limiting.py` | 7 | 3 | 4 | 0 |
| `test_e2e_training_flow.py` | 7 | 7 | 0 | 0 |
| `test_ws_resilience.py` | 14 | 11 | 3 | 0 |
| **Total** | **58** | **32** | **23** | **3** |

**Pass rate: 55%.** 23 failures. QA is NOT ready to promote.

---

## CRITICAL findings — Sprint 1 fixes are NOT on QA

All four Sprint 1 CRITICAL items are still broken on QA. Either the fixes were
never deployed to QA, or the deploy rolled back, or the build on :8002 is older
than the dev build. **This must be confirmed before anything else.**

### SEC-1 — Path Traversal: NOT FIXED ❌

8 tests failing.

```
valid-uuid/../../etc/passwd            → 500 Internal Server Error
../../../etc/passwd                    → 500 Internal Server Error
..\..\windows\system32\config\sam      → 500 Internal Server Error
models/../../../etc/shadow             → 500 Internal Server Error
%2e%2e/%2e%2e/etc/passwd               → 500 Internal Server Error
....//....//etc/passwd                 → 500 Internal Server Error
(valid model path)                     → 500 Internal Server Error  ← also broken
```

Both attack payloads AND the valid-model-path control case crash with 500.
That implies:

1. No traversal filter is in place — server attempts the file open and crashes.
2. The `/api/evaluation/run` endpoint is broken on QA independently of SEC-1.

**Impact:** The server leaks stack traces on malformed input and the evaluation
endpoint is unusable.

### SEC-2 — CORS reflection with credentials: NOT FIXED ❌

4 tests failing.

```
Origin: https://evil.com
  → access-control-allow-origin: https://evil.com
  → access-control-allow-credentials: true

Origin: https://attacker.malicious.site
  → access-control-allow-origin: https://attacker.malicious.site
  → access-control-allow-credentials: true

Origin: http://localhost:9999
  → access-control-allow-origin: http://localhost:9999
  → access-control-allow-credentials: true

Preflight OPTIONS with Origin: https://evil.com
  → access-control-allow-origin: https://evil.com
```

QA still runs with `allow_origins=["*"]` + `allow_credentials=True`. Any attacker
origin can make authenticated cross-origin requests. This is the **worst-case
CORS misconfiguration** and was the headline SEC-2 finding.

### SEC-3 — Rate limiting: NOT FIXED ❌

5 tests failing (1 in sprint1, 4 in rate_limiting burst).

| Endpoint | 200-burst result |
|----------|-----------------|
| `/api/health` | 200x200, 0x429 |
| `/api/models` | 200x200, 0x429 |
| `/api/training/status` | 200x200, 0x429 |
| `/api/evaluation/results` | 200x200, 0x429 |

No rate limiting on any GET endpoint. Server happily served 200 concurrent
requests with no throttling. Trivially DoS-able.

### BUG-3 — Concurrent `training:start` crash: NOT FIXED ❌

2 tests failing.

```
test_double_start_returns_error_message
  → Server accepted both starts, never returned an error message.
  → Got types: ['training:status']; expected 'error' or 'already running'.

test_concurrent_starts_all_survive
  → Fired 5 parallel training:start messages.
  → Only 1 of 5 WebSocket connections survived. The other 4 died.
```

This is the exact failure mode from the original BUG-3 report. 4-of-5
connection kill rate on concurrent start is worse than I saw on dev last week.

### BUG-5 — null payload crashes connection: NOT FIXED ❌

1 test failing.

```
{"type": "training:start", "payload": null}
  → Connection closed (no close frame).
```

A `null` payload should return an error message, not kill the socket. Still
crashes the connection.

---

## HIGH findings

### BE-1 — WS handshake times out after abrupt disconnect storm ❌

3 tests failing in `test_ws_resilience.py`:

- `TestAbruptDisconnect::test_abrupt_close_does_not_crash_server`
- `TestAbruptDisconnect::test_abrupt_close_does_not_affect_sibling`
- `TestReconnectRecovery::test_reconnect_can_issue_stop`

Symptom in all three: after an abrupt-close sequence (or after stopping
training), the next `websockets.connect()` times out during the opening
handshake. Even with `open_timeout=10s` and a 1-second reap delay, the server
stops answering WS handshakes for tens of seconds.

Stack (representative):

```
tests/test_ws_resilience.py:156:
    async with websockets.connect(ws_url, open_timeout=5) as a:
websockets/asyncio/client.py:581:
    raise TimeoutError("timed out during opening handshake") from exc
```

This is a **real BE-1 regression signal** — the server becomes temporarily
unresponsive to new WS handshakes after concurrent disconnects. Probably the
same root cause as the BUG-3 connection-kill issue: something in the
`ConnectionManager` is not releasing the event loop or is holding a lock while
cleaning up.

---

## PASSING work (good news)

### `test_e2e_training_flow.py` — 7/7 ✅

Full training lifecycle works on the happy path:

- `start` → returns `training:status { state: running, experiment_id: ... }`
- Metrics stream arrives within 20s of start
- `stop` → returns `training:status { state: stopped }`
- REST `/api/training/status` matches WS broadcast
- `set_level` reflected in subsequent status
- `stop` → `resume` produces a new running session
- Second client connected mid-training receives broadcasts

So the **single-client, serial flow is healthy**. All the failures are under
adversarial input or concurrency.

### `test_ws_resilience.py` — 11/14 ✅

Single-stream malformed-input handling is fine:

- Unknown `type` values are ignored without killing the connection
- Non-JSON text frames don't kill the pool
- 50 rapid connect/disconnect cycles complete in bound time
- Reconnected clients can re-subscribe to an in-flight training session

### `test_sprint1_verification.py` — 11/30 ✅

Passing areas:

- Rate-limit health (no 5xx leaks under burst) — server doesn't crash, just
  doesn't throttle
- Basic training start/stop round-trip
- BUG-5 field-mismatch cases that use the correct `payload` wrapper shape

---

## Dev vs QA comparison — QA image is from the wrong branch

Same `test_sprint1_verification.py + test_rate_limiting.py` suite against
**dev (`localhost:8001`)** for comparison:

| Check | Dev | QA |
|-------|:---:|:--:|
| SEC-1 Path traversal blocked | ✅ | ❌ |
| SEC-2 CORS attacker origin rejected | ✅ | ❌ |
| SEC-3 Rate limiting (most endpoints) | ✅ (except `/api/health`) | ❌ (all endpoints) |
| BUG-3 Concurrent training:start | ✅ | ❌ |
| BUG-5 null payload | ✅ | ❌ |
| BE-1 Heartbeat/disconnect-during-broadcast | ✅ | (not re-run, but related BE-1 handshake stall reproduces) |
| **Dev totals** | **32 pass / 2 fail / 3 skip** | **14 pass / 20 fail / 3 skip** |

Container image SHAs:

| Env | Image | Built | SHA |
|-----|-------|-------|-----|
| dev | `pikachu-rl-dev-backend` | 2026-04-11T16:54 | `367884fca502…` |
| qa  | `pikachu-rl-qa-backend`  | 2026-04-12T03:28 | `d96c32aa3fe6…` |
| prod | `pikachu-rl-prod-backend` | 2026-04-11T15:20 | `38f8583d5c47…` |

**The QA image is chronologically newer than dev but functionally older.**
QA was rebuilt at 03:28 today but almost certainly from `main` (pre-Sprint 1)
rather than from the current dev branch. This is the only explanation for
every Sprint 1 fix being absent while the image is newer.

## Recommended action

1. **DevOps: rebuild `pikachu-rl-qa-backend` from the Sprint 1 branch.** The
   current QA image (`d96c32aa3fe6…`) does not contain SEC-1/2/3, BUG-3, BUG-5
   fixes even though it was built today. Best guess: the QA build pipeline is
   pinned to `main` instead of the dev/Sprint 1 branch.
2. **After QA redeploy**, re-run:
   ```bash
   cd backend && python3 -m pytest \
     tests/test_sprint1_verification.py \
     tests/test_rate_limiting.py \
     tests/test_ws_resilience.py \
     --base-url http://localhost:8002 -v
   ```
3. **Do not promote QA → prod** until post-redeploy suite matches the dev
   result (≤2 failures, both on `/api/health` rate limiting — triage that one
   as its own follow-up ticket).
4. **NEW finding — `/api/health` rate limiting gap** (reproduces on both
   dev and QA): when the other endpoints were added to the rate-limit
   middleware, `/api/health` was evidently skipped. This is intentional in some
   products (to avoid throttling load balancers) but should be explicit. File
   as `RL-HEALTH-RATE` for Backend Engineer to confirm.
5. **BE-1 WS handshake stall** — re-verify after QA redeploy. It may be a
   symptom of the same old-branch issue (pre-fix `ConnectionManager`).

---

## Reproduce

```bash
cd backend
python3 -m pytest \
  tests/test_sprint1_verification.py \
  tests/test_rate_limiting.py \
  tests/test_e2e_training_flow.py \
  tests/test_ws_resilience.py \
  --base-url http://localhost:8002 -v
```

Load tests (`test_load.py`) are gated on `-m load` and were NOT included in
this run — they need a dedicated QA window because they open 100 sockets and
start training across many clients. Schedule separately.
