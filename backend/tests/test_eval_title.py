"""title + experiment_id on evaluation records (BE-T11)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.app.api.routes import (
    _experiment_id_from_model_path,
    _resolve_training_identity,
)
from backend.app.models.schemas import EvaluationRecord


class TestExperimentIdFromModelPath:
    """Path parsing — first segment is experiment_id."""

    def test_extracts_experiment_id_from_nested_path(self):
        assert _experiment_id_from_model_path(
            "exp-abc123/run-baseline__abcdef01__200000.zip"
        ) == "exp-abc123"

    def test_strips_leading_models_prefix(self):
        assert _experiment_id_from_model_path(
            "models/exp-a/x__y__1.zip"
        ) == "exp-a"
        assert _experiment_id_from_model_path(
            "./models/exp-b/x__y__1.zip"
        ) == "exp-b"

    def test_windows_backslash_normalised(self):
        assert _experiment_id_from_model_path(
            "exp-xyz\\file__abc__1.zip"
        ) == "exp-xyz"

    def test_flat_layout_returns_none(self):
        assert _experiment_id_from_model_path("final.zip") is None
        assert _experiment_id_from_model_path("run__abc__1.zip") is None

    def test_empty_path_returns_none(self):
        assert _experiment_id_from_model_path("") is None
        assert _experiment_id_from_model_path(None) is None  # type: ignore[arg-type]


class TestEvaluationRecordFields:
    """Schema accepts title + experiment_id (BE-T11) alongside legacy fields."""

    def test_accepts_title_and_experiment_id(self):
        r = EvaluationRecord(
            model_path="exp/a.zip",
            bot_level=1,
            n_games=10,
            win_rate=0.5,
            avg_score=7.0,
            avg_rally_length=55.0,
            title="run-alpha",
            experiment_id="exp-abc123",
        )
        assert r.title == "run-alpha"
        assert r.experiment_id == "exp-abc123"

    def test_legacy_record_without_new_fields(self):
        r = EvaluationRecord(
            model_path="x.zip",
            bot_level=1,
            n_games=10,
            win_rate=0.5,
            avg_score=7.0,
            avg_rally_length=55.0,
        )
        assert r.title is None
        assert r.experiment_id is None

    def test_title_max_length_enforced(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            EvaluationRecord(
                model_path="x.zip",
                bot_level=1,
                n_games=10,
                win_rate=0.5,
                avg_score=7.0,
                avg_rally_length=55.0,
                title="x" * 61,
            )


class TestResolveTrainingIdentity:
    """Handler-side title/experiment_id lookup for the eval job."""

    def _request(
        self,
        *,
        live_exp_id: str | None = None,
        live_title: str = "",
        stored: dict[str, dict] | None = None,
    ):
        req = MagicMock()
        req.app.state.training_service = MagicMock()
        req.app.state.training_service.status.return_value = {
            "experiment_id": live_exp_id,
            "title": live_title,
            "state": "running" if live_exp_id else "stopped",
        }
        runs = MagicMock()
        runs.get_by_experiment_ids = AsyncMock(return_value=stored or {})
        req.app.state.training_runs_service = runs
        return req

    @pytest.mark.asyncio
    async def test_live_training_fast_path(self):
        req = self._request(live_exp_id="exp-live", live_title="run-live")
        title, exp_id = await _resolve_training_identity(
            req, "exp-live/m__abc__1.zip"
        )
        assert title == "run-live"
        assert exp_id == "exp-live"
        # No db lookup when the live manager answers.
        req.app.state.training_runs_service.get_by_experiment_ids.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_db_lookup_for_stopped_runs(self):
        req = self._request(
            live_exp_id=None,
            stored={"exp-old": {"experiment_id": "exp-old", "title": "run-old"}},
        )
        title, exp_id = await _resolve_training_identity(
            req, "exp-old/m__abc__1.zip"
        )
        assert title == "run-old"
        assert exp_id == "exp-old"

    @pytest.mark.asyncio
    async def test_unknown_experiment_returns_exp_id_but_no_title(self):
        req = self._request(live_exp_id=None, stored={})
        title, exp_id = await _resolve_training_identity(
            req, "exp-nope/m__abc__1.zip"
        )
        # Path-derived exp_id survives even without a runs_service hit.
        assert exp_id == "exp-nope"
        assert title is None

    @pytest.mark.asyncio
    async def test_flat_layout_returns_none_for_both(self):
        req = self._request()
        title, exp_id = await _resolve_training_identity(req, "final.zip")
        assert title is None and exp_id is None

    @pytest.mark.asyncio
    async def test_runs_service_failure_degrades_gracefully(self):
        req = self._request(live_exp_id=None)
        req.app.state.training_runs_service.get_by_experiment_ids = AsyncMock(
            side_effect=RuntimeError("mongo down")
        )
        title, exp_id = await _resolve_training_identity(
            req, "exp-x/m__abc__1.zip"
        )
        # exp_id still derives from the path; title is None (degraded).
        assert exp_id == "exp-x"
        assert title is None
