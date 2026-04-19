"""Checkpoint admission callback for the self-play league.

Extends the existing ``CheckpointCallback`` so every successful save
also evaluates whether the new checkpoint should be admitted to the
league pool. A checkpoint is admitted iff its provisional rating
exceeds ``pool_median + admission_elo_delta`` (default +25 Elo) per
ADR §1 "Opponent pool → admission gate". Rejected checkpoints are
*not* deleted — the file stays on disk for post-hoc inspection, it's
just not registered in the manifest.

The actual manifest write / rating evaluation is BE-owned; this
callback publishes "admission request" records onto a queue and lets
the BE's pool service apply the final decision. The callback does
apply the gate locally using a pure helper (:func:`should_admit`) so
rejects don't even hit the queue — saves write bandwidth when
training produces many low-rated checkpoints in a row.

See docs/adr/0014-self-play-league.md §1 + §5 (champion rules).
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Callable

from backend.rl.callbacks import CheckpointCallback, _safe_enqueue

logger = logging.getLogger(__name__)

# Default gate: new checkpoints must beat the pool median by at least
# this many Elo points to be registered. Low enough that a genuinely
# improving run still admits every few saves, high enough that
# noise-level regressions don't pollute the pool. ADR §1.
DEFAULT_ADMISSION_ELO_DELTA: float = 25.0


def should_admit(
    provisional_rating: float,
    pool_median_rating: float | None,
    *,
    admission_elo_delta: float = DEFAULT_ADMISSION_ELO_DELTA,
) -> bool:
    """Return True iff the checkpoint's provisional rating passes the gate.

    Pure function so the gate is unit-testable without the SB3 machinery.

    Empty pool (``pool_median_rating is None``) auto-admits — the
    first few checkpoints of a fresh run need to seed the pool
    regardless of their absolute rating. ADR §5 allows bot-ladder
    anchors to be present but the league pool itself starts empty.
    """
    if pool_median_rating is None:
        return True
    return float(provisional_rating) > (
        float(pool_median_rating) + float(admission_elo_delta)
    )


class LeagueAdmissionCallback(CheckpointCallback):
    """CheckpointCallback + post-save admission gate.

    Extends CheckpointCallback so save cadence is unchanged and the
    file layout on disk is identical to v1.0.0 — callers that don't
    set up a league queue still see the legacy save behavior.

    Parameters beyond CheckpointCallback:
    - ``admission_queue``: target queue for admission requests. A
      successful gate → one enqueue per save. Shape:
      ``{"checkpoint_id", "path", "step", "provisional_rating",
      "admitted": True}``.
    - ``loop``: event loop the queue is bound to (marshals the
      enqueue via ``call_soon_threadsafe`` like MetricsCallback).
    - ``provisional_rating_provider``: callable returning the
      current agent's provisional rating (float). Usually wired to
      the rating store's ``get_my_rating()``.
    - ``pool_median_provider``: callable returning the current pool
      median rating (float | None). None when the pool is empty.
    - ``admission_elo_delta``: gate delta; default 25.
    - ``notify_rejected``: when True, also enqueues rejected
      checkpoints (with ``admitted: False``) so the dashboard can
      show "this save didn't make the cut". Default False.
    """

    def __init__(
        self,
        experiment_id: str,
        admission_queue: asyncio.Queue[dict[str, Any]],
        loop: asyncio.AbstractEventLoop,
        *,
        model_dir: str = "models",
        save_interval: int = 10000,
        verbose: int = 0,
        slug: str = "run",
        provisional_rating_provider: Callable[[], float] | None = None,
        pool_median_provider: Callable[[], float | None] | None = None,
        admission_elo_delta: float = DEFAULT_ADMISSION_ELO_DELTA,
        notify_rejected: bool = False,
    ) -> None:
        super().__init__(
            experiment_id=experiment_id,
            model_dir=model_dir,
            save_interval=save_interval,
            verbose=verbose,
            slug=slug,
        )
        self.admission_queue = admission_queue
        self.loop = loop
        self.provisional_rating_provider = provisional_rating_provider
        self.pool_median_provider = pool_median_provider
        self.admission_elo_delta = float(admission_elo_delta)
        self.notify_rejected = bool(notify_rejected)
        self._last_admission_step: int = -1

    # ------------------------------------------------------------------
    # SB3 hook
    # ------------------------------------------------------------------
    def _on_step(self) -> bool:
        if self.num_timesteps % self.save_interval != 0:
            return True
        # Guard against double-fires on the same timestep (happens with
        # n_envs > 1 when the VecEnv steps arrive at the same aggregated
        # timestep count).
        if self.num_timesteps == self._last_admission_step:
            return True
        self._last_admission_step = self.num_timesteps

        name = f"{self.slug}__{self._exp8}__{self.num_timesteps}"
        path = self._checkpoint_dir / name
        self.model.save(str(path))

        provisional_rating = self._read_provisional_rating()
        pool_median = self._read_pool_median()
        admitted = should_admit(
            provisional_rating=provisional_rating,
            pool_median_rating=pool_median,
            admission_elo_delta=self.admission_elo_delta,
        )
        if admitted or self.notify_rejected:
            self._enqueue_admission(
                checkpoint_id=name,
                path=path,
                step=self.num_timesteps,
                provisional_rating=provisional_rating,
                admitted=admitted,
            )
        return True

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _read_provisional_rating(self) -> float:
        if self.provisional_rating_provider is None:
            # No rating signal wired in: default to 1000 so the
            # admission gate falls back to the seed value. Combined
            # with an empty pool this still auto-admits via
            # ``should_admit``; against a populated pool this causes
            # rejections, which is the correct conservative default.
            return 1000.0
        try:
            return float(self.provisional_rating_provider())
        except Exception as exc:  # pragma: no cover — defensive
            logger.warning(
                "provisional_rating_provider raised %s; "
                "falling back to 1000.0",
                exc,
            )
            return 1000.0

    def _read_pool_median(self) -> float | None:
        if self.pool_median_provider is None:
            return None
        try:
            return self.pool_median_provider()
        except Exception as exc:  # pragma: no cover — defensive
            logger.warning(
                "pool_median_provider raised %s; treating as empty pool",
                exc,
            )
            return None

    def _enqueue_admission(
        self,
        *,
        checkpoint_id: str,
        path: Path,
        step: int,
        provisional_rating: float,
        admitted: bool,
    ) -> None:
        payload = {
            "checkpoint_id": checkpoint_id,
            "path": str(path),
            "step": int(step),
            "provisional_rating": float(provisional_rating),
            "admitted": bool(admitted),
        }
        _safe_enqueue(self.loop, self.admission_queue, payload)
