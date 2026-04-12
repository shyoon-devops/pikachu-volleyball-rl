"""Elo rating system for cross-comparison of models and bot levels.

Players (RL checkpoints, rule-based bot levels) start at a fixed base rating
(1500 by default). After each evaluation match, both players' ratings are
updated based on the actual vs. expected outcome.

Bot rule-based levels are seeded with anchor ratings so that early model
evaluations have a meaningful reference point:
    L1 -> 1200    L2 -> 1350    L3 -> 1500    L4 -> 1650    L5 -> 1800

Usage:
    rs = EloRatingSystem()
    rs.update_from_eval(result)              # single match
    rs.update_from_evals(results)            # batch
    print(rs.leaderboard())                  # ranked list
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.rl.evaluator import EvalResult

DEFAULT_RATING: float = 1500.0
DEFAULT_K_FACTOR: float = 32.0

# Seed bot levels with sensible anchor ratings so that the first
# evaluations against them produce non-trivial Elo deltas.
BOT_ANCHOR_RATINGS: dict[str, float] = {
    "bot_L1": 1200.0,
    "bot_L2": 1350.0,
    "bot_L3": 1500.0,
    "bot_L4": 1650.0,
    "bot_L5": 1800.0,
}


def bot_player_id(level: int) -> str:
    """Canonical player id for a rule-based bot at the given level."""
    if level not in (1, 2, 3, 4, 5):
        raise ValueError(f"bot level must be 1-5, got {level}")
    return f"bot_L{level}"


def expected_score(rating_a: float, rating_b: float) -> float:
    """Standard Elo expected-score formula. Range: [0, 1]."""
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))


def update_ratings(
    rating_a: float,
    rating_b: float,
    score_a: float,
    *,
    k: float = DEFAULT_K_FACTOR,
) -> tuple[float, float]:
    """Compute updated ratings after one match.

    score_a in [0, 1] (1 = A won, 0 = B won, 0.5 = draw).
    Returns (new_rating_a, new_rating_b).
    """
    if not 0.0 <= score_a <= 1.0:
        raise ValueError(f"score_a must be in [0, 1], got {score_a}")
    expected_a = expected_score(rating_a, rating_b)
    delta = k * (score_a - expected_a)
    return rating_a + delta, rating_b - delta


@dataclass
class EloRatingSystem:
    """Tracks Elo ratings for any number of named players."""

    k_factor: float = DEFAULT_K_FACTOR
    base_rating: float = DEFAULT_RATING
    _ratings: dict[str, float] = field(default_factory=dict)
    _games: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Seed bot anchors
        for name, rating in BOT_ANCHOR_RATINGS.items():
            self._ratings.setdefault(name, rating)
            self._games.setdefault(name, 0)

    def get_rating(self, player_id: str) -> float:
        """Return current rating for a player (auto-creates at base rating)."""
        if player_id not in self._ratings:
            self._ratings[player_id] = self.base_rating
            self._games[player_id] = 0
        return self._ratings[player_id]

    def games_played(self, player_id: str) -> int:
        return self._games.get(player_id, 0)

    def record_match(
        self, player_a: str, player_b: str, score_a: float
    ) -> tuple[float, float]:
        """Record a single match and update both players' ratings."""
        ra = self.get_rating(player_a)
        rb = self.get_rating(player_b)
        new_ra, new_rb = update_ratings(ra, rb, score_a, k=self.k_factor)
        self._ratings[player_a] = new_ra
        self._ratings[player_b] = new_rb
        self._games[player_a] = self._games.get(player_a, 0) + 1
        self._games[player_b] = self._games.get(player_b, 0) + 1
        return new_ra, new_rb

    def update_from_eval(self, result: EvalResult) -> None:
        """Apply N games' worth of outcomes from one EvalResult.

        We treat each of the n_games games as a separate match between
        the model and the bot, with score_a derived from win_rate.
        For aggregated stability, we apply n_games * win_rate wins and
        n_games * (1 - win_rate) losses sequentially.
        """
        model_id = result.model_path
        bot_id = bot_player_id(result.bot_level)

        n_wins = round(result.n_games * result.win_rate)
        n_losses = result.n_games - n_wins

        for _ in range(n_wins):
            self.record_match(model_id, bot_id, score_a=1.0)
        for _ in range(n_losses):
            self.record_match(model_id, bot_id, score_a=0.0)

    def update_from_evals(self, results: list[EvalResult]) -> None:
        """Apply a batch of evaluation results."""
        for r in results:
            self.update_from_eval(r)

    def leaderboard(self) -> list[tuple[str, float, int]]:
        """Return players sorted by rating descending: (id, rating, games)."""
        return sorted(
            ((pid, rating, self._games.get(pid, 0)) for pid, rating in self._ratings.items()),
            key=lambda row: row[1],
            reverse=True,
        )

    def to_dict(self) -> dict[str, dict[str, float | int]]:
        """Serialize the full rating table for storage or reporting."""
        return {
            pid: {"rating": self._ratings[pid], "games": self._games.get(pid, 0)}
            for pid in self._ratings
        }
