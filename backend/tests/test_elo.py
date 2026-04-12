"""Tests for the Elo rating system."""

from __future__ import annotations

import pytest

from backend.rl.elo import (
    BOT_ANCHOR_RATINGS,
    DEFAULT_K_FACTOR,
    DEFAULT_RATING,
    EloRatingSystem,
    bot_player_id,
    expected_score,
    update_ratings,
)
from backend.rl.evaluator import EvalResult


def _make_eval(
    *,
    model_path: str = "/models/m1",
    bot_level: int = 1,
    n_games: int = 10,
    win_rate: float = 0.5,
) -> EvalResult:
    return EvalResult(
        model_path=model_path,
        bot_level=bot_level,
        n_games=n_games,
        win_rate=win_rate,
        avg_score=10.0,
        avg_opponent_score=10.0,
        avg_rally_length=80.0,
        avg_episode_length=5000.0,
        timestamp="2026-04-12T00:00:00+00:00",
        dominance_score=0.5,
    )


class TestExpectedScore:
    def test_equal_ratings_yields_half(self) -> None:
        assert expected_score(1500.0, 1500.0) == pytest.approx(0.5)

    def test_higher_rating_favored(self) -> None:
        assert expected_score(1700.0, 1500.0) > 0.5

    def test_400_point_diff_is_about_91_percent(self) -> None:
        # Standard Elo: 400 point gap → ~0.909
        assert expected_score(1900.0, 1500.0) == pytest.approx(0.909, abs=0.01)


class TestUpdateRatings:
    def test_winning_increases_rating(self) -> None:
        new_a, new_b = update_ratings(1500.0, 1500.0, score_a=1.0)
        assert new_a > 1500.0
        assert new_b < 1500.0
        # Symmetric: total points conserved
        assert new_a + new_b == pytest.approx(3000.0)

    def test_losing_decreases_rating(self) -> None:
        new_a, new_b = update_ratings(1500.0, 1500.0, score_a=0.0)
        assert new_a < 1500.0
        assert new_b > 1500.0

    def test_draw_no_change_when_equal(self) -> None:
        new_a, new_b = update_ratings(1500.0, 1500.0, score_a=0.5)
        assert new_a == pytest.approx(1500.0)
        assert new_b == pytest.approx(1500.0)

    def test_invalid_score_raises(self) -> None:
        with pytest.raises(ValueError):
            update_ratings(1500.0, 1500.0, score_a=1.5)

    def test_k_factor_scales_delta(self) -> None:
        a1, _ = update_ratings(1500.0, 1500.0, 1.0, k=16.0)
        a2, _ = update_ratings(1500.0, 1500.0, 1.0, k=32.0)
        # Bigger k -> bigger swing
        assert (a2 - 1500.0) == pytest.approx(2 * (a1 - 1500.0))


class TestEloRatingSystem:
    def test_bot_anchors_seeded(self) -> None:
        rs = EloRatingSystem()
        for name, rating in BOT_ANCHOR_RATINGS.items():
            assert rs.get_rating(name) == rating

    def test_new_player_gets_base_rating(self) -> None:
        rs = EloRatingSystem()
        assert rs.get_rating("model_x") == DEFAULT_RATING

    def test_record_match_updates_both(self) -> None:
        rs = EloRatingSystem()
        ra_new, rb_new = rs.record_match("model_x", "bot_L1", score_a=1.0)
        assert rs.get_rating("model_x") == ra_new
        assert rs.get_rating("bot_L1") == rb_new
        assert rs.games_played("model_x") == 1
        assert rs.games_played("bot_L1") == 1

    def test_update_from_eval_n_games(self) -> None:
        rs = EloRatingSystem()
        ev = _make_eval(model_path="m1", bot_level=3, n_games=10, win_rate=0.7)
        rs.update_from_eval(ev)
        # 10 matches recorded against bot_L3
        assert rs.games_played("m1") == 10
        assert rs.games_played("bot_L3") == 10
        # Winning 70% against an equal-rated bot → rating should rise
        assert rs.get_rating("m1") > DEFAULT_RATING

    def test_higher_win_rate_yields_higher_rating(self) -> None:
        rs1 = EloRatingSystem()
        rs2 = EloRatingSystem()
        rs1.update_from_eval(_make_eval(model_path="m_lo", win_rate=0.2))
        rs2.update_from_eval(_make_eval(model_path="m_hi", win_rate=0.9))
        assert rs2.get_rating("m_hi") > rs1.get_rating("m_lo")

    def test_leaderboard_sorted_descending(self) -> None:
        rs = EloRatingSystem()
        rs.update_from_eval(_make_eval(model_path="weak", win_rate=0.1))
        rs.update_from_eval(_make_eval(model_path="strong", win_rate=0.9))
        board = rs.leaderboard()
        ratings_only = [r for _, r, _ in board]
        assert ratings_only == sorted(ratings_only, reverse=True)
        # Weak model below the strong one
        ids = [pid for pid, _, _ in board]
        assert ids.index("strong") < ids.index("weak")

    def test_bot_player_id(self) -> None:
        assert bot_player_id(3) == "bot_L3"
        with pytest.raises(ValueError):
            bot_player_id(7)

    def test_to_dict_includes_anchors_when_fresh(self) -> None:
        rs = EloRatingSystem()
        d = rs.to_dict()
        assert d["bot_L1"]["rating"] == BOT_ANCHOR_RATINGS["bot_L1"]
        assert d["bot_L5"]["rating"] == BOT_ANCHOR_RATINGS["bot_L5"]

    def test_to_dict_includes_models(self) -> None:
        rs = EloRatingSystem()
        rs.update_from_eval(_make_eval(model_path="m1", win_rate=0.5))
        d = rs.to_dict()
        assert "m1" in d
        assert "rating" in d["m1"] and "games" in d["m1"]
        assert d["m1"]["games"] == 10

    def test_default_k_factor(self) -> None:
        # Make sure the published constant matches the system default
        rs = EloRatingSystem()
        assert rs.k_factor == DEFAULT_K_FACTOR
