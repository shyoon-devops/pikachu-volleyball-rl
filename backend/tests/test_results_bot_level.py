"""Regression tests for the "all games saved as L1" bug.

Context
-------
Users reported that every row in Recent Games (/api/games) showed L1
regardless of the actual training difficulty. Root cause was a 3-layer
silent-default chain:

* ``LiveFrameCallback._on_step`` omitted ``bot_level`` /
  ``experiment_id`` from the results dict it enqueued.
* ``handlers.results_push_loop`` coerced missing ``bot_level`` to 1
  via ``data.get("bot_level", 1)`` — hiding the upstream omission.
* ``TrainingManager.set_bot_level`` mid-run updated ``_bot_level`` on
  the manager but never propagated to the already-cached
  ``LiveFrameCallback.bot_level`` field.

Fix
---
The callback now snapshots ``manager._bot_level`` /
``manager._experiment_id`` at the *start* of every demo game it plays
— so both the in-process demo opponent and the saved GameRecord
reflect the user's current intent. The handler no longer supplies a
silent default; a missing field falls through to the dead-letter so
the regression is loud next time.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from backend.rl import callbacks as callbacks_mod
from backend.rl.callbacks import LiveFrameCallback


class _FakeManager:
    """Minimal TrainingManager stand-in exposing the fields the callback reads.

    Using a bare stub rather than a real TrainingManager keeps the unit test
    hermetic — we do not want to spin up a training thread just to verify
    the callback reads ``_bot_level`` at demo-start.
    """

    def __init__(self, bot_level: int, experiment_id: str) -> None:
        self._bot_level = bot_level
        self._experiment_id = experiment_id
        self.last_frame: dict | None = None


def _run_one_demo(
    monkeypatch: pytest.MonkeyPatch,
    manager: _FakeManager | None,
    cached_bot_level: int = 1,
    tmp_path: Path | None = None,
) -> dict[str, Any]:
    """Drive LiveFrameCallback._on_step once and return the enqueued result.

    The real demo loop plays to MAX_SCORE=15 which is far too slow for a
    unit test. We patch it to 1 so one ground-out ends the game. We also
    stub out model.predict to a deterministic no-op action.
    """
    monkeypatch.setattr(callbacks_mod, "MAX_SCORE", 1)

    loop = asyncio.new_event_loop()
    frames_q: asyncio.Queue[dict] = asyncio.Queue()
    results_q: asyncio.Queue[dict] = asyncio.Queue()

    cb = LiveFrameCallback(
        frames_queue=frames_q,
        results_queue=results_q,
        loop=loop,
        bot_level=cached_bot_level,
        play_interval=1,
        replay_dir=str(tmp_path or Path("/tmp")),
        manager=manager,
    )
    cb.num_timesteps = 1

    # The real model.predict does inference; for this test any int action
    # works because we only need the demo loop to tick until ground-out.
    fake_model = MagicMock()
    fake_model.predict.return_value = (0, None)
    cb.model = fake_model

    captured: list[dict] = []

    def _capture(loop_: Any, queue: asyncio.Queue, item: dict) -> None:
        # Bypass the cross-thread marshal so the test sees every enqueue
        # synchronously — we would otherwise need to pump the event loop.
        captured.append(item)

    monkeypatch.setattr(callbacks_mod, "_safe_enqueue", _capture)

    assert cb._on_step() is True
    loop.close()

    # The demo produces many frames (stream) and exactly one result
    # (game end). Separate them by schema — results carry ``winner``.
    results = [c for c in captured if "winner" in c]
    assert len(results) == 1, f"expected 1 result, got {len(results)}: {results}"
    return results[0]


def test_result_carries_bot_level_from_manager(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """Pre-fix: saved games were all L1. Post-fix: saved level tracks manager."""
    manager = _FakeManager(bot_level=3, experiment_id="exp-abc")
    # Cached value on the callback is 1 — the point of this test is that
    # the *manager's* value wins, not whatever __init__ saw.
    result = _run_one_demo(monkeypatch, manager, cached_bot_level=1, tmp_path=tmp_path)

    assert result["bot_level"] == 3
    assert result["experiment_id"] == "exp-abc"
    assert "game_id" in result
    assert "winner" in result


def test_result_reflects_mid_run_set_level(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """set_bot_level mid-run must update the next saved game's level.

    SubprocVecEnv workers are forked with the initial level so mid-run
    set_level cannot change what PPO actually learns from — that is
    documented behavior. But the *demo* opponent the callback plays
    runs in-process, and the saved GameRecord records that demo. This
    test pins both: read-back at demo-start → manager is source of
    truth → set_level mid-run reflects in the next save.
    """
    manager = _FakeManager(bot_level=1, experiment_id="exp-mid")
    first = _run_one_demo(monkeypatch, manager, tmp_path=tmp_path)
    assert first["bot_level"] == 1

    # Simulate PM flipping the dial on a running session.
    manager._bot_level = 5
    second = _run_one_demo(monkeypatch, manager, tmp_path=tmp_path)
    assert second["bot_level"] == 5


def test_result_falls_back_to_init_level_without_manager(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """Manager-less construction (unit tests, legacy code) still works.

    The callback can be built without a TrainingManager for isolated
    tests. In that case the cached __init__ level is used — the same
    behavior as before the fix — so existing tests don't silently
    regress on bot_level semantics.
    """
    result = _run_one_demo(monkeypatch, manager=None, cached_bot_level=4, tmp_path=tmp_path)
    assert result["bot_level"] == 4
    assert result["experiment_id"] == ""


def test_result_handles_none_experiment_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """Manager may have _experiment_id=None briefly between start() calls.

    ``TrainingManager._experiment_id`` is typed ``str`` but legacy paths
    (interrupted resume, manual teardown in tests) can leave it None.
    The callback must coerce to an empty string so GameRecord validation
    (``experiment_id: str``) doesn't explode the results loop.
    """
    manager = _FakeManager(bot_level=2, experiment_id="")
    manager._experiment_id = None  # type: ignore[assignment]
    result = _run_one_demo(monkeypatch, manager, tmp_path=tmp_path)
    assert result["experiment_id"] == ""
    assert result["bot_level"] == 2
