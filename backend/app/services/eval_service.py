"""Evaluation service wrapper — adapts ModelEvaluator for FastAPI + MongoDB."""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from backend.app.models.schemas import EvaluationRecord
from backend.rl.evaluator import ModelEvaluator


class EvalServiceWrapper:
    """Wraps ModelEvaluator: runs evaluations off-thread and persists results."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._evaluator = ModelEvaluator()
        self._col = db["evaluations"]

    async def run(
        self,
        model_path: str,
        bot_level: int = 1,
        n_games: int = 50,
    ) -> dict[str, Any]:
        result = await asyncio.to_thread(
            self._evaluator.evaluate,
            model_path=model_path,
            bot_level=bot_level,
            n_games=n_games,
        )
        record = EvaluationRecord(
            model_path=result.model_path,
            bot_level=result.bot_level,
            n_games=result.n_games,
            win_rate=result.win_rate,
            avg_score=result.avg_score,
            avg_rally_length=result.avg_rally_length,
        )
        doc = record.model_dump(by_alias=True, exclude_none=True)
        await self._col.insert_one(doc)
        return asdict(result)

    async def get_results(self) -> dict[str, Any]:
        cursor = self._col.find().sort("timestamp", -1).limit(100)
        docs = await cursor.to_list(length=100)
        for d in docs:
            d["_id"] = str(d["_id"])
        return {"data": docs}
