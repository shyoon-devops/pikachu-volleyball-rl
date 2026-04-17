"""Aggregate stored evaluations into time-series chart data.

Purpose:
    The frontend chart needs arrays of (timestamp, value) points for a
    given metric, grouped by (model_path, bot_level). This module owns
    the pure aggregation — the FastAPI endpoint simply calls it.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.models.evaluation import EvaluationRecord

# Metrics exposed to the chart layer.
SUPPORTED_METRICS: tuple[str, ...] = (
    "win_rate",
    "avg_score",
    "avg_opponent_score",
    "avg_rally_length",
    "avg_episode_length",
    "dominance_score",
)


@dataclass(frozen=True)
class TimeSeriesPoint:
    timestamp: str
    value: float
    training_step: int | None = None
    checkpoint_label: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "timestamp": self.timestamp,
            "value": self.value,
            "training_step": self.training_step,
            "checkpoint_label": self.checkpoint_label,
        }


@dataclass(frozen=True)
class TimeSeries:
    """One chart line: a metric for a (model_path, bot_level) pair."""

    model_path: str
    bot_level: int
    metric: str
    points: list[TimeSeriesPoint]

    def to_dict(self) -> dict[str, object]:
        return {
            "model_path": self.model_path,
            "bot_level": self.bot_level,
            "metric": self.metric,
            "points": [p.to_dict() for p in self.points],
        }


def _extract_metric(record: EvaluationRecord, metric: str) -> float | None:
    """Pull the metric value off the record, or None if not available."""
    value = getattr(record, metric, None)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_timeseries(
    records: list[EvaluationRecord],
    *,
    metric: str = "win_rate",
    group_by_level: bool = True,
) -> list[TimeSeries]:
    """Group records into time-series by (model_path[, bot_level]).

    Points within a series are sorted by timestamp ascending — that's
    the order the chart expects. Records whose value is None or NaN
    are dropped from the series (no silent zeros).
    """
    if metric not in SUPPORTED_METRICS:
        raise ValueError(
            f"Unsupported metric {metric!r}; expected one of {SUPPORTED_METRICS}"
        )

    grouped: dict[tuple[str, int], list[EvaluationRecord]] = {}
    for r in records:
        key = (r.model_path, r.bot_level if group_by_level else 0)
        grouped.setdefault(key, []).append(r)

    out: list[TimeSeries] = []
    for (model_path, bot_level), group in grouped.items():
        group.sort(key=lambda x: x.timestamp)
        points: list[TimeSeriesPoint] = []
        for r in group:
            value = _extract_metric(r, metric)
            if value is None:
                continue
            points.append(
                TimeSeriesPoint(
                    timestamp=r.timestamp,
                    value=value,
                    training_step=r.training_step,
                    checkpoint_label=r.checkpoint_label,
                )
            )
        if not points:
            continue
        out.append(
            TimeSeries(
                model_path=model_path,
                bot_level=bot_level,
                metric=metric,
                points=points,
            )
        )

    # Stable ordering: by model_path, then bot_level.
    out.sort(key=lambda s: (s.model_path, s.bot_level))
    return out


__all__ = [
    "SUPPORTED_METRICS",
    "TimeSeries",
    "TimeSeriesPoint",
    "build_timeseries",
]
