#!/usr/bin/env python3
"""One-shot migration/cleanup for the games collection.

Two modes
---------
``--mode=shape`` (default)
    Backfill ``bot_level`` / ``experiment_id`` on rows missing the fields
    or with out-of-range values. Ensures FE never reads ``undefined``.
    See the "shape" section below for rationale.

``--mode=purge-pre-fix``
    Delete every ``games`` row whose ``timestamp`` predates the fix
    commit (05ffd073 on 2026-04-12T12:00:48Z UTC). Product decision: the
    silent-L1 taint on pre-fix rows can't be recovered, and showing it
    as "L1 history" to end users is worse than dropping it. Emits a
    JSON sidecar with the deleted ``game_id`` list so replay files
    (``replays/{game_id}.msgpack``) can be cleaned up separately.

Shape-mode context (historical)
-------------------------------
Prior to commit 05ffd073 (fix(ws): route missing bot_level/experiment_id
to dead-letter, not silent L1), ``LiveFrameCallback._on_step`` omitted
both ``bot_level`` and ``experiment_id`` from the results dict. The WS
handler silently coerced a missing bot_level to 1. Result: every row
written during that window shows bot_level=1 regardless of the user's
actual training level, and experiment_id is the empty string.

For rows that already carry a bad *value* (not a missing field), shape
mode can't help — use purge-pre-fix instead.

Usage
-----
    # Dry-run, shape mode.
    MONGODB_URL=mongodb://host:27018/pikachu_rl_dev \\
        python3 backend/scripts/migrate-games-bot-level.py

    # Apply shape backfill.
    MONGODB_URL=... python3 backend/scripts/migrate-games-bot-level.py --commit

    # Dry-run, purge mode (reports count + sample + total row impact).
    MONGODB_URL=... python3 backend/scripts/migrate-games-bot-level.py \\
        --mode=purge-pre-fix

    # Apply purge. Emits deleted-game-ids sidecar next to the script.
    MONGODB_URL=... python3 backend/scripts/migrate-games-bot-level.py \\
        --mode=purge-pre-fix --commit

    # Override cutoff (defaults to the fix commit time).
    ... --mode=purge-pre-fix --cutoff 2026-04-10T00:00:00Z

Idempotency
-----------
Rerunning after --commit is a no-op in both modes:
* shape mode filters only match rows where the field is absent or invalid.
* purge mode filters on ``timestamp < cutoff``; once purged, surviving
  rows are all post-cutoff and never match again.

Why this is a separate script
-----------------------------
* It's a one-time operation, not part of normal request flow.
* It reads/writes every game doc — must not run inside the event loop
  that serves user traffic.
* Dry-run-first protects against accidentally destroying production data
  before the diff has been inspected.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger("migrate-games-bot-level")

# Same default used by TrainingManager.__init__ and the pre-fix handler
# fallback — keeping it here (rather than importing from the app) so the
# script stays runnable against a checked-out repo without pulling in
# the FastAPI dependency graph just to read one int.
DEFAULT_BOT_LEVEL = 1
DEFAULT_EXPERIMENT_ID = ""
VALID_LEVEL_RANGE = (1, 5)

# Commit time of 05ffd073 "fix(ws): route missing bot_level/experiment_id
# to dead-letter, not silent L1" in UTC. Every row saved BEFORE this
# moment was produced by handler code that silently defaulted bot_level
# to 1 (see handlers.py history). "전량 삭제" policy treats anything with
# timestamp < this as unrecoverably tainted, regardless of stored value.
FIX_COMMIT_UTC = "2026-04-12T12:00:48Z"


def _build_client() -> tuple[AsyncIOMotorClient, str]:
    """Build a Motor client from MONGODB_URL and return the db name."""
    url = os.getenv("MONGODB_URL", "mongodb://localhost:27017/pikachu_rl")
    client = AsyncIOMotorClient(
        url,
        # Short timeouts — a migration that hangs for 30s per op is useless.
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
    )
    # AsyncIOMotorClient.get_default_database picks the DB from the URL.
    db_name = client.get_default_database().name
    return client, db_name


async def _count_and_preview(col, filt: dict, label: str, preview_n: int = 5) -> int:
    """Count docs matching filter and log the first N game_ids as a preview."""
    total = await col.count_documents(filt)
    if total == 0:
        logger.info("[%s] 0 documents match — nothing to migrate.", label)
        return 0

    cursor = col.find(filt, {"game_id": 1, "_id": 1}).limit(preview_n)
    sample = [doc async for doc in cursor]
    preview = ", ".join(
        str(doc.get("game_id") or doc.get("_id")) for doc in sample
    )
    logger.info(
        "[%s] %d document(s) match. Preview (first %d): %s%s",
        label, total, min(preview_n, total), preview,
        " ..." if total > preview_n else "",
    )
    return total


def _parse_cutoff(raw: str) -> datetime:
    """Parse an ISO-8601 cutoff into an aware UTC datetime.

    Accepts both ``...Z`` and ``...+00:00``. Fails loud on naive inputs
    rather than silently treating them as UTC — operators should be
    explicit about TZ when wiping production data.
    """
    s = raw.replace("Z", "+00:00") if raw.endswith("Z") else raw
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        raise ValueError(f"cutoff must be timezone-aware, got naive: {raw!r}")
    return dt.astimezone(timezone.utc)


async def _purge_pre_fix(commit: bool, cutoff_raw: str) -> int:
    """Delete games whose timestamp predates the fix commit.

    Product decision ("Option B, 전량 삭제"): pre-fix rows are
    unrecoverably tainted — every automated demo game was saved as L1
    regardless of the user's actual training level. Dropping them beats
    showing misleading history.

    Writes a ``deleted_game_ids.json`` sidecar next to this script so
    replay files (``replays/{game_id}.msgpack``) can be cleaned up in a
    separate step without re-querying the DB.
    """
    cutoff = _parse_cutoff(cutoff_raw)
    client, db_name = _build_client()
    try:
        db = client.get_default_database()
        col = db["games"]

        logger.info(
            "Connected to MongoDB database %r (purge mode, cutoff=%s).",
            db_name, cutoff.isoformat(),
        )

        filt = {"timestamp": {"$lt": cutoff}}
        total = await col.count_documents(filt)
        post_fix = await col.count_documents({"timestamp": {"$gte": cutoff}})
        with_gid = await col.count_documents(
            {"timestamp": {"$lt": cutoff}, "game_id": {"$exists": True}},
        )
        without_gid = total - with_gid

        logger.info(
            "Pre-fix rows to purge: %d  |  Post-fix rows preserved: %d",
            total, post_fix,
        )
        logger.info(
            "  with game_id (mappable to replay file): %d", with_gid,
        )
        logger.info(
            "  without game_id (legacy schema, replay not mappable): %d",
            without_gid,
        )

        if total == 0:
            logger.info("Nothing to purge — no rows older than cutoff.")
            return 0

        # Preview up to 5 docs so the operator can spot-check before commit.
        cursor = col.find(
            filt, {"game_id": 1, "_id": 1, "timestamp": 1, "bot_level": 1},
        ).sort("timestamp", 1).limit(5)
        sample = [doc async for doc in cursor]
        logger.info("Oldest 5 pre-fix sample:")
        for doc in sample:
            logger.info(
                "  _id=%s game_id=%s ts=%s bot_level=%s",
                doc.get("_id"), doc.get("game_id", "<none>"),
                doc.get("timestamp"), doc.get("bot_level"),
            )

        if not commit:
            logger.warning(
                "DRY RUN — pass --commit to delete %d document(s). "
                "No sidecar written in dry-run mode.", total,
            )
            return 0

        # Collect game_ids BEFORE the delete — the sidecar drives the
        # separate replay-file cleanup step, so it must survive the drop.
        sidecar_path = Path(__file__).parent / "deleted_game_ids.json"
        game_ids_cursor = col.find(
            {"timestamp": {"$lt": cutoff}, "game_id": {"$exists": True}},
            {"game_id": 1, "_id": 0},
        )
        game_ids = [doc["game_id"] async for doc in game_ids_cursor]
        payload = {
            "db_name": db_name,
            "cutoff": cutoff.isoformat(),
            "total_deleted": total,
            "with_game_id": len(game_ids),
            "without_game_id": without_gid,
            "game_ids": game_ids,
        }
        # Append-style: if the operator runs across multiple envs, each
        # run creates a per-db sidecar so replays can be cleaned per env.
        per_env_path = sidecar_path.with_name(
            f"deleted_game_ids.{db_name}.json",
        )
        per_env_path.write_text(json.dumps(payload, indent=2))
        logger.info(
            "Wrote sidecar %s (%d game_ids for replay cleanup).",
            per_env_path, len(game_ids),
        )

        res = await col.delete_many(filt)
        logger.info(
            "Purge complete — deleted %d doc(s) from %r.games.",
            res.deleted_count, db_name,
        )
        if res.deleted_count != total:
            logger.warning(
                "Deleted count (%d) differs from pre-count (%d) — "
                "new rows may have been inserted during the run.",
                res.deleted_count, total,
            )
        return 0
    except Exception:
        logger.exception("Purge failed")
        return 1
    finally:
        client.close()


async def _migrate(commit: bool) -> int:
    """Return a process exit code: 0 = success, non-zero on error."""
    client, db_name = _build_client()
    try:
        db = client.get_default_database()
        col = db["games"]

        logger.info("Connected to MongoDB database %r, collection 'games'.", db_name)

        # --- Bucket 1: bot_level missing entirely -----------------------
        # The pre-fix insert path called GameRecord(bot_level=...) with
        # data.get("bot_level", 1), so bot_level WAS written — just as 1.
        # Rows missing the field only exist if a record was inserted by
        # legacy code paths (ad-hoc scripts, imports, very old versions).
        missing_level = {"bot_level": {"$exists": False}}
        n_missing_level = await _count_and_preview(
            col, missing_level, "missing bot_level",
        )

        # --- Bucket 2: bot_level out of range --------------------------
        # GameRecord enforces 1..5. Old docs could contain 0 or other
        # stale values from early development. Clamp to the default
        # rather than dropping — the game itself is still a valid
        # record of play.
        lo, hi = VALID_LEVEL_RANGE
        out_of_range = {
            "bot_level": {"$exists": True},
            "$or": [{"bot_level": {"$lt": lo}}, {"bot_level": {"$gt": hi}}],
        }
        n_out_of_range = await _count_and_preview(
            col, out_of_range, "bot_level out of range",
        )

        # --- Bucket 3: experiment_id missing ---------------------------
        # Empty string is the official post-fix legacy value for rows
        # that predate per-experiment tracking; missing field is not.
        missing_exp = {"experiment_id": {"$exists": False}}
        n_missing_exp = await _count_and_preview(
            col, missing_exp, "missing experiment_id",
        )

        total_to_fix = n_missing_level + n_out_of_range + n_missing_exp
        if total_to_fix == 0:
            logger.info("Nothing to do — DB already matches post-fix shape.")
            return 0

        if not commit:
            logger.warning(
                "DRY RUN — pass --commit to apply. Would update %d document(s) "
                "(missing_level=%d, out_of_range=%d, missing_exp=%d).",
                total_to_fix, n_missing_level, n_out_of_range, n_missing_exp,
            )
            return 0

        # --- Apply writes -----------------------------------------------
        # Done as three targeted updateMany calls rather than one
        # $set-everything sweep, so the audit log shows exactly which
        # bucket each row fell into. $exists + $lt/$gt filters make
        # each write idempotent.
        if n_missing_level:
            res = await col.update_many(
                missing_level, {"$set": {"bot_level": DEFAULT_BOT_LEVEL}},
            )
            logger.info(
                "Backfilled bot_level=%d on %d doc(s).",
                DEFAULT_BOT_LEVEL, res.modified_count,
            )

        if n_out_of_range:
            res = await col.update_many(
                out_of_range, {"$set": {"bot_level": DEFAULT_BOT_LEVEL}},
            )
            logger.info(
                "Clamped out-of-range bot_level→%d on %d doc(s).",
                DEFAULT_BOT_LEVEL, res.modified_count,
            )

        if n_missing_exp:
            res = await col.update_many(
                missing_exp, {"$set": {"experiment_id": DEFAULT_EXPERIMENT_ID}},
            )
            logger.info(
                "Backfilled experiment_id=%r on %d doc(s).",
                DEFAULT_EXPERIMENT_ID, res.modified_count,
            )

        logger.info("Migration complete.")
        return 0
    except Exception:
        logger.exception("Migration failed")
        return 1
    finally:
        client.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode", choices=("shape", "purge-pre-fix"), default="shape",
        help=(
            "shape (default): backfill missing/out-of-range fields. "
            "purge-pre-fix: delete rows saved before the fix commit."
        ),
    )
    parser.add_argument(
        "--cutoff", default=FIX_COMMIT_UTC,
        help=(
            "ISO-8601 UTC cutoff for purge mode. Rows with timestamp < "
            "this are deleted. Default: %(default)s (fix commit time). "
            "Must be timezone-aware (ends with 'Z' or '+00:00')."
        ),
    )
    parser.add_argument(
        "--commit", action="store_true",
        help="Actually write changes. Without this flag, dry-run only.",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable DEBUG-level logging.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.mode == "shape":
        return asyncio.run(_migrate(commit=args.commit))
    if args.mode == "purge-pre-fix":
        return asyncio.run(
            _purge_pre_fix(commit=args.commit, cutoff_raw=args.cutoff),
        )
    # argparse `choices` already guards this; kept as a belt-and-braces
    # guard so a future mode addition doesn't silently no-op.
    logger.error("Unknown mode: %s", args.mode)
    return 2


if __name__ == "__main__":
    sys.exit(main())
