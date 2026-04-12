# Test Coverage Report — 2026-04-12

**Branch:** `yoon/qa-engineer`
**Run:** `pytest backend/tests/test_engine.py backend/tests/test_bot.py backend/tests/test_env.py backend/tests/test_game_scenarios.py backend/tests/test_integration.py backend/tests/test_coverage_gaps.py --cov=backend --cov-report=term-missing --cov-report=html:backend/htmlcov`
**Result:** 98 passed in 223s
**HTML report:** `backend/htmlcov/index.html`

---

## Summary

| Layer | Files | Stmts | Coverage | Status |
|-------|-------|-------|----------|--------|
| `backend/game/` | 3 | 281 | **100%** | ✅ Fully covered |
| `backend/rl/` | 4 | 344 | **72%** | ⚠️ trainer/callbacks gaps |
| `backend/app/` | 9 | 305 | **0%** | ❌ NO unit tests |
| **Source (non-test) total** | 16 | 930 | **~56%** | ⚠️ Below 80% target |

Total reported coverage 47% includes integration-only test files
(`test_e2e_training_flow.py`, `test_load.py`, `test_rate_limiting.py`,
`test_regression.py`, `test_sprint1_verification.py`, `test_ws_resilience.py`)
that run against live environments via `--base-url` and are excluded from
the unit-test coverage pass. Their own statements count toward the
denominator but none execute here, dragging the total down.

---

## Per-module detail

### ✅ Fully-covered modules (green)

| Module | Stmts | Cover |
|--------|-------|-------|
| `backend/game/bot.py` | 104 | **100%** |
| `backend/game/constants.py` | 17 | **100%** |
| `backend/game/engine.py` | 160 | **100%** |
| `backend/rl/env.py` | 81 | **99%** |
| `backend/rl/evaluator.py` | 53 | **98%** |

Core game engine and RL environment are comprehensively tested. The
single uncovered branch in `env.py:154` is the render-path fallback,
and `evaluator.py:88` is the empty-model-list guard in
`compare_checkpoints`. Both acceptable.

### ⚠️ Partial coverage — needs work

#### `backend/rl/callbacks.py` — 56% (47 of 108 lines uncovered)

Uncovered ranges: `45, 50-51, 63-65, 119-127, 130-171, 175-180, 200-210`

What's missing:

- `FramesCallback._on_step` — live frame emission to frames queue
- `ResultsCallback._on_step` — game-result dispatch
- `MetricsCallback._on_step` — partial (happy path covered;
  error/disconnect branches missing)
- `MetricsCallback.__init__` timing fields

**Why it matters:** These callbacks are the bridge between SB3 and the
WebSocket broadcast layer. If a queue is full or the listener is gone,
the callbacks must not kill training. Today that safety is unverified.

**Proposed additions:**

```python
# tests/test_callbacks.py
def test_metrics_callback_handles_full_queue()
def test_frames_callback_emits_at_configured_interval()
def test_frames_callback_drops_when_queue_full_without_crashing()
def test_results_callback_emits_on_episode_end()
def test_results_callback_tolerates_missing_info_keys()
```

#### `backend/rl/trainer.py` — 47% (54 of 102 lines uncovered)

Uncovered ranges: `68-87, 91-97, 105-121, 137-206, 210-214, 222-229`

What's missing:

- `TrainingManager._train_loop` — the actual threaded training loop
- `TrainingManager.start` error paths
- `stop()` / `resume()` / `set_bot_level()` state transitions
- `status` property under various states

**Why it matters:** BUG-3 (double-start crash) and BUG-5 (state sync)
both live in this area. Without unit tests, we rely on live-env
regression tests to catch regressions — which means changes here may
ship to QA before they're caught.

**Proposed additions:**

```python
# tests/test_trainer.py
def test_start_twice_raises_or_returns_same_experiment_id()
def test_stop_before_start_is_noop()
def test_resume_without_prior_start_raises()
def test_set_bot_level_during_training_updates_env()
def test_set_bot_level_while_stopped_persists_for_next_start()
def test_status_transitions_stopped_running_stopped()
def test_metrics_queue_isolated_per_manager()
```

### ❌ Zero-coverage modules

All `backend/app/` modules have **0% unit coverage**:

| Module | Stmts | Cover |
|--------|-------|-------|
| `backend/app/api/routes.py` | 59 | 0% |
| `backend/app/main.py` | 41 | 0% |
| `backend/app/models/schemas.py` | 38 | 0% |
| `backend/app/services/eval_service.py` | 23 | 0% |
| `backend/app/services/game_service.py` | 24 | 0% |
| `backend/app/services/replay_service.py` | 25 | 0% |
| `backend/app/services/training_service.py` | 16 | 0% |
| `backend/app/ws/handlers.py` | 57 | 0% |
| `backend/app/ws/manager.py` | 22 | 0% |

**Why it matters:** The app layer is verified only by integration tests
hitting a running dev/qa server. That gives real-environment fidelity,
but:

1. CI without a live server cannot catch regressions.
2. Edge cases that require mocking (e.g., MongoDB connection loss,
   partial queue drain, disconnection mid-broadcast) are difficult to
   reach through integration tests.
3. A broken Pydantic schema (`EvalRunRequest`) passes unit tests
   because no unit test imports it.

**Proposed test files:**

| Test file | Target | Approach |
|-----------|--------|----------|
| `tests/test_routes.py` | `api/routes.py` | `fastapi.testclient.TestClient` with stubbed `app.state` services |
| `tests/test_schemas.py` | `models/schemas.py` | Pydantic validation — boundary values, missing fields, coercion |
| `tests/test_ws_manager.py` | `ws/manager.py` | In-process `ConnectionManager`; mock `WebSocket` sink; verify broadcast + disconnect cleanup |
| `tests/test_ws_handlers.py` | `ws/handlers.py` | `_dispatch` called with mock WS + mock training_service |
| `tests/test_services.py` | `services/*` | Mock `motor` collections (`mongomock-motor` or fake client) |

### Service layer detail

- **`training_service.py`** — thin wrapper around `TrainingManager`.
  Tests should at minimum verify each method forwards its arguments
  intact. A test that mocks `TrainingManager` would catch BUG-5
  (field mismatch) at the wrapper boundary.
- **`replay_service.py`** — `load_replay` path construction and
  `save_replay` rotation behavior. Needs tmp_path fixture.
- **`game_service.py` / `eval_service.py`** — MongoDB-backed; should
  use `mongomock-motor` for unit tests.

---

## Gap priority (Sprint 2 candidates)

| # | Target | Current | Target | Rationale |
|---|--------|---------|--------|-----------|
| 1 | `ws/handlers.py` + `ws/manager.py` | 0% | ≥80% | BUG-3/BE-1 live here; regressions are high-impact |
| 2 | `rl/trainer.py` | 47% | ≥80% | Training correctness; state-machine bugs hide here |
| 3 | `api/routes.py` | 0% | ≥80% | HTTP contract surface; Pydantic validation |
| 4 | `rl/callbacks.py` | 56% | ≥80% | Broadcast bridge; silent failures are bad |
| 5 | `services/*` | 0% | ≥70% | Thin wrappers; lower risk but easy coverage wins |

Hitting all five would bring project coverage from **~56% → ~85%** on
non-test source files.

---

## What blocks this today

1. **No `fastapi.testclient` harness.** Adding one to `conftest.py`
   would make routes/WS trivially testable.
2. **No MongoDB fake.** `mongomock-motor` is ~5 lines to wire in.
3. **`TrainingManager` runs a real thread.** Unit tests need a seam
   to inject a fake trainer or a short-circuit mode.

None of these are large lifts. They can each land in a single PR.

---

## Appendix — Command to reproduce

```bash
cd backend
python3 -m pytest \
  tests/test_engine.py tests/test_bot.py tests/test_env.py \
  tests/test_game_scenarios.py tests/test_integration.py \
  tests/test_coverage_gaps.py \
  --cov=backend --cov-report=term-missing \
  --cov-report=html:backend/htmlcov
```

Live-environment tests (excluded from this pass because they require a
running server):

```bash
# Against QA
pytest tests/test_e2e_training_flow.py \
       tests/test_ws_resilience.py \
       tests/test_rate_limiting.py \
       tests/test_sprint1_verification.py \
       tests/test_regression.py \
       --base-url http://localhost:8002 -v

# Load tests (opt-in via marker)
pytest tests/test_load.py --base-url http://localhost:8002 -v -m load
```
