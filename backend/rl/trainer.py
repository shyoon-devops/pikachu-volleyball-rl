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
    EnvResultCallback,
    LiveFrameCallback,
    MetricsCallback,
    UpdateWindowCallback,
)
from backend.rl.env import PikachuVolleyballEnv
from backend.rl.league_callback import LeagueCallback

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
        # League-update broadcast queue (v2 Sprint-1). The LeagueCallback
        # (backend/rl/league_callback.py) pushes one record every 64
        # matches; the WS side drains via league_push_loop and rebroadcasts
        # as training:league_update. Bounded so a stalled FE subscriber
        # can't blow memory — one flush-window of records at a time.
        self.league_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=32)
        # Gradient-update window events (training:update_start /
        # training:update_end). Emitted by UpdateWindowCallback at
        # SB3 rollout boundaries so the FE stops heuristic-timing the
        # env.step gap; see docs/diagnostics/FREEZE-ANALYSIS-20260419.md
        # Fix A. Bounded at a handful of records — these fire at most
        # twice per rollout (start + end), so queue depth is always
        # small even if the WS fan-out stalls briefly.
        self.update_events_queue: asyncio.Queue[dict[str, Any]] = (
            asyncio.Queue(maxsize=32)
        )

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
        # Self-play league wiring: set in start(). Initialized here so
        # direct _train_loop attribute reads (after the ``getattr`` →
        # direct-access cleanup in the review follow-up) always find
        # them even if the class is constructed but start() was never
        # called (test isolation / introspection paths).
        self._training_mode: str = "bot_ladder"
        self._opponent_provider: Any = None
        # Human title + its filesystem slug for this run. Both are set
        # by start() before the thread kicks off; callbacks that tag
        # result/frame payloads read them off this object at emit time.
        self._title: str = ""
        self._slug: str = "run"
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
        title: str = "",
        slug: str = "",
        training_mode: str = "bot_ladder",
        opponent_provider: Any = None,
    ) -> str:
        """Start a new training experiment. Returns experiment_id.

        ``title`` / ``slug`` come from ``title_service.allocate_title`` +
        ``slugify`` at the WS handler layer — the manager takes whatever
        is handed in and stores it for downstream tagging. An empty
        title is permitted at this layer (legacy / test callers); the
        slug falls back to ``"run"`` via the title service.

        ``training_mode`` selects the opponent source (v2.x Sprint-1):
          * ``"bot_ladder"`` (default, v1.0.0-compatible) — each env gets
            a ``FixedBotProvider(level=bot_level)`` built in-process.
            Uses the same SubprocVecEnv path we shipped at v1.0.0 so
            throughput is unchanged.
          * ``"self_play"`` — the caller is expected to pass a shared
            ``opponent_provider`` (typically ``PFSPProvider``) that
            samples from the league pool. Runs on ``DummyVecEnv``
            (in-process) so the provider's rating store and checkpoint
            cache aren't duplicated across subprocesses. Trades a small
            amount of throughput for correct shared-state semantics.

        See docs/adr/0014-self-play-league.md §3 for the design.
        """
        if self.status == "running":
            raise RuntimeError("Training is already running")
        if training_mode not in ("bot_ladder", "self_play"):
            raise ValueError(
                f"training_mode must be 'bot_ladder' or 'self_play', "
                f"got {training_mode!r}"
            )
        if training_mode == "self_play" and opponent_provider is None:
            raise ValueError(
                "training_mode='self_play' requires an opponent_provider "
                "(typically a PFSPProvider built over the league pool)"
            )

        self._experiment_id = str(uuid.uuid4())
        self._bot_level = bot_level
        self._training_mode = training_mode
        self._opponent_provider = opponent_provider
        self._hyperparams = {**DEFAULT_HYPERPARAMS, **(hyperparams or {})}
        # Title + slug set BEFORE the thread starts so the first demo-
        # tick + result-drain both see them. Slug defaults keep legacy
        # tests that don't supply a title compiling.
        self._title = title or ""
        self._slug = slug or "run"
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
            training_mode = self._training_mode
            provider = self._opponent_provider
            if training_mode == "self_play" and provider is not None:
                # Shared in-process PFSP provider: DummyVecEnv keeps the
                # rating store, checkpoint cache, and pool manifest
                # singleton across all env workers. Sub-env index is
                # passed to env_kwargs so the provider's mirror / PFSP
                # sampling can stagger deterministically across workers.
                #
                # NB: ``make_vec_env`` auto-wraps each env in SB3's
                # Monitor, which is what populates ``info["episode"]``
                # on natural terminations — the key ``_PausePoke`` (and
                # MetricsCallback) read to drive current_episode. We
                # must apply the same wrap manually here; dropping
                # Monitor was the root cause of self-play runs showing
                # ``step`` incrementing while ``episode`` stayed at 0.
                # noqa kept on the import line itself so ruff actually
                # sees the PLC0415 suppression.
                from stable_baselines3.common.monitor import Monitor  # noqa: PLC0415
                from stable_baselines3.common.vec_env import DummyVecEnv  # noqa: PLC0415

                def _make_one(i: int) -> Any:
                    def _f() -> Any:
                        base_env = PikachuVolleyballEnv(
                            bot_level=bot_level,
                            opponent_provider=provider,
                            env_index=i,
                        )
                        return Monitor(base_env)
                    return _f

                env = DummyVecEnv([_make_one(i) for i in range(n_envs)])
            else:
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
                    slug=self._slug,
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
                EnvResultCallback(
                    results_queue=self.results_queue,
                    loop=loop,
                    manager=self,
                    drain_interval=hp.get("env_result_drain_interval", 4),
                ),
                # League aggregation — queues a broadcast record every
                # LEAGUE_BROADCAST_INTERVAL (64) completed matches for
                # the WS layer to drain + fan out as training:league_update.
                # See backend/rl/league_callback.py and
                # docs/adr/0014-self-play-league.md §4.
                LeagueCallback(
                    broadcast_queue=self.league_queue,
                    loop=loop,
                ),
                # Gradient-update window events (Fix A from freeze diag
                # 2026-04-19). Emits training:update_start at
                # rollout-end and training:update_end at rollout-start
                # so the FE overlay doesn't have to heuristic-time the
                # env.step gap.
                UpdateWindowCallback(
                    update_events_queue=self.update_events_queue,
                    loop=loop,
                    experiment_id=self._experiment_id,
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
        """Save a final checkpoint — slug-prefixed per BE-T2.

        Filename: ``{slug}__{exp8}__final.zip``. The legacy
        ``final.zip`` name stays forever-resolvable via the
        ``_find_latest_checkpoint`` glob below, which picks up any
        ``*.zip`` in the experiment directory.
        """
        if self._model is None:
            return
        checkpoint_dir = Path(self.model_dir) / self._experiment_id
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        exp8 = (self._experiment_id or "unknown0")[:8]
        name = f"{self._slug or 'run'}__{exp8}__final"
        self._model.save(str(checkpoint_dir / name))

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
