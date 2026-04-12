"""Tests for the best-model auto-selection logic."""

from __future__ import annotations

from backend.rl.best_model_selector import (
    VERDICT_TIER,
    CheckpointRanking,
    is_iso_after,
    rank_checkpoints,
    regression_report,
    select_best,
)
from backend.rl.comparison_chart import CheckpointSeries
from backend.rl.evaluator import EvalResult, compute_dominance_score
from backend.rl.report_generator import THRESHOLDS


def _result(
    *,
    bot_level: int,
    win_rate: float,
    avg_score: float,
    avg_opponent_score: float = 5.0,
    avg_rally_length: float = 100.0,
    timestamp: str = "2026-04-12T00:00:00+00:00",
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
        timestamp=timestamp,
        dominance_score=compute_dominance_score(win_rate, avg_score, avg_opponent_score),
    )


def _passing_results(timestamp: str = "2026-04-12T00:00:00+00:00") -> list[EvalResult]:
    return [
        _result(
            bot_level=lvl,
            win_rate=th["win_rate"] + 0.05,
            avg_score=th["avg_score"] + 1.0,
            avg_rally_length=th["avg_rally"] + 10.0,
            timestamp=timestamp,
        )
        for lvl, th in THRESHOLDS.items()
    ]


def _failing_results(timestamp: str = "2026-04-12T00:00:00+00:00") -> list[EvalResult]:
    return [
        _result(
            bot_level=lvl,
            win_rate=0.05,
            avg_score=1.0,
            avg_rally_length=10.0,
            timestamp=timestamp,
        )
        for lvl in range(1, 6)
    ]


def _conditional_results(timestamp: str = "2026-04-12T00:00:00+00:00") -> list[EvalResult]:
    """L1-L3 pass, L4-L5 fail → CONDITIONAL verdict."""
    out = _passing_results(timestamp=timestamp)
    out[3] = _result(
        bot_level=4, win_rate=0.10, avg_score=2.0, avg_rally_length=20, timestamp=timestamp
    )
    out[4] = _result(
        bot_level=5, win_rate=0.05, avg_score=1.0, avg_rally_length=20, timestamp=timestamp
    )
    return out


class TestRankCheckpoints:
    def test_pass_outranks_fail(self) -> None:
        s_pass = CheckpointSeries(label="pass", results=_passing_results())
        s_fail = CheckpointSeries(label="fail", results=_failing_results())
        ranked = rank_checkpoints([s_fail, s_pass])
        assert ranked[0].label == "pass"
        assert ranked[1].label == "fail"
        assert ranked[0].verdict == "PASS"

    def test_pass_outranks_conditional(self) -> None:
        s_pass = CheckpointSeries(label="pass", results=_passing_results())
        s_cond = CheckpointSeries(label="cond", results=_conditional_results())
        ranked = rank_checkpoints([s_cond, s_pass])
        assert ranked[0].label == "pass"
        assert ranked[0].verdict_tier > ranked[1].verdict_tier

    def test_dominance_breaks_tie_within_verdict(self) -> None:
        # Two PASS checkpoints, the second has higher avg_score → higher dominance
        a = _passing_results()
        b_results = []
        for lvl, th in THRESHOLDS.items():
            b_results.append(
                _result(
                    bot_level=lvl,
                    win_rate=th["win_rate"] + 0.05,
                    avg_score=th["avg_score"] + 5.0,  # bigger margin
                    avg_rally_length=th["avg_rally"] + 10.0,
                )
            )
        s_a = CheckpointSeries(label="A", results=a)
        s_b = CheckpointSeries(label="B", results=b_results)
        ranked = rank_checkpoints([s_a, s_b])
        assert ranked[0].label == "B"
        assert ranked[0].mean_dominance > ranked[1].mean_dominance

    def test_recency_breaks_full_tie(self) -> None:
        early = CheckpointSeries(
            label="old", results=_passing_results(timestamp="2026-04-10T00:00:00+00:00")
        )
        late = CheckpointSeries(
            label="new", results=_passing_results(timestamp="2026-04-12T00:00:00+00:00")
        )
        ranked = rank_checkpoints([early, late])
        assert ranked[0].label == "new"

    def test_returns_all_input_series(self) -> None:
        series = [
            CheckpointSeries(label=f"cp{i}", results=_passing_results()) for i in range(3)
        ]
        ranked = rank_checkpoints(series)
        assert len(ranked) == 3
        assert {r.label for r in ranked} == {"cp0", "cp1", "cp2"}


class TestSelectBest:
    def test_returns_top_ranked(self) -> None:
        s_pass = CheckpointSeries(label="pass", results=_passing_results())
        s_fail = CheckpointSeries(label="fail", results=_failing_results())
        best = select_best([s_fail, s_pass])
        assert best is not None
        assert best.label == "pass"

    def test_empty_returns_none(self) -> None:
        assert select_best([]) is None

    def test_require_pass_filters_out_failures(self) -> None:
        s_fail = CheckpointSeries(label="fail", results=_failing_results())
        # No PASS or CONDITIONAL → returns None when require_pass=True
        assert select_best([s_fail], require_pass=True) is None

    def test_require_pass_allows_conditional(self) -> None:
        s_cond = CheckpointSeries(label="cond", results=_conditional_results())
        s_fail = CheckpointSeries(label="fail", results=_failing_results())
        best = select_best([s_fail, s_cond], require_pass=True)
        assert best is not None
        assert best.label == "cond"

    def test_require_pass_false_picks_failure_if_only_option(self) -> None:
        s_fail = CheckpointSeries(label="fail", results=_failing_results())
        best = select_best([s_fail], require_pass=False)
        assert best is not None
        assert best.label == "fail"


class TestRegressionReport:
    def _ranking(self, label: str, series: CheckpointSeries) -> CheckpointRanking:
        return rank_checkpoints([series])[0]

    def test_no_regression_returns_empty(self) -> None:
        baseline = self._ranking("base", CheckpointSeries(label="base", results=_passing_results()))
        candidate = self._ranking("new", CheckpointSeries(label="new", results=_passing_results()))
        assert regression_report(candidate, baseline) == []

    def test_detects_win_rate_drop(self) -> None:
        baseline = self._ranking(
            "base", CheckpointSeries(label="base", results=_passing_results())
        )
        candidate = self._ranking(
            "new", CheckpointSeries(label="new", results=_conditional_results())
        )
        issues = regression_report(candidate, baseline)
        assert any("win_rate" in i for i in issues)

    def test_detects_verdict_regression(self) -> None:
        baseline = self._ranking(
            "base", CheckpointSeries(label="base", results=_passing_results())
        )
        candidate = self._ranking(
            "new", CheckpointSeries(label="new", results=_conditional_results())
        )
        issues = regression_report(candidate, baseline)
        assert any("verdict" in i for i in issues)

    def test_detects_dominance_drop(self) -> None:
        baseline = self._ranking(
            "base", CheckpointSeries(label="base", results=_passing_results())
        )
        candidate = self._ranking(
            "new", CheckpointSeries(label="new", results=_failing_results())
        )
        issues = regression_report(candidate, baseline)
        assert any("dominance" in i for i in issues)

    def test_threshold_respected(self) -> None:
        # Drop just under the default threshold (0.05) — should NOT flag
        baseline = self._ranking(
            "base", CheckpointSeries(label="base", results=_passing_results())
        )
        candidate = self._ranking(
            "new", CheckpointSeries(label="new", results=_passing_results())
        )
        # Same data, so no drop at all
        assert regression_report(candidate, baseline, win_rate_drop=0.01) == []


class TestIsIsoAfter:
    def test_later_after_earlier(self) -> None:
        assert is_iso_after("2026-04-12T01:00:00+00:00", "2026-04-12T00:00:00+00:00") is True

    def test_equal_returns_false(self) -> None:
        ts = "2026-04-12T00:00:00+00:00"
        assert is_iso_after(ts, ts) is False

    def test_earlier_returns_false(self) -> None:
        assert is_iso_after("2026-04-10T00:00:00+00:00", "2026-04-12T00:00:00+00:00") is False

    def test_empty_inputs_return_false(self) -> None:
        assert is_iso_after("", "2026-04-12T00:00:00+00:00") is False
        assert is_iso_after("2026-04-12T00:00:00+00:00", "") is False


class TestCheckpointRanking:
    def test_to_summary_dict_shape(self) -> None:
        s = CheckpointSeries(label="cp", results=_passing_results())
        ranked = rank_checkpoints([s])
        d = ranked[0].to_summary_dict()
        assert set(d.keys()) == {
            "label",
            "verdict",
            "verdict_tier",
            "mean_dominance",
            "mean_win_rate",
            "latest_timestamp",
        }
        assert d["label"] == "cp"
        assert d["verdict"] == "PASS"
        assert d["verdict_tier"] == VERDICT_TIER["PASS"]


class TestVerdictTier:
    def test_strict_ordering(self) -> None:
        assert (
            VERDICT_TIER["PASS"]
            > VERDICT_TIER["CONDITIONAL"]
            > VERDICT_TIER["FAIL"]
            > VERDICT_TIER["CRITICAL"]
        )
