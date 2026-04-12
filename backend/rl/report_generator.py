"""Auto-generate evaluation reports as markdown with embedded charts.

Takes a set of CheckpointSeries (one per model checkpoint) and produces:
  - Per-checkpoint summary tables (one row per bot level)
  - Per-level pass/fail verdict against EVAL_CRITERIA thresholds
  - Overall verdict (PASS / CONDITIONAL / FAIL / CRITICAL)
  - Dominance score and Elo rating columns
  - Embedded comparison and progression PNG charts

The report is fully self-contained — it links to chart files saved next to it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from backend.rl.comparison_chart import (
    CheckpointSeries,
    render_comparison_chart,
    render_progression_chart,
)
from backend.rl.elo import EloRatingSystem, bot_player_id
from backend.rl.evaluator import EvalResult

# Per-level thresholds — kept consistent with docs/EVAL_CRITERIA.md.
THRESHOLDS: dict[int, dict[str, float]] = {
    1: {"win_rate": 0.90, "avg_score": 13.0, "avg_rally": 100.0},
    2: {"win_rate": 0.75, "avg_score": 11.0, "avg_rally": 80.0},
    3: {"win_rate": 0.50, "avg_score": 8.0, "avg_rally": 70.0},
    4: {"win_rate": 0.25, "avg_score": 5.0, "avg_rally": 60.0},
    5: {"win_rate": 0.10, "avg_score": 3.0, "avg_rally": 50.0},
}


def level_passes(result: EvalResult) -> bool:
    """True if all three primary metrics meet the level threshold."""
    th = THRESHOLDS.get(result.bot_level)
    if th is None:
        return False
    return (
        result.win_rate >= th["win_rate"]
        and result.avg_score >= th["avg_score"]
        and result.avg_rally_length >= th["avg_rally"]
    )


def overall_verdict(results: list[EvalResult]) -> str:
    """Compute overall verdict per the EVAL_CRITERIA spec."""
    by_level = {r.bot_level: r for r in results}
    l1 = by_level.get(1)
    if l1 is not None and l1.win_rate < 0.50:
        return "CRITICAL"

    pass_flags = {lvl: level_passes(r) for lvl, r in by_level.items()}

    if all(pass_flags.values()):
        return "PASS"

    core_pass = all(pass_flags.get(lvl, False) for lvl in (1, 2, 3))
    stretch_fail = not all(pass_flags.get(lvl, False) for lvl in (4, 5))
    if core_pass and stretch_fail:
        return "CONDITIONAL"
    return "FAIL"


def _format_pct(v: float) -> str:
    return f"{v * 100:.0f}%"


def _checkpoint_table(results: list[EvalResult]) -> str:
    """Build per-level table for one checkpoint."""
    sorted_results = sorted(results, key=lambda r: r.bot_level)
    lines = [
        "| Level | Win Rate | Avg Score | Opp Score | Rally | Episode | Dominance | Verdict |",
        "|------:|---------:|----------:|----------:|------:|--------:|----------:|---------|",
    ]
    for r in sorted_results:
        verdict = "PASS" if level_passes(r) else "FAIL"
        lines.append(
            f"| L{r.bot_level} "
            f"| {_format_pct(r.win_rate)} "
            f"| {r.avg_score:.1f} "
            f"| {r.avg_opponent_score:.1f} "
            f"| {r.avg_rally_length:.0f} "
            f"| {r.avg_episode_length:.0f} "
            f"| {r.dominance_score:.2f} "
            f"| **{verdict}** |"
        )
    return "\n".join(lines)


def _elo_table(elo: EloRatingSystem) -> str:
    lines = [
        "| Player | Rating | Games |",
        "|--------|-------:|------:|",
    ]
    for pid, rating, games in elo.leaderboard():
        lines.append(f"| `{pid}` | {rating:.0f} | {games} |")
    return "\n".join(lines)


def generate_report(
    series: list[CheckpointSeries],
    output_path: str | Path,
    *,
    title: str = "Pikachu Volleyball RL — Evaluation Report",
    chart_subdir: str = "charts",
) -> Path:
    """Build a complete markdown report with embedded charts.

    Returns the path to the markdown file. Chart PNGs are written to
    `{output_path.parent}/{chart_subdir}/`.
    """
    if not series:
        raise ValueError("Cannot generate report with empty series list")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    chart_dir = output_path.parent / chart_subdir
    chart_dir.mkdir(parents=True, exist_ok=True)

    # Charts
    cmp_path = render_comparison_chart(
        series, chart_dir / "comparison.png", title=f"{title} — Per-Level Metrics"
    )
    progression_paths: list[tuple[int, Path]] = []
    if len(series) >= 2:
        for level in (1, 3, 5):
            try:
                p = render_progression_chart(
                    series,
                    chart_dir / f"progression_L{level}.png",
                    bot_level=level,
                    title=f"Training Progression — Level {level}",
                )
                progression_paths.append((level, p))
            except ValueError:
                # Some series don't include this level — skip that chart
                continue

    # Elo
    elo = EloRatingSystem()
    for cs in series:
        elo.update_from_evals(cs.results)

    # Render markdown
    parts: list[str] = []
    parts.append(f"# {title}\n")
    parts.append(
        f"_Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}_\n"
    )
    parts.append("## Summary\n")
    parts.append(
        f"- Checkpoints evaluated: **{len(series)}**\n"
        f"- Levels evaluated per checkpoint: "
        f"{', '.join(f'L{lvl}' for lvl in sorted({r.bot_level for cs in series for r in cs.results}))}\n"
    )

    parts.append("\n## Per-Checkpoint Results\n")
    for cs in series:
        verdict = overall_verdict(cs.results)
        parts.append(f"\n### {cs.label} — **{verdict}**\n")
        parts.append(_checkpoint_table(cs.results))
        parts.append("")

    parts.append(f"\n## Per-Level Comparison\n\n![Comparison chart]({chart_subdir}/{cmp_path.name})\n")

    if progression_paths:
        parts.append("\n## Training Progression\n")
        for level, p in progression_paths:
            parts.append(f"\n### Level {level}\n")
            parts.append(f"![Level {level} progression]({chart_subdir}/{p.name})\n")

    parts.append("\n## Elo Ratings (Cross-Player)\n")
    parts.append(_elo_table(elo))
    parts.append("")

    parts.append("\n## Threshold Reference\n")
    parts.append("| Level | Min Win Rate | Min Avg Score | Min Avg Rally |")
    parts.append("|------:|:------------:|:-------------:|:-------------:|")
    for lvl in sorted(THRESHOLDS):
        th = THRESHOLDS[lvl]
        parts.append(
            f"| L{lvl} | {_format_pct(th['win_rate'])} | "
            f"{th['avg_score']:.1f} | {th['avg_rally']:.0f} |"
        )

    output_path.write_text("\n".join(parts) + "\n", encoding="utf-8")
    return output_path


# Re-export bot_player_id so report consumers can label rows consistently.
__all__ = [
    "THRESHOLDS",
    "level_passes",
    "overall_verdict",
    "generate_report",
    "bot_player_id",
]
