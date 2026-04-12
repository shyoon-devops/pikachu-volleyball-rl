"""Tests for the batch evaluation runner."""

from __future__ import annotations

from concurrent.futures import Future
from pathlib import Path

import pytest

from backend.rl import batch_evaluate
from backend.rl.batch_evaluate import (
    BatchFailure,
    BatchReport,
    BatchTask,
    discover_checkpoints,
    format_batch_summary,
    run_batch,
)
from backend.rl.evaluator import EvalResult


class _SyncExecutor:
    """Synchronous stand-in for ProcessPoolExecutor — runs tasks in-thread."""

    def __init__(self, max_workers: int = 1) -> None:
        self.max_workers = max_workers
        self.submitted_workers = max_workers

    def __enter__(self) -> "_SyncExecutor":
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def submit(self, fn, *args, **kwargs):  # type: ignore[no-untyped-def]
        fut: Future = Future()
        try:
            fut.set_result(fn(*args, **kwargs))
        except Exception as e:  # pragma: no cover — surfaced via Future
            fut.set_exception(e)
        return fut


def _fake_eval_result(task: BatchTask) -> EvalResult:
    return EvalResult(
        model_path=task.model_path,
        bot_level=task.bot_level,
        n_games=task.n_games,
        win_rate=0.5 + task.bot_level * 0.01,
        avg_score=10.0,
        avg_opponent_score=5.0,
        avg_rally_length=80.0,
        avg_episode_length=4000.0,
        timestamp="2026-04-12T00:00:00+00:00",
        dominance_score=0.5,
    )


@pytest.fixture(autouse=True)
def _fake_evaluate(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace _evaluate_single with a fast, deterministic fake."""
    monkeypatch.setattr(batch_evaluate, "_evaluate_single", _fake_eval_result)


class TestDiscoverCheckpoints:
    def test_expands_directory_to_zips(self, tmp_path: Path) -> None:
        (tmp_path / "a.zip").write_text("x")
        (tmp_path / "b.zip").write_text("x")
        (tmp_path / "readme.txt").write_text("not a model")
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "c.zip").write_text("x")

        found = discover_checkpoints([str(tmp_path)])
        assert len(found) == 3
        assert all(p.endswith(".zip") for p in found)

    def test_accepts_individual_zip_files(self, tmp_path: Path) -> None:
        f = tmp_path / "model.zip"
        f.write_text("x")
        found = discover_checkpoints([str(f)])
        assert found == [str(f.resolve())]

    def test_skips_nonexistent_paths(self, tmp_path: Path) -> None:
        missing = str(tmp_path / "does-not-exist")
        assert discover_checkpoints([missing]) == []

    def test_skips_non_zip_files(self, tmp_path: Path) -> None:
        f = tmp_path / "notes.txt"
        f.write_text("x")
        assert discover_checkpoints([str(f)]) == []

    def test_deduplicates_across_inputs(self, tmp_path: Path) -> None:
        f = tmp_path / "m.zip"
        f.write_text("x")
        found = discover_checkpoints([str(f), str(tmp_path)])
        assert len(found) == 1


class TestRunBatch:
    def test_empty_input_returns_empty_report(self) -> None:
        report = run_batch([], executor_factory=_SyncExecutor)
        assert report.results == []
        assert report.failures == []
        assert report.ok is True

    def test_runs_cross_product_of_levels_and_checkpoints(self) -> None:
        checkpoints = ["/a.zip", "/b.zip"]
        report = run_batch(
            checkpoints, levels=[1, 3, 5], n_games=10, executor_factory=_SyncExecutor
        )
        assert len(report.results) == 2 * 3
        assert len(report.failures) == 0
        # Each checkpoint has all 3 evaluated levels
        grouped = report.by_checkpoint()
        assert set(grouped.keys()) == set(checkpoints)
        for results in grouped.values():
            assert [r.bot_level for r in results] == [1, 3, 5]

    def test_results_are_sorted(self) -> None:
        report = run_batch(
            ["/z.zip", "/a.zip"],
            levels=[2, 1],
            n_games=5,
            executor_factory=_SyncExecutor,
        )
        paths = [r.model_path for r in report.results]
        assert paths == sorted(paths)

    def test_invalid_level_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid bot levels"):
            run_batch(["/a.zip"], levels=[7], executor_factory=_SyncExecutor)

    def test_empty_levels_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            run_batch(["/a.zip"], levels=[], executor_factory=_SyncExecutor)

    def test_captures_failures_without_stopping(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def flaky(task: BatchTask) -> EvalResult | BatchFailure:
            if task.bot_level == 3:
                return BatchFailure(
                    model_path=task.model_path,
                    bot_level=task.bot_level,
                    error="boom",
                )
            return _fake_eval_result(task)

        monkeypatch.setattr(batch_evaluate, "_evaluate_single", flaky)

        report = run_batch(
            ["/a.zip", "/b.zip"],
            levels=[1, 3],
            n_games=5,
            executor_factory=_SyncExecutor,
        )
        assert len(report.results) == 2  # L1 for each checkpoint
        assert len(report.failures) == 2  # L3 for each checkpoint
        assert report.ok is False
        assert all(f.error == "boom" for f in report.failures)


class TestResolveWorkerCount:
    def test_none_workers_uses_min_cpu_and_tasks(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(batch_evaluate.os, "cpu_count", lambda: 8)
        assert batch_evaluate._resolve_worker_count(None, 3) == 3
        assert batch_evaluate._resolve_worker_count(None, 100) == 8

    def test_zero_workers_treated_as_auto(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(batch_evaluate.os, "cpu_count", lambda: 4)
        assert batch_evaluate._resolve_worker_count(0, 10) == 4

    def test_explicit_worker_capped_by_cpu(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(batch_evaluate.os, "cpu_count", lambda: 2)
        assert batch_evaluate._resolve_worker_count(16, 10) == 2

    def test_zero_tasks_returns_one(self) -> None:
        assert batch_evaluate._resolve_worker_count(None, 0) == 1


class TestFormatBatchSummary:
    def test_includes_success_and_failure_counts(self) -> None:
        report = BatchReport(
            results=[_fake_eval_result(BatchTask("/m.zip", 1, 5))],
            failures=[BatchFailure(model_path="/m.zip", bot_level=3, error="boom")],
        )
        text = format_batch_summary(report)
        assert "Successful evaluations: 1" in text
        assert "Failures: 1" in text
        assert "boom" in text
        assert "/m.zip" in text


class TestMainCLI:
    def test_main_returns_zero_on_success(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # The CLI path uses ProcessPoolExecutor by default; swap in the
        # synchronous stand-in so fake evaluator patches apply.
        monkeypatch.setattr(batch_evaluate, "ProcessPoolExecutor", _SyncExecutor)
        zipf = tmp_path / "m.zip"
        zipf.write_text("x")
        code = batch_evaluate.main(
            [str(zipf), "--levels", "1", "--n-games", "2", "--workers", "1"]
        )
        assert code == 0
        out = capsys.readouterr().out
        assert "Successful evaluations: 1" in out

    def test_main_returns_nonzero_on_missing_checkpoints(
        self, tmp_path: Path
    ) -> None:
        missing = str(tmp_path / "nope")
        code = batch_evaluate.main([missing])
        assert code == 1
