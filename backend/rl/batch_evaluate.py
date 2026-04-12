"""Batch evaluation — run several checkpoints across all bot levels in parallel.

Usage (CLI):
    python -m backend.rl.batch_evaluate models/ --n-games 50 --workers 4
    python -m backend.rl.batch_evaluate ckpt1.zip ckpt2.zip --levels 1 3 5

Design notes:
    * Each (checkpoint, level) pair is an independent evaluation task.
    * A ProcessPoolExecutor runs tasks in parallel so the GIL does not
      serialize SB3 inference on top of pure Python game logic.
    * Workers default to `min(cpu_count, n_tasks)` — the game engine is
      CPU-bound, so over-subscription slows things down.
    * Failures are captured as BatchFailure rather than killing the run.
"""

from __future__ import annotations

import argparse
import logging
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from backend.rl.evaluator import EvalResult, ModelEvaluator

logger = logging.getLogger(__name__)

ALL_LEVELS: tuple[int, ...] = (1, 2, 3, 4, 5)
DEFAULT_N_GAMES: int = 50


@dataclass(frozen=True)
class BatchTask:
    """A single (checkpoint, bot_level) evaluation unit."""

    model_path: str
    bot_level: int
    n_games: int


@dataclass(frozen=True)
class BatchFailure:
    """Structured failure record when a task throws."""

    model_path: str
    bot_level: int
    error: str


@dataclass
class BatchReport:
    """Aggregated result of a batch run."""

    results: list[EvalResult] = field(default_factory=list)
    failures: list[BatchFailure] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures

    def by_checkpoint(self) -> dict[str, list[EvalResult]]:
        """Group results by model_path — useful for producing series."""
        grouped: dict[str, list[EvalResult]] = {}
        for r in self.results:
            grouped.setdefault(r.model_path, []).append(r)
        for k in grouped:
            grouped[k].sort(key=lambda x: x.bot_level)
        return grouped


def discover_checkpoints(paths: list[str]) -> list[str]:
    """Expand directories → .zip files; pass through individual files.

    Accepts .zip files directly, or directories (recursively searched
    for *.zip). Returns a sorted, de-duplicated list of absolute paths.
    """
    found: set[str] = set()
    for raw in paths:
        p = Path(raw)
        if not p.exists():
            logger.warning("Checkpoint path does not exist: %s", raw)
            continue
        if p.is_file() and p.suffix == ".zip":
            found.add(str(p.resolve()))
        elif p.is_dir():
            for zipped in p.rglob("*.zip"):
                found.add(str(zipped.resolve()))
        else:
            logger.warning("Skipping non-checkpoint path: %s", raw)
    return sorted(found)


def _evaluate_single(task: BatchTask) -> EvalResult | BatchFailure:
    """Worker entrypoint — runs one evaluation in a child process."""
    try:
        evaluator = ModelEvaluator()
        # SB3 loads the .zip regardless of suffix, but ModelEvaluator
        # is happy with either, so pass through.
        return evaluator.evaluate(
            task.model_path, bot_level=task.bot_level, n_games=task.n_games
        )
    except Exception as exc:  # noqa: BLE001 — structured reporting, not swallowing
        return BatchFailure(
            model_path=task.model_path,
            bot_level=task.bot_level,
            error=f"{type(exc).__name__}: {exc}",
        )


def _resolve_worker_count(requested: int | None, n_tasks: int) -> int:
    if n_tasks == 0:
        return 1
    cap = max(1, os.cpu_count() or 1)
    if requested is None or requested <= 0:
        return min(cap, n_tasks)
    return min(requested, cap, n_tasks)


def run_batch(
    checkpoints: list[str],
    *,
    levels: list[int] | tuple[int, ...] = ALL_LEVELS,
    n_games: int = DEFAULT_N_GAMES,
    workers: int | None = None,
    executor_factory=None,
) -> BatchReport:
    """Run all (checkpoint, level) tasks in parallel and collect results.

    `executor_factory` is injectable so tests can use a synchronous or
    thread-based executor instead of spawning processes. When None
    (the default), the module-level ProcessPoolExecutor is resolved at
    call time so monkeypatching works.
    """
    if executor_factory is None:
        executor_factory = ProcessPoolExecutor
    if not checkpoints:
        return BatchReport()

    if not levels:
        raise ValueError("levels must contain at least one bot level")

    invalid = [lvl for lvl in levels if lvl not in ALL_LEVELS]
    if invalid:
        raise ValueError(f"Invalid bot levels {invalid}; expected subset of {ALL_LEVELS}")

    tasks = [
        BatchTask(model_path=cp, bot_level=lvl, n_games=n_games)
        for cp in checkpoints
        for lvl in levels
    ]
    n_workers = _resolve_worker_count(workers, len(tasks))

    report = BatchReport()
    with executor_factory(max_workers=n_workers) as pool:
        futures = {pool.submit(_evaluate_single, t): t for t in tasks}
        for fut in as_completed(futures):
            outcome = fut.result()
            if isinstance(outcome, BatchFailure):
                report.failures.append(outcome)
                logger.warning(
                    "Evaluation failed: %s L%d: %s",
                    outcome.model_path,
                    outcome.bot_level,
                    outcome.error,
                )
            else:
                report.results.append(outcome)

    # Stable ordering for callers
    report.results.sort(key=lambda r: (r.model_path, r.bot_level))
    report.failures.sort(key=lambda f: (f.model_path, f.bot_level))
    return report


def format_batch_summary(report: BatchReport) -> str:
    """Human-readable summary string for the CLI."""
    lines: list[str] = [
        f"Checkpoints: {len(report.by_checkpoint())}",
        f"Successful evaluations: {len(report.results)}",
        f"Failures: {len(report.failures)}",
    ]
    for cp, results in report.by_checkpoint().items():
        lines.append(f"\n  {cp}")
        for r in results:
            lines.append(
                f"    L{r.bot_level}: win={r.win_rate:.2%} "
                f"score={r.avg_score:.1f} dominance={r.dominance_score:.3f}"
            )
    for f in report.failures:
        lines.append(f"\n  FAIL {f.model_path} L{f.bot_level}: {f.error}")
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Parallel evaluation of RL checkpoints against bot levels"
    )
    parser.add_argument(
        "paths",
        nargs="+",
        help="Checkpoint .zip files or directories containing them",
    )
    parser.add_argument(
        "--levels",
        type=int,
        nargs="+",
        default=list(ALL_LEVELS),
        choices=list(ALL_LEVELS),
        help="Bot levels to evaluate against (default: 1-5)",
    )
    parser.add_argument(
        "--n-games",
        type=int,
        default=DEFAULT_N_GAMES,
        help=f"Games per (checkpoint, level) (default: {DEFAULT_N_GAMES})",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Parallel workers (default: min(cpu_count, n_tasks))",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = build_arg_parser().parse_args(argv)

    checkpoints = discover_checkpoints(args.paths)
    if not checkpoints:
        logger.error("No checkpoints discovered under: %s", args.paths)
        return 1

    logger.info(
        "Evaluating %d checkpoints against levels %s (n_games=%d)",
        len(checkpoints),
        args.levels,
        args.n_games,
    )
    report = run_batch(
        checkpoints,
        levels=args.levels,
        n_games=args.n_games,
        workers=args.workers,
    )
    print(format_batch_summary(report))
    return 0 if report.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ALL_LEVELS",
    "DEFAULT_N_GAMES",
    "BatchTask",
    "BatchFailure",
    "BatchReport",
    "discover_checkpoints",
    "run_batch",
    "format_batch_summary",
    "build_arg_parser",
    "main",
]
