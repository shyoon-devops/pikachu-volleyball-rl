"""Pure Elo helpers for the self-play league (v2.x Sprint 1).

Separate from ``backend/rl/elo.py`` (evaluator-side leaderboard with
its own seed + K-factor). This module is the league's rating engine —
same arithmetic, but the constants and anchor scheme come from
docs/adr/0014-self-play-league.md:

  * seed = 1000 (v1 L1=600 ... L5=1200 baseline corridor)
  * K = 16 if games_played < 30 else 8 (chess-like annealing)
  * anchors (``L1``/``L3``/``L5``) are pinned and never update

Functions here are pure: no disk IO, no logging, no mutation of
shared state. Callers (league_repository, admission callback,
migration script) compose them.
"""

from __future__ import annotations

from backend.app.models.league import ANCHOR_RATINGS

# ADR §2 — K-factor anneals once a checkpoint has logged enough games
# that the noise floor of individual match outcomes is small compared
# to its current rating. Below 30 games the rating moves faster so a
# freshly-admitted checkpoint can find its level in the pool quickly.
K_EARLY: int = 16
K_LATE: int = 8
K_ANNEAL_GAMES: int = 30


def k_factor_for_games(games_played: int) -> int:
    """Return the K-factor to use for a match, given how many games
    this checkpoint has already played.

    ADR §2: K=16 below ``K_ANNEAL_GAMES`` (30) then K=8. The threshold
    is "strictly less than" — game 30 itself uses the late K so the
    transition is monotone with total games regardless of which
    helper the caller invokes first (pre- vs. post-update count).
    """
    return K_EARLY if games_played < K_ANNEAL_GAMES else K_LATE


def expected_score(rating_a: float, rating_b: float) -> float:
    """Standard logistic expectation for player A vs. player B.

    Returns ``1 / (1 + 10 ** ((rating_b - rating_a) / 400))`` — the
    textbook Elo expectation. Pulled out as a named helper so tests
    can pin the formula shape without reinventing the numerator.
    """
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))


def update_elo(
    rating_a: float,
    rating_b: float,
    winner: int,
    k_factor: float,
) -> tuple[float, float]:
    """Pure Elo update. ``winner`` is 1 (A won) or 2 (B won).

    Returns ``(new_rating_a, new_rating_b)``. Draws aren't representable
    in pikachu-volleyball (MAX_SCORE always decides); if a future
    Sprint 2 adds a draw concept, expand the signature with
    ``winner=0 → score_a=0.5`` rather than silently allowing any
    integer.

    Both players use the SAME k_factor for a given match — the caller
    is responsible for picking one (typically by the minimum games-
    played of the two sides, which keeps the rating motion symmetric
    even when one side is early-career and the other isn't). Anchor
    rows (L1/L3/L5) never call this helper at all; callers filter
    via :func:`is_anchor` before invoking.
    """
    if winner not in (1, 2):
        raise ValueError(f"winner must be 1 or 2, got {winner!r}")
    e_a = expected_score(rating_a, rating_b)
    e_b = 1.0 - e_a
    score_a = 1.0 if winner == 1 else 0.0
    score_b = 1.0 - score_a
    new_a = rating_a + k_factor * (score_a - e_a)
    new_b = rating_b + k_factor * (score_b - e_b)
    return new_a, new_b


def is_anchor(checkpoint_id: str) -> bool:
    """Anchor ids (``L1``, ``L3``, ``L5``) never have their ratings
    updated — they're the fixed-reference corridor the rest of the
    pool is measured against.

    Returns True iff ``checkpoint_id`` is exactly one of the anchor
    keys. Substring / case-insensitive matching is intentionally NOT
    done — a real training checkpoint named ``L1_variant`` should
    still update normally.
    """
    return checkpoint_id in ANCHOR_RATINGS


def apply_match_result(
    rating_a: float,
    games_a: int,
    rating_b: float,
    games_b: int,
    winner: int,
    *,
    id_a: str | None = None,
    id_b: str | None = None,
) -> tuple[float, float]:
    """Convenience wrapper: picks the K-factor from each side's prior
    games count and anchors through ``is_anchor`` so callers don't
    need to re-check before updating.

    Both sides use the SAME K — ``min(k(games_a), k(games_b))``, which
    means the overall rating motion stays symmetric (equal-and-
    opposite deltas) even when one player is early-career.

    If either id is an anchor, that side's rating is returned
    unchanged. If BOTH are anchors the call is a no-op — the caller
    should have filtered this case out upstream but we handle it
    defensively rather than silently corrupting an anchor row.
    """
    a_is_anchor = id_a is not None and is_anchor(id_a)
    b_is_anchor = id_b is not None and is_anchor(id_b)
    if a_is_anchor and b_is_anchor:
        return rating_a, rating_b

    k = float(min(k_factor_for_games(games_a), k_factor_for_games(games_b)))
    new_a, new_b = update_elo(rating_a, rating_b, winner, k)
    if a_is_anchor:
        new_a = rating_a  # anchor row never moves
    if b_is_anchor:
        new_b = rating_b
    return new_a, new_b


__all__ = [
    "K_ANNEAL_GAMES",
    "K_EARLY",
    "K_LATE",
    "apply_match_result",
    "expected_score",
    "is_anchor",
    "k_factor_for_games",
    "update_elo",
]
