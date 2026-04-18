"""Training title propagation (BE-T1)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from backend.app.models.schemas import (
    EvaluationRecord,
    GameRecord,
    WsTrainingStartPayload,
)
from backend.app.services.title_service import (
    MAX_TITLE_LEN,
    TrainingRunsService,
    allocate_title,
    is_valid_title,
    slugify,
)


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


class TestIsValidTitle:
    def test_accepts_normal_title(self):
        ok, err = is_valid_title("my-run-baseline")
        assert ok and err is None

    def test_rejects_empty_and_whitespace(self):
        for bad in ("", "   ", "\t\n"):
            ok, err = is_valid_title(bad)
            assert not ok
            assert err == "제목 필수"

    def test_rejects_too_long(self):
        ok, err = is_valid_title("x" * (MAX_TITLE_LEN + 1))
        assert not ok
        assert err == "최대 60자"

    def test_accepts_boundary_length(self):
        ok, err = is_valid_title("x" * MAX_TITLE_LEN)
        assert ok and err is None


class TestSlugify:
    def test_lowercase_and_replace_special(self):
        assert slugify("My Run #1!") == "my-run-1"

    def test_collapses_runs_of_non_alnum(self):
        assert slugify("a!!!b???c") == "a-b-c"

    def test_strips_edge_dashes(self):
        assert slugify("--hello--") == "hello"

    def test_truncates_to_max_len(self):
        s = slugify("a" * 100)
        assert len(s) <= 40
        assert s == "a" * 40

    def test_empty_falls_back_to_run(self):
        assert slugify("") == "run"
        assert slugify("!!!") == "run"
        assert slugify("---") == "run"


# ---------------------------------------------------------------------------
# allocate_title — honors caller title, generates on empty, retries on clash
# ---------------------------------------------------------------------------


class TestAllocateTitle:
    @pytest.mark.asyncio
    async def test_caller_title_wins_when_unique(self):
        svc = TrainingRunsService(db=None)  # no collisions possible
        out = await allocate_title(svc, "my-run")
        assert out == "my-run"

    @pytest.mark.asyncio
    async def test_empty_generates_random(self):
        svc = TrainingRunsService(db=None)
        for supplied in (None, "", "   "):
            out = await allocate_title(svc, supplied)
            assert out.startswith("run-")
            # run-{adj}-{noun}-{4hex} has exactly 4 segments.
            assert out.count("-") == 3

    @pytest.mark.asyncio
    async def test_retries_on_collision(self):
        """If the first generated title clashes, allocate_title tries again."""
        svc = TrainingRunsService(db=None)

        calls = {"n": 0}
        original = svc.title_taken

        async def fake_taken(title):
            calls["n"] += 1
            # Claim the first 2 generated candidates as taken.
            return calls["n"] <= 2

        svc.title_taken = fake_taken  # type: ignore[method-assign]
        try:
            out = await allocate_title(svc, None)
            # Should have probed at least 3 times (2 collisions + 1 hit).
            assert calls["n"] >= 3
            assert out.startswith("run-")
        finally:
            svc.title_taken = original  # type: ignore[method-assign]

    @pytest.mark.asyncio
    async def test_caller_title_falls_through_when_taken(self):
        svc = TrainingRunsService(db=None)

        async def taken(title):
            # Caller's explicit title is taken; generated ones are free.
            return title == "dup-run"

        svc.title_taken = taken  # type: ignore[method-assign]
        out = await allocate_title(svc, "dup-run")
        assert out != "dup-run"
        assert out.startswith("run-")


# ---------------------------------------------------------------------------
# Schema fields
# ---------------------------------------------------------------------------


class TestPayloadTitleField:
    def test_title_is_optional(self):
        p = WsTrainingStartPayload()
        assert p.title is None

    def test_title_accepts_valid(self):
        p = WsTrainingStartPayload(title="my-run")
        assert p.title == "my-run"

    def test_title_rejects_over_60(self):
        with pytest.raises(ValidationError):
            WsTrainingStartPayload(title="x" * 61)


class TestGameRecordTitleField:
    def test_accepts_title(self):
        r = GameRecord(
            experiment_id="e", bot_level=1,
            score1=15, score2=10, winner=1,
            duration_frames=1000, rally_count=20,
            title="run-xyz",
        )
        assert r.title == "run-xyz"

    def test_title_optional_none_for_legacy(self):
        r = GameRecord(
            experiment_id="e", bot_level=1,
            score1=15, score2=10, winner=1,
            duration_frames=1000, rally_count=20,
        )
        assert r.title is None


class TestEvaluationRecordTrainingTitle:
    def test_accepts_training_title(self):
        r = EvaluationRecord(
            model_path="x.zip", bot_level=1, n_games=10,
            win_rate=0.5, avg_score=7.0, avg_rally_length=50.0,
            training_title="my-run",
        )
        assert r.training_title == "my-run"

    def test_training_title_optional(self):
        r = EvaluationRecord(
            model_path="x.zip", bot_level=1, n_games=10,
            win_rate=0.5, avg_score=7.0, avg_rally_length=50.0,
        )
        assert r.training_title is None


# ---------------------------------------------------------------------------
# WS handler — title in training:status broadcast + record propagation
# ---------------------------------------------------------------------------


class TestHandlerForwardsTitle:
    @staticmethod
    def _fake_training_service():
        svc = MagicMock()
        svc.status.return_value = {
            "state": "stopped",
            "current_step": 0,
            "current_episode": 0,
            "experiment_id": None,
            "bot_level": 1,
            "started_at": None,
            "title": "",
        }
        svc.start = AsyncMock(return_value="exp-xyz")
        svc.runs_service = TrainingRunsService(db=None)
        return svc

    @pytest.mark.asyncio
    async def test_caller_title_flows_to_manager_start(self):
        from backend.app.ws.handlers import _dispatch
        from backend.app.ws.validation import ParsedMessage

        svc = self._fake_training_service()
        parsed = ParsedMessage(
            type="training:start",
            payload=WsTrainingStartPayload(title="my-run", total_timesteps=500_000),
        )
        ws = MagicMock()
        ws.send_json = AsyncMock()
        manager = MagicMock()
        manager.broadcast = AsyncMock()

        await _dispatch(ws, parsed, svc, MagicMock(), manager)

        kwargs = svc.start.await_args.kwargs
        assert kwargs["title"] == "my-run"
        assert kwargs["slug"] == "my-run"

    @pytest.mark.asyncio
    async def test_missing_title_generated_and_broadcast(self):
        from backend.app.ws.handlers import _dispatch
        from backend.app.ws.validation import ParsedMessage

        svc = self._fake_training_service()
        parsed = ParsedMessage(
            type="training:start",
            payload=WsTrainingStartPayload(total_timesteps=500_000),  # no title
        )
        ws = MagicMock()
        ws.send_json = AsyncMock()
        manager = MagicMock()
        manager.broadcast = AsyncMock()

        await _dispatch(ws, parsed, svc, MagicMock(), manager)

        kwargs = svc.start.await_args.kwargs
        # Server generated a run-{adj}-{noun}-{4hex} title.
        assert kwargs["title"].startswith("run-")
        assert kwargs["slug"].startswith("run-")
        # training:status broadcast carries the final title.
        assert manager.broadcast.await_args is not None
        status = manager.broadcast.await_args.args[0]
        assert status["type"] == "training:status"
        assert status["payload"]["title"] == kwargs["title"]


class TestResultsPushLoopForwardsTitle:
    @pytest.mark.asyncio
    async def test_title_lands_on_game_record(self):
        import asyncio

        from backend.app.ws.handlers import results_push_loop

        saved: list = []

        class _Svc:
            async def save_game(self, record):
                saved.append(record)

        training_service = MagicMock()
        training_service.manager.results_queue = asyncio.Queue()
        await training_service.manager.results_queue.put({
            "game_id": "22222222-2222-2222-2222-222222222222",
            "experiment_id": "exp",
            "bot_level": 2,
            "score1": 15, "score2": 10, "winner": 1,
            "duration_frames": 1500, "rally_count": 23,
            "env_id": "0",
            "title": "run-brave-fox-a3f9",
        })

        manager = MagicMock()

        async def _broadcast(_p):
            raise asyncio.CancelledError

        manager.broadcast = _broadcast

        with pytest.raises(asyncio.CancelledError):
            await results_push_loop(manager, training_service, _Svc())
        assert saved[0].title == "run-brave-fox-a3f9"
