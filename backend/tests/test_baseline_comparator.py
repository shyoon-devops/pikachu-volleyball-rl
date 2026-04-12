"""Tests for the baseline checkpoint comparator."""

from __future__ import annotations

from backend.rl.baseline_comparator import (
    BaselineComparison,
    LevelDelta,
    compare_to_baseline,
    format_delta_table,
)
from backend.rl.evaluator import EvalResult, compute_dominance_score


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


def _baseline() -> list[EvalResult]:
    # Moderate performance across all levels
    return [
        _result(bot_level=1, win_rate=0.80, avg_score=12.0, avg_rally_length=100),
        _result(bot_level=2, win_rate=0.60, avg_score=10.0, avg_rally_length=80),
        _result(bot_level=3, win_rate=0.40, avg_score=7.0, avg_rally_length=70),
        _result(bot_level=4, win_rate=0.20, avg_score=4.0, avg_rally_length=60),
        _result(bot_level=5, win_rate=0.05, avg_score=2.0, avg_rally_length=50),
    ]


class TestLevelDeltaClassification:
    def test_uniform_improvement_yields_improved_overall(self) -> None:
        baseline = _baseline()
        # Candidate strictly better on every level
        candidate = [
            _result(
                bot_level=r.bot_level,
                win_rate=r.win_rate + 0.10,
                avg_score=r.avg_score + 2.0,
                avg_rally_length=r.avg_rally_length + 10.0,
            )
            for r in baseline
        ]
        cmp = compare_to_baseline(baseline, candidate)
        assert cmp.overall_status == "IMPROVED"
        for d in cmp.level_deltas:
            assert d.status == "IMPROVED"
            assert d.win_rate_delta > 0
            assert d.dominance_delta > 0

    def test_uniform_regression_yields_regressed(self) -> None:
        baseline = _baseline()
        candidate = [
            _result(
                bot_level=r.bot_level,
                win_rate=max(0.0, r.win_rate - 0.15),
                avg_score=max(0.0, r.avg_score - 3.0),
                avg_rally_length=max(0.0, r.avg_rally_length - 20),
            )
            for r in baseline
        ]
        cmp = compare_to_baseline(baseline, candidate)
        assert cmp.overall_status == "REGRESSED"
        assert all(d.status == "REGRESSED" for d in cmp.level_deltas)

    def test_mixed_produces_mixed_overall(self) -> None:
        baseline = _baseline()
        candidate = list(baseline)
        # L1 way better, L5 way worse
        candidate[0] = _result(bot_level=1, win_rate=0.95, avg_score=14.0, avg_rally_length=110)
        candidate[4] = _result(bot_level=5, win_rate=0.0, avg_score=0.0, avg_rally_length=10)
        cmp = compare_to_baseline(baseline, candidate)
        assert cmp.overall_status == "MIXED"
        statuses = {d.bot_level: d.status for d in cmp.level_deltas}
        assert statuses[1] == "IMPROVED"
        assert statuses[5] == "REGRESSED"

    def test_within_deadband_is_neutral(self) -> None:
        baseline = _baseline()
        # Add noise smaller than default deadbands (0.02 win_rate, 0.02 dominance)
        candidate = [
            _result(
                bot_level=r.bot_level,
                win_rate=r.win_rate + 0.005,
                avg_score=r.avg_score + 0.05,
                avg_rally_length=r.avg_rally_length + 0.5,
            )
            for r in baseline
        ]
        cmp = compare_to_baseline(baseline, candidate)
        assert cmp.overall_status == "NEUTRAL"
        assert all(d.status == "NEUTRAL" for d in cmp.level_deltas)


class TestMissingLevels:
    def test_candidate_missing_level_is_flagged(self) -> None:
        baseline = _baseline()
        candidate = baseline[:3]  # Missing L4 and L5
        cmp = compare_to_baseline(baseline, candidate)
        statuses = {d.bot_level: d.status for d in cmp.level_deltas}
        assert statuses[4] == "MISSING"
        assert statuses[5] == "MISSING"
        # Should still be IMPROVED/NEUTRAL overall, not affected by MISSING
        assert cmp.overall_status in {"IMPROVED", "NEUTRAL", "REGRESSED", "MIXED"}
        # Notes should explicitly mention the missing levels
        joined = " ".join(cmp.notes)
        assert "L4" in joined and "L5" in joined

    def test_baseline_missing_level_is_flagged(self) -> None:
        baseline = _baseline()[:3]
        candidate = _baseline()
        cmp = compare_to_baseline(baseline, candidate)
        statuses = {d.bot_level: d.status for d in cmp.level_deltas}
        assert statuses[4] == "MISSING"

    def test_empty_inputs_neutral(self) -> None:
        cmp = compare_to_baseline([], [])
        assert cmp.overall_status == "NEUTRAL"
        assert cmp.level_deltas == []
        assert cmp.regressions == []


class TestRegressionIntegration:
    def test_regressions_populated_on_drop(self) -> None:
        baseline = _baseline()
        # Massive degradation → regression_report should flag
        candidate = [
            _result(bot_level=lvl, win_rate=0.0, avg_score=0.0, avg_rally_length=10)
            for lvl in range(1, 6)
        ]
        cmp = compare_to_baseline(baseline, candidate)
        assert cmp.regressions  # non-empty
        assert cmp.baseline_rank is not None
        assert cmp.candidate_rank is not None
        # Not safe to promote
        assert cmp.promoted is False

    def test_no_regressions_when_uniformly_better(self) -> None:
        baseline = _baseline()
        candidate = [
            _result(
                bot_level=r.bot_level,
                win_rate=min(1.0, r.win_rate + 0.10),
                avg_score=r.avg_score + 2.0,
                avg_rally_length=r.avg_rally_length + 10,
            )
            for r in baseline
        ]
        cmp = compare_to_baseline(baseline, candidate)
        assert cmp.regressions == []
        assert cmp.promoted is True


class TestFormatDeltaTable:
    def test_table_contains_all_levels(self) -> None:
        cmp = compare_to_baseline(_baseline(), _baseline())
        text = format_delta_table(cmp)
        for lvl in range(1, 6):
            assert f"L{lvl}" in text
        assert "Overall:" in text

    def test_table_includes_regressions_line_when_present(self) -> None:
        baseline = _baseline()
        bad = [
            _result(bot_level=lvl, win_rate=0.0, avg_score=0.0, avg_rally_length=10)
            for lvl in range(1, 6)
        ]
        cmp = compare_to_baseline(baseline, bad)
        text = format_delta_table(cmp)
        assert "Regressions:" in text


class TestLabelsAndSerialization:
    def test_custom_labels_propagate(self) -> None:
        cmp = compare_to_baseline(
            _baseline(),
            _baseline(),
            baseline_label="prod_v1.2",
            candidate_label="candidate_20250412",
        )
        assert cmp.baseline_label == "prod_v1.2"
        assert cmp.candidate_label == "candidate_20250412"
        d = cmp.to_summary_dict()
        assert d["baseline"] == "prod_v1.2"
        assert d["candidate"] == "candidate_20250412"
        assert isinstance(d["level_deltas"], list)
        assert all("bot_level" in lvl for lvl in d["level_deltas"])

    def test_level_delta_to_dict_shape(self) -> None:
        ld = LevelDelta(
            bot_level=1,
            win_rate_delta=0.1,
            avg_score_delta=1.5,
            avg_rally_delta=10.0,
            dominance_delta=0.08,
            status="IMPROVED",
        )
        d = ld.to_dict()
        assert d == {
            "bot_level": 1,
            "win_rate_delta": 0.1,
            "avg_score_delta": 1.5,
            "avg_rally_delta": 10.0,
            "dominance_delta": 0.08,
            "status": "IMPROVED",
        }


class TestBaselineComparisonDataclass:
    def test_promoted_requires_improved_and_no_regressions(self) -> None:
        base = BaselineComparison(
            baseline_label="b",
            candidate_label="c",
            level_deltas=[],
            regressions=[],
            overall_status="IMPROVED",
        )
        assert base.promoted is True

        with_regression = BaselineComparison(
            baseline_label="b",
            candidate_label="c",
            level_deltas=[],
            regressions=["win_rate dropped"],
            overall_status="IMPROVED",
        )
        assert with_regression.promoted is False

        mixed = BaselineComparison(
            baseline_label="b",
            candidate_label="c",
            level_deltas=[],
            regressions=[],
            overall_status="MIXED",
        )
        assert mixed.promoted is False
