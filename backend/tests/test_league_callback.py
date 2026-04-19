"""Tests for LeagueCallback — the VecEnv-side match aggregator.

SB3 is never actually called here: we stub the parts we need
(`self.locals["infos"]`) and call `_on_step` directly.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from backend.game.constants import MAX_SCORE
from backend.rl.league_callback import LeagueCallback, winner_from_scores


def _make_callback(
    broadcast_interval: int = 64,
    recent_buffer_size: int = 64,
) -> tuple[LeagueCallback, asyncio.AbstractEventLoop, asyncio.Queue]:
    """Build a LeagueCallback with a fresh event loop + queue."""
    loop = asyncio.new_event_loop()
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=128)
    cb = LeagueCallback(
        broadcast_queue=queue,
        loop=loop,
        broadcast_interval=broadcast_interval,
        recent_buffer_size=recent_buffer_size,
    )
    # Minimal SB3 locals shim — we only need `infos`.
    cb.locals = {"infos": []}
    return cb, loop, queue


def _drain(loop: asyncio.AbstractEventLoop, queue: asyncio.Queue) -> list[Any]:
    # _safe_enqueue marshals onto the loop via call_soon_threadsafe;
    # run the loop once so the queued callbacks execute.
    # Run pending callbacks without blocking.
    loop.call_soon(loop.stop)
    loop.run_forever()
    items = []
    while True:
        try:
            items.append(queue.get_nowait())
        except asyncio.QueueEmpty:
            break
    return items


# ─── winner_from_scores helper ────────────────────────────────────────


class TestWinnerFromScores:
    def test_p1_higher_returns_1(self) -> None:
        assert winner_from_scores(15, 9) == 1

    def test_p2_higher_returns_2(self) -> None:
        assert winner_from_scores(7, 15) == 2

    def test_equal_returns_2_by_tiebreak(self) -> None:
        # Contract: strict > for p1; equal falls to p2. Should never
        # happen in practice (requires both at MAX_SCORE) but we pin
        # the tiebreak so a caller can rely on it.
        assert winner_from_scores(15, 15) == 2


# ─── _info_reports_completion ─────────────────────────────────────────


class TestCompletionDetection:
    def _f(self, info: dict[str, Any]) -> bool:
        return LeagueCallback._info_reports_completion(info)

    def test_below_max_is_incomplete(self) -> None:
        assert not self._f({"score1": 5, "score2": 3})

    def test_p1_at_max_is_complete(self) -> None:
        assert self._f({"score1": MAX_SCORE, "score2": 9})

    def test_p2_at_max_is_complete(self) -> None:
        assert self._f({"score1": 11, "score2": MAX_SCORE})

    def test_missing_scores_is_incomplete(self) -> None:
        # Truncated env with no score info attached — must NOT count.
        assert not self._f({"frame": 3000})
        assert not self._f({})


# ─── Counting + dedup ─────────────────────────────────────────────────


class TestMatchCounting:
    def test_single_env_single_match_counts_once(self) -> None:
        cb, loop, _ = _make_callback()
        cb.locals["infos"] = [{"score1": MAX_SCORE, "score2": 7}]
        cb._on_step()
        assert cb._total_matches == 1
        # Same info reported again on the auto-reset step — must NOT
        # re-count the same match.
        cb._on_step()
        assert cb._total_matches == 1
        loop.close()

    def test_changed_score_counts_new_match(self) -> None:
        cb, loop, _ = _make_callback()
        cb.locals["infos"] = [{"score1": MAX_SCORE, "score2": 7}]
        cb._on_step()
        cb.locals["infos"] = [{"score1": 9, "score2": MAX_SCORE}]
        cb._on_step()
        assert cb._total_matches == 2
        loop.close()

    def test_multi_env_each_counted(self) -> None:
        cb, loop, _ = _make_callback()
        cb.locals["infos"] = [
            {"score1": MAX_SCORE, "score2": 7},
            {"score1": 5, "score2": MAX_SCORE},
            {"score1": 3, "score2": 1},  # incomplete
        ]
        cb._on_step()
        assert cb._total_matches == 2
        loop.close()

    def test_same_scores_in_different_slots_both_count(self) -> None:
        # Per-slot dedup keeps on (env_i, scores) tuples, so identical
        # scores in different env slots must still count as distinct
        # matches.
        cb, loop, _ = _make_callback()
        cb.locals["infos"] = [
            {"score1": MAX_SCORE, "score2": 10},
            {"score1": MAX_SCORE, "score2": 10},
        ]
        cb._on_step()
        assert cb._total_matches == 2
        loop.close()


# ─── Broadcast cadence + recent buffer ────────────────────────────────


class TestBroadcastCadence:
    def test_broadcast_at_interval(self) -> None:
        cb, loop, queue = _make_callback(broadcast_interval=4)
        # Feed 3 completed matches — no broadcast yet.
        for i in range(3):
            cb.locals["infos"] = [
                {"score1": MAX_SCORE, "score2": i}
            ]
            cb._on_step()
        assert cb._since_last_broadcast == 3
        # 4th completion triggers broadcast.
        cb.locals["infos"] = [{"score1": MAX_SCORE, "score2": 3}]
        cb._on_step()
        items = _drain(loop, queue)
        assert len(items) == 1
        payload = items[0]
        assert payload["total_matches"] == 4
        assert payload["since_last_broadcast"] == 4
        assert len(payload["recent"]) == 4
        # Counter resets after flush.
        assert cb._since_last_broadcast == 0
        loop.close()

    def test_recent_buffer_bounded(self) -> None:
        cb, loop, queue = _make_callback(
            broadcast_interval=1000,  # never broadcast
            recent_buffer_size=3,
        )
        for i in range(10):
            cb.locals["infos"] = [{"score1": MAX_SCORE, "score2": i}]
            cb._on_step()
        assert len(cb._recent) == 3
        # Must be the LAST 3, not the first 3.
        assert [r["score2"] for r in cb._recent] == [7, 8, 9]
        loop.close()


# ─── SB3 `step` contract ──────────────────────────────────────────────


class TestStepContract:
    def test_on_step_returns_true(self) -> None:
        # BaseCallback._on_step convention: False aborts training.
        cb, loop, _ = _make_callback()
        cb.locals["infos"] = []
        assert cb._on_step() is True
        loop.close()

    def test_no_infos_is_noop(self) -> None:
        cb, loop, _ = _make_callback()
        cb.locals["infos"] = []
        cb._on_step()
        assert cb._total_matches == 0
        loop.close()

    def test_missing_infos_key_is_tolerated(self) -> None:
        # SB3 convention sets "infos" — but a bare-bones test harness
        # (or a mocked caller) might not. Gracefully no-op.
        cb, loop, _ = _make_callback()
        cb.locals = {}
        # Uses the ``locals.get("infos", [])`` default branch.
        assert cb._on_step() is True
        loop.close()
