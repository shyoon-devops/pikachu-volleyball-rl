"""Pydantic schemas for evaluation records stored in MongoDB."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.rl.evaluator import EvalResult, compute_dominance_score


class EvaluationCreate(BaseModel):
    """Payload accepted from the batch runner / evaluator service."""

    # protected_namespaces=() because `model_path` collides with Pydantic's
    # default "model_" reserved prefix.
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    model_path: str = Field(..., min_length=1)
    bot_level: Annotated[int, Field(ge=1, le=5)]
    n_games: Annotated[int, Field(ge=1)]
    win_rate: Annotated[float, Field(ge=0.0, le=1.0)]
    avg_score: Annotated[float, Field(ge=0.0)]
    avg_opponent_score: Annotated[float, Field(ge=0.0)]
    avg_rally_length: Annotated[float, Field(ge=0.0)]
    avg_episode_length: Annotated[float, Field(ge=0.0)]
    timestamp: str
    dominance_score: Annotated[float, Field(ge=0.0, le=1.0)] | None = None
    checkpoint_label: str | None = None
    training_step: int | None = None

    @field_validator("timestamp")
    @classmethod
    def _parse_timestamp(cls, v: str) -> str:
        # Fail early on malformed ISO strings so we don't store garbage.
        datetime.fromisoformat(v)
        return v

    def with_derived_fields(self) -> "EvaluationCreate":
        """Fill in dominance_score if the caller didn't."""
        if self.dominance_score is None:
            return self.model_copy(
                update={
                    "dominance_score": compute_dominance_score(
                        self.win_rate, self.avg_score, self.avg_opponent_score
                    )
                }
            )
        return self

    @classmethod
    def from_eval_result(
        cls,
        result: EvalResult,
        *,
        checkpoint_label: str | None = None,
        training_step: int | None = None,
    ) -> "EvaluationCreate":
        return cls(
            model_path=result.model_path,
            bot_level=result.bot_level,
            n_games=result.n_games,
            win_rate=result.win_rate,
            avg_score=result.avg_score,
            avg_opponent_score=result.avg_opponent_score,
            avg_rally_length=result.avg_rally_length,
            avg_episode_length=result.avg_episode_length,
            timestamp=result.timestamp,
            dominance_score=result.dominance_score,
            checkpoint_label=checkpoint_label,
            training_step=training_step,
        )


class EvaluationRecord(EvaluationCreate):
    """Stored record — adds the document id and insertion time."""

    id: str
    inserted_at: str

    @classmethod
    def from_mongo(cls, doc: dict) -> "EvaluationRecord":
        # Our stable identifier is the `id` field we wrote on insert.
        # Fall back to stringifying the Mongo `_id` only when `id` is
        # absent (legacy rows or partial documents).
        payload = dict(doc)
        raw_id = payload.pop("_id", None)
        if "id" not in payload or not payload["id"]:
            payload["id"] = str(raw_id) if raw_id is not None else ""
        if "inserted_at" not in payload:
            payload["inserted_at"] = datetime.now(timezone.utc).isoformat(
                timespec="seconds"
            )
        return cls(**payload)


__all__ = ["EvaluationCreate", "EvaluationRecord"]
