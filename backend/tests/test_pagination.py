"""Pagination envelope and ``has_more`` computation tests.

Covers the ``PaginatedResponse`` schema and the ``/api/games`` and
``/api/replays`` endpoints that use it. The key invariant exercised here is
that callers cannot supply a ``has_more`` inconsistent with (page, limit,
total): the field is computed from those three and emitted via
``@computed_field``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from backend.app.models.schemas import PaginatedResponse


def test_has_more_true_when_more_pages_exist():
    r = PaginatedResponse(data=[1, 2, 3], total=10, page=1, limit=3)
    assert r.has_more is True


def test_has_more_false_on_last_exact_fit_page():
    # 10 items, 2-per-page → page 5 is the last page and has no more
    r = PaginatedResponse(data=[1, 2], total=10, page=5, limit=2)
    assert r.has_more is False


def test_has_more_false_on_last_partial_page():
    r = PaginatedResponse(data=[1], total=5, page=3, limit=2)
    assert r.has_more is False


def test_has_more_false_when_page_overflow():
    # Requesting a page past the end must never imply more pages exist.
    r = PaginatedResponse(data=[], total=5, page=999, limit=10)
    assert r.has_more is False


def test_has_more_false_for_empty_dataset():
    r = PaginatedResponse(data=[], total=0, page=1, limit=20)
    assert r.has_more is False


def test_has_more_handles_zero_limit_gracefully():
    # A zero limit cannot produce progress; must not divide by zero nor claim
    # more pages exist.
    r = PaginatedResponse(data=[], total=10, page=1, limit=0)
    assert r.has_more is False


def test_model_dump_includes_has_more():
    r = PaginatedResponse(data=[1], total=5, page=1, limit=2)
    dumped = r.model_dump()
    assert dumped["has_more"] is True
    assert set(dumped) == {"data", "total", "page", "limit", "has_more"}


@pytest.mark.parametrize(
    "page,limit,total,expected",
    [
        (1, 20, 0, False),
        (1, 20, 20, False),
        (1, 20, 21, True),
        (2, 20, 40, False),
        (2, 20, 41, True),
    ],
)
def test_has_more_parametrized(page, limit, total, expected):
    r = PaginatedResponse(data=[], total=total, page=page, limit=limit)
    assert r.has_more is expected


# --- Integration: endpoints emit the envelope -----------------------------


def test_games_envelope_shape(client):
    resp = client.get("/api/games?page=1&limit=5")
    assert resp.status_code == 200
    body = resp.json()
    for field in ("data", "total", "page", "limit", "has_more"):
        assert field in body, f"missing envelope field: {field}"
    assert body["has_more"] is False  # FakeGameService is empty


def test_replays_envelope_shape(client):
    resp = client.get("/api/replays?page=1&limit=5")
    assert resp.status_code == 200
    body = resp.json()
    for field in ("data", "total", "page", "limit", "has_more"):
        assert field in body, f"missing envelope field: {field}"
    # Backward-compat alias for existing frontend callers
    assert "replays" in body
    assert body["replays"] == body["data"]


def test_replays_envelope_with_more_pages(client, app_instance):
    """Replays beyond one page must report has_more=True and slice correctly."""
    fake_items = [{"game_id": f"g{i}", "size_bytes": i, "created_at": i} for i in range(7)]
    app_instance.state.replay_service.list_replays = AsyncMock(return_value=fake_items)

    resp = client.get("/api/replays?page=1&limit=3")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 7
    assert body["page"] == 1
    assert body["limit"] == 3
    assert len(body["data"]) == 3
    assert body["data"] == body["replays"]
    assert body["has_more"] is True

    resp = client.get("/api/replays?page=3&limit=3")
    body = resp.json()
    assert len(body["data"]) == 1  # last partial page
    assert body["has_more"] is False
