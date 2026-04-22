"""training:start mode/sampling extension (B-impl-7)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from backend.app.models.league import (
    LeagueCheckpoint,
    LeagueManifest,
    now_iso,
)
from backend.app.models.schemas import WsTrainingStartPayload


class TestPayloadValidation:
    def test_mode_defaults_to_bot_ladder(self):
        p = WsTrainingStartPayload()
        assert p.mode == "bot_ladder"
        assert p.sampling == "pfsp"

    def test_mode_accepts_self_play(self):
        p = WsTrainingStartPayload(mode="self_play")
        assert p.mode == "self_play"

    def test_mode_rejects_unknown(self):
        with pytest.raises(ValidationError):
            WsTrainingStartPayload(mode="banana")

    def test_sampling_rejects_unknown(self):
        with pytest.raises(ValidationError):
            WsTrainingStartPayload(sampling="random")

    def test_sampling_accepts_all_three_strategies(self):
        for s in ("uniform", "elo_proximity", "pfsp"):
            p = WsTrainingStartPayload(sampling=s)
            assert p.sampling == s


class TestHandlerProviderBuilder:
    """``_build_league_opponent_provider`` wires a PFSPProvider when
    possible and returns None to signal fallback."""

    def _app_with_pool(self, tmp_path, *, include_anchors=True,
                       include_training=True):
        from backend.app.services.league_repository import LeagueRepository

        repo = LeagueRepository(db=None, league_dir=str(tmp_path / "league"))
        ckpts = []
        if include_anchors:
            ckpts.append(LeagueCheckpoint.model_validate({
                "id": "L3", "elo": 900, "wins": 0, "losses": 0,
                "games": 0, "admitted_at": now_iso(), "source": "anchor",
            }))
        if include_training:
            ckpts.append(LeagueCheckpoint.model_validate({
                "id": "run-a", "elo": 1050, "wins": 0, "losses": 0,
                "games": 0, "admitted_at": now_iso(), "source": "training",
            }))
        repo.save_manifest(LeagueManifest(checkpoints=ckpts))
        app = MagicMock()
        app.state.league_repository = repo
        return app

    def test_returns_none_when_repository_unwired(self):
        from backend.app.ws.handlers import _build_league_opponent_provider

        app = MagicMock()
        # Explicitly drop the attribute so getattr returns None.
        del app.state.league_repository
        app.state = MagicMock(spec=[])
        assert _build_league_opponent_provider(app, "pfsp") is None

    def test_returns_none_when_pool_empty(self, tmp_path):
        from backend.app.ws.handlers import _build_league_opponent_provider

        app = self._app_with_pool(
            tmp_path, include_anchors=False, include_training=False,
        )
        assert _build_league_opponent_provider(app, "pfsp") is None

    def test_returns_none_when_only_anchors_present(self, tmp_path):
        """Anchor rows aren't valid opponents (no .zip to load from).

        Until at least one training checkpoint is admitted, the
        provider must fall back to bot_ladder.
        """
        from backend.app.ws.handlers import _build_league_opponent_provider

        app = self._app_with_pool(
            tmp_path, include_anchors=True, include_training=False,
        )
        assert _build_league_opponent_provider(app, "pfsp") is None

    def test_builds_pfsp_when_training_ckpt_present(self, tmp_path):
        from backend.app.ws.handlers import _build_league_opponent_provider

        app = self._app_with_pool(tmp_path)
        provider = _build_league_opponent_provider(app, "pfsp")
        assert provider is not None
        # strategy was forwarded.
        assert provider.strategy == "pfsp"
        # Only non-anchor rows made it into the pool.
        assert all(c.id != "L3" for c in provider.pool)

    def test_invalid_strategy_returns_none(self, tmp_path):
        """PFSPProvider raises on unknown strategy — builder swallows.

        We rely on pydantic to have rejected the strategy upstream, but
        the builder has a defensive catch so a config drift can't kill
        the training start handler.
        """
        from backend.app.ws.handlers import _build_league_opponent_provider

        app = self._app_with_pool(tmp_path)
        # ``strategy="banana"`` is rejected at pydantic parse time
        # in real flow; the builder's try/except is the safety net for
        # pre-validation callers or future schema drift.
        assert _build_league_opponent_provider(app, "banana") is None


class TestHandlerForwarding:
    """training:start WS handler forwards mode/sampling to the manager."""

    @staticmethod
    def _fake_service():
        svc = MagicMock()
        svc.status.return_value = {
            "state": "stopped",
            "current_step": 0, "current_episode": 0,
            "experiment_id": None, "bot_level": 1,
            "started_at": None, "title": "",
        }
        svc.start = AsyncMock(return_value="exp-v2")
        return svc

    @pytest.mark.asyncio
    async def test_bot_ladder_mode_does_not_set_opponent_provider(self):
        from backend.app.ws.handlers import _dispatch
        from backend.app.ws.validation import ParsedMessage

        svc = self._fake_service()
        parsed = ParsedMessage(
            type="training:start",
            payload=WsTrainingStartPayload(mode="bot_ladder"),
        )
        ws = MagicMock()
        ws.send_json = AsyncMock()
        manager = MagicMock()
        manager.broadcast = AsyncMock()

        await _dispatch(ws, parsed, svc, MagicMock(), manager)
        kwargs = svc.start.await_args.kwargs
        # bot_ladder → manager default path; handler doesn't add
        # training_mode/opponent_provider kwargs.
        assert "training_mode" not in kwargs
        assert "opponent_provider" not in kwargs

    @pytest.mark.asyncio
    async def test_self_play_with_empty_pool_falls_back_silently(self):
        """FE requested self_play but no pool → handler downgrades to
        bot_ladder, start() still succeeds."""
        from backend.app.ws.handlers import _dispatch
        from backend.app.ws.validation import ParsedMessage

        svc = self._fake_service()
        parsed = ParsedMessage(
            type="training:start",
            payload=WsTrainingStartPayload(mode="self_play"),
        )
        ws = MagicMock()
        ws.send_json = AsyncMock()
        ws.app = None  # no app context — provider builder returns None
        manager = MagicMock()
        manager.broadcast = AsyncMock()

        await _dispatch(ws, parsed, svc, MagicMock(), manager)
        # Fell back: no training_mode/opponent_provider passed.
        kwargs = svc.start.await_args.kwargs
        assert "training_mode" not in kwargs
        assert "opponent_provider" not in kwargs
