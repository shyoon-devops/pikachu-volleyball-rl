"""Regression tests for the BE-6 hotfix: training:status must reach every client.

Context
-------
Prior to this hotfix, _dispatch() acknowledged state transitions only to the
requesting WebSocket via ``ws.send_json(...)``. After BE-6 refactored broadcast
fan-out, QA observed that auxiliary tabs / the global ``TrainingStateProvider``
(FE-8) remained on "stopped" while training was actually running — they never
saw the status frame because it was unicast to the initiator.

What these tests pin
--------------------
* Every ``training:status`` transition (start / stop / resume / set_level) is
  broadcast to *all* connected clients, not just the requester.
* Rejections that are strictly caller-specific (``training:error`` for
  "already running") stay per-requester — broadcasting them would spam
  unrelated tabs.

The tests drive ``_dispatch`` directly with fake clients so the assertion is
on the dispatcher contract itself, not on any particular wire topology. The
push-loop broadcasts (metrics, frames, results) are already covered by
test_ws_broadcast.py and are orthogonal to this regression.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from backend.app.ws import handlers as handlers_mod
from backend.app.ws.manager import ConnectionManager
from backend.app.ws.validation import ParsedMessage
from backend.app.models.schemas import (
    WsEmptyPayload,
    WsSetLevelPayload,
    WsTrainingStartPayload,
)


# --- Test doubles -----------------------------------------------------------


class _FakeWebSocket:
    """Minimal WebSocket stand-in recording both unicast and broadcast frames.

    broadcast() uses ``send_text`` (serialize-once path); direct unicasts use
    ``send_json``. Capturing both lets each test assert precisely which path a
    message took — the whole point of the regression is that training:status
    must end up on the broadcast path.
    """

    def __init__(self) -> None:
        self.sent_text: list[str] = []
        self.sent_json: list[dict] = []

    async def send_text(self, payload: str) -> None:
        self.sent_text.append(payload)

    async def send_json(self, payload: dict) -> None:
        self.sent_json.append(payload)

    @property
    def received_messages(self) -> list[dict]:
        """All messages this client actually saw, regardless of path."""
        return [json.loads(p) for p in self.sent_text] + list(self.sent_json)


def _register(mgr: ConnectionManager, ws: _FakeWebSocket) -> None:
    # Skip connect()/accept() — broadcast is the unit under test.
    mgr._connections[ws] = None  # type: ignore[assignment]


def _make_training_service(state: str = "stopped", bot_level: int = 1) -> AsyncMock:
    """Build a training_service double that matches TrainingServiceWrapper.

    Only the methods _dispatch touches are stubbed; the shape of ``status()``
    mirrors the real wrapper's return.
    """
    svc = AsyncMock()
    svc.status = lambda: {"state": state, "bot_level": bot_level, "current_step": 0}
    svc.start = AsyncMock(return_value="exp-hotfix-1")
    svc.stop = AsyncMock(return_value=None)
    svc.resume = AsyncMock(return_value=None)
    svc.set_bot_level = lambda level: None
    return svc


def _statuses(ws: _FakeWebSocket) -> list[dict]:
    return [m for m in ws.received_messages if m.get("type") == "training:status"]


# --- Broadcast fan-out ------------------------------------------------------


@pytest.mark.asyncio
async def test_training_start_status_reaches_all_clients():
    """Initiator and every passive client must see the running transition.

    Without the fix, only the initiator saw training:status and the passive
    dashboard stayed on "stopped" — the exact QA-reported symptom.
    """
    mgr = ConnectionManager()
    initiator = _FakeWebSocket()
    passive = _FakeWebSocket()
    _register(mgr, initiator)
    _register(mgr, passive)

    svc = _make_training_service(state="stopped")
    msg = ParsedMessage(
        type="training:start",
        payload=WsTrainingStartPayload(bot_level=2, total_timesteps=5000),
    )

    await handlers_mod._dispatch(initiator, msg, svc, replay_service=AsyncMock(), manager=mgr)

    for client in (initiator, passive):
        statuses = _statuses(client)
        assert len(statuses) == 1, f"client missed training:status ({client is initiator=})"
        assert statuses[0]["payload"]["state"] == "running"
        assert statuses[0]["payload"]["experiment_id"] == "exp-hotfix-1"


@pytest.mark.asyncio
async def test_training_stop_status_reaches_all_clients():
    mgr = ConnectionManager()
    initiator = _FakeWebSocket()
    passive = _FakeWebSocket()
    _register(mgr, initiator)
    _register(mgr, passive)

    svc = _make_training_service(state="running")
    msg = ParsedMessage(type="training:stop", payload=WsEmptyPayload())

    await handlers_mod._dispatch(initiator, msg, svc, replay_service=AsyncMock(), manager=mgr)

    for client in (initiator, passive):
        statuses = _statuses(client)
        assert len(statuses) == 1
        assert statuses[0]["payload"] == {"state": "stopped"}


@pytest.mark.asyncio
async def test_training_resume_status_reaches_all_clients():
    mgr = ConnectionManager()
    initiator = _FakeWebSocket()
    passive = _FakeWebSocket()
    _register(mgr, initiator)
    _register(mgr, passive)

    svc = _make_training_service(state="paused")
    msg = ParsedMessage(type="training:resume", payload=WsEmptyPayload())

    await handlers_mod._dispatch(initiator, msg, svc, replay_service=AsyncMock(), manager=mgr)

    for client in (initiator, passive):
        statuses = _statuses(client)
        assert len(statuses) == 1
        assert statuses[0]["payload"] == {"state": "running"}


@pytest.mark.asyncio
async def test_training_set_level_status_reaches_all_clients():
    """Bot-level changes are session-wide — other dashboards must re-render."""
    mgr = ConnectionManager()
    initiator = _FakeWebSocket()
    passive = _FakeWebSocket()
    _register(mgr, initiator)
    _register(mgr, passive)

    svc = _make_training_service(state="running", bot_level=1)
    msg = ParsedMessage(type="training:set_level", payload=WsSetLevelPayload(level=3))

    await handlers_mod._dispatch(initiator, msg, svc, replay_service=AsyncMock(), manager=mgr)

    for client in (initiator, passive):
        statuses = _statuses(client)
        assert len(statuses) == 1
        assert statuses[0]["payload"]["bot_level"] == 3


# --- Serialize-once property carries over ----------------------------------


@pytest.mark.asyncio
async def test_training_status_is_serialized_once_for_all_clients():
    """Inherit BE-6's single-encode property through _dispatch.

    Broadcast's guarantee must survive the hotfix: N clients = 1 encode. A
    regression that falls back to ``ws.send_json`` per client would show up
    here as per-client duplicated payload strings (plus the uncaptured
    json.dumps cost at fleet scale).
    """
    mgr = ConnectionManager()
    clients = [_FakeWebSocket() for _ in range(4)]
    for c in clients:
        _register(mgr, c)

    svc = _make_training_service(state="stopped")
    msg = ParsedMessage(
        type="training:start",
        payload=WsTrainingStartPayload(bot_level=1, total_timesteps=5000),
    )

    await handlers_mod._dispatch(clients[0], msg, svc, replay_service=AsyncMock(), manager=mgr)

    # Every client received exactly one serialized frame and they're identical.
    payloads = {c.sent_text[0] for c in clients}
    assert len(payloads) == 1
    # None of them fell back to the unicast path.
    for c in clients:
        assert c.sent_json == []


# --- Rejections stay per-requester ------------------------------------------


@pytest.mark.asyncio
async def test_already_running_error_is_not_broadcast():
    """training:error is a rejection of the caller's action, not a state change.

    Broadcasting it would surface a spurious error toast on every other open
    tab — keep it per-requester.
    """
    mgr = ConnectionManager()
    initiator = _FakeWebSocket()
    passive = _FakeWebSocket()
    _register(mgr, initiator)
    _register(mgr, passive)

    svc = _make_training_service(state="running")
    msg = ParsedMessage(
        type="training:start",
        payload=WsTrainingStartPayload(bot_level=1, total_timesteps=5000),
    )

    await handlers_mod._dispatch(initiator, msg, svc, replay_service=AsyncMock(), manager=mgr)

    # Initiator sees the rejection via its unicast send_json.
    errors = [m for m in initiator.received_messages if m.get("type") == "training:error"]
    assert len(errors) == 1
    # Passive clients saw neither the rejection nor a phantom status flip.
    assert passive.received_messages == []
    # The duplicate-start guard must also skip calling start().
    svc.start.assert_not_called()


# --- Backwards-compat: dispatcher still works without a manager -------------


@pytest.mark.asyncio
async def test_dispatch_without_manager_falls_back_to_unicast():
    """``_dispatch`` keeps its manager-less contract for unit test callers.

    Several legacy call sites (and a handful of in-tree tests) invoke
    ``_dispatch`` without constructing a ConnectionManager. The hotfix must
    not turn that into an AttributeError on ``manager.broadcast``.
    """
    ws = _FakeWebSocket()
    svc = _make_training_service(state="stopped")
    msg = ParsedMessage(type="training:stop", payload=WsEmptyPayload())

    await handlers_mod._dispatch(ws, msg, svc, replay_service=AsyncMock(), manager=None)

    # No manager → direct unicast on the requester, same as before the fix.
    assert len(ws.sent_json) == 1
    assert ws.sent_json[0]["type"] == "training:status"
