"""TrainingServiceWrapper.start forwards reward_model to TrainingManager (S2).

Unit-level: we intercept the wrapper's underlying ``manager.start``
coroutine and inspect the kwargs. The test does NOT spin up a real
PPO run — only the plumbing contract is exercised.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from backend.app.services.training_service import TrainingServiceWrapper


@pytest.fixture
def wrapper_with_mock_manager(tmp_path):
    """Wrapper wired to an AsyncMock manager.start for kwarg capture."""
    w = TrainingServiceWrapper(
        model_dir=str(tmp_path / "models"),
        replay_dir=str(tmp_path / "replays"),
    )
    w.manager.start = AsyncMock(return_value="exp-123")
    return w


class TestRewardModelForwarding:
    @pytest.mark.asyncio
    async def test_default_is_shaped_v1(self, wrapper_with_mock_manager):
        """No explicit kwarg → ``shaped_v1`` reaches the manager. Matches
        v1.0.0 behavior so legacy callers don't change semantics."""
        w = wrapper_with_mock_manager
        await w.start()
        kwargs = w.manager.start.await_args.kwargs
        assert kwargs["reward_model"] == "shaped_v1"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "value", ["shaped_v1", "sparse_v1", "learned_shaped_v1"]
    )
    async def test_explicit_value_passes_through(
        self, wrapper_with_mock_manager, value
    ):
        w = wrapper_with_mock_manager
        await w.start(reward_model=value)
        kwargs = w.manager.start.await_args.kwargs
        assert kwargs["reward_model"] == value

    @pytest.mark.asyncio
    async def test_forwarding_alongside_other_kwargs(
        self, wrapper_with_mock_manager
    ):
        """reward_model must not collide with or clobber sibling kwargs
        (title/slug/training_mode) — they all land on the manager."""
        w = wrapper_with_mock_manager
        await w.start(
            title="run-alpha",
            slug="run-alpha",
            training_mode="bot_ladder",
            reward_model="sparse_v1",
        )
        kwargs = w.manager.start.await_args.kwargs
        assert kwargs["title"] == "run-alpha"
        assert kwargs["training_mode"] == "bot_ladder"
        assert kwargs["reward_model"] == "sparse_v1"


class TestManagerStoresRewardModel:
    """TrainingManager.start records the selector on ``_reward_model``
    before the training thread launches, so downstream readers (run
    registrar, env factory) see a consistent value mid-run."""

    @pytest.mark.asyncio
    async def test_manager_stores_value_before_thread_start(self, tmp_path):
        """Use the real manager but stub the thread start — we only want
        to verify the pre-thread bookkeeping, not exercise PPO."""
        from unittest.mock import patch

        w = TrainingServiceWrapper(
            model_dir=str(tmp_path / "models"),
            replay_dir=str(tmp_path / "replays"),
        )
        with patch.object(w.manager, "_thread", None), patch(
            "threading.Thread"
        ) as _MockThread:
            _MockThread.return_value.start = lambda: None
            await w.start(reward_model="learned_shaped_v1")
        assert w.manager._reward_model == "learned_shaped_v1"

    @pytest.mark.asyncio
    async def test_manager_default_is_shaped_v1(self, tmp_path):
        from unittest.mock import patch

        w = TrainingServiceWrapper(
            model_dir=str(tmp_path / "models"),
            replay_dir=str(tmp_path / "replays"),
        )
        with patch("threading.Thread") as _MockThread:
            _MockThread.return_value.start = lambda: None
            await w.start()
        assert w.manager._reward_model == "shaped_v1"
