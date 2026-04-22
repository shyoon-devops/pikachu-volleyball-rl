"""Pydantic league schemas (B-impl-1)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.models.league import (
    ANCHOR_RATINGS,
    LEAGUE_POOL_SIZE,
    LeagueCheckpoint,
    LeagueManifest,
    LeagueStandings,
    SEED_ELO,
    now_iso,
)


class TestConstants:
    def test_pool_size_matches_adr(self):
        assert LEAGUE_POOL_SIZE == 32

    def test_seed_elo_is_1000(self):
        assert SEED_ELO == 1000.0

    def test_anchor_ratings_match_adr(self):
        assert ANCHOR_RATINGS == {"L1": 600.0, "L3": 900.0, "L5": 1200.0}


class TestLeagueCheckpoint:
    def _valid_doc(self, **overrides):
        base = {
            "id": "run-baseline__a3f9bc21__200000",
            "elo": 1050.0,
            "wins": 3,
            "losses": 1,
            "games": 4,
            "admitted_at": now_iso(),
            "step": 200_000,
            "experiment_id": "a3f9bc21-aaaa-bbbb-cccc-000000000001",
            "source": "training",
        }
        base.update(overrides)
        return base

    def test_accepts_valid(self):
        doc = LeagueCheckpoint.model_validate(self._valid_doc())
        assert doc.elo == 1050.0
        assert doc.win_rate == pytest.approx(0.75)
        assert doc.is_anchor is False

    def test_rejects_negative_elo(self):
        with pytest.raises(ValidationError):
            LeagueCheckpoint.model_validate(self._valid_doc(elo=-10.0))

    def test_rejects_games_less_than_wins_plus_losses(self):
        with pytest.raises(ValidationError):
            LeagueCheckpoint.model_validate(
                self._valid_doc(wins=5, losses=3, games=4)
            )

    def test_accepts_games_greater_than_wl_for_future_draws(self):
        # Invariant is >=, not == — leaves room for draws / unterminated.
        doc = LeagueCheckpoint.model_validate(
            self._valid_doc(wins=2, losses=1, games=5)
        )
        assert doc.games == 5

    def test_rejects_malformed_timestamp(self):
        with pytest.raises(ValidationError):
            LeagueCheckpoint.model_validate(
                self._valid_doc(admitted_at="not-an-iso-string")
            )

    def test_zero_games_win_rate_is_zero(self):
        doc = LeagueCheckpoint.model_validate(
            self._valid_doc(wins=0, losses=0, games=0)
        )
        assert doc.win_rate == 0.0

    def test_anchor_source_is_flagged(self):
        doc = LeagueCheckpoint.model_validate(
            self._valid_doc(id="L3", source="anchor", elo=900.0)
        )
        assert doc.is_anchor is True

    def test_v1_legacy_source_accepted(self):
        doc = LeagueCheckpoint.model_validate(
            self._valid_doc(source="v1_legacy")
        )
        assert doc.source == "v1_legacy"

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            LeagueCheckpoint.model_validate(
                self._valid_doc(surprise_field="boom")
            )


class TestLeagueManifest:
    def _cp(self, elo, games=0, cid="run"):
        return LeagueCheckpoint.model_validate({
            "id": cid, "elo": elo, "wins": 0, "losses": 0,
            "games": games, "admitted_at": now_iso(),
            "source": "training",
        })

    def test_defaults(self):
        m = LeagueManifest()
        assert m.checkpoints == []
        assert m.champion_id is None
        assert m.generation == 0
        assert m.pool_size == LEAGUE_POOL_SIZE

    def test_top_n_sorts_by_elo_desc(self):
        m = LeagueManifest(
            checkpoints=[
                self._cp(elo=1100, cid="b"),
                self._cp(elo=1300, cid="a"),
                self._cp(elo=1000, cid="c"),
            ]
        )
        ids = [c.id for c in m.top_n(n=3)]
        assert ids == ["a", "b", "c"]

    def test_top_n_truncates(self):
        m = LeagueManifest(
            checkpoints=[self._cp(elo=1000 + i, cid=f"c{i}") for i in range(20)]
        )
        assert len(m.top_n(n=5)) == 5

    def test_top_n_breaks_tie_by_games_desc(self):
        m = LeagueManifest(
            checkpoints=[
                self._cp(elo=1000, games=10, cid="veteran"),
                self._cp(elo=1000, games=1, cid="rookie"),
            ]
        )
        ids = [c.id for c in m.top_n(n=2)]
        assert ids == ["veteran", "rookie"]

    def test_pool_size_bounds(self):
        with pytest.raises(ValidationError):
            LeagueManifest(pool_size=0)
        with pytest.raises(ValidationError):
            LeagueManifest(pool_size=5000)


class TestLeagueStandings:
    def test_envelope_shape(self):
        ckpt = LeagueCheckpoint.model_validate({
            "id": "x", "elo": 1234.5, "wins": 1, "losses": 0, "games": 1,
            "admitted_at": now_iso(), "source": "training",
        })
        body = LeagueStandings(
            top=[ckpt],
            champion_id="x",
            generation=3,
            pool_size=LEAGUE_POOL_SIZE,
            total_checkpoints=1,
        )
        dumped = body.model_dump()
        assert dumped["top"][0]["id"] == "x"
        assert dumped["champion_id"] == "x"
        assert dumped["generation"] == 3
        assert dumped["pool_size"] == LEAGUE_POOL_SIZE
        assert dumped["total_checkpoints"] == 1
