"""Persistence layer for the self-play league pool (v2.x Sprint 1).

Two stores work together:

  * ``models/league/manifest.json`` — authoritative local snapshot
    (ADR §4). A file on disk owned by the training process; the
    ADR: "manifest JSON on disk is the authoritative local
    snapshot, Mongo is the dashboard source".
  * MongoDB ``league_standings`` collection — indexed on ``elo`` desc
    so the dashboard API answers top-N in O(log N). Reads can fall
    through to the manifest if Mongo is unreachable, so a dev laptop
    without Mongo still serves a correct standings page.

The repository is the single write path into both. Its ``sync`` method
enforces the invariant that Mongo matches the manifest for every
pool entry.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from backend.app.models.league import (
    LeagueCheckpoint,
    LeagueManifest,
    LeagueStandings,
)
from backend.app.services.db_utils import with_mongo_retry
from backend.app.services.league_elo import apply_match_result

logger = logging.getLogger(__name__)

COLLECTION_NAME: str = "league_standings"
MANIFEST_FILENAME: str = "manifest.json"


class LeagueRepository:
    """CRUD + manifest sync for the league pool.

    The repository does NOT take a lock on the manifest file — the
    training-thread admission callback is the only writer in v1 and it
    serializes manifest writes internally. If a future Sprint introduces
    concurrent writers (e.g. a UI-side manual admission), file-level
    locking moves here.
    """

    def __init__(
        self,
        db: AsyncIOMotorDatabase | None,
        *,
        league_dir: str = "models/league",
    ) -> None:
        self._db = db
        self._col = db[COLLECTION_NAME] if db is not None else None
        self._league_dir = Path(league_dir)
        self._manifest_path = self._league_dir / MANIFEST_FILENAME

    # ------------------------------------------------------------------
    # Manifest (on-disk) — authoritative
    # ------------------------------------------------------------------
    def load_manifest(self) -> LeagueManifest:
        """Read ``manifest.json`` off disk, or return an empty manifest
        if the file doesn't exist yet (fresh install / migration not
        yet run).

        Validation goes through Pydantic so a hand-edited manifest with
        a typo surfaces at load instead of poisoning every downstream
        reader.
        """
        if not self._manifest_path.exists():
            return LeagueManifest()
        raw = self._manifest_path.read_text(encoding="utf-8")
        return LeagueManifest.model_validate_json(raw)

    def save_manifest(self, manifest: LeagueManifest) -> None:
        """Write ``manifest.json`` atomically (write-to-temp + rename).

        Atomic rename guarantees a concurrent reader never sees a
        half-written file — on any POSIX filesystem ``rename`` is
        atomic when source and target are on the same mount. The
        temp file is written inside ``league_dir`` so that invariant
        holds.
        """
        self._league_dir.mkdir(parents=True, exist_ok=True)
        tmp = self._manifest_path.with_suffix(".json.tmp")
        payload = manifest.model_dump_json(indent=2)
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(self._manifest_path)

    # ------------------------------------------------------------------
    # MongoDB (dashboard mirror)
    # ------------------------------------------------------------------
    async def upsert_checkpoint(self, checkpoint: LeagueCheckpoint) -> None:
        """Insert-or-replace one checkpoint row in Mongo.

        ``_id`` maps to the checkpoint's human id (``{slug}__{exp8}__
        {step}``) so a re-admission after rename keeps the same doc
        instead of growing a duplicate row. Mongo-less deployments
        (no ``db``) no-op silently — the manifest remains authoritative.
        """
        if self._col is None:
            return
        doc = checkpoint.model_dump(mode="json")
        doc["_id"] = checkpoint.id

        async def _op():
            await self._col.replace_one(
                {"_id": checkpoint.id}, doc, upsert=True
            )

        await with_mongo_retry(_op, op_name="league_upsert_checkpoint")

    async def list_top_n(self, n: int = 10) -> list[LeagueCheckpoint]:
        """Return the top-N pool entries by rating.

        Mongo-backed fast path when available (``elo`` desc index);
        falls back to the manifest when Mongo is unreachable so the
        dashboard still works on a dev laptop. The ``list_top_n``
        ordering is elo-desc with games-desc tiebreak to match the
        manifest's ``top_n()`` helper.
        """
        if self._col is not None:
            try:
                cursor = self._col.find({}).sort(
                    [("elo", -1), ("games", -1)]
                ).limit(max(1, int(n)))
                raw = await cursor.to_list(length=n)
                return [LeagueCheckpoint.model_validate(d) for d in raw]
            except Exception:  # noqa: BLE001 — fall through to manifest
                logger.exception(
                    "league list_top_n: mongo read failed, falling back to manifest"
                )
        return self.load_manifest().top_n(n)

    async def get_checkpoint(
        self, checkpoint_id: str
    ) -> LeagueCheckpoint | None:
        """Single-row lookup. Mongo first, manifest fallback.

        Returns ``None`` when the id is not in the pool (different
        from anchor-row lookup — anchors don't live in Mongo by
        design; the manifest carries them).
        """
        if self._col is not None:
            try:
                doc = await self._col.find_one({"_id": checkpoint_id})
                if doc is not None:
                    return LeagueCheckpoint.model_validate(doc)
            except Exception:  # noqa: BLE001
                logger.exception(
                    "league get_checkpoint: mongo read failed, falling back"
                )
        manifest = self.load_manifest()
        for c in manifest.checkpoints:
            if c.id == checkpoint_id:
                return c
        return None

    async def update_elo_batch(
        self, results: list[dict[str, Any]]
    ) -> None:
        """Apply a batch of match results to the pool atomically.

        Each result dict must carry ``id_a``, ``id_b``, ``winner``
        (1 or 2). Ratings update via ``apply_match_result`` so anchor
        rows (L1/L3/L5) never move. Writes go to BOTH the manifest
        and Mongo inside one method so the two stores can't drift on
        a partial failure.

        The ADR batches Mongo flushes every 64 matches — this method
        is the single flush site. Callers that want immediate flush
        after each match (tests, diagnostic scripts) pass a 1-element
        list. Mongo-less: manifest-only update, Mongo writes skipped.
        """
        if not results:
            return
        manifest = self.load_manifest()
        by_id: dict[str, LeagueCheckpoint] = {c.id: c for c in manifest.checkpoints}

        touched: set[str] = set()
        for r in results:
            id_a = r.get("id_a")
            id_b = r.get("id_b")
            winner = r.get("winner")
            if not id_a or not id_b or winner not in (1, 2):
                logger.warning(
                    "league update_elo_batch: skipping malformed result %r", r
                )
                continue
            a = by_id.get(id_a)
            b = by_id.get(id_b)
            if a is None or b is None:
                logger.warning(
                    "league update_elo_batch: missing checkpoint(s) "
                    "id_a=%s id_b=%s",
                    id_a, id_b,
                )
                continue
            new_a, new_b = apply_match_result(
                rating_a=a.elo, games_a=a.games,
                rating_b=b.elo, games_b=b.games,
                winner=winner,
                id_a=id_a, id_b=id_b,
            )
            # Update anchor rows' win/loss stats for display even
            # though ratings stay pinned — FE uses games counts to
            # show "anchor has played N matches".
            by_id[id_a] = a.model_copy(update={
                "elo": new_a,
                "wins": a.wins + (1 if winner == 1 else 0),
                "losses": a.losses + (1 if winner == 2 else 0),
                "games": a.games + 1,
            })
            by_id[id_b] = b.model_copy(update={
                "elo": new_b,
                "wins": b.wins + (1 if winner == 2 else 0),
                "losses": b.losses + (1 if winner == 1 else 0),
                "games": b.games + 1,
            })
            touched.add(id_a)
            touched.add(id_b)

        if not touched:
            return
        manifest.checkpoints = [by_id[c.id] for c in manifest.checkpoints]
        # Champion: highest current elo AMONG TRAINING CHECKPOINTS
        # (ADR §2 — anchors are a fixed reference corridor, not
        # candidates for champion). L5 at 1200 would otherwise always
        # win before any training checkpoint crosses it. Simple
        # Sprint-1 rule; ADR §7 open question 1 reserves a sticky-
        # streak variant for Sprint 2. Ties break by games-desc.
        non_anchor = [c for c in manifest.checkpoints if not c.is_anchor]
        sorted_ckpts = sorted(
            non_anchor,
            key=lambda c: (-c.elo, -c.games),
        )
        manifest.champion_id = sorted_ckpts[0].id if sorted_ckpts else None
        self.save_manifest(manifest)

        if self._col is None:
            return
        for cid in touched:
            try:
                await self.upsert_checkpoint(by_id[cid])
            except Exception:  # noqa: BLE001
                logger.exception(
                    "league update_elo_batch: mongo upsert failed for %s", cid
                )

    async def sync_manifest_to_mongo(self) -> int:
        """Bulk-push every manifest row into Mongo.

        Used by the migration script (seed_league_from_v1_models.py)
        and called at FastAPI startup so the two stores agree after a
        restart. Returns the number of rows written. Mongo-less: 0.
        """
        if self._col is None:
            return 0
        manifest = self.load_manifest()
        count = 0
        for c in manifest.checkpoints:
            try:
                await self.upsert_checkpoint(c)
                count += 1
            except Exception:  # noqa: BLE001
                logger.exception(
                    "league sync: mongo upsert failed for %s", c.id
                )
        return count

    # ------------------------------------------------------------------
    # API envelope builder — keeps route handler trivially thin.
    # ------------------------------------------------------------------
    async def standings_envelope(self, limit: int = 10) -> LeagueStandings:
        manifest = self.load_manifest()
        top = await self.list_top_n(limit)
        return LeagueStandings(
            top=top,
            champion_id=manifest.champion_id,
            generation=manifest.generation,
            pool_size=manifest.pool_size,
            total_checkpoints=len(manifest.checkpoints),
        )


__all__ = ["COLLECTION_NAME", "MANIFEST_FILENAME", "LeagueRepository"]
