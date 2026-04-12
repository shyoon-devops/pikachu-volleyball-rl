"""Baseline checkpoint comparator.

Produces a per-level delta summary between a baseline checkpoint (typically
the currently-deployed prod model) and a candidate checkpoint (a new
training artifact). Used by the trainer's reward-tuning loop to decide
whether a newly trained model is ready for promotion.

Output highlights:
    * Per-level deltas: win_rate, avg_score, avg_rally_length, dominance
    * Per-level status: IMPROVED / REGRESSED / NEUTRAL (w/ tunable deadbands)
    * Overall summary: IMPROVED / MIXED / REGRESSED / NEUTRAL
    * Regression flags from best_model_selector.regression_report

The comparator is pure — no I/O, no MongoDB — so it plugs cleanly into
scripts, tests, and the FastAPI layer alike.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.rl.best_model_selector import (
    CheckpointRanking,
    rank_checkpoints,
    regression_report,
)
from backend.rl.comparison_chart import CheckpointSeries
from backend.rl.evaluator import EvalResult

# Deadbands — smaller absolute deltas than these are treated as NEUTRAL.
DEFAULT_WIN_RATE_DEADBAND: float = 0.02
DEFAULT_DOMINANCE_DEADBAND: float = 0.02


@dataclass(frozen=True)
class LevelDelta:
    """Per-level metric delta (candidate minus baseline)."""

    bot_level: int
    win_rate_delta: float
    avg_score_delta: float
    avg_rally_delta: float
    dominance_delta: float
    status: str  # "IMPROVED" | "REGRESSED" | "NEUTRAL" | "MISSING"

    def to_dict(self) -> dict[str, float | int | str]:
        return {
            "bot_level": self.bot_level,
            "win_rate_delta": round(self.win_rate_delta, 4),
            "avg_score_delta": round(self.avg_score_delta, 2),
            "avg_rally_delta": round(self.avg_rally_delta, 2),
            "dominance_delta": round(self.dominance_delta, 4),
            "status": self.status,
        }


@dataclass(frozen=True)
class BaselineComparison:
    """Full comparison of a candidate against a baseline."""

    baseline_label: str
    candidate_label: str
    level_deltas: list[LevelDelta]
    regressions: list[str]
    overall_status: str  # "IMPROVED" | "REGRESSED" | "MIXED" | "NEUTRAL"
    baseline_rank: CheckpointRanking | None = None
    candidate_rank: CheckpointRanking | None = None
    notes: list[str] = field(default_factory=list)

    def to_summary_dict(self) -> dict[str, object]:
        return {
            "baseline": self.baseline_label,
            "candidate": self.candidate_label,
            "overall_status": self.overall_status,
            "regressions": list(self.regressions),
            "level_deltas": [d.to_dict() for d in self.level_deltas],
            "notes": list(self.notes),
        }

    @property
    def promoted(self) -> bool:
        """Would this candidate be safe to promote over the baseline?"""
        return self.overall_status == "IMPROVED" and not self.regressions


def _classify_delta(
    win_rate_delta: float,
    dominance_delta: float,
    *,
    win_rate_deadband: float,
    dominance_deadband: float,
) -> str:
    """Classify a single level's delta. Both signals must agree on REGRESSED."""
    wr_reg = win_rate_delta < -win_rate_deadband
    dom_reg = dominance_delta < -dominance_deadband
    wr_imp = win_rate_delta > win_rate_deadband
    dom_imp = dominance_delta > dominance_deadband

    # Hard REGRESSED only if at least one signal says so and neither says IMPROVED.
    if (wr_reg or dom_reg) and not (wr_imp or dom_imp):
        return "REGRESSED"
    # IMPROVED only when at least one signal improved and neither regressed.
    if (wr_imp or dom_imp) and not (wr_reg or dom_reg):
        return "IMPROVED"
    if not (wr_reg or dom_reg or wr_imp or dom_imp):
        return "NEUTRAL"
    # Signals disagree — keep as NEUTRAL, record in notes upstream.
    return "NEUTRAL"


def _per_level_delta(
    baseline: EvalResult,
    candidate: EvalResult,
    *,
    win_rate_deadband: float,
    dominance_deadband: float,
) -> LevelDelta:
    return LevelDelta(
        bot_level=baseline.bot_level,
        win_rate_delta=candidate.win_rate - baseline.win_rate,
        avg_score_delta=candidate.avg_score - baseline.avg_score,
        avg_rally_delta=candidate.avg_rally_length - baseline.avg_rally_length,
        dominance_delta=candidate.dominance_score - baseline.dominance_score,
        status=_classify_delta(
            candidate.win_rate - baseline.win_rate,
            candidate.dominance_score - baseline.dominance_score,
            win_rate_deadband=win_rate_deadband,
            dominance_deadband=dominance_deadband,
        ),
    )


def _overall_from_levels(deltas: list[LevelDelta]) -> str:
    """Roll per-level statuses into an overall verdict."""
    statuses = [d.status for d in deltas if d.status != "MISSING"]
    if not statuses:
        return "NEUTRAL"
    has_imp = any(s == "IMPROVED" for s in statuses)
    has_reg = any(s == "REGRESSED" for s in statuses)
    if has_imp and has_reg:
        return "MIXED"
    if has_imp:
        return "IMPROVED"
    if has_reg:
        return "REGRESSED"
    return "NEUTRAL"


def compare_to_baseline(
    baseline_results: list[EvalResult],
    candidate_results: list[EvalResult],
    *,
    baseline_label: str = "baseline",
    candidate_label: str = "candidate",
    win_rate_deadband: float = DEFAULT_WIN_RATE_DEADBAND,
    dominance_deadband: float = DEFAULT_DOMINANCE_DEADBAND,
) -> BaselineComparison:
    """Compare a candidate checkpoint against a baseline checkpoint.

    Both inputs are lists of EvalResults across bot levels. Any level
    present in one but not the other contributes a `MISSING` delta and
    a note; it does not affect the overall verdict.
    """
    by_level_base = {r.bot_level: r for r in baseline_results}
    by_level_cand = {r.bot_level: r for r in candidate_results}
    all_levels = sorted(set(by_level_base) | set(by_level_cand))

    deltas: list[LevelDelta] = []
    notes: list[str] = []
    for lvl in all_levels:
        base = by_level_base.get(lvl)
        cand = by_level_cand.get(lvl)
        if base is None or cand is None:
            notes.append(f"L{lvl} missing from {'candidate' if base else 'baseline'}")
            deltas.append(
                LevelDelta(
                    bot_level=lvl,
                    win_rate_delta=0.0,
                    avg_score_delta=0.0,
                    avg_rally_delta=0.0,
                    dominance_delta=0.0,
                    status="MISSING",
                )
            )
            continue
        deltas.append(
            _per_level_delta(
                base,
                cand,
                win_rate_deadband=win_rate_deadband,
                dominance_deadband=dominance_deadband,
            )
        )

    # Rankings give us a verdict-tier comparison using the existing
    # best_model_selector semantics — reuse rather than duplicate.
    baseline_rank = candidate_rank = None
    regressions: list[str] = []
    if baseline_results and candidate_results:
        ranked = rank_checkpoints(
            [
                CheckpointSeries(label=baseline_label, results=baseline_results),
                CheckpointSeries(label=candidate_label, results=candidate_results),
            ]
        )
        by_label = {r.label: r for r in ranked}
        baseline_rank = by_label.get(baseline_label)
        candidate_rank = by_label.get(candidate_label)
        if baseline_rank and candidate_rank:
            regressions = regression_report(candidate_rank, baseline_rank)

    return BaselineComparison(
        baseline_label=baseline_label,
        candidate_label=candidate_label,
        level_deltas=deltas,
        regressions=regressions,
        overall_status=_overall_from_levels(deltas),
        baseline_rank=baseline_rank,
        candidate_rank=candidate_rank,
        notes=notes,
    )


def format_delta_table(comparison: BaselineComparison) -> str:
    """Render a monospace table of per-level deltas for CLI / logs."""
    header = "| Level | ΔWinRate | ΔScore | ΔRally | ΔDominance | Status   |"
    sep = "|------:|---------:|-------:|-------:|-----------:|----------|"
    rows: list[str] = [header, sep]
    for d in comparison.level_deltas:
        rows.append(
            f"| L{d.bot_level} "
            f"| {d.win_rate_delta:+.2%} "
            f"| {d.avg_score_delta:+.2f} "
            f"| {d.avg_rally_delta:+.1f} "
            f"| {d.dominance_delta:+.3f} "
            f"| {d.status:<8} |"
        )
    rows.append("")
    rows.append(f"Overall: **{comparison.overall_status}**")
    if comparison.regressions:
        rows.append("Regressions: " + "; ".join(comparison.regressions))
    if comparison.notes:
        rows.append("Notes: " + "; ".join(comparison.notes))
    return "\n".join(rows)


__all__ = [
    "DEFAULT_WIN_RATE_DEADBAND",
    "DEFAULT_DOMINANCE_DEADBAND",
    "LevelDelta",
    "BaselineComparison",
    "compare_to_baseline",
    "format_delta_table",
]
