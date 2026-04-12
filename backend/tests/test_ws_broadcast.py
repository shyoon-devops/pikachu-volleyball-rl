"""Tests for the parallel broadcast refactor (BE-6) in ConnectionManager.

The previous implementation iterated clients sequentially and called
``ws.send_json`` (re-serializing per client). The concurrency and serialize-
once properties are load-bearing for the training push loops at dashboard
scale, so we pin them here rather than rely on manual inspection.

Design notes
------------
* We build a minimal ``_FakeWebSocket`` that records every ``send_text`` call
  and can be configured to sleep or raise. This lets us assert both *what*
  was sent and *when* — the latter is the only way to prove sends happened in
  parallel rather than sequence.
* ``asyncio.sleep`` is our clock: if five 200ms-slow clients finish in
  ~200ms we know they ran concurrently; a serial loop would take ~1s.
* We bypass ``connect()`` (which would call ``ws.accept()`` on a real socket
  and start a heartbeat task) by poking directly into the private dict.
  This is intentional — ``broadcast`` is what's under test.
"""

from __future__ import annotations

import asyncio
import json
import time
from unittest.mock import patch

import pytest

from backend.app.ws import manager as manager_mod
from backend.app.ws.manager import SEND_TIMEOUT, ConnectionManager


class _FakeWebSocket:
    """Stand-in for ``fastapi.WebSocket`` used by broadcast tests.

    Only the attributes broadcast touches are implemented. ``send_text`` is
    an async method so it plugs into ``asyncio.wait_for`` the same way the
    real implementation does.
    """

    def __init__(
        self,
        *,
        delay: float = 0.0,
        raise_on_send: BaseException | None = None,
    ) -> None:
        self.delay = delay
        self.raise_on_send = raise_on_send
        self.sent: list[str] = []
        self.send_times: list[float] = []

    async def send_text(self, payload: str) -> None:
        if self.delay:
            await asyncio.sleep(self.delay)
        self.send_times.append(time.monotonic())
        if self.raise_on_send is not None:
            raise self.raise_on_send
        self.sent.append(payload)


def _register(mgr: ConnectionManager, ws: _FakeWebSocket) -> None:
    """Bypass ``connect()`` and register a fake client directly.

    ``connect()`` awaits ``ws.accept()`` and spawns a heartbeat task, neither
    of which is meaningful for the broadcast unit-of-work we're testing.
    """
    # The heartbeat task attribute isn't inspected by broadcast; None is fine.
    mgr._connections[ws] = None  # type: ignore[assignment]


# --- Basic behavior ---------------------------------------------------------


@pytest.mark.asyncio
async def test_broadcast_empty_connection_set_is_noop():
    """No clients → no gather, no serialize, no state change."""
    mgr = ConnectionManager()
    # Patch json.dumps so we can assert it was never called.
    with patch.object(manager_mod.json, "dumps") as dumps:
        await mgr.broadcast({"type": "noise"})
    assert dumps.call_count == 0


@pytest.mark.asyncio
async def test_broadcast_serializes_payload_exactly_once():
    """Serialize-once property: N clients → 1 json.dumps call.

    This is the cheap part, but the property matters at fleet scale — a
    regression that flips back to send_json would re-serialize per client.
    """
    mgr = ConnectionManager()
    clients = [_FakeWebSocket() for _ in range(5)]
    for c in clients:
        _register(mgr, c)

    original_dumps = json.dumps
    with patch.object(manager_mod.json, "dumps", wraps=original_dumps) as dumps:
        await mgr.broadcast({"type": "training:metrics", "payload": {"step": 1}})

    assert dumps.call_count == 1
    # Every client got the same serialized string.
    payloads = {c.sent[0] for c in clients}
    assert len(payloads) == 1


@pytest.mark.asyncio
async def test_broadcast_delivers_valid_json_to_every_client():
    mgr = ConnectionManager()
    clients = [_FakeWebSocket() for _ in range(3)]
    for c in clients:
        _register(mgr, c)

    message = {"type": "training:frame", "payload": {"n": 42}}
    await mgr.broadcast(message)

    for c in clients:
        assert len(c.sent) == 1
        # Round-trip confirms the payload landed uncorrupted.
        assert json.loads(c.sent[0]) == message


# --- Concurrency ------------------------------------------------------------


@pytest.mark.asyncio
async def test_broadcast_dispatches_clients_in_parallel():
    """Five 200ms-slow clients finishing in ~200ms proves parallel dispatch.

    Serial dispatch would take ~1s. We allow a generous upper bound (500ms)
    so a slow CI host doesn't false-positive, but the gap between 200ms and
    1s is wide enough that the assertion is meaningful.
    """
    mgr = ConnectionManager()
    per_send = 0.2
    clients = [_FakeWebSocket(delay=per_send) for _ in range(5)]
    for c in clients:
        _register(mgr, c)

    start = time.monotonic()
    await mgr.broadcast({"type": "training:metrics", "payload": {}})
    elapsed = time.monotonic() - start

    # Parallel → near per_send. Serial would be 5 * per_send = 1.0s.
    assert elapsed < 0.5, f"broadcast ran serially (elapsed={elapsed:.3f}s)"
    for c in clients:
        assert len(c.sent) == 1


@pytest.mark.asyncio
async def test_slow_client_does_not_block_fast_clients():
    """A single slow client must not hold up the others' completion.

    Even though we ``await`` gather (which resolves when all clients finish),
    *each* fast client's send_text should have landed well before the slow
    one. We compare send-completion timestamps to assert that ordering.
    """
    mgr = ConnectionManager()
    slow = _FakeWebSocket(delay=0.3)
    fast1 = _FakeWebSocket(delay=0.0)
    fast2 = _FakeWebSocket(delay=0.0)
    for c in (slow, fast1, fast2):
        _register(mgr, c)

    start = time.monotonic()
    await mgr.broadcast({"type": "ping"})

    # Fast clients should have logged their send within the first ~100ms.
    for f in (fast1, fast2):
        assert (f.send_times[0] - start) < 0.1


# --- Error handling ---------------------------------------------------------


@pytest.mark.asyncio
async def test_client_raising_on_send_is_disconnected():
    """A client whose send_text raises is removed from the pool; others still receive."""
    mgr = ConnectionManager()
    good = _FakeWebSocket()
    bad = _FakeWebSocket(raise_on_send=RuntimeError("socket closed"))
    _register(mgr, good)
    _register(mgr, bad)

    await mgr.broadcast({"type": "hello"})

    assert good in mgr._connections
    assert bad not in mgr._connections
    assert len(good.sent) == 1


@pytest.mark.asyncio
async def test_timeout_client_is_disconnected_and_others_proceed(monkeypatch):
    """A wedged client past SEND_TIMEOUT is force-disconnected; others succeed.

    We shrink SEND_TIMEOUT for the duration of the test so the hung client
    only costs us ~50ms instead of the 5s production default.
    """
    monkeypatch.setattr(manager_mod, "SEND_TIMEOUT", 0.05)

    mgr = ConnectionManager()
    # delay > SEND_TIMEOUT → asyncio.wait_for raises TimeoutError → disconnect.
    hung = _FakeWebSocket(delay=1.0)
    healthy = _FakeWebSocket()
    _register(mgr, hung)
    _register(mgr, healthy)

    start = time.monotonic()
    await mgr.broadcast({"type": "x"})
    elapsed = time.monotonic() - start

    # The hung client must not have pinned the broadcast for a full second.
    assert elapsed < 0.5
    assert hung not in mgr._connections
    assert healthy in mgr._connections
    assert len(healthy.sent) == 1


@pytest.mark.asyncio
async def test_non_serializable_payload_is_logged_and_dropped(caplog):
    """Malformed payload must not crash the broadcast or partially send."""
    mgr = ConnectionManager()
    ws = _FakeWebSocket()
    _register(mgr, ws)

    # A self-referential dict defeats even the ``default=str`` fallback
    # because ``default`` is only consulted for leaf values, not for
    # container cycles — json.dumps raises ValueError instead.
    cycle: dict = {}
    cycle["self"] = cycle

    import logging

    with caplog.at_level(logging.ERROR, logger="backend.app.ws.manager"):
        await mgr.broadcast(cycle)

    assert ws.sent == []  # nothing sent
    assert ws in mgr._connections  # not disconnected — serialization fault is server-side
    assert any("not JSON-serializable" in r.message for r in caplog.records)


# --- Invariant --------------------------------------------------------------


def test_send_timeout_is_reasonable():
    """Guard against someone tuning SEND_TIMEOUT into a footgun.

    If somebody sets this to 0.001 we want CI to yelp, not discover it after
    clients get cut mid-keepalive. If someone sets it to 300 we've lost the
    latency-bounding property the refactor was introduced for.
    """
    assert 0.5 <= SEND_TIMEOUT <= 30.0
