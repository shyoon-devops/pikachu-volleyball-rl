"""Tests for the evaluation report module."""

from __future__ import annotations

from backend.rl.eval_report import (
    EvalRecord,
    extract_checkpoint,
    overall_verdict,
    verdict,
)


class TestVerdict:
    """Per-level verdict logic."""

    def test_l1_pass(self) -> None:
        assert verdict(1, 0.95) == "PASS"

    def test_l1_critical(self) -> None:
        assert verdict(1, 0.30) == "CRITICAL"

    def test_l1_fail_at_boundary(self) -> None:
        assert verdict(1, 0.89) == "FAIL"

    def test_l2_pass(self) -> None:
        assert verdict(2, 0.80) == "PASS"

    def test_l2_critical_below_50(self) -> None:
        assert verdict(2, 0.40) == "CRITICAL"

    def test_l3_pass(self) -> None:
        assert verdict(3, 0.55) == "PASS"

    def test_l4_fail(self) -> None:
        assert verdict(4, 0.10) == "FAIL"

    def test_l5_pass(self) -> None:
        assert verdict(5, 0.15) == "PASS"

    def test_l5_fail(self) -> None:
        assert verdict(5, 0.05) == "FAIL"


class TestOverallVerdict:
    """Overall model verdict from multiple level results."""

    def _record(self, level: int, win_rate: float) -> EvalRecord:
        return EvalRecord(
            env="test",
            model_path="test/100000",
            bot_level=level,
            n_games=20,
            win_rate=win_rate,
            avg_score=10.0,
            avg_rally_length=100.0,
            timestamp="2026-01-01",
        )

    def test_all_pass(self) -> None:
        records = [
            self._record(1, 0.95),
            self._record(2, 0.80),
            self._record(3, 0.55),
            self._record(4, 0.30),
            self._record(5, 0.15),
        ]
        assert overall_verdict(records) == "PASS"

    def test_l4_l5_fail_is_conditional(self) -> None:
        records = [
            self._record(1, 0.95),
            self._record(2, 0.80),
            self._record(3, 0.55),
            self._record(4, 0.10),
            self._record(5, 0.05),
        ]
        assert overall_verdict(records) == "CONDITIONAL"

    def test_l1_critical(self) -> None:
        records = [self._record(1, 0.20)]
        assert overall_verdict(records) == "CRITICAL"

    def test_l2_fail_blocks(self) -> None:
        records = [
            self._record(1, 0.95),
            self._record(2, 0.40),
        ]
        assert overall_verdict(records) == "CRITICAL"

    def test_no_data(self) -> None:
        assert overall_verdict([]) == "NO DATA"


class TestExtractCheckpoint:
    """Checkpoint extraction from model paths."""

    def test_with_zip(self) -> None:
        assert extract_checkpoint("/app/models/abc123/140000.zip") == "140000"

    def test_without_zip(self) -> None:
        assert extract_checkpoint("/app/models/abc123/140000") == "140000"

    def test_final(self) -> None:
        assert extract_checkpoint("models/exp/final.zip") == "final"
