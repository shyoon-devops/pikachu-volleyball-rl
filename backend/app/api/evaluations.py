"""FastAPI router for evaluation persistence + lookup.

The router holds no state of its own — it takes a dependency-injected
`EvaluationRepository`. Tests wire in a repository backed by the
in-memory fake collection; production wiring supplies a motor-backed
collection at app startup.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.app.models.evaluation import EvaluationCreate, EvaluationRecord
from backend.app.services.evaluation_repository import (
    DEFAULT_QUERY_LIMIT,
    MAX_QUERY_LIMIT,
    EvaluationRepository,
)
from backend.app.services.evaluation_timeseries import (
    SUPPORTED_METRICS,
    build_timeseries,
)


def get_repository() -> EvaluationRepository:
    """Placeholder dependency — overridden via FastAPI app.dependency_overrides.

    Production startup code should replace this via:
        app.dependency_overrides[get_repository] = lambda: real_repo
    """
    raise RuntimeError(
        "EvaluationRepository dependency not configured — override get_repository"
    )


router = APIRouter(prefix="/evaluations", tags=["evaluations"])


@router.post(
    "",
    response_model=EvaluationRecord,
    status_code=status.HTTP_201_CREATED,
)
async def create_evaluation(
    payload: EvaluationCreate,
    repo: Annotated[EvaluationRepository, Depends(get_repository)],
) -> EvaluationRecord:
    return await repo.save(payload)


@router.get("", response_model=list[EvaluationRecord])
async def list_evaluations(
    repo: Annotated[EvaluationRepository, Depends(get_repository)],
    model_path: str | None = Query(default=None, description="Exact checkpoint path filter"),
    bot_level: int | None = Query(default=None, ge=1, le=5),
    since: str | None = Query(
        default=None, description="ISO-8601 timestamp lower bound (inclusive)"
    ),
    limit: int = Query(default=DEFAULT_QUERY_LIMIT, ge=1, le=MAX_QUERY_LIMIT),
) -> list[EvaluationRecord]:
    return await repo.list(
        model_path=model_path, bot_level=bot_level, since=since, limit=limit
    )


@router.get("/checkpoints", response_model=list[str])
async def list_checkpoints(
    repo: Annotated[EvaluationRepository, Depends(get_repository)],
    limit: int = Query(default=DEFAULT_QUERY_LIMIT, ge=1, le=MAX_QUERY_LIMIT),
) -> list[str]:
    """Distinct model_paths present in storage."""
    return await repo.list_checkpoints(limit=limit)


@router.get("/timeseries")
async def timeseries(
    repo: Annotated[EvaluationRepository, Depends(get_repository)],
    metric: str = Query(
        default="win_rate",
        description=f"One of {list(SUPPORTED_METRICS)}",
    ),
    model_path: str | None = Query(default=None),
    bot_level: int | None = Query(default=None, ge=1, le=5),
    since: str | None = Query(default=None),
    limit: int = Query(default=MAX_QUERY_LIMIT, ge=1, le=MAX_QUERY_LIMIT),
    group_by_level: bool = Query(default=True),
) -> list[dict[str, object]]:
    """Time-series chart data grouped by (model_path, bot_level).

    Returned payload is a list of series; each series has a list of
    points sorted oldest → newest. The frontend renders one line per
    series.
    """
    if metric not in SUPPORTED_METRICS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"metric must be one of {list(SUPPORTED_METRICS)}",
        )

    records = await repo.list(
        model_path=model_path,
        bot_level=bot_level,
        since=since,
        limit=limit,
    )
    series = build_timeseries(records, metric=metric, group_by_level=group_by_level)
    return [s.to_dict() for s in series]


@router.get("/{record_id}", response_model=EvaluationRecord)
async def get_evaluation(
    record_id: str,
    repo: Annotated[EvaluationRepository, Depends(get_repository)],
) -> EvaluationRecord:
    record = await repo.get(record_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="evaluation not found")
    return record


__all__ = ["router", "get_repository"]
