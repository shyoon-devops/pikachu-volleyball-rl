"""WS push-loop integration test for training:update_start/update_end.

Verifies that the consumer side of the UpdateWindowCallback contract
(``update_events_push_loop``) forwards records verbatim to
``ConnectionManager.broadcast`` — unlike the frames/metrics/league
loops, this one does NOT wrap the payload with a type field, because
the callback already produces fully-formed WS envelopes.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.app.ws.handlers import update_events_push_loop


@pytest.mark.asyncio
async def test_push_loop_forwards_envelopes_verbatim() -> None:
    # Build a training_service-like stub exposing the queue path the
    # loop reads.
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=8)
    await queue.put(
        {"type": "training:update_start", "experiment_id": "exp_x"}
    )
    await queue.put(
        {"type": "training:update_end", "experiment_id": "exp_x"}
    )

    service = MagicMock()
    service.manager.update_events_queue = queue

    manager = MagicMock()
    manager.broadcast = AsyncMock()

    # Run the drain loop as a background task and give it just enough
    # time to process the two records, then cancel.
    task = asyncio.create_task(update_events_push_loop(manager, service))
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    # Both payloads forwarded verbatim (no extra wrapping).
    assert manager.broadcast.await_count == 2
    sent = [call.args[0] for call in manager.broadcast.await_args_list]
    assert sent[0] == {
        "type": "training:update_start",
        "experiment_id": "exp_x",
    }
    assert sent[1] == {
        "type": "training:update_end",
        "experiment_id": "exp_x",
    }
