"""League REST API — standings + checkpoint detail (B-impl-4)."""

from __future__ import annotations

import pytest

from backend.app.models.league import (
    LEAGUE_POOL_SIZE,
    LeagueCheckpoint,
    LeagueManifest,
    now_iso,
)


def _seed_manifest(client, *, checkpoints, champion_id=None, generation=0):
    repo = client.app.state.league_repository
    repo.save_manifest(LeagueManifest(
        checkpoints=checkpoints,
        champion_id=champion_id,
        generation=generation,
    ))


def _ckpt(cid, *, elo=1000.0, games=0, wins=0, losses=0,
          source="training", step=None, experiment_id=None):
    return LeagueCheckpoint.model_validate({
        "id": cid,
        "elo": elo,
        "wins": wins,
        "losses": losses,
        "games": games,
        "admitted_at": now_iso(),
        "source": source,
        "step": step,
        "experiment_id": experiment_id,
    })


class TestStandingsEndpoint:
    def test_empty_pool_returns_empty_envelope(self, client):
        _seed_manifest(client, checkpoints=[])
        resp = client.get("/api/league/standings")
        assert resp.status_code == 200
        body = resp.json()
        assert body["top"] == []
        assert body["champion_id"] is None
        assert body["generation"] == 0
        assert body["pool_size"] == LEAGUE_POOL_SIZE
        assert body["total_checkpoints"] == 0

    def test_top_n_sorted_by_elo_desc(self, client):
        _seed_manifest(client, checkpoints=[
            _ckpt("b", elo=1100),
            _ckpt("a", elo=1300),
            _ckpt("c", elo=900),
        ])
        resp = client.get("/api/league/standings?limit=3")
        body = resp.json()
        assert [c["id"] for c in body["top"]] == ["a", "b", "c"]
        assert body["total_checkpoints"] == 3

    def test_limit_query_bounded(self, client):
        # >100 → 422 from pydantic.
        resp = client.get("/api/league/standings?limit=500")
        assert resp.status_code == 422

    def test_limit_truncates(self, client):
        _seed_manifest(client, checkpoints=[
            _ckpt(f"c{i}", elo=1000 + i) for i in range(20)
        ])
        resp = client.get("/api/league/standings?limit=5")
        assert len(resp.json()["top"]) == 5

    def test_champion_id_surfaced(self, client):
        _seed_manifest(
            client,
            checkpoints=[_ckpt("a", elo=1200)],
            champion_id="a",
            generation=7,
        )
        body = client.get("/api/league/standings").json()
        assert body["champion_id"] == "a"
        assert body["generation"] == 7


class TestCheckpointDetailEndpoint:
    def test_unknown_checkpoint_returns_404(self, client):
        _seed_manifest(client, checkpoints=[])
        resp = client.get("/api/league/checkpoint/not-there")
        assert resp.status_code == 404

    def test_known_checkpoint_returns_detail(self, client):
        _seed_manifest(client, checkpoints=[
            _ckpt("x", elo=1055, wins=3, losses=1, games=4,
                  step=200000, experiment_id="exp-a"),
        ])
        resp = client.get("/api/league/checkpoint/x")
        assert resp.status_code == 200
        body = resp.json()
        assert body["checkpoint"]["id"] == "x"
        assert body["checkpoint"]["elo"] == 1055
        assert body["checkpoint"]["step"] == 200_000
        assert isinstance(body["head_to_head"], list)

    def test_oversize_id_rejected(self, client):
        resp = client.get("/api/league/checkpoint/" + "x" * 201)
        assert resp.status_code == 400

    def test_anchor_row_has_no_head_to_head(self, client):
        # Anchor rows have no experiment_id → head_to_head always [].
        _seed_manifest(client, checkpoints=[
            _ckpt("L3", elo=900, source="anchor"),
        ])
        body = client.get("/api/league/checkpoint/L3").json()
        assert body["checkpoint"]["source"] == "anchor"
        assert body["head_to_head"] == []


class TestFallbackWhenRepositoryMissing:
    def test_standings_empty_when_repository_unwired(self, client):
        # Simulate older deployments that haven't wired the repo yet.
        original = client.app.state.league_repository
        client.app.state.league_repository = None
        try:
            resp = client.get("/api/league/standings")
            assert resp.status_code == 200
            body = resp.json()
            assert body["top"] == []
            assert body["pool_size"] == LEAGUE_POOL_SIZE
        finally:
            client.app.state.league_repository = original

    def test_detail_503_when_repository_unwired(self, client):
        original = client.app.state.league_repository
        client.app.state.league_repository = None
        try:
            resp = client.get("/api/league/checkpoint/x")
            assert resp.status_code == 503
        finally:
            client.app.state.league_repository = original
