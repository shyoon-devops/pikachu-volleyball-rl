"""Tests for the EvaluationRepository against an in-memory fake collection."""

from __future__ import annotations

import pytest

from backend.app.models.evaluation import EvaluationCreate
from backend.app.services.evaluation_repository import (
    DEFAULT_QUERY_LIMIT,
    EvaluationRepository,
)
from backend.rl.evaluator import EvalResult
from backend.tests.fake_mongo import FakeCollection


def _payload(
    *,
    model_path: str = "/models/a.zip",
    bot_level: int = 1,
    win_rate: float = 0.8,
    timestamp: str = "2026-04-12T00:00:00+00:00",
    dominance_score: float | None = None,
) -> EvaluationCreate:
    return EvaluationCreate(
        model_path=model_path,
        bot_level=bot_level,
        n_games=20,
        win_rate=win_rate,
        avg_score=10.0,
        avg_opponent_score=5.0,
        avg_rally_length=80.0,
        avg_episode_length=4500.0,
        timestamp=timestamp,
        dominance_score=dominance_score,
    )


@pytest.fixture
def repo() -> EvaluationRepository:
    return EvaluationRepository(FakeCollection())


class TestSave:
    @pytest.mark.asyncio
    async def test_save_stamps_id_and_inserted_at(
        self, repo: EvaluationRepository
    ) -> None:
        record = await repo.save(_payload())
        assert record.id
        assert record.inserted_at
        assert record.model_path == "/models/a.zip"

    @pytest.mark.asyncio
    async def test_save_derives_dominance_when_missing(
        self, repo: EvaluationRepository
    ) -> None:
        record = await repo.save(_payload(dominance_score=None))
        # 0.6*0.8 + 0.4*(10/(10+5)) = 0.48 + 0.2667 ≈ 0.7467
        assert record.dominance_score == pytest.approx(0.7467, abs=0.001)

    @pytest.mark.asyncio
    async def test_save_preserves_explicit_dominance(
        self, repo: EvaluationRepository
    ) -> None:
        record = await repo.save(_payload(dominance_score=0.42))
        assert record.dominance_score == 0.42

    @pytest.mark.asyncio
    async def test_save_many_persists_all(self, repo: EvaluationRepository) -> None:
        records = await repo.save_many([_payload(bot_level=lvl) for lvl in (1, 2, 3)])
        assert {r.bot_level for r in records} == {1, 2, 3}


class TestList:
    @pytest.mark.asyncio
    async def test_list_newest_first(self, repo: EvaluationRepository) -> None:
        await repo.save(_payload(timestamp="2026-04-10T00:00:00+00:00"))
        await repo.save(_payload(timestamp="2026-04-12T00:00:00+00:00"))
        records = await repo.list()
        assert [r.timestamp for r in records] == [
            "2026-04-12T00:00:00+00:00",
            "2026-04-10T00:00:00+00:00",
        ]

    @pytest.mark.asyncio
    async def test_list_filter_by_model_path(
        self, repo: EvaluationRepository
    ) -> None:
        await repo.save(_payload(model_path="/a.zip"))
        await repo.save(_payload(model_path="/b.zip"))
        records = await repo.list(model_path="/a.zip")
        assert [r.model_path for r in records] == ["/a.zip"]

    @pytest.mark.asyncio
    async def test_list_filter_by_bot_level(
        self, repo: EvaluationRepository
    ) -> None:
        await repo.save(_payload(bot_level=1))
        await repo.save(_payload(bot_level=3))
        records = await repo.list(bot_level=3)
        assert [r.bot_level for r in records] == [3]

    @pytest.mark.asyncio
    async def test_list_filter_by_since(self, repo: EvaluationRepository) -> None:
        await repo.save(_payload(timestamp="2026-04-10T00:00:00+00:00"))
        await repo.save(_payload(timestamp="2026-04-12T00:00:00+00:00"))
        records = await repo.list(since="2026-04-11T00:00:00+00:00")
        assert len(records) == 1
        assert records[0].timestamp == "2026-04-12T00:00:00+00:00"

    @pytest.mark.asyncio
    async def test_limit_is_clamped(self, repo: EvaluationRepository) -> None:
        # default limit should apply when limit=None
        for i in range(DEFAULT_QUERY_LIMIT + 5):
            await repo.save(
                _payload(timestamp=f"2026-04-{(i % 28) + 1:02d}T00:00:00+00:00")
            )
        records = await repo.list()
        assert len(records) == DEFAULT_QUERY_LIMIT


class TestGet:
    @pytest.mark.asyncio
    async def test_get_returns_saved_record(
        self, repo: EvaluationRepository
    ) -> None:
        saved = await repo.save(_payload())
        fetched = await repo.get(saved.id)
        assert fetched is not None
        assert fetched.id == saved.id

    @pytest.mark.asyncio
    async def test_get_missing_returns_none(
        self, repo: EvaluationRepository
    ) -> None:
        assert await repo.get("does-not-exist") is None


class TestListCheckpoints:
    @pytest.mark.asyncio
    async def test_distinct_checkpoints(self, repo: EvaluationRepository) -> None:
        await repo.save(_payload(model_path="/a.zip", bot_level=1))
        await repo.save(_payload(model_path="/a.zip", bot_level=3))
        await repo.save(_payload(model_path="/b.zip", bot_level=1))
        checkpoints = await repo.list_checkpoints()
        assert set(checkpoints) == {"/a.zip", "/b.zip"}


class TestEvalResultConversion:
    @pytest.mark.asyncio
    async def test_from_eval_result_roundtrips(
        self, repo: EvaluationRepository
    ) -> None:
        er = EvalResult(
            model_path="/m.zip",
            bot_level=2,
            n_games=10,
            win_rate=0.6,
            avg_score=9.0,
            avg_opponent_score=6.0,
            avg_rally_length=70.0,
            avg_episode_length=4200.0,
            timestamp="2026-04-12T00:00:00+00:00",
            dominance_score=0.5,
        )
        payload = EvaluationCreate.from_eval_result(
            er, checkpoint_label="step_10k", training_step=10000
        )
        record = await repo.save(payload)
        assert record.checkpoint_label == "step_10k"
        assert record.training_step == 10000
        assert record.win_rate == 0.6


class TestValidation:
    def test_rejects_invalid_win_rate(self) -> None:
        with pytest.raises(ValueError):
            EvaluationCreate(
                model_path="/m",
                bot_level=1,
                n_games=1,
                win_rate=1.5,  # invalid
                avg_score=0.0,
                avg_opponent_score=0.0,
                avg_rally_length=0.0,
                avg_episode_length=0.0,
                timestamp="2026-04-12T00:00:00+00:00",
            )

    def test_rejects_invalid_bot_level(self) -> None:
        with pytest.raises(ValueError):
            EvaluationCreate(
                model_path="/m",
                bot_level=99,  # invalid
                n_games=1,
                win_rate=0.5,
                avg_score=0.0,
                avg_opponent_score=0.0,
                avg_rally_length=0.0,
                avg_episode_length=0.0,
                timestamp="2026-04-12T00:00:00+00:00",
            )

    def test_rejects_malformed_timestamp(self) -> None:
        with pytest.raises(ValueError):
            EvaluationCreate(
                model_path="/m",
                bot_level=1,
                n_games=1,
                win_rate=0.5,
                avg_score=0.0,
                avg_opponent_score=0.0,
                avg_rally_length=0.0,
                avg_episode_length=0.0,
                timestamp="not-a-date",
            )
