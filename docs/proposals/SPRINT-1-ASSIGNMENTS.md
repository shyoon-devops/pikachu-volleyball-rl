# Sprint 1 (v0.2.1) — Work Assignments

> **Date**: 2026-04-12 | **Approved by**: Project Manager
> **Policy**: CRITICAL/BLOCKER items first, then HIGH bugs, then remaining Sprint 1 items

---

## Priority 1: CRITICAL Security Issues (Backend Engineer)

### SEC-1. Path Traversal in Evaluation Endpoint

| Field | Value |
|-------|-------|
| Severity | **CRITICAL** |
| Assignee | **Backend Engineer** |
| File | `backend/app/api/routes.py:85-105` |
| Effort | 0.25d |

**Problem**: `EvalRunRequest.model_path` accepts arbitrary user string and passes it directly to the evaluator. An attacker can use `../../etc/passwd` or similar paths to escape the model directory.

**Required Fix**:
1. Resolve `model_path` against `MODEL_DIR` using `Path.resolve()`
2. Validate the resolved path is within `MODEL_DIR` boundary
3. Reject paths containing `..` or absolute paths
4. Return 400 for invalid paths with clear error message

**Verification**: `curl -X POST /api/evaluation/run -d '{"model_path":"../../etc/passwd"}' → 400`

---

### SEC-2. CORS Wildcard in Production

| Field | Value |
|-------|-------|
| Severity | **CRITICAL** |
| Assignee | **Backend Engineer** |
| File | `backend/app/main.py:69-73` |
| Effort | 0.25d |

**Problem**: `CORS_ORIGINS` defaults to `"*"` — all origins allowed in all environments including prod. This enables CSRF-like attacks from any domain.

**Required Fix**:
1. Set `CORS_ORIGINS` default to `http://localhost:3000` (dev only)
2. In `.env.qa`: `CORS_ORIGINS=http://localhost:3001`
3. In `.env.prod`: `CORS_ORIGINS=http://localhost:5173` (or actual prod domain)
4. Log configured origins at startup

**Verification**: Cross-origin request from unauthorized domain → blocked

---

### SEC-3. No Rate Limiting on REST API

| Field | Value |
|-------|-------|
| Severity | **CRITICAL** |
| Assignee | **Backend Engineer** |
| File | `backend/app/main.py` |
| Effort | 0.25d |

**Problem**: No rate limiting middleware. All endpoints are vulnerable to abuse — especially `/api/evaluation/run` (CPU-intensive) and `/api/games` (DB queries).

**Required Fix**:
1. Add `slowapi` rate limiting middleware
2. Global default: 60 req/min per IP
3. `/api/evaluation/run`: 5 req/min (already has semaphore, but needs rate limit too)
4. `/api/health`: exempt from rate limiting
5. Return 429 with `Retry-After` header

**Verification**: Rapid-fire requests → 429 after limit exceeded

---

## Priority 2: BLOCKER (Trainer + AI Engineer)

### TR-4. Training Session Protection

| Field | Value |
|-------|-------|
| Severity | **BLOCKER** |
| Assignee | **Trainer + AI Engineer** |
| Files | `backend/rl/trainer.py`, `backend/app/ws/handlers.py` |
| Effort | 0.5d |

**Problem**: Running training can be interfered with by any connected WS client. Current code only sends "already running" error message but doesn't lock the session — other commands (`training:stop`, `training:set_level`) can still be sent by any client, disrupting prod training.

**Required Fix**:
1. Add `locked` state to training session management
2. When training starts, set session to `locked` with owner client ID
3. Only the owner client (or `training:force_stop` with confirmation) can stop training
4. `training:set_level` during locked session: only owner can change
5. Add `training:force_stop` endpoint with explicit confirmation payload
6. Log all session state transitions

**Verification**:
- Client A starts training → Client B sends `training:stop` → rejected
- Client A sends `training:stop` → accepted
- `training:force_stop` with confirmation → always accepted (emergency)

---

## Priority 3: QA-Reported HIGH Bugs (Cross-team)

### BUG-1. WebSocket Queue Unbounded — Memory Leak Risk

| Field | Value |
|-------|-------|
| Severity | **HIGH** |
| Assignee | **Backend Engineer** |
| Related | BE-1 (WebSocket Heartbeat + Backpressure) |
| Effort | Included in BE-1 |

**Problem**: `metrics_queue`, `frames_queue`, `results_queue` in training service use `asyncio.Queue()` without `maxsize`. During long training sessions with slow/disconnected clients, queues grow unbounded → OOM.

**Fix**: Set `maxsize=1000` on all queues. On full queue, drop oldest entry (backpressure).

---

### BUG-2. Health Check Returns False "ok"

| Field | Value |
|-------|-------|
| Severity | **HIGH** |
| Assignee | **Backend Engineer** |
| Related | Sprint 2 BE-3 (pulled forward) |
| Effort | 0.25d |

**Problem**: `GET /api/health` returns `{"status": "ok"}` without verifying MongoDB connectivity, disk space, or training thread liveness. DevOps monitoring and QA automated checks rely on this endpoint.

**Fix**: Expand health check to verify: MongoDB ping, disk usage < 90%, training thread alive (if running), queue depth.

---

### BUG-3. Training Status Returns Incomplete Data

| Field | Value |
|-------|-------|
| Severity | **HIGH** |
| Assignee | **Trainer** |
| Effort | 0.25d |

**Problem**: `training_service.status()` doesn't return actual `current_step` or `current_episode` counts. The dashboard shows stale/zero values, making it impossible to monitor training progress.

**Fix**: Wire `MetricsCallback` step/episode counters into `status()` return dict. Include: `current_step`, `total_timesteps`, `current_episode`, `elapsed_time`, `bot_level`.

---

### BUG-4. Heartbeat Sends Ping But No Pong Protocol

| Field | Value |
|-------|-------|
| Severity | **HIGH** |
| Assignee | **Backend Engineer** |
| Related | BE-1 |
| Effort | Included in BE-1 |

**Problem**: `ConnectionManager._heartbeat()` sends `{"type": "ping"}` but the client has no pong handler. The heartbeat only detects send failures, not truly stale connections where the client receives but never responds.

**Fix**: Implement proper ping/pong protocol — server sends ping, expects pong within timeout. Frontend must implement pong response handler.

---

### BUG-5. /api/models and /api/replays No Pagination

| Field | Value |
|-------|-------|
| Severity | **HIGH** |
| Assignee | **Backend Engineer** |
| Related | Sprint 2 BE-2 (pulled forward partially) |
| Effort | 0.25d |

**Problem**: `/api/models` runs `model_dir.rglob("*.zip")` + `stat()` on every file. `/api/replays` does full glob + stat scan. With 100+ models/replays, response time degrades significantly. No `page`/`limit` parameters.

**Fix**: Add `page`/`limit` query parameters (default: page=1, limit=20). Apply to both endpoints. Sort by mtime descending.

---

### BUG-6. Game Result Save Failure Silently Drops Data

| Field | Value |
|-------|-------|
| Severity | **HIGH** |
| Assignee | **Backend Engineer** |
| File | `backend/app/ws/handlers.py:152-157` |
| Effort | 0.25d |

**Problem**: In `results_push_loop`, if `game_service.save_game()` fails, the exception is logged but the game result is lost permanently. No retry mechanism, no dead-letter queue.

**Fix**: Add retry with exponential backoff (3 attempts). If all retries fail, write to a local fallback file (`data/failed_results.jsonl`) for manual recovery. Emit WS error event.

---

### BUG-7. Frontend WS Reconnection Not Implemented

| Field | Value |
|-------|-------|
| Severity | **HIGH** |
| Assignee | **Frontend Engineer** |
| Effort | 0.25d |

**Problem**: When WebSocket disconnects (network glitch, server restart), the frontend shows "disconnected" but doesn't automatically reconnect. User must manually refresh the page to restore real-time updates.

**Fix**: Implement exponential backoff reconnection in `useWebSocket` hook (1s, 2s, 4s, 8s, max 30s). Show reconnecting indicator in UI. Resume subscription state after reconnection.

---

## Priority 4: Remaining Sprint 1 Items

### BE-1. WebSocket Heartbeat + Backpressure

| Field | Value |
|-------|-------|
| Assignee | **Backend Engineer** |
| Effort | 0.5d (includes BUG-1, BUG-4) |

**Scope**: Already partially implemented in `manager.py`. Remaining:
1. Add bounded queues (`maxsize=1000`) → addresses BUG-1
2. Implement proper ping/pong with client response → addresses BUG-4
3. Queue full → drop oldest with logging

---

### BE-4. Input Validation + Rate Limiting

| Field | Value |
|-------|-------|
| Assignee | **Backend Engineer** |
| Effort | 0.5d (overlaps SEC-1/2/3) |

**Scope**: WS message validation already done via Pydantic on dev. Remaining:
1. Path traversal fix → SEC-1
2. CORS fix → SEC-2
3. Rate limiting → SEC-3
4. Validate `bot_level` range in `training:set_level` (already has Pydantic)

**Note**: SEC-1/2/3 overlap significantly with BE-4. Backend Engineer should do them together.

---

### FE-3. GameCanvas Responsive Scaling

| Field | Value |
|-------|-------|
| Assignee | **Frontend Engineer** |
| Effort | 0.5d |

**Scope**: PixiJS canvas doesn't resize on window resize. Implement:
1. `ResizeObserver` on canvas container
2. Scale PixiJS renderer to container width while maintaining aspect ratio
3. Handle mobile viewport changes

---

### FE-1. Replay Keyboard Shortcuts

| Field | Value |
|-------|-------|
| Assignee | **Frontend Engineer** |
| Effort | 0.5d |

**Scope**:
1. Space → play/pause toggle
2. Left/Right arrow → seek ±1 second
3. `[` / `]` → speed decrease/increase
4. `F` → fullscreen toggle
5. Show shortcut help tooltip on `?` key

---

### FE-5. Accessibility (A11y) Improvements

| Field | Value |
|-------|-------|
| Assignee | **Frontend Engineer** |
| Effort | 0.5d |

**Scope**:
1. ARIA labels on all interactive elements
2. Keyboard navigation (Tab order, focus indicators)
3. Screen reader support for training status/metrics
4. Color contrast compliance (WCAG AA)
5. Reduced motion support (`prefers-reduced-motion`)

---

### QA-2. CI/CD Test Pipeline

| Field | Value |
|-------|-------|
| Assignee | **QA Engineer** |
| Effort | 1d |

**Scope**:
1. GitHub Actions workflow: run all backend tests + frontend tests on PR
2. Coverage gate: fail PR if coverage < 80%
3. Lint gate: `ruff check` + `eslint` must pass
4. Test result summary in PR comment

---

### QA-4. Security Auto-Scan

| Field | Value |
|-------|-------|
| Assignee | **QA Engineer** |
| Effort | 0.5d |

**Scope**:
1. `bandit` scan for Python security issues in CI
2. `npm audit` for frontend dependencies
3. SAST scan results as PR check
4. Block merge on HIGH/CRITICAL findings

---

## Team Assignment Summary

### Backend Engineer (Day 1-3)

```
Day 1 (CRITICAL — 최우선):
  AM: SEC-1 Path Traversal fix + SEC-2 CORS fix          (0.5d)
  PM: SEC-3 Rate Limiting (slowapi)                       (0.25d)
      BUG-2 Health Check expansion                        (0.25d)

Day 2:
  AM: BE-1 WS Heartbeat + Backpressure                   (0.5d)
      (includes BUG-1 queue bounds + BUG-4 ping/pong)
  PM: BUG-5 Models/Replays pagination                    (0.25d)
      BUG-6 Game result save retry                        (0.25d)

Day 3:
  AM: BE-4 remaining input validation                     (0.25d)
  PM: 자체 테스트 + 코드 리뷰                              (0.25d)
```

**Total**: ~3d | **Items**: SEC-1, SEC-2, SEC-3, BE-1, BE-4, BUG-1, BUG-2, BUG-4, BUG-5, BUG-6

---

### Trainer + AI Engineer (Day 1-2)

```
Day 1:
  TR-4 Training Session Protection (BLOCKER)              (0.5d)
  - Trainer: session lock logic in trainer.py
  - AI Engineer: WS handler changes in handlers.py

Day 2:
  BUG-3 Training Status data completeness                 (0.25d)
  자체 테스트 + 통합 검증                                   (0.25d)
```

**Total**: ~1d | **Items**: TR-4, BUG-3

---

### Frontend Engineer (Day 1-3)

```
Day 1:
  AM: BUG-7 WS Reconnection logic                        (0.25d)
  PM: FE-3 GameCanvas responsive scaling                  (0.5d)

Day 2:
  AM: FE-1 Replay keyboard shortcuts                      (0.5d)
  PM: FE-5 Accessibility improvements                     (0.5d)

Day 3:
  AM: WS pong handler (BUG-4 frontend counterpart)        (0.25d)
  PM: 자체 테스트 + 코드 리뷰                              (0.25d)
```

**Total**: ~2.5d | **Items**: FE-3, FE-1, FE-5, BUG-7, BUG-4(FE side)

---

### QA Engineer (Day 1-3)

```
Day 1:
  QA-2 CI/CD Test Pipeline setup                          (1d)

Day 2:
  AM: QA-4 Security auto-scan (bandit + npm audit)        (0.5d)
  PM: SEC-1/2/3 fix 검증 + regression 테스트               (0.5d)

Day 3:
  BUG-1~7 fix 검증 + Sprint 1 전체 QA 리포트              (1d)
```

**Total**: ~3d | **Items**: QA-2, QA-4, 전체 검증

---

### DevOps Engineer (Day 1-2)

```
Day 1:
  v0.2.0 QA 환경 배포 (Issue #6)                          (0.5d)
  .env.qa / .env.prod CORS_ORIGINS 설정 업데이트            (0.25d)

Day 2:
  QA 환경 모니터링 + 배포 이슈 대응                         (대기)
```

**Total**: ~1d | **Items**: QA deploy, env config update

---

## Sprint 1 Expanded Scope Summary

| Category | Count | Items |
|----------|-------|-------|
| CRITICAL Security | 3 | SEC-1, SEC-2, SEC-3 |
| BLOCKER | 1 | TR-4 |
| HIGH Bugs (QA) | 7 | BUG-1 ~ BUG-7 |
| Sprint 1 Original | 7 | BE-1, BE-4, FE-1, FE-3, FE-5, QA-2, QA-4 |
| **Total** | **18** | (overlap: BUG-1/4 in BE-1, SEC-1/2/3 in BE-4) |
| **Net unique work items** | **14** | (after overlap consolidation) |

## Definition of Done

- [ ] All CRITICAL security fixes verified with test cases
- [ ] TR-4 blocker: training session cannot be interrupted by external clients
- [ ] All 7 HIGH bugs fixed with regression tests
- [ ] All Sprint 1 items implemented and tested
- [ ] Backend test coverage ≥ 80%
- [ ] CI/CD pipeline running on PRs
- [ ] Security scan passing
- [ ] QA 검증 리포트 완료
- [ ] PM prod 배포 승인 판단
