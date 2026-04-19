"""Tests for UpdateWindowCallback — gradient-update WS event emission.

The callback is a BaseCallback that fires on SB3 rollout boundaries;
we drive the lifecycle methods directly instead of running an actual
learn loop. Queue drain verifies the payload shape contract the FE
subscribes to.
"""

from __future__ import annotations

import asyncio
from typing import Any

from backend.rl.callbacks import UpdateWindowCallback


def _make(
    experiment_id: str = "exp_abc",
) -> tuple[UpdateWindowCallback, asyncio.AbstractEventLoop, asyncio.Queue]:
    loop = asyncio.new_event_loop()
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=64)
    cb = UpdateWindowCallback(
        update_events_queue=queue,
        loop=loop,
        experiment_id=experiment_id,
    )
    return cb, loop, queue


def _drain(
    loop: asyncio.AbstractEventLoop, queue: asyncio.Queue
) -> list[dict[str, Any]]:
    loop.call_soon(loop.stop)
    loop.run_forever()
    items = []
    while True:
        try:
            items.append(queue.get_nowait())
        except asyncio.QueueEmpty:
            break
    return items


# ─── First-rollout latch ──────────────────────────────────────────────


class TestFirstRolloutLatch:
    def test_initial_on_rollout_start_is_skipped(self) -> None:
        # Before any _on_rollout_end has fired, the very first
        # _on_rollout_start must NOT emit — there's no preceding
        # gradient update to close.
        cb, loop, queue = _make()
        cb._on_rollout_start()
        items = _drain(loop, queue)
        assert items == []
        loop.close()

    def test_first_rollout_end_emits_update_start(self) -> None:
        cb, loop, queue = _make()
        cb._on_rollout_end()
        items = _drain(loop, queue)
        assert len(items) == 1
        assert items[0]["type"] == "training:update_start"
        assert items[0]["experiment_id"] == "exp_abc"
        loop.close()

    def test_second_rollout_start_emits_update_end(self) -> None:
        # After the first _on_rollout_end has latched the flag,
        # subsequent _on_rollout_start calls DO emit update_end.
        cb, loop, queue = _make()
        cb._on_rollout_end()     # latches flag + emits update_start
        cb._on_rollout_start()   # now emits update_end
        items = _drain(loop, queue)
        types = [i["type"] for i in items]
        assert types == ["training:update_start", "training:update_end"]
        loop.close()


# ─── Full rollout cadence ─────────────────────────────────────────────


class TestRolloutCadence:
    def test_three_rollouts_produce_expected_event_sequence(self) -> None:
        # Simulated learn loop:
        #   rollout 1: rollout_start (skip), rollout_end → start
        #   rollout 2: rollout_start → end, rollout_end → start
        #   rollout 3: rollout_start → end, rollout_end → start
        # Expected types: start, end, start, end, start (5 events).
        cb, loop, queue = _make()
        cb._on_rollout_start()  # skip (first)
        cb._on_rollout_end()    # start
        cb._on_rollout_start()  # end
        cb._on_rollout_end()    # start
        cb._on_rollout_start()  # end
        cb._on_rollout_end()    # start
        items = _drain(loop, queue)
        assert [i["type"] for i in items] == [
            "training:update_start",
            "training:update_end",
            "training:update_start",
            "training:update_end",
            "training:update_start",
        ]
        loop.close()

    def test_experiment_id_consistent_across_all_events(self) -> None:
        cb, loop, queue = _make(experiment_id="run_7af92")
        for _ in range(3):
            cb._on_rollout_end()
            cb._on_rollout_start()
        items = _drain(loop, queue)
        assert all(i["experiment_id"] == "run_7af92" for i in items)
        loop.close()


# ─── Payload shape ────────────────────────────────────────────────────


class TestPayloadShape:
    def test_minimal_payload_has_type_and_experiment_id(self) -> None:
        cb, loop, queue = _make()
        cb._on_rollout_end()
        items = _drain(loop, queue)
        assert set(items[0].keys()) == {"type", "experiment_id"}
        loop.close()

    def test_on_step_returns_true_and_emits_nothing(self) -> None:
        # _on_step is called every env step; it must be cheap and must
        # not emit events of its own.
        cb, loop, queue = _make()
        for _ in range(100):
            assert cb._on_step() is True
        items = _drain(loop, queue)
        assert items == []
        loop.close()


# ─── Queue interactions ───────────────────────────────────────────────


class TestQueueInteractions:
    def test_enqueue_on_closed_loop_does_not_raise(self) -> None:
        # Matches the existing _safe_enqueue contract: a closed loop
        # must not wedge the training thread. We close the loop
        # BEFORE emitting.
        cb, loop, _q = _make()
        loop.close()
        cb._on_rollout_end()  # must not raise

    def test_independent_queues_isolate_runs(self) -> None:
        # Two callbacks on two runs — each must only see its own
        # events on its own queue. No cross-talk.
        cb1, loop1, q1 = _make(experiment_id="run_a")
        cb2, loop2, q2 = _make(experiment_id="run_b")
        cb1._on_rollout_end()
        cb2._on_rollout_end()
        items1 = _drain(loop1, q1)
        items2 = _drain(loop2, q2)
        assert items1 == [
            {"type": "training:update_start", "experiment_id": "run_a"}
        ]
        assert items2 == [
            {"type": "training:update_start", "experiment_id": "run_b"}
        ]
        loop1.close()
        loop2.close()
