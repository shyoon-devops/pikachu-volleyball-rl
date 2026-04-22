"""TrainingServiceWrapper.start forwards policy_type (ADR 0016 S3).

Mirrors the S2 reward_model wrapper test. Plumbing-only — we don't
spin up a real trainer or policy factory; the AI Sprint-3 branch owns
the dispatch logic. The BE contract is the pass-through.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from backend.app.services.training_service import TrainingServiceWrapper


@pytest.fixture
def wrapper_with_mock_manager(tmp_path):
    w = TrainingServiceWrapper(
        model_dir=str(tmp_path / "models"),
        replay_dir=str(tmp_path / "replays"),
    )
    w.manager.start = AsyncMock(return_value="exp-123")
    return w


class TestPolicyTypeForwarding:
    @pytest.mark.asyncio
    async def test_default_is_mlp_v1(self, wrapper_with_mock_manager):
        """No explicit kwarg → ``mlp_v1`` reaches the manager."""
        w = wrapper_with_mock_manager
        await w.start()
        kwargs = w.manager.start.await_args.kwargs
        assert kwargs["policy_type"] == "mlp_v1"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "value", ["mlp_v1", "lstm_v1", "gru_v1", "transformer_v1"]
    )
    async def test_explicit_value_passes_through(
        self, wrapper_with_mock_manager, value
    ):
        w = wrapper_with_mock_manager
        await w.start(policy_type=value)
        kwargs = w.manager.start.await_args.kwargs
        assert kwargs["policy_type"] == value

    @pytest.mark.asyncio
    async def test_forwarding_alongside_reward_model(
        self, wrapper_with_mock_manager
    ):
        """policy_type is independent from reward_model — both land on
        the manager in the same start() call."""
        w = wrapper_with_mock_manager
        await w.start(
            reward_model="sparse_v1",
            policy_type="lstm_v1",
            title="run-beta",
        )
        kwargs = w.manager.start.await_args.kwargs
        assert kwargs["reward_model"] == "sparse_v1"
        assert kwargs["policy_type"] == "lstm_v1"
        assert kwargs["title"] == "run-beta"


class TestManagerStoresPolicyType:
    """TrainingManager.start records the selector on ``_policy_type``
    before the training thread launches. Mirror of the reward_model
    storage test."""

    @pytest.mark.asyncio
    async def test_manager_stores_value_before_thread_start(self, tmp_path):
        w = TrainingServiceWrapper(
            model_dir=str(tmp_path / "models"),
            replay_dir=str(tmp_path / "replays"),
        )
        with patch.object(w.manager, "_thread", None), patch(
            "threading.Thread"
        ) as _MockThread:
            _MockThread.return_value.start = lambda: None
            await w.start(policy_type="lstm_v1")
        assert w.manager._policy_type == "lstm_v1"

    @pytest.mark.asyncio
    async def test_manager_default_is_mlp_v1(self, tmp_path):
        w = TrainingServiceWrapper(
            model_dir=str(tmp_path / "models"),
            replay_dir=str(tmp_path / "replays"),
        )
        with patch("threading.Thread") as _MockThread:
            _MockThread.return_value.start = lambda: None
            await w.start()
        assert w.manager._policy_type == "mlp_v1"

    @pytest.mark.asyncio
    async def test_manager_holds_both_selectors_independently(self, tmp_path):
        """Setting both reward_model and policy_type at start lands
        both on the manager — they're orthogonal dials, not coupled."""
        w = TrainingServiceWrapper(
            model_dir=str(tmp_path / "models"),
            replay_dir=str(tmp_path / "replays"),
        )
        with patch("threading.Thread") as _MockThread:
            _MockThread.return_value.start = lambda: None
            await w.start(reward_model="learned_shaped_v1", policy_type="gru_v1")
        assert w.manager._reward_model == "learned_shaped_v1"
        assert w.manager._policy_type == "gru_v1"
