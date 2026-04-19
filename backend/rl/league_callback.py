"""SB3 callback that drives the self-play league aggregation layer.

Rating updates against individual opponents are already performed by
:meth:`OpponentProvider.on_match_end` inside the env's step — it runs
per-env, per-match and is the single write path. This callback sits on
top of the training VecEnv and handles the *aggregate* side:

1. Counts completed matches across all VecEnv workers.
2. Every ``BROADCAST_INTERVAL`` matches, enqueues a broadcast-request
   record so the FE dashboard can refresh the league standings tab.
3. Buffers per-match outcome summaries so a dashboard poller can read
   a consistent head-to-head snapshot without racing the env.

The BE owns the actual WS broadcast (``training:league_update``) — this
callback is queue-producer-only, matching the MetricsCallback pattern
already shipped at backend/rl/callbacks.py:75. See
docs/adr/0014-self-play-league.md §4 for the ops contract.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from stable_baselines3.common.callbacks import BaseCallback

from backend.game.constants import MAX_SCORE
from backend.rl.callbacks import _safe_enqueue

logger = logging.getLogger(__name__)


class LeagueCallback(BaseCallback):
    """Aggregates league match outcomes across the training VecEnv.

    Reads ``infos[i]`` from each SB3 rollout step and marks a match
    complete when ``infos[i]["score1"] >= MAX_SCORE`` or
    ``infos[i]["score2"] >= MAX_SCORE`` — the same signal the env uses
    for its terminated flag. (We key off scores rather than the
    ``monitor.r`` episode key so that truncated-but-full matches are
    correctly excluded: truncation fires ``episode`` too, but scores
    stay below MAX_SCORE.)

    ``broadcast_queue`` is the WS-side queue the BE's broadcast loop
    drains. A single-element record is enqueued every
    ``broadcast_interval`` completed matches:

        {"total_matches": int, "since_last_broadcast": int,
         "recent": [{"winner": 1, "score1": 15, "score2": 9}, ...]}

    Enqueue uses the :func:`_safe_enqueue` helper from callbacks.py so
    event-loop closure (client disconnected, server shutting down)
    can't wedge the training thread. Recent-match buffer is capped at
    ``recent_buffer_size`` (default 64) to match the broadcast cadence
    — one broadcast window of history at a time.
    """

    # Broadcast cadence matches ADR §4 ("LEAGUE_BROADCAST_INTERVAL = 64").
    BROADCAST_INTERVAL: int = 64

    def __init__(
        self,
        broadcast_queue: asyncio.Queue[dict[str, Any]],
        loop: asyncio.AbstractEventLoop,
        *,
        broadcast_interval: int | None = None,
        recent_buffer_size: int = 64,
        verbose: int = 0,
    ) -> None:
        super().__init__(verbose)
        self.broadcast_queue = broadcast_queue
        self.loop = loop
        self.broadcast_interval = (
            broadcast_interval
            if broadcast_interval is not None
            else self.BROADCAST_INTERVAL
        )
        self.recent_buffer_size = int(recent_buffer_size)
        self._total_matches: int = 0
        self._since_last_broadcast: int = 0
        self._recent: list[dict[str, Any]] = []
        # Tracks the (score1, score2) we last saw per env slot so we
        # only count a given completion once — infos repeat across
        # steps until the env auto-resets.
        self._last_terminal_key: dict[int, tuple[int, int]] = {}

    # ------------------------------------------------------------------
    # SB3 hook
    # ------------------------------------------------------------------
    def _on_step(self) -> bool:
        infos = self.locals.get("infos", [])
        for i, info in enumerate(infos):
            if not self._info_reports_completion(info):
                continue
            key = (int(info.get("score1", 0)), int(info.get("score2", 0)))
            # Skip repeated reports of the same terminal info (SB3
            # forwards the last info on the auto-reset step).
            if self._last_terminal_key.get(i) == key:
                continue
            self._last_terminal_key[i] = key
            self._record_match(winner_from_scores(*key), key[0], key[1])
        return True

    # ------------------------------------------------------------------
    # Internal helpers (pure-ish — no IO except through the queue)
    # ------------------------------------------------------------------
    @staticmethod
    def _info_reports_completion(info: dict[str, Any]) -> bool:
        """True iff ``info`` describes a terminated (won) match.

        Key on score rather than ``episode`` so truncation-induced
        auto-resets (stalled rallies, max_steps) don't masquerade as
        completed matches for league ranking purposes.
        """
        s1 = info.get("score1")
        s2 = info.get("score2")
        if s1 is None or s2 is None:
            return False
        return int(s1) >= MAX_SCORE or int(s2) >= MAX_SCORE

    def _record_match(self, winner: int, score1: int, score2: int) -> None:
        self._total_matches += 1
        self._since_last_broadcast += 1
        self._recent.append(
            {"winner": winner, "score1": score1, "score2": score2}
        )
        if len(self._recent) > self.recent_buffer_size:
            # Drop-oldest — keeps the buffer bounded at one broadcast
            # window. Older matches are already consumed via the WS
            # results_push_loop (BE-A2); we keep them here only for
            # the standings-snapshot broadcast below.
            self._recent = self._recent[-self.recent_buffer_size:]
        if self._since_last_broadcast >= self.broadcast_interval:
            self._flush_broadcast()

    def _flush_broadcast(self) -> None:
        payload = {
            "total_matches": self._total_matches,
            "since_last_broadcast": self._since_last_broadcast,
            "recent": list(self._recent),
        }
        _safe_enqueue(self.loop, self.broadcast_queue, payload)
        self._since_last_broadcast = 0


def winner_from_scores(score1: int, score2: int) -> int:
    """Returns 1 if player 1 wins, 2 if player 2 wins.

    Tie-breaker: player with the strictly higher score wins. Ties
    (both below MAX_SCORE) should never reach here — the caller
    filters via :meth:`LeagueCallback._info_reports_completion` which
    requires one side to have reached MAX_SCORE. Kept as a module-
    level pure function so tests can exercise the winner logic without
    instantiating the SB3 callback machinery.
    """
    return 1 if score1 > score2 else 2
