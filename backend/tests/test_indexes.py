"""Tests for backend.app.services.indexes.

Index creation talks to Mongo, which isn't available in the unit-test
environment. We substitute a fake database + collection that records every
``create_indexes`` call and verify:

  * Every declared collection gets exercised exactly once.
  * Each collection gets the documented set of index names.
  * Spec mismatches (``OperationFailure``) on one collection do not block
    the others — the subsequent collection still gets its indexes created.
  * Transient Mongo errors are logged but do not propagate.

The ``test_declared_specs_are_sane`` case is a pure assertion over the
declared data, giving us a quick regression net if someone accidentally
removes or renames an index that an endpoint's query plan depends on.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock

import pytest
from pymongo.errors import AutoReconnect, OperationFailure

from backend.app.services import indexes as indexes_mod
from backend.app.services.indexes import ensure_indexes


class _FakeCollection:
    def __init__(self, name: str, *, side_effect=None) -> None:
        self.name = name
        self.create_indexes = AsyncMock(side_effect=side_effect or self._default)

    async def _default(self, models):
        return [m.document["name"] for m in models]


class _FakeDB:
    """Minimal AsyncIOMotorDatabase stand-in keyed by collection name."""

    def __init__(self, overrides: dict[str, _FakeCollection] | None = None) -> None:
        self._cols: dict[str, _FakeCollection] = overrides or {}

    def __getitem__(self, name: str) -> _FakeCollection:
        if name not in self._cols:
            self._cols[name] = _FakeCollection(name)
        return self._cols[name]


@pytest.mark.asyncio
async def test_ensure_indexes_touches_every_declared_collection():
    db = _FakeDB()
    result = await ensure_indexes(db)  # type: ignore[arg-type]

    # Every declared collection must appear. ``training_runs`` joined
    # with BE-T3 (title uniqueness + recency + exp_id lookup);
    # ``league_standings`` joined with v2 Sprint-1 B-impl-2.
    assert set(result.keys()) == {
        "games",
        "evaluations",
        "metrics",
        "training_runs",
        "league_standings",
    }
    for name in (
        "games", "evaluations", "metrics", "training_runs", "league_standings"
    ):
        assert db[name].create_indexes.await_count == 1


@pytest.mark.asyncio
async def test_games_indexes_have_expected_names_and_uniqueness():
    db = _FakeDB()
    result = await ensure_indexes(db)  # type: ignore[arg-type]

    assert "games_timestamp_desc" in result["games"]
    assert "games_game_id" in result["games"]
    assert "games_experiment_timestamp" in result["games"]

    # Pull the IndexModel that was passed in and confirm game_id is unique —
    # uniqueness is load-bearing: duplicate uuid4s would silently corrupt
    # replay ↔ game linkage if we lose this flag.
    models_arg = db["games"].create_indexes.await_args.args[0]
    by_name = {m.document["name"]: m for m in models_arg}
    assert by_name["games_game_id"].document.get("unique") is True


@pytest.mark.asyncio
async def test_evaluations_and_metrics_indexes_declared():
    db = _FakeDB()
    result = await ensure_indexes(db)  # type: ignore[arg-type]

    assert "evaluations_timestamp_desc" in result["evaluations"]
    assert "evaluations_model_timestamp" in result["evaluations"]
    assert "metrics_experiment_timestamp" in result["metrics"]
    assert "metrics_timestamp_desc" in result["metrics"]


@pytest.mark.asyncio
async def test_operation_failure_on_one_collection_does_not_block_others(caplog):
    """Spec mismatch on ``games`` must not prevent ``evaluations`` indexing."""
    failing_games = _FakeCollection(
        "games", side_effect=OperationFailure("Index already exists with different options")
    )
    db = _FakeDB({"games": failing_games})

    with caplog.at_level(logging.ERROR, logger="backend.app.services.indexes"):
        result = await ensure_indexes(db)  # type: ignore[arg-type]

    assert result["games"] == []  # failed
    assert "evaluations_timestamp_desc" in result["evaluations"]
    assert any("index spec mismatch on games" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_transient_error_is_warned_and_swallowed(caplog):
    flaky = _FakeCollection("games", side_effect=AutoReconnect("mongo restarting"))
    db = _FakeDB({"games": flaky})

    with caplog.at_level(logging.WARNING, logger="backend.app.services.indexes"):
        result = await ensure_indexes(db)  # type: ignore[arg-type]

    assert result["games"] == []
    assert any("transient error creating indexes on games" in r.message for r in caplog.records)


def test_declared_specs_are_sane():
    """Static invariants on the declarative index table."""
    seen_names: set[str] = set()
    for spec in indexes_mod._ALL_INDEXES:
        assert spec.collection, "collection name must not be empty"
        assert spec.models, f"collection {spec.collection} has no indexes declared"
        for model in spec.models:
            name = model.document.get("name")
            assert name, f"every index needs an explicit name (collection={spec.collection})"
            assert name not in seen_names, f"duplicate index name across collections: {name}"
            seen_names.add(name)
