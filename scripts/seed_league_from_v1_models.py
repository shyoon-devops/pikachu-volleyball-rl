"""One-shot migration — seed the self-play league with v1.0.0 checkpoints.

See docs/adr/0014-self-play-league.md §8 ("Migration + compatibility").
Every ``*.zip`` under ``<MODEL_DIR>/<experiment_id>/`` gets a
``LeagueCheckpoint`` row with:

  * ``elo = 1000`` (SEED_ELO — AA hasn't played any league match yet)
  * ``source = "v1_legacy"`` (provenance tag; FE renders a badge)
  * ``admitted_at = now``
  * ``step`` parsed from the T2 filename (``{slug}__{exp8}__{step}.zip``)
  * ``experiment_id`` taken from the parent directory name

Anchors (L1/L3/L5) are inserted unconditionally with their fixed
ratings so the FE standings tab always has the baseline corridor.

Usage:

    $ python -m scripts.seed_league_from_v1_models \\
        --model-dir ./models --league-dir ./models/league \\
        [--dry-run] [--mongo-url mongodb://...]

``--dry-run`` prints what would be written without touching disk or
Mongo. Without ``--mongo-url`` the script seeds the manifest only;
the repository mirrors to Mongo on its next ``sync_manifest_to_mongo``
call at app startup.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from pathlib import Path

from backend.app.models.league import (
    ANCHOR_RATINGS,
    LEAGUE_POOL_SIZE,
    SEED_ELO,
    LeagueCheckpoint,
    LeagueManifest,
    now_iso,
)
from backend.app.services.league_repository import LeagueRepository

logger = logging.getLogger("seed_league")

# ``{slug}__{exp8}__{step}.zip`` (BE-T2 filename convention). ``step``
# can also be the literal ``final`` — we coerce that to a sentinel so
# final checkpoints sort above numbered steps the same way /api/models
# does.
_FILENAME_RE = re.compile(
    r"^(?P<slug>[^_]+(?:__[^_]+)*?)__"
    r"(?P<exp8>[0-9a-f]{8})__"
    r"(?P<step>final|[0-9]+)"
    r"$"
)
_FINAL_STEP_SENTINEL: int = 10**12  # matches routes._parse_checkpoint_filename


def parse_checkpoint_filename(stem: str) -> tuple[str | None, int | None]:
    """Return ``(slug, step)`` or ``(None, None)`` for pre-T2 legacy
    names (e.g. ``final``, ``200000``) that the caller should tag as
    ``v1_legacy`` without a parsed step.
    """
    m = _FILENAME_RE.match(stem)
    if m is None:
        return None, None
    step_str = m.group("step")
    step = _FINAL_STEP_SENTINEL if step_str == "final" else int(step_str)
    return m.group("slug"), step


def discover_checkpoints(model_dir: Path) -> list[Path]:
    """Return every ``*.zip`` under ``<model_dir>/<experiment_id>/``.

    Excludes the league subdirectory itself (``<model_dir>/league/*.zip``)
    so a re-run doesn't admit migration artefacts back into the pool.
    """
    if not model_dir.exists():
        return []
    league_dir = (model_dir / "league").resolve()
    out: list[Path] = []
    for path in model_dir.rglob("*.zip"):
        resolved = path.resolve()
        if str(resolved).startswith(str(league_dir)):
            continue
        out.append(path)
    return sorted(out)


def build_checkpoint_row(
    path: Path, model_dir: Path, *, admitted_at: str
) -> LeagueCheckpoint:
    """Build one ``LeagueCheckpoint`` for a v1-era file.

    ``experiment_id`` is the immediate parent directory of the file
    relative to ``model_dir`` (``models/<exp>/file.zip`` → ``<exp>``).
    A file sitting directly under ``model_dir`` (no parent dir) carries
    ``experiment_id=None``.
    """
    rel = path.relative_to(model_dir)
    parts = rel.parts
    experiment_id = parts[0] if len(parts) > 1 else None
    slug, step = parse_checkpoint_filename(path.stem)
    # id must be unique per pool entry; use the filename stem which is
    # unique per-experiment already thanks to the T2 ``exp8`` tail.
    return LeagueCheckpoint(
        id=path.stem,
        elo=SEED_ELO,
        wins=0, losses=0, games=0,
        admitted_at=admitted_at,
        step=step,
        experiment_id=experiment_id,
        source="v1_legacy",
    )


def build_anchor_rows(admitted_at: str) -> list[LeagueCheckpoint]:
    """Anchor rows (L1/L3/L5) — always present, ratings pinned."""
    return [
        LeagueCheckpoint(
            id=name,
            elo=rating,
            wins=0, losses=0, games=0,
            admitted_at=admitted_at,
            step=None,
            experiment_id=None,
            source="anchor",
        )
        for name, rating in ANCHOR_RATINGS.items()
    ]


def seed_manifest(
    model_dir: Path, league_dir: Path, *, dry_run: bool = False
) -> LeagueManifest:
    """Build the seeded manifest. Writes to disk unless ``dry_run``.

    Returns the manifest object so callers can inspect without
    re-reading from disk (tests + the ``--mongo-url`` push step).
    """
    admitted_at = now_iso()
    rows: list[LeagueCheckpoint] = build_anchor_rows(admitted_at)
    for path in discover_checkpoints(model_dir):
        try:
            rows.append(build_checkpoint_row(path, model_dir, admitted_at=admitted_at))
        except Exception:  # noqa: BLE001 — one bad file shouldn't abort the run
            logger.exception("seed_league: skipping %s", path)

    manifest = LeagueManifest(
        checkpoints=rows,
        champion_id=None,  # unknown until first admission cycle runs
        generation=0,
        pool_size=LEAGUE_POOL_SIZE,
    )

    if dry_run:
        logger.info(
            "dry-run: would seed %d rows (%d anchors + %d legacy)",
            len(rows), len(ANCHOR_RATINGS), len(rows) - len(ANCHOR_RATINGS),
        )
        return manifest

    repo = LeagueRepository(db=None, league_dir=str(league_dir))
    repo.save_manifest(manifest)
    logger.info("wrote %s (%d checkpoints)", repo._manifest_path, len(rows))
    return manifest


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Seed the self-play league from v1.0.0 checkpoints",
    )
    parser.add_argument(
        "--model-dir",
        default=os.getenv("MODEL_DIR", "./models"),
        help="Root of v1 checkpoints (default: $MODEL_DIR or ./models).",
    )
    parser.add_argument(
        "--league-dir",
        default=None,
        help="Destination for manifest.json. Defaults to <model-dir>/league.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print the plan without writing.",
    )
    parser.add_argument(
        "--mongo-url",
        default=None,
        help="If provided, also mirror the manifest into Mongo after write.",
    )
    return parser


async def _async_mongo_sync(league_dir: Path, mongo_url: str) -> int:
    """Mirror the manifest into Mongo. Late import so the sync path
    stays importable without motor installed (the script's default
    use case is manifest-only).
    """
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(mongo_url)
    db = client.get_default_database()
    repo = LeagueRepository(db=db, league_dir=str(league_dir))
    written = await repo.sync_manifest_to_mongo()
    client.close()
    return written


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = _build_arg_parser().parse_args(argv)

    model_dir = Path(args.model_dir).resolve()
    league_dir = Path(args.league_dir).resolve() if args.league_dir else model_dir / "league"
    manifest = seed_manifest(model_dir, league_dir, dry_run=args.dry_run)

    if args.mongo_url and not args.dry_run:
        import asyncio

        written = asyncio.run(_async_mongo_sync(league_dir, args.mongo_url))
        logger.info("mirrored %d rows into Mongo", written)

    logger.info("done — pool=%d", len(manifest.checkpoints))
    return 0


if __name__ == "__main__":
    sys.exit(main())
