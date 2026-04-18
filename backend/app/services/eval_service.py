"""Evaluation service wrapper — adapts ModelEvaluator for FastAPI + MongoDB."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from backend.app.models.schemas import EvaluationRecord
from backend.app.services.db_utils import with_mongo_retry
from backend.rl.evaluator import ModelEvaluator


class EvalServiceWrapper:
    """Wraps ModelEvaluator: runs evaluations off-thread and persists results."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._evaluator = ModelEvaluator()
        self._col = db["evaluations"]
        self._model_dir = Path(os.getenv("MODEL_DIR", "./models"))

    def validate_model_path(self, model_path: str) -> Path:
        """Resolve + validate without loading the model.

        Extracted so the async endpoint can reject obviously bad paths
        (traversal, missing file) synchronously — before accepting the
        job — instead of letting the background task fail with 404 that
        the client can only discover by polling. Raises FileNotFoundError
        for the same three reasons ``run()`` does.
        """
        full_path = (self._model_dir / model_path).resolve()
        if not str(full_path).startswith(str(self._model_dir.resolve())):
            raise FileNotFoundError(f"Invalid model path: {model_path}")
        if not full_path.exists():
            raise FileNotFoundError(f"Model not found: {model_path}")
        return full_path

    async def run(
        self,
        model_path: str,
        bot_level: int = 1,
        n_games: int = 50,
        *,
        progress_callback: Callable[[int, int], None] | None = None,
        training_title: str | None = None,
        experiment_id: str | None = None,
    ) -> dict[str, Any]:
        """Run a full evaluation and persist the aggregated record.

        ``progress_callback`` is forwarded to the underlying evaluator and
        fires once per completed game on the WORKER THREAD (not the event
        loop). The caller is responsible for marshaling back to the loop
        if it needs to touch async-only state — the async job registry
        uses ``asyncio.run_coroutine_threadsafe`` for exactly this.

        ``training_title`` / ``experiment_id`` (BE-T11) are snapshots of
        the source training run. Persisted on the saved record so the
        FE can filter / cross-reference without joining against
        ``training_runs`` at read time. Both are optional — ad-hoc
        evaluations of uploaded models leave them None.
        """
        full_path = self.validate_model_path(model_path)

        result = await asyncio.to_thread(
            self._evaluator.evaluate,
            model_path=str(full_path),
            bot_level=bot_level,
            n_games=n_games,
            progress_callback=progress_callback,
        )
        record = EvaluationRecord(
            model_path=result.model_path,
            bot_level=result.bot_level,
            n_games=result.n_games,
            win_rate=result.win_rate,
            avg_score=result.avg_score,
            avg_rally_length=result.avg_rally_length,
            # Both field names populated so API consumers keying off
            # either one see the same value. Empty string → None so
            # exclude_none drops the key rather than storing "".
            training_title=training_title or None,
            title=training_title or None,
            experiment_id=experiment_id or None,
        )
        doc = record.model_dump(by_alias=True, exclude_none=True)
        await with_mongo_retry(
            lambda: self._col.insert_one(doc), op_name="save_evaluation"
        )
        return asdict(result)

    async def get_results(self) -> dict[str, Any]:
        async def _fetch() -> dict[str, Any]:
            cursor = self._col.find().sort("timestamp", -1).limit(100)
            docs = await cursor.to_list(length=100)
            for d in docs:
                d["_id"] = str(d["_id"])
            return {"data": docs}

        return await with_mongo_retry(_fetch, op_name="get_evaluation_results")
