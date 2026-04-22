"""Training title helpers — random generation, slug, and collision checks.

Per the 2026-04-18 UX spec (docs/DESIGN-TRAINING-TITLE.md, modified to
make title optional the same day): every training run carries a human-
readable ``title`` alongside its UUID ``experiment_id``. The backend:

  * auto-generates a memorable title when the client sends an empty /
    whitespace-only / missing one (``run-{adj}-{noun}-{4hex}``),
  * rejects duplicates via the ``training_runs`` collection,
  * derives a filesystem-safe ``slug`` for model filenames.

This module is the single source of truth for those rules so WS
handlers, tests, and migrations don't grow their own variants.
"""

from __future__ import annotations

import logging
import re
import secrets
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

# Hard spec limits lifted straight from docs/DESIGN-TRAINING-TITLE.md §0.
# Kept as module constants so tests + validators + migrations agree.
MAX_TITLE_LEN = 60
MAX_SLUG_LEN = 40
GENERATE_RETRIES = 3  # collision retries before the last resort suffix

# Short word lists — 10 × 10 = 100 base combinations, ×65 536 hex4
# tails ≈ 6.5M distinct auto-titles. Collisions are astronomically
# unlikely in the single-user dev setup this spec targets; the retry
# loop below handles the pathological case regardless.
_ADJECTIVES: tuple[str, ...] = (
    "brave", "calm", "clever", "eager", "gentle",
    "lucky", "noble", "quiet", "swift", "wise",
)
_NOUNS: tuple[str, ...] = (
    "tiger", "falcon", "whale", "panda", "otter",
    "lynx", "raven", "badger", "hawk", "fox",
)

_SLUG_REPLACE_RE = re.compile(r"[^a-z0-9]+")


def slugify(title: str, *, max_len: int = MAX_SLUG_LEN) -> str:
    """Port of the slug rule in DESIGN-TRAINING-TITLE.md §6.

    Steps (matching the spec exactly so FE + BE agree on filenames):
      1. lowercase
      2. replace runs of ``[^a-z0-9]+`` with ``-``
      3. strip leading/trailing ``-``
      4. truncate to ``max_len`` (default 40)
      5. empty result → fallback ``"run"``
    """
    s = _SLUG_REPLACE_RE.sub("-", title.lower()).strip("-")
    if len(s) > max_len:
        s = s[:max_len].rstrip("-")
    return s or "run"


def _random_title() -> str:
    """Generate a ``run-{adj}-{noun}-{4hex}`` candidate.

    Uses ``secrets`` so tests can't predict collisions cheaply and the
    entropy isn't correlated with other process-level RNGs (PPO seeds,
    game engine RNG).
    """
    adj = secrets.choice(_ADJECTIVES)
    noun = secrets.choice(_NOUNS)
    tail = secrets.token_hex(2)  # 4 hex chars
    return f"run-{adj}-{noun}-{tail}"


def is_valid_title(title: str) -> tuple[bool, str | None]:
    """Validate a caller-supplied title.

    Returns ``(ok, error_message_or_None)``. The error string is the
    one the client surfaces inline under the Title input (Korean —
    matches the spec's UI copy).
    """
    if not isinstance(title, str) or not title.strip():
        return False, "제목 필수"
    if len(title) > MAX_TITLE_LEN:
        return False, "최대 60자"
    return True, None


class TrainingRunsService:
    """CRUD helper for the ``training_runs`` collection.

    Lean on purpose — a training run lives here from the moment a
    client clicks Start until the next one overwrites its slot. The
    collection exists mainly to answer two questions:

      * is this title taken? (uniqueness check at start + GET /titles)
      * list recent titles for autocomplete

    Legacy games + evaluations hold a denormalised snapshot of the
    title so rename-later workflows don't orphan historical rows.
    """

    def __init__(self, db: AsyncIOMotorDatabase | None) -> None:
        # ``db`` is Optional because unit tests without Mongo can use a
        # service that short-circuits to "nothing taken yet". The live
        # app always supplies a real db at lifespan-start.
        self._db = db
        self._col = db["training_runs"] if db is not None else None

    async def title_taken(self, title: str) -> bool:
        if self._col is None:
            return False
        doc = await self._col.find_one({"title": title})
        return doc is not None

    async def register(
        self,
        *,
        experiment_id: str,
        title: str,
        slug: str,
        bot_level: int,
        started_at,
        hyperparams: dict[str, Any] | None = None,
        reward_model: str = "shaped_v1",
        policy_type: str = "mlp_v1",
        algorithm: str = "ppo",
    ) -> None:
        """Insert a run doc; tolerates a dead Mongo (best-effort).

        ``hyperparams`` is a snapshot of what the run was started with
        (BE-T10) — learning rate, n_envs, total_timesteps, etc. Stored
        here rather than on every ``GameRecord`` because the values
        don't change over the run; ``/api/training/runs`` joins on
        ``experiment_id`` at query time.

        ``reward_model`` (ADR 0015 — v2 Sprint-2) records which reward
        variant produced this run. Stored verbatim so a future ablation
        report can group evaluator scorecards by reward function. The
        default ``"shaped_v1"`` matches the migration backfill so a
        legacy run inserted without the arg is indistinguishable from
        a v1.0.0-era run tagged explicitly.

        ``policy_type`` (ADR 0016 — v2 Sprint-3) records the policy
        architecture for this run (``mlp_v1`` / ``lstm_v1`` / reserved
        ``gru_v1`` / ``transformer_v1``). Enables the evaluator and
        LoadedPolicyBot to pick the correct ``PPO.load`` vs
        ``RecurrentPPO.load`` path later; the run-record write is the
        source of truth. Default matches the migration backfill.

        ``algorithm`` (ADR 0017 — v2 Sprint-4) records the learner
        family (``ppo`` / ``sac``). Drives ``PPO.load`` vs ``SAC.load``
        dispatch symmetrically to ``policy_type``; pre-S4 rows are
        PPO by construction so the default matches the backfill.

        The in-memory manager remains the source of truth for the live
        run — Mongo is the persistence layer for the history + title
        uniqueness lookup. If the insert fails we log and continue; the
        FE still renders the run correctly because training:status
        carries the title directly.
        """
        if self._col is None:
            return
        try:
            doc: dict[str, Any] = {
                "experiment_id": experiment_id,
                "title": title,
                "slug": slug,
                "bot_level": int(bot_level),
                "started_at": started_at,
                "reward_model": reward_model,
                "policy_type": policy_type,
                "algorithm": algorithm,
            }
            if hyperparams:
                # Pass through as-is so a new field the caller adds
                # (e.g. policy_kwargs) doesn't require a service change.
                doc["hyperparams"] = dict(hyperparams)
            await self._col.insert_one(doc)
        except Exception:  # noqa: BLE001 — non-fatal; log and move on
            logger.exception("training_runs insert failed for %s", experiment_id)

    async def get_by_experiment_ids(
        self, experiment_ids: list[str]
    ) -> dict[str, dict[str, Any]]:
        """Bulk-lookup for the runs aggregation join (BE-T10).

        Returns ``{experiment_id: run_doc}`` so the caller can decorate
        each aggregation row without a separate round-trip per run.
        Missing experiments resolve to an absent key — callers should
        use ``dict.get`` with a default.
        """
        if self._col is None or not experiment_ids:
            return {}
        cursor = self._col.find(
            {"experiment_id": {"$in": list(experiment_ids)}},
            {"_id": 0},
        )
        docs = await cursor.to_list(length=len(experiment_ids))
        return {d["experiment_id"]: d for d in docs if d.get("experiment_id")}

    async def list_titles(
        self, *, q: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Return recent titles, optionally filtered by substring.

        Used by the FE autocomplete combobox (spec §3) and the Title
        input's debounced uniqueness check (spec §1). Returns plain
        dicts (title + experiment_id + started_at) so FE can render
        the "prior run's date" hint on duplicates.
        """
        if self._col is None:
            return []
        query: dict[str, Any] = {}
        if q:
            # Case-insensitive substring match — no regex escape because
            # the FE payload is size-capped at 60 chars by the schema
            # and Mongo's regex engine is safe against slow backtracking
            # on inputs that small.
            query["title"] = {"$regex": re.escape(q), "$options": "i"}
        cursor = (
            self._col.find(query, {"_id": 0, "title": 1, "experiment_id": 1, "started_at": 1})
            .sort("started_at", -1)
            .limit(max(1, min(int(limit), 500)))
        )
        docs = await cursor.to_list(length=limit)
        # ISO-serialize timestamps so the REST response is JSON-clean.
        for d in docs:
            ts = d.get("started_at")
            if ts is not None and hasattr(ts, "isoformat"):
                d["started_at"] = ts.isoformat()
        return docs


async def allocate_title(
    service: TrainingRunsService, requested: str | None
) -> str:
    """Return the final title for a new training run.

    If ``requested`` is a non-empty string that passes ``is_valid_title``
    and is not already taken, it wins. Otherwise we generate
    ``run-{adj}-{noun}-{4hex}`` candidates until one is free (bounded
    at GENERATE_RETRIES). The last-resort fallback appends a random
    hex tail so a pathological collision run still terminates.
    """
    # Explicit caller title takes priority — validation is the responsibility
    # of the WS payload layer, but we re-check here defensively so a direct
    # HTTP / test path can't skip it.
    if isinstance(requested, str) and requested.strip():
        ok, _ = is_valid_title(requested)
        if ok and not await service.title_taken(requested):
            return requested
        # Caller-supplied title rejected — fall through to random.

    for _ in range(GENERATE_RETRIES):
        candidate = _random_title()
        if not await service.title_taken(candidate):
            return candidate

    # Pathological case: every generated word pair clashed. Tack on
    # 8 more hex chars so this path is deterministically unique.
    return f"{_random_title()}-{secrets.token_hex(4)}"
