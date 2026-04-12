"""Tests for the checkpoint comparison chart generator."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.rl.comparison_chart import (
    CheckpointSeries,
    render_comparison_chart,
    render_progression_chart,
)
from backend.rl.evaluator import EvalResult


def _make_result(
    *,
    bot_level: int,
    win_rate: float = 0.5,
    avg_score: float = 10.0,
    avg_rally_length: float = 80.0,
    avg_episode_length: float = 5000.0,
    model_path: str = "/models/test",
) -> EvalResult:
    return EvalResult(
        model_path=model_path,
        bot_level=bot_level,
        n_games=10,
        win_rate=win_rate,
        avg_score=avg_score,
        avg_opponent_score=15.0 - avg_score,
        avg_rally_length=avg_rally_length,
        avg_episode_length=avg_episode_length,
        timestamp="2026-04-12T00:00:00+00:00",
    )


def _make_series(label: str, win_rate_base: float = 0.2) -> CheckpointSeries:
    return CheckpointSeries(
        label=label,
        results=[
            _make_result(bot_level=lvl, win_rate=min(1.0, win_rate_base + lvl * 0.1))
            for lvl in range(1, 6)
        ],
    )


class TestRenderComparisonChart:
    def test_creates_png_file(self, tmp_path: Path) -> None:
        series = [_make_series("10K"), _make_series("20K", 0.3)]
        out = render_comparison_chart(series, tmp_path / "cmp.png")
        assert out.exists()
        assert out.stat().st_size > 0
        # PNG magic bytes
        assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"

    def test_creates_parent_directory(self, tmp_path: Path) -> None:
        series = [_make_series("10K")]
        out = render_comparison_chart(series, tmp_path / "nested" / "cmp.png")
        assert out.exists()

    def test_empty_series_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            render_comparison_chart([], tmp_path / "x.png")

    def test_single_series(self, tmp_path: Path) -> None:
        out = render_comparison_chart([_make_series("only")], tmp_path / "single.png")
        assert out.exists()


class TestRenderProgressionChart:
    def test_creates_png_file(self, tmp_path: Path) -> None:
        series = [_make_series(f"{i}K", 0.1 * i) for i in range(1, 6)]
        out = render_progression_chart(series, tmp_path / "prog.png", bot_level=1)
        assert out.exists()
        assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"

    def test_empty_series_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            render_progression_chart([], tmp_path / "x.png", bot_level=1)

    def test_missing_level_raises(self, tmp_path: Path) -> None:
        # Series has only level 5
        series = [
            CheckpointSeries(
                label="x", results=[_make_result(bot_level=5)]
            )
        ]
        with pytest.raises(ValueError, match="No results for bot_level=1"):
            render_progression_chart(series, tmp_path / "x.png", bot_level=1)
