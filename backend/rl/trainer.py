"""Training manager for PPO training with SB3."""

from __future__ import annotations

import asyncio
import threading
import uuid
from pathlib import Path
from typing import Any

from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback, CallbackList
from stable_baselines3.common.env_util import make_vec_env
from stable_baselines3.common.vec_env import SubprocVecEnv

from backend.rl.callbacks import (
    CheckpointCallback,
    LiveFrameCallback,
    MetricsCallback,
)
from backend.rl.env import PikachuVolleyballEnv

DEFAULT_HYPERPARAMS: dict[str, Any] = {
    "learning_rate": 3e-4,
    "n_steps": 2048,
    "batch_size": 64,
    "n_epochs": 10,
    "gamma": 0.99,
    "gae_lambda": 0.95,
    "clip_range": 0.2,
    "ent_coef": 0.01,
}

DEFAULT_NET_ARCH: list[int] = [256, 256]


class TrainingManager:
    """Manages PPO training in a background thread with async queue communication."""

    def __init__(
        self,
        model_dir: str = "models",
        replay_dir: str = "replays",
    ) -> None:
        self.model_dir = model_dir
        self.replay_dir = replay_dir
        self.status: str = "stopped"
        self.metrics_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.frames_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.results_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

        self._model: PPO | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._experiment_id: str = ""
        self._bot_level: int = 1
        self._hyperparams: dict[str, Any] = {}
        self._total_timesteps_trained: int = 0

    async def start(
        self,
        hyperparams: dict[str, Any] | None = None,
        bot_level: int = 1,
        total_timesteps: int = 1_000_000,
        n_envs: int = 8,
    ) -> str:
        """Start a new training experiment. Returns experiment_id."""
        if self.status == "running":
            raise RuntimeError("Training is already running")

        self._experiment_id = str(uuid.uuid4())
        self._bot_level = bot_level
        self._hyperparams = {**DEFAULT_HYPERPARAMS, **(hyperparams or {})}
        self._stop_event.clear()
        self._total_timesteps_trained = 0

        loop = asyncio.get_running_loop()

        self._thread = threading.Thread(
            target=self._train_loop,
            args=(loop, total_timesteps, n_envs),
            daemon=True,
        )
        self.status = "running"
        self._thread.start()

        return self._experiment_id

    async def stop(self) -> None:
        """Gracefully stop training and save a final checkpoint."""
        if self.status != "running":
            return

        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=30)
        self.status = "stopped"

    async def resume(
        self,
        total_timesteps: int = 1_000_000,
        n_envs: int = 8,
    ) -> None:
        """Resume training from the latest checkpoint."""
        if self.status == "running":
            raise RuntimeError("Training is already running")

        checkpoint_path = self._find_latest_checkpoint()
        if checkpoint_path is None:
            raise FileNotFoundError("No checkpoint found to resume from")

        self._stop_event.clear()
        loop = asyncio.get_running_loop()

        self._thread = threading.Thread(
            target=self._train_loop,
            args=(loop, total_timesteps, n_envs, checkpoint_path),
            daemon=True,
        )
        self.status = "running"
        self._thread.start()

    def set_bot_level(self, level: int) -> None:
        """Change bot difficulty for curriculum learning."""
        if level < 1 or level > 5:
            raise ValueError(f"Bot level must be 1-5, got {level}")
        self._bot_level = level

    def _train_loop(
        self,
        loop: asyncio.AbstractEventLoop,
        total_timesteps: int,
        n_envs: int,
        checkpoint_path: str | None = None,
    ) -> None:
        """Run SB3 PPO training (called from a background thread)."""
        try:
            bot_level = self._bot_level
            env = make_vec_env(
                PikachuVolleyballEnv,
                n_envs=n_envs,
                env_kwargs={"bot_level": bot_level},
                vec_env_cls=SubprocVecEnv,
            )

            hp = self._hyperparams
            if checkpoint_path:
                self._model = PPO.load(
                    checkpoint_path,
                    env=env,
                    learning_rate=hp.get("learning_rate", 3e-4),
                )
            else:
                self._model = PPO(
                    policy="MlpPolicy",
                    env=env,
                    learning_rate=hp.get("learning_rate", 3e-4),
                    n_steps=hp.get("n_steps", 2048),
                    batch_size=hp.get("batch_size", 64),
                    n_epochs=hp.get("n_epochs", 10),
                    gamma=hp.get("gamma", 0.99),
                    gae_lambda=hp.get("gae_lambda", 0.95),
                    clip_range=hp.get("clip_range", 0.2),
                    ent_coef=hp.get("ent_coef", 0.01),
                    verbose=0,
                    policy_kwargs={"net_arch": DEFAULT_NET_ARCH},
                )

            callbacks = CallbackList([
                MetricsCallback(
                    queue=self.metrics_queue,
                    loop=loop,
                    log_interval=hp.get("metrics_interval", 100),
                ),
                CheckpointCallback(
                    experiment_id=self._experiment_id,
                    model_dir=self.model_dir,
                    save_interval=hp.get("checkpoint_interval", 10000),
                ),
                LiveFrameCallback(
                    frames_queue=self.frames_queue,
                    results_queue=self.results_queue,
                    loop=loop,
                    bot_level=bot_level,
                    play_interval=hp.get("live_frame_interval", 5000),
                    replay_dir=self.replay_dir,
                ),
                _StopEventCallback(self._stop_event),
            ])

            self._model.learn(
                total_timesteps=total_timesteps,
                callback=callbacks,
                progress_bar=False,
            )

            # Save final checkpoint
            self._save_final_checkpoint()
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Training thread crashed")
        finally:
            self.status = "stopped"
            try:
                env.close()
            except Exception:
                pass

    def _save_final_checkpoint(self) -> None:
        """Save a final checkpoint with the label 'final'."""
        if self._model is None:
            return
        checkpoint_dir = Path(self.model_dir) / self._experiment_id
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self._model.save(str(checkpoint_dir / "final"))

    def _find_latest_checkpoint(self) -> str | None:
        """Find the latest checkpoint .zip for the current experiment."""
        checkpoint_dir = Path(self.model_dir) / self._experiment_id
        if not checkpoint_dir.exists():
            return None

        zips = sorted(
            checkpoint_dir.glob("*.zip"),
            key=lambda p: p.stat().st_mtime,
        )
        if not zips:
            return None
        # SB3 load expects path without .zip extension
        return str(zips[-1].with_suffix(""))


class _StopEventCallback(BaseCallback):
    """Stops training when the threading.Event is set."""

    def __init__(self, stop_event: threading.Event) -> None:
        super().__init__(verbose=0)
        self._stop_event = stop_event

    def _on_step(self) -> bool:
        return not self._stop_event.is_set()
