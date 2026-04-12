# Prod Environment QA Report

- **Date**: 2026-04-12
- **Environment**: prod (http://localhost:8003, MongoDB :27020)
- **Tester**: QA Engineer (automated)
- **Verdict**: **FAIL** (0/7 PASS)

---

## Test Results Summary

| # | Category | Verdict | Issues Found |
|---|----------|---------|-------------|
| 1 | API Functionality | **FAIL** | Invalid ID returns generic 500, no input sanitization |
| 2 | WebSocket | **FAIL** | Ghost state on boot, no frames pushed during training |
| 3 | Training Lifecycle | **FAIL** | Ghost state, set_level ignored, negative timesteps accepted |
| 4 | Replay Flow | **FAIL** | Game exists without replay data, data integrity broken |
| 5 | Model Evaluation | **FAIL** | All eval requests 500 (double .zip extension) |
| 6 | Error Handling | **FAIL** | 500 on all malformed inputs, WS crashes on bad data |
| 7 | Load Testing | **CONDITIONAL** | Throughput OK but no rate limiting, empty-data latency concerning |

---

## CRITICAL Issues (3)

### PROD-SEC-1: Path Traversal via model_path

Server attempts filesystem access with unsanitized paths.

```bash
curl -X POST http://localhost:8003/api/evaluation/run \
  -H "Content-Type: application/json" \
  -d '{"model_path": "../../../etc/passwd", "num_episodes": 3, "bot_level": 1}'
```

Server log: `ValueError: Error: the file ../../../etc/passwd wasn't a zip-file`
File was accessed. Only failed because it's not a zip.

**Fix**: Reject paths containing `..`. Resolve against allowed model directory.

### PROD-SEC-2: CORS Allows All Origins with Credentials

```bash
curl -sI -H "Origin: https://attacker.malicious.site" http://localhost:8003/api/health
# access-control-allow-origin: https://attacker.malicious.site
# access-control-allow-credentials: true
# access-control-allow-methods: DELETE, GET, HEAD, OPTIONS, PATCH, POST, PUT
```

Any origin can make credentialed requests to the API.

**Fix**: Restrict `allow_origins` to actual frontend domains only.

### PROD-SEC-3: No Rate Limiting

100 burst concurrent requests: 100x 200 OK, 0x 429.

**Fix**: Add rate limiting middleware or reverse proxy.

---

## HIGH Issues (7)

### PROD-BUG-1: Training Ghost State on Boot

Server starts with `state: "running"`, `step: 0`, `episode: 0`. No metrics or frames pushed. Training is not actually running.

**Reproduce**:
1. Start prod server
2. `GET /api/training/status` → `{"state":"running","current_step":0,"current_episode":0}`
3. Connect WS, wait 30s → 0 messages

### PROD-BUG-2: Model Evaluation — Double .zip Extension

All evaluation requests return 500. `PPO.load()` appends `.zip` to path that already ends in `.zip`.

**Reproduce**:
```bash
curl -X POST http://localhost:8003/api/evaluation/run \
  -H "Content-Type: application/json" \
  -d '{"model_path": "10fa9a86-824f-449a-aedb-d88afc6c4391/10000.zip", "num_episodes": 3, "bot_level": 1}'
```
Server log: `FileNotFoundError: 10000.zip.zip`

**Fix**: Strip `.zip` suffix before passing to `PPO.load()` in `evaluator.py:35`.

### PROD-BUG-3: Negative Timesteps Accepted

Training starts with `total_timesteps: -1`. No server-side validation.

**Reproduce**:
```
WS → {"type":"training:start","data":{"total_timesteps":-1,"bot_level":1}}
```
Result: Training starts, frames are pushed.

**Fix**: Validate `total_timesteps > 0` and `1 <= bot_level <= 5`.

### PROD-BUG-4: WS Connection Dies on Missing/Invalid Input

All of these kill the WebSocket connection with no error message:
- `{"type":"training:start"}` (missing data)
- `{"type":"training:start","data":null}`
- `{"type":"training:start","data":{"total_timesteps":0,"bot_level":1}}`
- `"not-json"` (malformed)
- `""` (empty)

**Fix**: Catch exceptions in `_dispatch()`, return error JSON, keep connection alive.

### PROD-BUG-5: Double training:start Crashes WS (BUG-3 from QA)

```
WS → training:start
WS → training:start (while running)
```
`RuntimeError("Training is already running")` kills connection.

### PROD-BUG-6: Race Condition — 5 Concurrent Starts

5 simultaneous `training:start` → 1 succeeds, 4 connections die.

### PROD-BUG-7: training:frame Never Sent

Fresh `training:start` with 20s monitoring:
- `training:status`: 1
- `training:metrics`: 25
- `training:frame`: **0**

Frontend cannot render live game visualization during training.

---

## MEDIUM Issues (6)

### PROD-BUG-8: Security Headers Missing

`curl -sI http://localhost:8003/api/health` returns only `server: uvicorn`.
Missing: `X-Frame-Options`, `X-Content-Type-Options`, `Strict-Transport-Security`, `Content-Security-Policy`, `Referrer-Policy`.

### PROD-BUG-9: set_level Not Applied

```
WS → {"type":"training:set_level","data":{"level":3}}
Response → {"type":"training:status","payload":{"state":"running","bot_level":1}}
```
Level change ignored. Response shows `bot_level: 1`.

### PROD-BUG-10: Invalid Game ID Returns Generic 500

All of these return `Internal Server Error` with no detail:
```bash
GET /api/games/invalid-id          # 500
GET /api/games/가나다라              # 500
GET /api/games/';DROP TABLE;--     # 500
GET /api/games/%00                  # 500
GET /api/games/AAAA...(10000 chars) # 500
```

**Fix**: Catch `InvalidId` → `400 {"detail": "Invalid game ID format"}`.

### PROD-BUG-11: Eval Input Validation Missing

All return 500 instead of 422:
- `model_path: ""`
- `num_episodes: -1`
- `num_episodes: 0`
- `bot_level: 999`
- `bot_level: -1`
- `num_episodes: 999999`

**Fix**: Add Pydantic validators: `model_path` non-empty, `num_episodes > 0`, `1 <= bot_level <= 5`.

### PROD-BUG-12: Game-Replay Data Integrity

Game `69da6e7728b03b34167e1a69` exists in MongoDB (score 5-15) but replay returns 404. `experiment_id` is empty string.

### PROD-BUG-13: rally_count Always Zero

Game with score 5-15 shows `rally_count: 0`. Either rally tracking is unimplemented or broken.

---

## QA-Inherited Bugs (Confirmed in Prod)

| QA Bug | Status | Prod Confirmed |
|--------|--------|---------------|
| BUG-1: Invalid ObjectId 500 | Backend fixing | YES |
| BUG-2: Non-existent model 500 | Backend fixing | YES |
| BUG-3: Double start WS crash | Assigned | YES |

---

## Load Test Results

### Single Endpoint (50 concurrent, 10s)
| Metric | Value |
|--------|-------|
| Throughput | 3,940 req/s |
| P50 | 12.2ms |
| P95 | 17.8ms |
| P99 | 20.9ms |
| Error rate | 0.00% |

### Mixed Endpoints (30 concurrent, 10s)
| Endpoint | Throughput | P95 |
|----------|-----------|-----|
| /api/health | 372 req/s | 20.8ms |
| /api/training/status | 374 req/s | 20.8ms |
| /api/models | 373 req/s | 20.9ms |
| /api/games | 93 req/s | 75.4ms |
| /api/evaluation/results | 124 req/s | 57.4ms |

**Note**: `/api/games` and `/api/evaluation/results` are 3-4x slower despite near-empty data. Concern for data growth.

### WebSocket (20 concurrent, 5s)
| Metric | Value |
|--------|-------|
| Connections | 20/20 |
| Pings | 1,000 |
| Error rate | 0.0% |

---

## Total Issue Count

| Severity | Count |
|----------|-------|
| CRITICAL | 3 |
| HIGH | 7 |
| MEDIUM | 6 |
| **Total** | **16** |

---

## Verdict

**FAIL**. 16 issues found (3 CRITICAL security, 7 HIGH, 6 MEDIUM). CRITICAL issues must be fixed before any user-facing deployment.
