"""Tests for the markdown evaluation report generator."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.rl.comparison_chart import CheckpointSeries
from backend.rl.evaluator import EvalResult, compute_dominance_score
from backend.rl.report_generator import (
    THRESHOLDS,
    generate_report,
    level_passes,
    overall_verdict,
)


def _result(
    *,
    bot_level: int,
    win_rate: float,
    avg_score: float,
    avg_opponent_score: float = 5.0,
    avg_rally_length: float = 100.0,
) -> EvalResult:
    return EvalResult(
        model_path="/m",
        bot_level=bot_level,
        n_games=20,
        win_rate=win_rate,
        avg_score=avg_score,
        avg_opponent_score=avg_opponent_score,
        avg_rally_length=avg_rally_length,
        avg_episode_length=4500.0,
        timestamp="2026-04-12T00:00:00+00:00",
        dominance_score=compute_dominance_score(win_rate, avg_score, avg_opponent_score),
    )


def _passing_results() -> list[EvalResult]:
    """A set of results that meets every threshold."""
    out: list[EvalResult] = []
    for lvl, th in THRESHOLDS.items():
        out.append(
            _result(
                bot_level=lvl,
                win_rate=th["win_rate"] + 0.05,
                avg_score=th["avg_score"] + 1.0,
                avg_rally_length=th["avg_rally"] + 10.0,
            )
        )
    return out


class TestLevelPasses:
    def test_meets_threshold(self) -> None:
        r = _result(bot_level=1, win_rate=0.95, avg_score=14.0, avg_rally_length=110.0)
        assert level_passes(r) is True

    def test_below_win_rate(self) -> None:
        r = _result(bot_level=1, win_rate=0.85, avg_score=14.0, avg_rally_length=110.0)
        assert level_passes(r) is False

    def test_below_avg_score(self) -> None:
        r = _result(bot_level=1, win_rate=0.95, avg_score=10.0, avg_rally_length=110.0)
        assert level_passes(r) is False

    def test_below_rally(self) -> None:
        r = _result(bot_level=1, win_rate=0.95, avg_score=14.0, avg_rally_length=50.0)
        assert level_passes(r) is False

    def test_unknown_level(self) -> None:
        r = _result(bot_level=9, win_rate=1.0, avg_score=15.0, avg_rally_length=200.0)
        assert level_passes(r) is False


class TestOverallVerdict:
    def test_pass_when_all_meet(self) -> None:
        assert overall_verdict(_passing_results()) == "PASS"

    def test_critical_when_l1_below_50(self) -> None:
        results = _passing_results()
        # Drop L1 below 50% win rate
        results[0] = _result(bot_level=1, win_rate=0.30, avg_score=14.0)
        assert overall_verdict(results) == "CRITICAL"

    def test_fail_when_l2_misses(self) -> None:
        results = _passing_results()
        # L2 below threshold but L1 still ≥50%
        results[1] = _result(bot_level=2, win_rate=0.50, avg_score=5.0)
        assert overall_verdict(results) == "FAIL"

    def test_conditional_when_only_l4_l5_miss(self) -> None:
        results = _passing_results()
        # Drop L4 and L5 below threshold but keep L1 strong
        results[3] = _result(bot_level=4, win_rate=0.10, avg_score=2.0, avg_rally_length=20)
        results[4] = _result(bot_level=5, win_rate=0.05, avg_score=1.0, avg_rally_length=20)
        assert overall_verdict(results) == "CONDITIONAL"


class TestGenerateReport:
    def test_writes_markdown_with_charts(self, tmp_path: Path) -> None:
        s1 = CheckpointSeries(label="10K", results=_passing_results())
        s2 = CheckpointSeries(
            label="20K",
            results=[
                _result(bot_level=lvl, win_rate=0.4, avg_score=8.0)
                for lvl in range(1, 6)
            ],
        )
        out = generate_report([s1, s2], tmp_path / "report.md")
        assert out.exists()

        text = out.read_text(encoding="utf-8")
        assert "Pikachu Volleyball RL — Evaluation Report" in text
        assert "10K" in text and "20K" in text
        assert "PASS" in text  # 10K should pass
        assert "Elo Ratings" in text
        assert "Threshold Reference" in text

        # Charts written
        chart_dir = tmp_path / "charts"
        assert (chart_dir / "comparison.png").exists()
        assert (chart_dir / "progression_L1.png").exists()

    def test_single_checkpoint_skips_progression(self, tmp_path: Path) -> None:
        out = generate_report(
            [CheckpointSeries(label="only", results=_passing_results())],
            tmp_path / "report.md",
        )
        text = out.read_text(encoding="utf-8")
        assert "## Per-Level Comparison" in text
        # No progression section when only 1 checkpoint
        assert "Training Progression" not in text

    def test_empty_series_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            generate_report([], tmp_path / "report.md")

    def test_critical_verdict_in_output(self, tmp_path: Path) -> None:
        bad = [
            _result(bot_level=lvl, win_rate=0.0, avg_score=0.0, avg_rally_length=10)
            for lvl in range(1, 6)
        ]
        out = generate_report(
            [CheckpointSeries(label="random", results=bad)],
            tmp_path / "report.md",
        )
        text = out.read_text(encoding="utf-8")
        assert "CRITICAL" in text
