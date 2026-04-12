"""Tests for the training pipeline: TrainingManager, callbacks, and replays."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from backend.rl.trainer import (
    STOP_PROTECTION_THRESHOLD,
    TrainingManager,
    _INTERRUPTED_META_FILENAME,
)


@pytest.fixture
def tmp_dirs(tmp_path: Path) -> tuple[str, str]:
    model_dir = str(tmp_path / "models")
    replay_dir = str(tmp_path / "replays")
    return model_dir, replay_dir


@pytest.fixture
def manager(tmp_dirs: tuple[str, str]) -> TrainingManager:
    model_dir, replay_dir = tmp_dirs
    return TrainingManager(model_dir=model_dir, replay_dir=replay_dir)


class TestTrainingManagerStart:
    """TrainingManager.start() launches training and produces checkpoints."""

    @pytest.mark.asyncio
    async def test_start_returns_experiment_id(
        self, manager: TrainingManager
    ) -> None:
        exp_id = await manager.start(
            bot_level=1, total_timesteps=256, n_envs=2,
            hyperparams={"n_steps": 128, "checkpoint_interval": 128},
        )
        assert isinstance(exp_id, str) and len(exp_id) > 0
        # Wait for training to finish
        while manager.status == "running":
            await asyncio.sleep(0.2)

    @pytest.mark.asyncio
    async def test_start_creates_checkpoint(
        self, manager: TrainingManager
    ) -> None:
        await manager.start(
            bot_level=1, total_timesteps=256, n_envs=2,
            hyperparams={"n_steps": 128, "checkpoint_interval": 128},
        )
        while manager.status == "running":
            await asyncio.sleep(0.2)

        checkpoint_dir = Path(manager.model_dir) / manager._experiment_id
        zips = list(checkpoint_dir.glob("*.zip"))
        assert len(zips) >= 1, "Expected at least one checkpoint file"


class TestTrainingManagerStop:
    """TrainingManager.stop() gracefully stops training."""

    @pytest.mark.asyncio
    async def test_stop_sets_status_stopped(
        self, manager: TrainingManager
    ) -> None:
        await manager.start(
            bot_level=1, total_timesteps=100_000, n_envs=2,
            hyperparams={"n_steps": 128},
        )
        assert manager.status == "running"
        await asyncio.sleep(1)
        result = await manager.stop()
        assert manager.status == "stopped"
        assert result["stopped"] is True
        assert result["reason"] == "stopped"

    @pytest.mark.asyncio
    async def test_stop_not_running_returns_not_running(
        self, manager: TrainingManager
    ) -> None:
        result = await manager.stop()
        assert result["stopped"] is True
        assert result["reason"] == "not_running"

    @pytest.mark.asyncio
    async def test_stop_rejected_when_protected(
        self, manager: TrainingManager
    ) -> None:
        """Stop without force is rejected once current_step >= threshold."""
        await manager.start(
            bot_level=1, total_timesteps=100_000, n_envs=2,
            hyperparams={"n_steps": 128},
        )
        await asyncio.sleep(1)
        # Simulate many steps completed
        manager.current_step = STOP_PROTECTION_THRESHOLD + 1
        result = await manager.stop(force=False)
        assert result["stopped"] is False
        assert result["reason"] == "protected"
        assert manager.status == "running"
        # Clean up — force stop
        await manager.stop(force=True)

    @pytest.mark.asyncio
    async def test_stop_forced_when_protected(
        self, manager: TrainingManager
    ) -> None:
        """Stop with force=True succeeds even past threshold."""
        await manager.start(
            bot_level=1, total_timesteps=100_000, n_envs=2,
            hyperparams={"n_steps": 128},
        )
        await asyncio.sleep(1)
        manager.current_step = STOP_PROTECTION_THRESHOLD + 1
        result = await manager.stop(force=True)
        assert result["stopped"] is True
        assert result["reason"] == "stopped"
        assert manager.status == "stopped"


class TestStopAndCountersHotfix:
    """Regressions QA flagged on dev: Stop not stopping, counters pinned 0/0.

    These tests exercise the live thread — not mocks — because the bug was
    that the wrapper silently swallowed the manager's rejection dict. Only a
    real training thread can prove that ``stop`` *actually joins* and that
    ``current_step`` / ``current_episode`` advance while training runs.
    """

    @pytest.mark.asyncio
    async def test_stop_endpoint_actually_stops_the_training_thread(
        self, manager: TrainingManager
    ) -> None:
        """Real join: after stop, the OS thread must no longer be alive.

        The dev-environment symptom was "Stop 버튼 클릭해도 학습 안 멈춤".
        This guards the deepest layer: ``stop`` must set the event, join
        the background thread, and leave behind no ghost that keeps
        stepping.
        """
        await manager.start(
            bot_level=1, total_timesteps=100_000, n_envs=2,
            hyperparams={"n_steps": 128},
        )
        # Give learn() time to enter its loop so the callback is live.
        await asyncio.sleep(1)
        assert manager._thread is not None
        assert manager._thread.is_alive()

        result = await manager.stop(force=True)
        assert result["stopped"] is True
        # join() must have returned — not just the status flag.
        assert not manager._thread.is_alive(), (
            "training thread kept running after stop() — "
            "join() did not complete within timeout"
        )
        assert manager.status == "stopped"

    @pytest.mark.asyncio
    async def test_wrapper_stop_defaults_to_force_true(
        self, manager: TrainingManager, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """WS Stop path must not be rejected by STOP_PROTECTION_THRESHOLD.

        Pre-hotfix flow: wrapper.stop() → manager.stop(force=False) →
        rejected past threshold → wrapper returns None → handler broadcasts
        false "stopped". Now the wrapper defaults force=True so UI clicks
        always take effect.
        """
        from backend.app.services.training_service import TrainingServiceWrapper

        wrapper = TrainingServiceWrapper.__new__(TrainingServiceWrapper)
        wrapper.manager = manager

        await manager.start(
            bot_level=1, total_timesteps=100_000, n_envs=2,
            hyperparams={"n_steps": 128},
        )
        await asyncio.sleep(1)
        # Simulate a long-running session well past the protection threshold.
        manager.current_step = STOP_PROTECTION_THRESHOLD + 1

        result = await wrapper.stop()  # default force=True
        assert result["stopped"] is True
        assert manager.status == "stopped"

    @pytest.mark.asyncio
    async def test_step_and_episode_counter_updates_during_training(
        self, manager: TrainingManager
    ) -> None:
        """Counters must tick past 0 while training is live.

        QA's second complaint: "Step/Episode 카운터 0/0 고정". Root cause
        had two legs — the wrapper's status() hardcoded 0, and
        current_episode was never written anywhere. The wrapper change is
        covered separately; this test proves the manager-level counter
        write actually happens on the training thread's callback ticks.
        """
        await manager.start(
            bot_level=1, total_timesteps=2048, n_envs=2,
            hyperparams={"n_steps": 128, "metrics_interval": 64},
        )

        # Poll for counter movement rather than a fixed sleep — slow CI
        # hosts take longer to spin up SB3's first rollout.
        deadline = asyncio.get_event_loop().time() + 20
        while asyncio.get_event_loop().time() < deadline:
            if manager.current_step > 0:
                break
            await asyncio.sleep(0.2)

        assert manager.current_step > 0, (
            "current_step stayed at 0 — _StopEventCallback did not "
            "propagate num_timesteps onto the manager"
        )
        # Wait out the run so the fixture tears down cleanly.
        while manager.status == "running":
            await asyncio.sleep(0.2)

    @pytest.mark.asyncio
    async def test_status_wrapper_surfaces_live_counters(
        self, manager: TrainingManager
    ) -> None:
        """TrainingServiceWrapper.status() must mirror the manager, not 0/0.

        This is the exact path the GET /api/training/status endpoint uses;
        a regression here is what left FE-8's counters frozen on the
        dashboard.
        """
        from backend.app.services.training_service import TrainingServiceWrapper

        wrapper = TrainingServiceWrapper.__new__(TrainingServiceWrapper)
        wrapper.manager = manager

        # Simulate live counters — avoids waiting on a real SB3 tick loop.
        manager.status = "running"
        manager.current_step = 1234
        manager.current_episode = 7
        manager._experiment_id = "exp-status-check"

        got = wrapper.status()
        assert got["state"] == "running"
        assert got["current_step"] == 1234
        assert got["current_episode"] == 7
        assert got["experiment_id"] == "exp-status-check"


class TestPauseResumeHotfix:
    """Pause/Resume state machine (FE-8 backend landing)."""

    @pytest.mark.asyncio
    async def test_pause_flips_state_without_stopping_thread(
        self, manager: TrainingManager
    ) -> None:
        """Pause must keep the SB3 learn() call alive — no checkpoint reload."""
        await manager.start(
            bot_level=1, total_timesteps=100_000, n_envs=2,
            hyperparams={"n_steps": 128},
        )
        await asyncio.sleep(1)
        thread_before = manager._thread

        result = await manager.pause()
        assert result["paused"] is True
        assert manager.status == "paused"
        # Same thread object — learn() wasn't torn down.
        assert manager._thread is thread_before
        assert manager._thread is not None and manager._thread.is_alive()

        # Cleanup.
        await manager.stop(force=True)

    @pytest.mark.asyncio
    async def test_resume_from_paused_is_idempotent_and_does_not_reload_checkpoint(
        self, manager: TrainingManager
    ) -> None:
        """Resume-from-paused clears the pause event; it must NOT raise on
        missing checkpoint (unlike resume-from-stopped)."""
        await manager.start(
            bot_level=1, total_timesteps=100_000, n_envs=2,
            hyperparams={"n_steps": 128},
        )
        await asyncio.sleep(1)
        await manager.pause()
        assert manager.status == "paused"

        result = await manager.resume()
        assert result["resumed"] is True
        assert result["reason"] == "unpaused"
        assert manager.status == "running"

        await manager.stop(force=True)

    @pytest.mark.asyncio
    async def test_pause_is_noop_when_not_running(
        self, manager: TrainingManager
    ) -> None:
        result = await manager.pause()
        assert result == {"paused": False, "reason": "not_running"}
        assert manager.status == "stopped"


class TestTrainingManagerResume:
    """TrainingManager.resume() loads from checkpoint and continues."""

    @pytest.mark.asyncio
    async def test_resume_after_stop(
        self, manager: TrainingManager
    ) -> None:
        await manager.start(
            bot_level=1, total_timesteps=256, n_envs=2,
            hyperparams={"n_steps": 128, "checkpoint_interval": 128},
        )
        while manager.status == "running":
            await asyncio.sleep(0.2)

        # Now resume
        await manager.resume(total_timesteps=256, n_envs=2)
        assert manager.status == "running"
        while manager.status == "running":
            await asyncio.sleep(0.2)
        assert manager.status == "stopped"


class TestMetricsCallback:
    """MetricsCallback pushes metrics to the queue."""

    @pytest.mark.asyncio
    async def test_metrics_pushed_to_queue(
        self, manager: TrainingManager
    ) -> None:
        await manager.start(
            bot_level=1, total_timesteps=512, n_envs=2,
            hyperparams={"n_steps": 128, "metrics_interval": 128},
        )
        while manager.status == "running":
            await asyncio.sleep(0.2)

        collected: list[dict] = []
        while not manager.metrics_queue.empty():
            collected.append(manager.metrics_queue.get_nowait())

        assert len(collected) >= 1, "Expected at least one metrics entry"
        sample = collected[0]
        assert "step" in sample
        assert "mean_reward" in sample
        assert "win_rate" in sample


class TestCheckpointCallback:
    """CheckpointCallback creates checkpoint files on disk."""

    @pytest.mark.asyncio
    async def test_checkpoint_files_created(
        self, manager: TrainingManager
    ) -> None:
        await manager.start(
            bot_level=1, total_timesteps=256, n_envs=2,
            hyperparams={"n_steps": 128, "checkpoint_interval": 128},
        )
        while manager.status == "running":
            await asyncio.sleep(0.2)

        checkpoint_dir = Path(manager.model_dir) / manager._experiment_id
        assert checkpoint_dir.exists()
        zips = list(checkpoint_dir.glob("*.zip"))
        assert len(zips) >= 1


async def _wait_for_model_ready(
    manager: TrainingManager, timeout: float = 30,
) -> None:
    """Wait until the training thread has created the model and started stepping."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if manager._model is not None and manager.current_step > 0:
            return
        await asyncio.sleep(0.3)
    raise TimeoutError("Model did not become ready within timeout")


class TestEmergencySave:
    """SIGTERM emergency checkpoint save and resume."""

    @pytest.mark.asyncio
    async def test_emergency_save_creates_checkpoint_and_meta(
        self, manager: TrainingManager
    ) -> None:
        """_emergency_save writes interrupted.zip + interrupted.json."""
        await manager.start(
            bot_level=2, total_timesteps=100_000, n_envs=2,
            hyperparams={"n_steps": 128},
        )
        await _wait_for_model_ready(manager)
        assert manager.status == "running"

        manager._emergency_save()

        checkpoint_dir = Path(manager.model_dir) / manager._experiment_id
        assert (checkpoint_dir / "interrupted.zip").exists()

        meta_path = Path(manager.model_dir) / _INTERRUPTED_META_FILENAME
        assert meta_path.exists()
        meta = json.loads(meta_path.read_text())
        assert meta["experiment_id"] == manager._experiment_id
        assert meta["bot_level"] == 2
        assert meta["current_step"] >= 0

        await manager.stop(force=True)

    @pytest.mark.asyncio
    async def test_get_interrupted_session_returns_none_when_clean(
        self, manager: TrainingManager
    ) -> None:
        assert manager.get_interrupted_session() is None

    @pytest.mark.asyncio
    async def test_get_interrupted_session_returns_meta(
        self, manager: TrainingManager
    ) -> None:
        """After emergency save, get_interrupted_session returns metadata."""
        await manager.start(
            bot_level=1, total_timesteps=100_000, n_envs=2,
            hyperparams={"n_steps": 128},
        )
        await _wait_for_model_ready(manager)
        manager._emergency_save()
        await manager.stop(force=True)

        meta = manager.get_interrupted_session()
        assert meta is not None
        assert meta["experiment_id"] == manager._experiment_id

    @pytest.mark.asyncio
    async def test_resume_interrupted_restores_session(
        self, manager: TrainingManager
    ) -> None:
        """resume_interrupted picks up from the emergency checkpoint."""
        await manager.start(
            bot_level=3, total_timesteps=100_000, n_envs=2,
            hyperparams={"n_steps": 128},
        )
        await _wait_for_model_ready(manager)
        original_exp_id = manager._experiment_id
        manager._emergency_save()
        await manager.stop(force=True)

        manager2 = TrainingManager(
            model_dir=manager.model_dir,
            replay_dir=manager.replay_dir,
        )
        resumed_id = await manager2.resume_interrupted(
            total_timesteps=256, n_envs=2,
        )
        assert resumed_id == original_exp_id
        assert manager2.status == "running"
        assert manager2._bot_level == 3

        while manager2.status == "running":
            await asyncio.sleep(0.2)

    @pytest.mark.asyncio
    async def test_clear_interrupted_session(
        self, manager: TrainingManager
    ) -> None:
        """clear_interrupted_session removes the marker file."""
        await manager.start(
            bot_level=1, total_timesteps=100_000, n_envs=2,
            hyperparams={"n_steps": 128},
        )
        await _wait_for_model_ready(manager)
        manager._emergency_save()
        await manager.stop(force=True)

        assert manager.get_interrupted_session() is not None
        manager.clear_interrupted_session()
        assert manager.get_interrupted_session() is None
