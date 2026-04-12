"""Training manager for PPO training with SB3."""

from __future__ import annotations

import asyncio
import datetime as _dt
import json
import logging
import signal
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback, CallbackList
from stable_baselines3.common.env_util import make_vec_env
from stable_baselines3.common.vec_env import SubprocVecEnv

from backend.rl.callbacks import (
    CheckpointCallback,
    CurriculumCallback,
    EarlyStoppingCallback,
    LiveFrameCallback,
    MetricsCallback,
)
from backend.rl.env import PikachuVolleyballEnv

logger = logging.getLogger(__name__)

# File written on SIGTERM so the next process can auto-resume.
_INTERRUPTED_META_FILENAME = "interrupted.json"

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

# Training sessions beyond this step count require force=True to stop.
STOP_PROTECTION_THRESHOLD: int = 10_000


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
        self.current_step: int = 0
        self.current_episode: int = 0
        self.metrics_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.frames_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.results_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

        self._model: PPO | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._experiment_id: str = ""
        self._bot_level: int = 1
        self._hyperparams: dict[str, Any] = {}
        self._seed: int | None = None
        self._total_timesteps: int = 0
        self._n_envs: int = 0
        self._started_at: float = 0.0

        self._install_signal_handler()

    async def start(
        self,
        hyperparams: dict[str, Any] | None = None,
        bot_level: int = 1,
        total_timesteps: int = 1_000_000,
        n_envs: int = 8,
        seed: int | None = None,
    ) -> str:
        """Start a new training experiment. Returns experiment_id."""
        if self.status == "running":
            raise RuntimeError("Training is already running")

        self._experiment_id = str(uuid.uuid4())
        self._bot_level = bot_level
        self._hyperparams = {**DEFAULT_HYPERPARAMS, **(hyperparams or {})}
        self._seed = seed
        self._total_timesteps = total_timesteps
        self._n_envs = n_envs
        self._stop_event.clear()
        self.current_step = 0
        self.current_episode = 0
        self._started_at = time.monotonic()

        self._write_run_config()

        loop = asyncio.get_running_loop()

        self._thread = threading.Thread(
            target=self._train_loop,
            args=(loop, total_timesteps, n_envs),
            daemon=True,
        )
        self.status = "running"
        self._thread.start()

        return self._experiment_id

    def _write_run_config(self) -> None:
        """Persist a config.json describing this run for reproducibility."""
        checkpoint_dir = Path(self.model_dir) / self._experiment_id
        checkpoint_dir.mkdir(parents=True, exist_ok=True)

        config = {
            "experiment_id": self._experiment_id,
            "bot_level": self._bot_level,
            "seed": self._seed,
            "total_timesteps": self._total_timesteps,
            "n_envs": self._n_envs,
            "hyperparams": self._hyperparams,
            "obs_space_shape": [18],
            "action_space_n": 12,
            "net_arch": DEFAULT_NET_ARCH,
            "started_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "git_commit": _get_git_commit(),
        }
        (checkpoint_dir / "config.json").write_text(json.dumps(config, indent=2))

    async def stop(self, *, force: bool = False) -> dict[str, Any]:
        """Gracefully stop training and save a final checkpoint.

        Returns a status dict. If the session has progressed past
        STOP_PROTECTION_THRESHOLD steps and ``force`` is False, the stop
        is **rejected** to prevent accidental termination of long-running
        training.
        """
        if self.status != "running":
            return {"stopped": True, "reason": "not_running"}

        if not force and self.current_step >= STOP_PROTECTION_THRESHOLD:
            logger.warning(
                "Stop rejected: step=%d >= threshold=%d (use force=True)",
                self.current_step,
                STOP_PROTECTION_THRESHOLD,
            )
            return {
                "stopped": False,
                "reason": "protected",
                "current_step": self.current_step,
                "threshold": STOP_PROTECTION_THRESHOLD,
            }

        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=30)
        self.status = "stopped"
        return {"stopped": True, "reason": "stopped"}

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

    # ------------------------------------------------------------------
    # Signal handling (uvicorn reload / SIGTERM protection)
    # ------------------------------------------------------------------

    def _install_signal_handler(self) -> None:
        """Register SIGTERM handler to save an emergency checkpoint."""
        try:
            prev = signal.getsignal(signal.SIGTERM)
            def _on_sigterm(signum: int, frame: Any) -> None:
                self._emergency_save()
                # Re-raise to let uvicorn/gunicorn proceed with shutdown.
                if callable(prev) and prev not in (signal.SIG_DFL, signal.SIG_IGN):
                    prev(signum, frame)
                else:
                    raise SystemExit(0)
            signal.signal(signal.SIGTERM, _on_sigterm)
        except (OSError, ValueError):
            # Not in main thread or signals unsupported — skip silently.
            pass

    def _emergency_save(self) -> None:
        """Save model + metadata so the next process can resume."""
        if self._model is None or self.status != "running":
            return
        logger.warning(
            "SIGTERM received — saving emergency checkpoint (step=%d, exp=%s)",
            self.current_step,
            self._experiment_id,
        )
        try:
            checkpoint_dir = Path(self.model_dir) / self._experiment_id
            checkpoint_dir.mkdir(parents=True, exist_ok=True)
            self._model.save(str(checkpoint_dir / "interrupted"))

            meta = {
                "experiment_id": self._experiment_id,
                "current_step": self.current_step,
                "bot_level": self._bot_level,
                "hyperparams": self._hyperparams,
            }
            meta_path = Path(self.model_dir) / _INTERRUPTED_META_FILENAME
            meta_path.write_text(json.dumps(meta, indent=2))
            logger.info("Emergency checkpoint saved to %s", checkpoint_dir)
        except Exception:
            logger.exception("Failed to save emergency checkpoint")

    def get_interrupted_session(self) -> dict[str, Any] | None:
        """Return metadata for an interrupted session if one exists."""
        meta_path = Path(self.model_dir) / _INTERRUPTED_META_FILENAME
        if not meta_path.exists():
            return None
        try:
            meta = json.loads(meta_path.read_text())
            exp_id = meta.get("experiment_id", "")
            checkpoint = Path(self.model_dir) / exp_id / "interrupted.zip"
            if not checkpoint.exists():
                meta_path.unlink(missing_ok=True)
                return None
            return meta
        except Exception:
            logger.exception("Failed to read interrupted session metadata")
            return None

    def clear_interrupted_session(self) -> None:
        """Remove the interrupted session marker after explicit resume or discard."""
        meta_path = Path(self.model_dir) / _INTERRUPTED_META_FILENAME
        meta_path.unlink(missing_ok=True)

    async def resume_interrupted(
        self,
        total_timesteps: int = 1_000_000,
        n_envs: int = 8,
    ) -> str | None:
        """Resume from an interrupted (SIGTERM) session if one exists.

        Returns the experiment_id if resumed, None otherwise.
        """
        meta = self.get_interrupted_session()
        if meta is None:
            return None

        exp_id = meta["experiment_id"]
        self._experiment_id = exp_id
        self._bot_level = meta.get("bot_level", 1)
        self._hyperparams = {**DEFAULT_HYPERPARAMS, **meta.get("hyperparams", {})}

        checkpoint_path = str(
            Path(self.model_dir) / exp_id / "interrupted"
        )
        self._stop_event.clear()
        self.current_step = meta.get("current_step", 0)
        self._started_at = time.monotonic()

        loop = asyncio.get_running_loop()

        self._thread = threading.Thread(
            target=self._train_loop,
            args=(loop, total_timesteps, n_envs, checkpoint_path),
            daemon=True,
        )
        self.status = "running"
        self._thread.start()

        self.clear_interrupted_session()
        logger.info(
            "Resumed interrupted session %s from step %d",
            exp_id,
            self.current_step,
        )
        return exp_id

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
            if self._seed is not None:
                env.seed(self._seed)
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
                    seed=self._seed,
                    verbose=0,
                    policy_kwargs={"net_arch": DEFAULT_NET_ARCH},
                )

            callback_list: list[BaseCallback] = [
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
                _StopEventCallback(self._stop_event, self),
            ]

            curriculum_cfg = hp.get("curriculum") or {}
            if curriculum_cfg.get("enabled"):
                callback_list.append(
                    CurriculumCallback(
                        initial_level=bot_level,
                        max_level=curriculum_cfg.get("max_level", 5),
                        win_rate_threshold=curriculum_cfg.get("win_rate_threshold", 0.7),
                        min_episodes=curriculum_cfg.get("min_episodes", 20),
                        loop=loop,
                        queue=self.metrics_queue,
                    )
                )

            early_stop_cfg = hp.get("early_stopping") or {}
            if early_stop_cfg.get("enabled"):
                callback_list.append(
                    EarlyStoppingCallback(
                        patience=early_stop_cfg.get("patience", 5),
                        min_delta=early_stop_cfg.get("min_delta", 0.01),
                        check_interval=early_stop_cfg.get("check_interval", 10_000),
                    )
                )

            callbacks = CallbackList(callback_list)

            self._model.learn(
                total_timesteps=total_timesteps,
                callback=callbacks,
                progress_bar=False,
            )

            # Save final checkpoint
            self._save_final_checkpoint()
        except Exception:
            logger.exception("Training thread crashed")
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


def _get_git_commit() -> str:
    """Best-effort git commit hash for the current checkout.

    Returns ``"unknown"`` when not in a git repo or when git is unavailable —
    config logging shouldn't fail the run.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=2, check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return "unknown"


class _StopEventCallback(BaseCallback):
    """Stops training when the threading.Event is set and reports step counts."""

    def __init__(
        self,
        stop_event: threading.Event,
        manager: TrainingManager,
    ) -> None:
        super().__init__(verbose=0)
        self._stop_event = stop_event
        self._manager = manager

    def _on_step(self) -> bool:
        self._manager.current_step = self.num_timesteps
        return not self._stop_event.is_set()
