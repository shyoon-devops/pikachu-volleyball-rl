"""Best-model auto-selection logic.

Ranks a set of checkpoint evaluations and selects the best model based on a
verdict-tiered scoring system:

    1. Verdict tier      (PASS > CONDITIONAL > FAIL > CRITICAL)
    2. Mean dominance    (across all bot levels)
    3. Mean win rate     (tiebreaker)
    4. Recency           (most recent timestamp wins)

The ranking is fully transparent — every checkpoint's score and the reason
it was (or wasn't) selected is exposed via `rank_checkpoints`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from backend.rl.comparison_chart import CheckpointSeries
from backend.rl.evaluator import EvalResult
from backend.rl.report_generator import overall_verdict

# Higher value = better verdict tier
VERDICT_TIER: dict[str, int] = {
    "PASS": 4,
    "CONDITIONAL": 3,
    "FAIL": 2,
    "CRITICAL": 1,
}


@dataclass(frozen=True)
class CheckpointRanking:
    label: str
    verdict: str
    verdict_tier: int
    mean_dominance: float
    mean_win_rate: float
    latest_timestamp: str
    series: CheckpointSeries

    def to_summary_dict(self) -> dict[str, float | int | str]:
        """Compact representation suitable for logging / serialization."""
        return {
            "label": self.label,
            "verdict": self.verdict,
            "verdict_tier": self.verdict_tier,
            "mean_dominance": round(self.mean_dominance, 4),
            "mean_win_rate": round(self.mean_win_rate, 4),
            "latest_timestamp": self.latest_timestamp,
        }


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _latest_timestamp(results: list[EvalResult]) -> str:
    if not results:
        return ""
    return max(r.timestamp for r in results)


def _ranking_key(r: CheckpointRanking) -> tuple[int, float, float, str]:
    """Composite ranking key. Larger is better."""
    return (
        r.verdict_tier,
        r.mean_dominance,
        r.mean_win_rate,
        r.latest_timestamp,  # ISO timestamps sort lexicographically
    )


def rank_checkpoints(
    series: list[CheckpointSeries],
) -> list[CheckpointRanking]:
    """Return all checkpoints ranked best-first."""
    rankings = []
    for cs in series:
        verdict = overall_verdict(cs.results)
        rankings.append(
            CheckpointRanking(
                label=cs.label,
                verdict=verdict,
                verdict_tier=VERDICT_TIER.get(verdict, 0),
                mean_dominance=_mean([r.dominance_score for r in cs.results]),
                mean_win_rate=_mean([r.win_rate for r in cs.results]),
                latest_timestamp=_latest_timestamp(cs.results),
                series=cs,
            )
        )
    rankings.sort(key=_ranking_key, reverse=True)
    return rankings


def select_best(
    series: list[CheckpointSeries],
    *,
    require_pass: bool = False,
) -> CheckpointRanking | None:
    """Pick the best checkpoint. Returns None if none qualify.

    When `require_pass=True`, only checkpoints with verdict PASS or
    CONDITIONAL are considered.
    """
    if not series:
        return None
    ranked = rank_checkpoints(series)
    if require_pass:
        ranked = [r for r in ranked if r.verdict in ("PASS", "CONDITIONAL")]
    return ranked[0] if ranked else None


def regression_report(
    new: CheckpointRanking,
    baseline: CheckpointRanking,
    *,
    win_rate_drop: float = 0.05,
    dominance_drop: float = 0.05,
) -> list[str]:
    """List metrics where `new` regressed vs. `baseline`.

    Returns an empty list if no regressions are detected. Used by the
    selector to flag a candidate that wins on rank but is worse than a
    prior best on specific metrics.
    """
    issues: list[str] = []
    if baseline.mean_win_rate - new.mean_win_rate > win_rate_drop:
        issues.append(
            f"win_rate dropped {baseline.mean_win_rate:.2f} → {new.mean_win_rate:.2f}"
        )
    if baseline.mean_dominance - new.mean_dominance > dominance_drop:
        issues.append(
            f"dominance dropped {baseline.mean_dominance:.2f} → {new.mean_dominance:.2f}"
        )
    if VERDICT_TIER.get(new.verdict, 0) < VERDICT_TIER.get(baseline.verdict, 0):
        issues.append(f"verdict regressed {baseline.verdict} → {new.verdict}")
    return issues


def is_iso_after(later_iso: str, earlier_iso: str) -> bool:
    """Helper: True if later_iso is strictly after earlier_iso."""
    if not later_iso or not earlier_iso:
        return False
    return datetime.fromisoformat(later_iso) > datetime.fromisoformat(earlier_iso)
