"""TrainingServiceWrapper.start — league kwarg forwarding (hotfix).

Regression guard for the v2 Sprint-1 runtime crash:

    TypeError: TrainingServiceWrapper.start() got an unexpected
    keyword argument 'training_mode'

The WS handler (backend/app/ws/handlers.py, B-impl-7) forwards
``training_mode`` + ``opponent_provider`` in its ``start_kwargs``
dict, but the wrapper's signature didn't accept them, so any
self-play run died on the first ``training:start`` message.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


class TestWrapperStartAcceptsLeagueKwargs:
    @pytest.mark.asyncio
    async def test_training_mode_does_not_raise_type_error(self):
        """This is the exact call the WS handler makes — must not raise."""
        from backend.app.services.training_service import TrainingServiceWrapper

        wrapper = TrainingServiceWrapper.__new__(TrainingServiceWrapper)
        wrapper.manager = MagicMock()
        wrapper.manager.start = AsyncMock(return_value="exp-league")
        # Regression: this call previously raised TypeError. It must
        # now succeed and the kwargs must reach the manager.
        await wrapper.start(
            bot_level=3,
            total_timesteps=500_000,
            training_mode="self_play",
            opponent_provider=MagicMock(),
        )
        kwargs = wrapper.manager.start.await_args.kwargs
        assert kwargs["training_mode"] == "self_play"
        assert kwargs["opponent_provider"] is not None

    @pytest.mark.asyncio
    async def test_bot_ladder_default_preserved(self):
        """Old callers (no league kwargs) still work — kwargs default
        to manager-compatible values."""
        from backend.app.services.training_service import TrainingServiceWrapper

        wrapper = TrainingServiceWrapper.__new__(TrainingServiceWrapper)
        wrapper.manager = MagicMock()
        wrapper.manager.start = AsyncMock(return_value="exp-v1")
        await wrapper.start(bot_level=1, total_timesteps=500_000)
        kwargs = wrapper.manager.start.await_args.kwargs
        # When the caller omits training_mode, wrapper falls through
        # to the manager's default (``bot_ladder``). The wrapper is a
        # thin passthrough — it does not force self_play without
        # caller opt-in.
        assert kwargs.get("training_mode", "bot_ladder") == "bot_ladder"
        assert kwargs.get("opponent_provider") is None

    @pytest.mark.asyncio
    async def test_end_to_end_from_ws_handler_dispatch(self):
        """Actually dispatch the training:start message through the
        WS handler with self_play + a seeded league pool, and assert
        the wrapper call succeeds (no TypeError surfaces).
        """
        from backend.app.models.league import (
            LeagueCheckpoint,
            LeagueManifest,
            now_iso,
        )
        from backend.app.models.schemas import WsTrainingStartPayload
        from backend.app.services.league_repository import LeagueRepository
        from backend.app.services.training_service import TrainingServiceWrapper
        from backend.app.ws.handlers import _dispatch
        from backend.app.ws.validation import ParsedMessage

        # Real wrapper with a fake manager — so we're exercising the
        # wrapper's signature, not a MagicMock wildcard.
        wrapper = TrainingServiceWrapper.__new__(TrainingServiceWrapper)
        wrapper.manager = MagicMock()
        wrapper.manager.start = AsyncMock(return_value="exp-e2e")
        wrapper.status = MagicMock(return_value={
            "state": "stopped", "current_step": 0, "current_episode": 0,
            "experiment_id": None, "bot_level": 1, "started_at": None,
            "title": "",
        })

        # Seed one training-source checkpoint so PFSPProvider builds.
        import tempfile

        repo = LeagueRepository(db=None, league_dir=tempfile.mkdtemp())
        repo.save_manifest(LeagueManifest(checkpoints=[
            LeagueCheckpoint.model_validate({
                "id": "run-a", "elo": 1050, "wins": 0, "losses": 0,
                "games": 0, "admitted_at": now_iso(), "source": "training",
            }),
        ]))
        ws = MagicMock()
        ws.send_json = AsyncMock()
        ws.app = MagicMock()
        ws.app.state.league_repository = repo
        manager = MagicMock()
        manager.broadcast = AsyncMock()

        parsed = ParsedMessage(
            type="training:start",
            payload=WsTrainingStartPayload(
                mode="self_play", sampling="pfsp",
                total_timesteps=500_000,
            ),
        )
        # Before the hotfix this raised TypeError inside _dispatch.
        await _dispatch(ws, parsed, wrapper, MagicMock(), manager)
        # Sanity: wrapper was actually called with the league kwargs.
        kwargs = wrapper.manager.start.await_args.kwargs
        assert kwargs["training_mode"] == "self_play"
        assert kwargs["opponent_provider"] is not None
