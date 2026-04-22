"""League Elo pure helpers (B-impl-3)."""

from __future__ import annotations

import pytest

from backend.app.services.league_elo import (
    K_ANNEAL_GAMES,
    K_EARLY,
    K_LATE,
    apply_match_result,
    expected_score,
    is_anchor,
    k_factor_for_games,
    update_elo,
)


class TestKFactorAnneal:
    def test_early_k_below_threshold(self):
        assert k_factor_for_games(0) == K_EARLY
        assert k_factor_for_games(K_ANNEAL_GAMES - 1) == K_EARLY

    def test_late_k_at_and_above_threshold(self):
        # ADR: "strictly less than" boundary — games == 30 uses late K.
        assert k_factor_for_games(K_ANNEAL_GAMES) == K_LATE
        assert k_factor_for_games(K_ANNEAL_GAMES + 10) == K_LATE

    def test_k_early_is_16_k_late_is_8(self):
        assert K_EARLY == 16
        assert K_LATE == 8


class TestExpectedScore:
    def test_equal_ratings_expect_half(self):
        assert expected_score(1000, 1000) == pytest.approx(0.5)

    def test_400_point_gap_is_roughly_91_percent(self):
        # Textbook: 400-point gap ≈ 91% expectation for the higher.
        e = expected_score(1400, 1000)
        assert e == pytest.approx(0.9090909, abs=1e-6)

    def test_symmetric(self):
        e_a = expected_score(1200, 1050)
        e_b = expected_score(1050, 1200)
        assert e_a + e_b == pytest.approx(1.0)


class TestUpdateElo:
    def test_winner_gains_loser_loses_same_amount(self):
        new_a, new_b = update_elo(1000, 1000, winner=1, k_factor=16)
        # Equal ratings, A wins, K=16 → A gains +8, B loses 8.
        assert new_a == pytest.approx(1008.0)
        assert new_b == pytest.approx(992.0)
        # Sum is conserved.
        assert new_a + new_b == pytest.approx(2000.0)

    def test_winner_gets_smaller_gain_when_already_favored(self):
        # 200-point favorite still wins — small gain (expected to win).
        new_a, _ = update_elo(1200, 1000, winner=1, k_factor=16)
        delta = new_a - 1200
        assert 0 < delta < 8  # less than the equal-rating gain

    def test_underdog_upset_yields_large_gain(self):
        new_a, _ = update_elo(900, 1200, winner=1, k_factor=16)
        delta = new_a - 900
        assert delta > 8

    def test_winner_2_swaps_roles(self):
        new_a, new_b = update_elo(1000, 1000, winner=2, k_factor=16)
        assert new_a == pytest.approx(992.0)
        assert new_b == pytest.approx(1008.0)

    def test_invalid_winner_raises(self):
        with pytest.raises(ValueError, match="winner must be 1 or 2"):
            update_elo(1000, 1000, winner=0, k_factor=16)
        with pytest.raises(ValueError, match="winner must be 1 or 2"):
            update_elo(1000, 1000, winner=3, k_factor=16)

    def test_k_factor_scales_movement_linearly(self):
        new_a_k16, _ = update_elo(1000, 1000, winner=1, k_factor=16)
        new_a_k8, _ = update_elo(1000, 1000, winner=1, k_factor=8)
        assert (new_a_k16 - 1000) == pytest.approx(2 * (new_a_k8 - 1000))


class TestIsAnchor:
    def test_anchor_ids_detected(self):
        assert is_anchor("L1")
        assert is_anchor("L3")
        assert is_anchor("L5")

    def test_unknown_anchor_levels_rejected(self):
        # We don't anchor L2 / L4 in the ADR — only L1/L3/L5.
        assert not is_anchor("L2")
        assert not is_anchor("L4")

    def test_training_checkpoint_not_anchor(self):
        assert not is_anchor("run-baseline__abcdef01__200000")

    def test_case_sensitive(self):
        # Substring / case collapse would incorrectly flag a
        # training checkpoint named ``l1_variant`` as anchor.
        assert not is_anchor("l1")
        assert not is_anchor("L1_variant")
        assert not is_anchor("")


class TestApplyMatchResult:
    def test_both_non_anchors_update_normally(self):
        new_a, new_b = apply_match_result(
            rating_a=1000, games_a=5,
            rating_b=1050, games_b=5,
            winner=1,
            id_a="run-a", id_b="run-b",
        )
        assert new_a > 1000
        assert new_b < 1050

    def test_anchor_side_rating_preserved(self):
        # A (anchor) beats B (non-anchor) — A's rating does NOT move.
        new_a, new_b = apply_match_result(
            rating_a=900, games_a=0,
            rating_b=1000, games_b=10,
            winner=1,
            id_a="L3", id_b="run-x",
        )
        assert new_a == 900  # anchor stays pinned
        assert new_b < 1000  # non-anchor still moves

    def test_both_anchors_noop(self):
        # Degenerate case: anchor-vs-anchor (e.g. the migration script
        # accidentally pairs L1 and L5). Both ratings preserved.
        new_a, new_b = apply_match_result(
            rating_a=600, games_a=0,
            rating_b=1200, games_b=0,
            winner=1,
            id_a="L1", id_b="L5",
        )
        assert new_a == 600
        assert new_b == 1200

    def test_k_factor_uses_min_games(self):
        # One side has 0 games (K=16), the other has 100 (K=8).
        # The update uses min(16, 8) = 8 — fully-annealed pair.
        new_a, _ = apply_match_result(
            rating_a=1000, games_a=0,
            rating_b=1000, games_b=100,
            winner=1,
            id_a="a", id_b="b",
        )
        # At K=8, winner gets +4 exactly (equal ratings).
        assert new_a - 1000 == pytest.approx(4.0)

    def test_k_factor_uses_early_when_both_fresh(self):
        new_a, _ = apply_match_result(
            rating_a=1000, games_a=0,
            rating_b=1000, games_b=0,
            winner=1,
            id_a="a", id_b="b",
        )
        assert new_a - 1000 == pytest.approx(8.0)  # K=16, equal ratings

    def test_anchor_id_none_falls_through(self):
        # No ids supplied → apply_match_result treats both as non-anchor.
        new_a, new_b = apply_match_result(
            rating_a=1000, games_a=5,
            rating_b=1000, games_b=5,
            winner=1,
        )
        assert new_a != 1000
        assert new_b != 1000
