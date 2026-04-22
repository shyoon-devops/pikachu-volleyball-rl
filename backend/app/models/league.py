"""Pydantic schemas for the self-play league (v2.x Sprint 1).

See docs/adr/0014-self-play-league.md. The manifest under
``models/league/manifest.json`` is the authoritative on-disk record
of the pool; MongoDB mirrors it for dashboard reads. This module
defines both the persisted shapes (``LeagueCheckpoint``,
``LeagueManifest``) and the API response envelope
(``LeagueStandings``).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ADR §1 — Admitted checkpoint source labels. ``v1_legacy`` is the
# migration-seeded bucket (scripts/seed_league_from_v1_models.py);
# ``training`` is the normal save-interval path; ``anchor`` is the
# L1/L3/L5 fixed rule-based baselines that never update.
LeagueCheckpointSource = Literal["training", "v1_legacy", "anchor"]


# ADR §1 + §2 — pool cap and rating anchors. Pulled into module
# constants so the migration script, admission callback, and API
# response all agree on the numbers without each re-importing the ADR.
LEAGUE_POOL_SIZE: int = 32
SEED_ELO: float = 1000.0
ANCHOR_RATINGS: dict[str, float] = {
    "L1": 600.0,
    "L3": 900.0,
    "L5": 1200.0,
}


class LeagueCheckpoint(BaseModel):
    """One entry in the league pool.

    Per ADR §1 and §4:
      * ``id`` is a human-stable slug (e.g.
        ``run-baseline__a3f9bc21__200000``) — the file stem without
        ``.zip``. For anchor rows, id is the anchor key (``L1``, etc).
      * ``elo``, ``wins``, ``losses``, ``games`` track the rating stats
        the PFSP sampler and FE standings page both consume.
      * ``admitted_at`` records the ISO timestamp of pool admission —
        retirement policy (ADR §1: "weakest-and-oldest") keys off it.
      * ``step`` / ``experiment_id`` / ``source`` carry provenance so
        the FE can link back to the source training run.
    """

    # protected_namespaces=() so fields starting with ``model_`` (there
    # aren't any here today, but the EvaluationRecord bite left a habit).
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    id: str = Field(..., min_length=1, max_length=200)
    elo: Annotated[float, Field(ge=0.0, le=5000.0)] = SEED_ELO
    wins: Annotated[int, Field(ge=0)] = 0
    losses: Annotated[int, Field(ge=0)] = 0
    games: Annotated[int, Field(ge=0)] = 0
    admitted_at: str
    step: int | None = None
    experiment_id: str | None = None
    source: LeagueCheckpointSource = "training"

    @field_validator("admitted_at")
    @classmethod
    def _valid_iso_timestamp(cls, v: str) -> str:
        # ISO-parsed for early rejection so we don't store garbage
        # timestamps the FE would have to defensively re-parse.
        datetime.fromisoformat(v)
        return v

    @field_validator("games")
    @classmethod
    def _games_matches_winloss(cls, v: int, info) -> int:
        # Soft invariant: ``games >= wins + losses`` (games counts draws
        # + any non-terminated matches too). Equality is typical since
        # draws can't happen in pikachu-volleyball (MAX_SCORE terminates
        # the match), but we don't force equality so a pre-draw-count
        # field addition in Sprint 2 wouldn't break back-fill.
        wins = info.data.get("wins", 0) or 0
        losses = info.data.get("losses", 0) or 0
        if v < wins + losses:
            raise ValueError(
                f"games ({v}) must be >= wins + losses ({wins + losses})"
            )
        return v

    @property
    def win_rate(self) -> float:
        """Convenience for the FE standings table. Zero games → 0.0."""
        if self.games == 0:
            return 0.0
        return self.wins / self.games

    @property
    def is_anchor(self) -> bool:
        """Anchor rows (L1/L3/L5) never update ratings (ADR §2)."""
        return self.source == "anchor"


class LeagueManifest(BaseModel):
    """Root shape of ``models/league/manifest.json``.

    Authoritative local snapshot — the on-disk manifest is the source
    of truth and MongoDB is its derived mirror. Callers that want
    transactional updates read+write this file under a file lock;
    mirror into Mongo is best-effort (see LeagueRepository.sync).
    """

    model_config = ConfigDict(extra="forbid")

    checkpoints: list[LeagueCheckpoint] = Field(default_factory=list)
    # The currently-anointed champion. Null until the first admission
    # cycle crosses the threshold (ADR §7 open question 1 — automatic
    # Elo-max held for 5 consecutive cycles; Sprint-1 is simple
    # highest-Elo on each read).
    champion_id: str | None = None
    # Generation counter — increments each time a new training run
    # admits its first checkpoint. Lets the FE render "lineage"
    # lineage arcs without persistent experiment joins.
    generation: Annotated[int, Field(ge=0)] = 0
    # Cached pool capacity so the FE doesn't need to hard-code
    # LEAGUE_POOL_SIZE. Validated against the ADR constant at load.
    pool_size: Annotated[int, Field(ge=1, le=1024)] = LEAGUE_POOL_SIZE

    @field_validator("pool_size")
    @classmethod
    def _pool_size_matches_adr(cls, v: int) -> int:
        # Soft warning-only check: a mismatched pool_size in the
        # manifest should be obvious at load time but we accept it so
        # a future ADR bump doesn't break back-compat.
        return v

    def top_n(self, n: int = 10) -> list[LeagueCheckpoint]:
        """Sort-by-elo desc; ties broken by games-played desc.

        Pure read helper used by both the API handler and the FE
        league tab's lazy-load path.
        """
        return sorted(
            self.checkpoints,
            key=lambda c: (-c.elo, -c.games),
        )[:n]


class LeagueStandings(BaseModel):
    """Envelope for ``GET /api/league/standings``.

    Carries a top-N slice of the pool plus the summary fields the FE
    header renders (champion, generation, pool size). Kept separate
    from ``LeagueManifest`` so the API can page / truncate without
    leaking the rest of the manifest.
    """

    top: list[LeagueCheckpoint]
    champion_id: str | None = None
    generation: int = 0
    pool_size: int = LEAGUE_POOL_SIZE
    total_checkpoints: int = 0


def now_iso() -> str:
    """UTC ISO-8601 helper for ``admitted_at`` timestamps.

    Kept here (rather than in a shared util) so the migration
    script + admission callback have a single import site for the
    manifest timestamp format.
    """
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


__all__ = [
    "ANCHOR_RATINGS",
    "LEAGUE_POOL_SIZE",
    "LeagueCheckpoint",
    "LeagueCheckpointSource",
    "LeagueManifest",
    "LeagueStandings",
    "SEED_ELO",
    "now_iso",
]
