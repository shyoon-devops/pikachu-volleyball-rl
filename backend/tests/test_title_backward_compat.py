"""Backward compatibility for the training-title schema extension (BE-T3).

T1 made ``GameRecord.title`` and ``EvaluationRecord.training_title``
optional so legacy pre-title documents keep deserialising cleanly. T3
pins that contract explicitly — loading a legacy doc without the field
must never raise, and the resulting model must render as "-" on the FE
side (empty/None).

Also sanity-checks the Mongo index declarations so a future refactor
can't silently drop the title-scoped indexes.
"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.app.models.schemas import EvaluationRecord, GameRecord


class TestLegacyGameRecordDeserializes:
    """Pre-title ``games`` docs have no ``title`` field."""

    def test_legacy_doc_parses_without_title(self):
        legacy_doc = {
            "_id": "abc123",
            "game_id": "11111111-1111-1111-1111-111111111111",
            "experiment_id": "exp-legacy",
            "timestamp": datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
            "bot_level": 1,
            "score1": 15, "score2": 10, "winner": 1,
            "duration_frames": 1000, "rally_count": 15,
        }
        r = GameRecord.model_validate(legacy_doc)
        assert r.title is None
        # Output dict (exclude_none=True is the service default) must
        # not carry a spurious ``title: null`` that would confuse FE
        # consumers rendering "-" from the absence of the field.
        out = r.model_dump(by_alias=True, exclude_none=True)
        assert "title" not in out

    def test_legacy_doc_with_env_id_only(self):
        """Pre-title doc that already had env_id (post-A2, pre-T1)."""
        legacy_doc = {
            "game_id": "22222222-2222-2222-2222-222222222222",
            "experiment_id": "exp-a2",
            "bot_level": 2,
            "score1": 15, "score2": 8, "winner": 1,
            "duration_frames": 2000, "rally_count": 30,
            "env_id": "3",
        }
        r = GameRecord.model_validate(legacy_doc)
        assert r.env_id == "3"
        assert r.title is None

    def test_new_doc_with_title_round_trips(self):
        new_doc = {
            "game_id": "33333333-3333-3333-3333-333333333333",
            "experiment_id": "exp-new",
            "bot_level": 3,
            "score1": 15, "score2": 12, "winner": 1,
            "duration_frames": 2500, "rally_count": 42,
            "env_id": "0",
            "title": "run-brave-fox-a3f9",
        }
        r = GameRecord.model_validate(new_doc)
        assert r.title == "run-brave-fox-a3f9"
        out = r.model_dump(by_alias=True, exclude_none=True)
        assert out["title"] == "run-brave-fox-a3f9"


class TestLegacyEvaluationRecordDeserializes:
    def test_legacy_eval_parses_without_training_title(self):
        legacy = {
            "_id": "e1",
            "model_path": "exp-legacy/final.zip",
            "bot_level": 1,
            "n_games": 50,
            "win_rate": 0.4,
            "avg_score": 8.1,
            "avg_rally_length": 55.3,
            "timestamp": datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
        }
        r = EvaluationRecord.model_validate(legacy)
        assert r.training_title is None

    def test_new_eval_with_training_title(self):
        new_doc = {
            "model_path": "run-baseline__abc__200000.zip",
            "bot_level": 3,
            "n_games": 50,
            "win_rate": 0.7,
            "avg_score": 12.0,
            "avg_rally_length": 75.0,
            "training_title": "run-baseline-20260418",
        }
        r = EvaluationRecord.model_validate(new_doc)
        assert r.training_title == "run-baseline-20260418"


class TestIndexDeclarations:
    """Mongo index declarations include the title-scoped indexes."""

    def test_games_title_index_registered(self):
        from backend.app.services.indexes import _GAME_INDEXES

        names = [m.document["name"] for m in _GAME_INDEXES.models]
        assert "games_title_timestamp" in names

    def test_evaluations_title_index_registered(self):
        from backend.app.services.indexes import _EVAL_INDEXES

        names = [m.document["name"] for m in _EVAL_INDEXES.models]
        assert "evaluations_title_timestamp" in names

    def test_training_runs_indexes_registered(self):
        from backend.app.services.indexes import _ALL_INDEXES

        collections = {s.collection: s for s in _ALL_INDEXES}
        assert "training_runs" in collections
        names = [m.document["name"] for m in collections["training_runs"].models]
        assert "training_runs_title_unique" in names
        assert "training_runs_started_desc" in names
        assert "training_runs_experiment" in names

    def test_title_unique_index_is_partial(self):
        """Uniqueness applies only to non-NULL titles so migration-
        window docs without a title don't violate the constraint."""
        from backend.app.services.indexes import _ALL_INDEXES

        collections = {s.collection: s for s in _ALL_INDEXES}
        spec_models = collections["training_runs"].models
        title_idx = next(
            m for m in spec_models if m.document["name"] == "training_runs_title_unique"
        )
        assert title_idx.document.get("unique") is True
        partial = title_idx.document.get("partialFilterExpression", {})
        assert partial == {"title": {"$type": "string"}}
