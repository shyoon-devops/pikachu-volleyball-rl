"""LeagueRepository CRUD + manifest sync (B-impl-2)."""

from __future__ import annotations

import json

import pytest

from backend.app.models.league import (
    LEAGUE_POOL_SIZE,
    LeagueCheckpoint,
    LeagueManifest,
    now_iso,
)
from backend.app.services.league_repository import LeagueRepository


def _ckpt(cid: str, *, elo: float = 1000.0, games: int = 0,
          wins: int = 0, losses: int = 0,
          source: str = "training") -> LeagueCheckpoint:
    return LeagueCheckpoint.model_validate({
        "id": cid,
        "elo": elo,
        "wins": wins,
        "losses": losses,
        "games": games,
        "admitted_at": now_iso(),
        "source": source,
    })


class TestManifestDiskIO:
    @pytest.mark.asyncio
    async def test_missing_manifest_returns_empty(self, tmp_path):
        repo = LeagueRepository(db=None, league_dir=str(tmp_path / "league"))
        m = repo.load_manifest()
        assert m.checkpoints == []
        assert m.champion_id is None
        assert m.pool_size == LEAGUE_POOL_SIZE

    @pytest.mark.asyncio
    async def test_save_then_load_roundtrip(self, tmp_path):
        repo = LeagueRepository(db=None, league_dir=str(tmp_path / "league"))
        original = LeagueManifest(
            checkpoints=[_ckpt("a", elo=1100), _ckpt("b", elo=900)],
            champion_id="a",
            generation=3,
        )
        repo.save_manifest(original)
        reloaded = repo.load_manifest()
        assert {c.id for c in reloaded.checkpoints} == {"a", "b"}
        assert reloaded.champion_id == "a"
        assert reloaded.generation == 3

    @pytest.mark.asyncio
    async def test_save_is_atomic_via_rename(self, tmp_path):
        """No ``.tmp`` file is left behind after a successful save."""
        league_dir = tmp_path / "league"
        repo = LeagueRepository(db=None, league_dir=str(league_dir))
        repo.save_manifest(LeagueManifest(checkpoints=[_ckpt("x")]))
        names = {p.name for p in league_dir.iterdir()}
        assert "manifest.json" in names
        assert not any(n.endswith(".tmp") for n in names)

    @pytest.mark.asyncio
    async def test_load_rejects_malformed_json(self, tmp_path):
        """Bogus manifest surfaces at load time (via Pydantic)."""
        league_dir = tmp_path / "league"
        league_dir.mkdir()
        (league_dir / "manifest.json").write_text(
            json.dumps({"checkpoints": [{"id": "x", "elo": -1}]}),
            encoding="utf-8",
        )
        repo = LeagueRepository(db=None, league_dir=str(league_dir))
        with pytest.raises(Exception):
            repo.load_manifest()


class TestMongoFallback:
    """Mongo-less deployments read from the manifest directly."""

    @pytest.mark.asyncio
    async def test_list_top_n_falls_back_to_manifest(self, tmp_path):
        repo = LeagueRepository(db=None, league_dir=str(tmp_path / "league"))
        repo.save_manifest(LeagueManifest(
            checkpoints=[
                _ckpt("a", elo=1200),
                _ckpt("b", elo=900),
                _ckpt("c", elo=1100),
            ]
        ))
        top = await repo.list_top_n(n=2)
        assert [c.id for c in top] == ["a", "c"]

    @pytest.mark.asyncio
    async def test_get_checkpoint_falls_back_to_manifest(self, tmp_path):
        repo = LeagueRepository(db=None, league_dir=str(tmp_path / "league"))
        repo.save_manifest(LeagueManifest(
            checkpoints=[_ckpt("only", elo=1050, games=7)]
        ))
        c = await repo.get_checkpoint("only")
        assert c is not None and c.elo == 1050 and c.games == 7

    @pytest.mark.asyncio
    async def test_get_checkpoint_none_when_absent(self, tmp_path):
        repo = LeagueRepository(db=None, league_dir=str(tmp_path / "league"))
        assert (await repo.get_checkpoint("not-there")) is None


class TestStandingsEnvelope:
    @pytest.mark.asyncio
    async def test_envelope_carries_summary_fields(self, tmp_path):
        repo = LeagueRepository(db=None, league_dir=str(tmp_path / "league"))
        repo.save_manifest(LeagueManifest(
            checkpoints=[_ckpt("a", elo=1200)],
            champion_id="a",
            generation=5,
            pool_size=LEAGUE_POOL_SIZE,
        ))
        env = await repo.standings_envelope(limit=5)
        assert env.champion_id == "a"
        assert env.generation == 5
        assert env.pool_size == LEAGUE_POOL_SIZE
        assert env.total_checkpoints == 1
        assert [c.id for c in env.top] == ["a"]


class TestUpdateEloBatch:
    @pytest.mark.asyncio
    async def test_batch_updates_ratings_and_games(self, tmp_path):
        repo = LeagueRepository(db=None, league_dir=str(tmp_path / "league"))
        repo.save_manifest(LeagueManifest(
            checkpoints=[
                _ckpt("a", elo=1000, games=0),
                _ckpt("b", elo=1000, games=0),
            ]
        ))
        await repo.update_elo_batch([
            {"id_a": "a", "id_b": "b", "winner": 1},
        ])
        m = repo.load_manifest()
        a = next(c for c in m.checkpoints if c.id == "a")
        b = next(c for c in m.checkpoints if c.id == "b")
        assert a.elo > 1000
        assert b.elo < 1000
        assert a.games == 1
        assert a.wins == 1
        assert b.losses == 1
        assert m.champion_id == "a"

    @pytest.mark.asyncio
    async def test_batch_skips_anchor_rating_but_increments_games(self, tmp_path):
        repo = LeagueRepository(db=None, league_dir=str(tmp_path / "league"))
        repo.save_manifest(LeagueManifest(
            checkpoints=[
                _ckpt("L3", elo=900, source="anchor"),
                _ckpt("b", elo=1000, games=0),
            ]
        ))
        await repo.update_elo_batch([
            {"id_a": "L3", "id_b": "b", "winner": 1},
        ])
        m = repo.load_manifest()
        anchor = next(c for c in m.checkpoints if c.id == "L3")
        b = next(c for c in m.checkpoints if c.id == "b")
        assert anchor.elo == 900  # pinned
        assert anchor.games == 1  # still tracked
        assert anchor.wins == 1
        assert b.elo < 1000  # non-anchor moves

    @pytest.mark.asyncio
    async def test_empty_batch_noop(self, tmp_path):
        repo = LeagueRepository(db=None, league_dir=str(tmp_path / "league"))
        await repo.update_elo_batch([])
        assert repo.load_manifest().checkpoints == []

    @pytest.mark.asyncio
    async def test_malformed_result_logged_and_skipped(self, tmp_path, caplog):
        repo = LeagueRepository(db=None, league_dir=str(tmp_path / "league"))
        repo.save_manifest(LeagueManifest(
            checkpoints=[_ckpt("a"), _ckpt("b")]
        ))
        await repo.update_elo_batch([
            {"id_a": "a"},  # missing id_b + winner
            {"id_a": "a", "id_b": "missing", "winner": 1},  # unknown id_b
            {"id_a": "a", "id_b": "b", "winner": 1},  # good
        ])
        m = repo.load_manifest()
        a = next(c for c in m.checkpoints if c.id == "a")
        # Only the one good result applied.
        assert a.games == 1

    @pytest.mark.asyncio
    async def test_champion_updates_on_rating_flip(self, tmp_path):
        repo = LeagueRepository(db=None, league_dir=str(tmp_path / "league"))
        repo.save_manifest(LeagueManifest(
            checkpoints=[
                _ckpt("a", elo=1050),
                _ckpt("b", elo=1000),
            ],
            champion_id="a",
        ))
        # Force enough upsets that b overtakes a.
        results = [{"id_a": "a", "id_b": "b", "winner": 2}] * 20
        await repo.update_elo_batch(results)
        m = repo.load_manifest()
        b = next(c for c in m.checkpoints if c.id == "b")
        a = next(c for c in m.checkpoints if c.id == "a")
        assert b.elo > a.elo
        assert m.champion_id == "b"
