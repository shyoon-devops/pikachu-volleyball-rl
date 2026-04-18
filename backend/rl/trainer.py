"""Training manager for PPO training with SB3."""

from __future__ import annotations

import asyncio
import json
import logging
import signal
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback, CallbackList
from stable_baselines3.common.env_util import make_vec_env
from stable_baselines3.common.vec_env import SubprocVecEnv

from backend.rl.callbacks import (
    CheckpointCallback,
    EnvFrameCallback,
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
        # Latest live-demo frame — updated by LiveFrameCallback each demo tick
        # and served via GET /api/training/current_frame so a page refresh can
        # repaint the canvas without waiting for the next WS broadcast.
        # Kept as a plain dict (serialized GameState), not a queue: readers
        # want the newest value, not a history.
        self.last_frame: dict[str, Any] | None = None
        self.metrics_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.frames_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.results_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        # Per-env frames from the EnvFrameCallback — rate-limited by the
        # callback's broadcast_interval, but bounded here too so a slow
        # WS subscriber can never accumulate more than ``maxsize`` queued
        # snapshots. Drop-oldest is handled by _enqueue_with_drop.
        self.env_frames_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=256)

        self._model: PPO | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        # Pause is a distinct signal from stop: the training thread keeps its
        # model + vec env + RNG state but blocks on each callback tick. That
        # lets the user flip Pause/Resume on the dashboard (FE-8) without
        # tearing down and re-loading an SB3 checkpoint.
        self._pause_event = threading.Event()
        self._experiment_id: str = ""
        self._bot_level: int = 1
        self._hyperparams: dict[str, Any] = {}
        self._started_at: float = 0.0
        # ISO-8601 start timestamp surfaced by /api/training/status; None
        # until the first start() call. Kept separate from ``_started_at``
        # which is a ``monotonic()`` value useful only for duration math.
        self._started_at_wall: datetime | None = None

        self._install_signal_handler()

    async def start(
        self,
        hyperparams: dict[str, Any] | None = None,
        bot_level: int = 1,
        total_timesteps: int = 2_000_000,
        n_envs: int = 8,
    ) -> str:
        """Start a new training experiment. Returns experiment_id."""
        if self.status == "running":
            raise RuntimeError("Training is already running")

        self._experiment_id = str(uuid.uuid4())
        self._bot_level = bot_level
        self._hyperparams = {**DEFAULT_HYPERPARAMS, **(hyperparams or {})}
        self._stop_event.clear()
        self._pause_event.clear()
        self.current_step = 0
        self.current_episode = 0
        # Drop any frame left over from a previous experiment so the
        # /current_frame endpoint never surfaces a stale session.
        self.last_frame = None
        self._started_at = time.monotonic()
        # Wall-clock start time for GET /api/training/status. ``_started_at``
        # (above) uses monotonic for duration math — wall clock is the one the
        # dashboard displays.
        self._started_at_wall = datetime.now(timezone.utc)

        loop = asyncio.get_running_loop()

        self._thread = threading.Thread(
            target=self._train_loop,
            args=(loop, total_timesteps, n_envs),
            daemon=True,
        )
        self.status = "running"
        self._thread.start()

        return self._experiment_id

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
        # A paused thread is parked on _pause_event.wait(); clearing it lets
        # _on_step fall through to the stop-event check and return False so
        # learn() unwinds cleanly instead of hanging on join().
        self._pause_event.clear()
        if self._thread is not None:
            self._thread.join(timeout=30)
        self.status = "stopped"
        return {"stopped": True, "reason": "stopped"}

    async def pause(self) -> dict[str, Any]:
        """Pause a running training thread in place.

        No-op if not running. If already paused, returns idempotently so the
        WS handler can broadcast the current state without special-casing.
        """
        if self.status == "paused":
            return {"paused": True, "reason": "already_paused"}
        if self.status != "running":
            return {"paused": False, "reason": "not_running"}
        self._pause_event.set()
        self.status = "paused"
        return {"paused": True, "reason": "paused"}

    async def resume(
        self,
        total_timesteps: int = 2_000_000,
        n_envs: int = 8,
    ) -> dict[str, Any]:
        """Resume training.

        Two distinct resume paths share this method — the caller doesn't have
        to know which one applies:

        * **From paused**: the training thread is still alive, just parked on
          ``_pause_event``. Clear the event and flip state back to running.
          No checkpoint reload, no new vec_env — the exact same learn() call
          continues from its last tick.
        * **From stopped**: spawn a fresh training thread loaded from the
          latest checkpoint on disk. This is what the pre-pause wrapper did.
        """
        if self.status == "paused":
            self._pause_event.clear()
            self.status = "running"
            return {"resumed": True, "reason": "unpaused"}

        if self.status == "running":
            # Idempotent: avoid raising into the WS handler for a redundant
            # resume click while training is already active.
            return {"resumed": True, "reason": "already_running"}

        checkpoint_path = self._find_latest_checkpoint()
        if checkpoint_path is None:
            raise FileNotFoundError("No checkpoint found to resume from")

        self._stop_event.clear()
        self._pause_event.clear()
        loop = asyncio.get_running_loop()

        self._thread = threading.Thread(
            target=self._train_loop,
            args=(loop, total_timesteps, n_envs, checkpoint_path),
            daemon=True,
        )
        self.status = "running"
        self._thread.start()
        return {"resumed": True, "reason": "from_checkpoint"}

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
        total_timesteps: int = 2_000_000,
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
                    # 256 matches the MetricsCallback default — see the
                    # rationale there. hyperparams can still override
                    # (e.g. a fast CI run can drop to 64 for denser logs).
                    log_interval=hp.get("metrics_interval", 256),
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
                    manager=self,
                ),
                EnvFrameCallback(
                    env_frames_queue=self.env_frames_queue,
                    loop=loop,
                    broadcast_interval=hp.get("env_frame_interval", 4),
                ),
                _StopEventCallback(self._stop_event, self._pause_event, self),
            ])

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


class _StopEventCallback(BaseCallback):
    """Signals SB3 to stop/pause and keeps the manager counters live.

    Three responsibilities ride on a single callback because SB3 fires
    ``_on_step`` once per environment step per env and we don't want to pay
    the per-tick overhead of walking multiple callbacks for bookkeeping:

    * Propagate the stop signal back to ``model.learn()`` by returning False
      when ``stop_event`` is set.
    * Block (in place, without exiting learn()) while ``pause_event`` is
      set — so the vec env, model weights, and RNG state remain intact
      through a Pause/Resume cycle. A stop during a pause still aborts.
    * Keep ``manager.current_step`` / ``manager.current_episode`` in sync
      for ``/api/training/status``. The dashboard counters were pinned to
      0/0 before this was wired.
    """

    # Wake cadence while paused. Short enough to feel instant when the user
    # hits Resume; long enough that a paused training session doesn't eat a
    # full core spinning on an is_set() check.
    _PAUSE_POLL_INTERVAL_S = 0.05

    def __init__(
        self,
        stop_event: threading.Event,
        pause_event: threading.Event,
        manager: TrainingManager,
    ) -> None:
        super().__init__(verbose=0)
        self._stop_event = stop_event
        self._pause_event = pause_event
        self._manager = manager

    def _on_step(self) -> bool:
        self._manager.current_step = self.num_timesteps

        # Count episode completions from VecEnv monitor infos. Each env
        # emits an ``"episode"`` key on the tick that ends an episode, so
        # the increment is exactly the number of completions this step —
        # not bounded by the reward deque's maxlen (which is only used for
        # moving-average computation in MetricsCallback).
        for info in self.locals.get("infos", []) or []:
            if "episode" in info:
                self._manager.current_episode += 1

        # Pause: park here until the user resumes, or a stop request
        # arrives. We intentionally return True from this branch so
        # learn() keeps its call stack and the vec env doesn't get torn
        # down; a real stop drops through to the return below.
        while self._pause_event.is_set() and not self._stop_event.is_set():
            time.sleep(self._PAUSE_POLL_INTERVAL_S)

        return not self._stop_event.is_set()
