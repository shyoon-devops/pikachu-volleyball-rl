"""Tests for LeagueAdmissionCallback and the should_admit gate.

The callback extends CheckpointCallback — we mock self.model.save to
avoid an SB3 dependency and drive _on_step directly.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from backend.rl.league_admission import (
    DEFAULT_ADMISSION_ELO_DELTA,
    LeagueAdmissionCallback,
    should_admit,
)


# ─── Helpers ──────────────────────────────────────────────────────────


class _FakeModel:
    def __init__(self) -> None:
        self.saved_paths: list[str] = []

    def save(self, path: str) -> None:
        self.saved_paths.append(str(path))


def _make_cb(
    tmp_path: Path,
    *,
    median: float | None = 1200.0,
    rating: float = 1250.0,
    save_interval: int = 10,
    admission_elo_delta: float = DEFAULT_ADMISSION_ELO_DELTA,
    notify_rejected: bool = False,
) -> tuple[LeagueAdmissionCallback, asyncio.Queue, asyncio.AbstractEventLoop]:
    loop = asyncio.new_event_loop()
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=128)
    cb = LeagueAdmissionCallback(
        experiment_id="e0123456789abc",
        admission_queue=queue,
        loop=loop,
        model_dir=str(tmp_path),
        save_interval=save_interval,
        slug="run",
        provisional_rating_provider=lambda: rating,
        pool_median_provider=lambda: median,
        admission_elo_delta=admission_elo_delta,
        notify_rejected=notify_rejected,
    )
    cb.model = _FakeModel()
    return cb, queue, loop


def _tick(
    cb: LeagueAdmissionCallback, timestep: int
) -> None:
    cb.num_timesteps = timestep
    cb._on_step()


def _drain(
    loop: asyncio.AbstractEventLoop, queue: asyncio.Queue
) -> list[dict[str, Any]]:
    loop.call_soon(loop.stop)
    loop.run_forever()
    items = []
    while True:
        try:
            items.append(queue.get_nowait())
        except asyncio.QueueEmpty:
            break
    return items


# ─── should_admit gate ────────────────────────────────────────────────


class TestShouldAdmit:
    def test_empty_pool_auto_admits(self) -> None:
        # First-ever checkpoint in a fresh pool — must admit regardless
        # of the absolute rating so the pool can seed itself. ADR §5.
        assert should_admit(1000.0, pool_median_rating=None) is True
        assert should_admit(0.0, pool_median_rating=None) is True

    def test_strictly_above_median_plus_delta_admits(self) -> None:
        # Median 1200, delta 25 → gate at 1225. 1226 passes, 1225
        # fails (strict inequality per ADR wording "exceeds by ≥25").
        assert (
            should_admit(1226.0, pool_median_rating=1200.0) is True
        )

    def test_at_exact_threshold_rejects(self) -> None:
        # Exactly median+delta is NOT above → reject. Pins the strict-
        # > semantic so a wall-of-equal-rated checkpoints don't all
        # get admitted simultaneously.
        assert should_admit(1225.0, pool_median_rating=1200.0) is False

    def test_below_median_rejects(self) -> None:
        assert should_admit(1000.0, pool_median_rating=1200.0) is False

    def test_custom_delta(self) -> None:
        # Gate at median + 50. 1245 passes, 1249 fails (< 1250).
        assert should_admit(
            1260.0, pool_median_rating=1200.0, admission_elo_delta=50.0
        ) is True
        assert should_admit(
            1249.0, pool_median_rating=1200.0, admission_elo_delta=50.0
        ) is False


# ─── Callback save cadence ────────────────────────────────────────────


class TestSaveCadence:
    def test_save_only_fires_at_interval(self, tmp_path: Path) -> None:
        cb, _q, loop = _make_cb(tmp_path, save_interval=10)
        # timestep 0 → save (0 % 10 == 0); 5 → skip; 10 → save.
        _tick(cb, 0)
        _tick(cb, 5)
        _tick(cb, 10)
        # 2 save events; the dedup on (num_timesteps == _last_admission_step)
        # prevents the same step from double-firing.
        assert len(cb.model.saved_paths) == 2
        loop.close()

    def test_dedup_on_repeated_same_step(self, tmp_path: Path) -> None:
        cb, _q, loop = _make_cb(tmp_path, save_interval=10)
        _tick(cb, 10)
        _tick(cb, 10)  # duplicate — must NOT save again
        assert len(cb.model.saved_paths) == 1
        loop.close()


# ─── Admission enqueue behavior ───────────────────────────────────────


class TestAdmissionEnqueue:
    def test_admitted_checkpoint_enqueued(self, tmp_path: Path) -> None:
        cb, queue, loop = _make_cb(
            tmp_path,
            median=1200.0,  # gate at 1225
            rating=1250.0,  # well above
        )
        _tick(cb, 100)
        items = _drain(loop, queue)
        assert len(items) == 1
        payload = items[0]
        assert payload["admitted"] is True
        assert payload["step"] == 100
        assert payload["provisional_rating"] == 1250.0
        assert payload["checkpoint_id"] == "run__e0123456__100"
        loop.close()

    def test_rejected_checkpoint_not_enqueued_by_default(
        self, tmp_path: Path
    ) -> None:
        cb, queue, loop = _make_cb(
            tmp_path,
            median=1200.0,
            rating=1210.0,  # below gate (1225)
        )
        _tick(cb, 100)
        items = _drain(loop, queue)
        assert items == []
        # But the file is still saved (admission ≠ file retention).
        assert len(cb.model.saved_paths) == 1
        loop.close()

    def test_rejected_enqueued_when_notify_rejected_true(
        self, tmp_path: Path
    ) -> None:
        cb, queue, loop = _make_cb(
            tmp_path,
            median=1200.0,
            rating=1210.0,  # reject
            notify_rejected=True,
        )
        _tick(cb, 100)
        items = _drain(loop, queue)
        assert len(items) == 1
        assert items[0]["admitted"] is False
        loop.close()

    def test_empty_pool_always_admits(self, tmp_path: Path) -> None:
        cb, queue, loop = _make_cb(
            tmp_path,
            median=None,  # empty pool
            rating=500.0,  # ridiculously low
        )
        _tick(cb, 100)
        items = _drain(loop, queue)
        assert len(items) == 1
        assert items[0]["admitted"] is True
        loop.close()


# ─── Provider fallbacks ───────────────────────────────────────────────


class TestProviderFallbacks:
    def test_missing_rating_provider_defaults_to_1000(
        self, tmp_path: Path
    ) -> None:
        loop = asyncio.new_event_loop()
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=8)
        cb = LeagueAdmissionCallback(
            experiment_id="e0123456789abc",
            admission_queue=queue,
            loop=loop,
            model_dir=str(tmp_path),
            save_interval=10,
            slug="run",
            provisional_rating_provider=None,  # missing
            pool_median_provider=lambda: 500.0,
        )
        cb.model = _FakeModel()
        _tick(cb, 10)
        items = _drain(loop, queue)
        assert len(items) == 1
        # Default rating 1000 > pool median 500 + 25 → admit.
        assert items[0]["admitted"] is True
        assert items[0]["provisional_rating"] == 1000.0
        loop.close()

    def test_missing_pool_median_provider_auto_admits(
        self, tmp_path: Path
    ) -> None:
        loop = asyncio.new_event_loop()
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=8)
        cb = LeagueAdmissionCallback(
            experiment_id="e0123456789abc",
            admission_queue=queue,
            loop=loop,
            model_dir=str(tmp_path),
            save_interval=10,
            slug="run",
            provisional_rating_provider=lambda: 500.0,  # low rating
            pool_median_provider=None,
        )
        cb.model = _FakeModel()
        _tick(cb, 10)
        items = _drain(loop, queue)
        # None pool → auto admit regardless of rating.
        assert items[0]["admitted"] is True
        loop.close()


# ─── File retention on reject ─────────────────────────────────────────


class TestFileRetentionOnReject:
    def test_rejected_save_still_writes_file(
        self, tmp_path: Path
    ) -> None:
        # ADR requirement: rejected checkpoints stay on disk for post-
        # hoc inspection. Only the manifest entry is skipped.
        cb, _q, loop = _make_cb(
            tmp_path,
            median=1200.0,
            rating=1000.0,  # rejected
        )
        _tick(cb, 10)
        assert len(cb.model.saved_paths) == 1
        loop.close()
