"""Training service wrapper — adapts TrainingManager for FastAPI."""

from __future__ import annotations

from typing import Any

from backend.rl.trainer import TrainingManager


class TrainingServiceWrapper:
    """Thin wrapper exposing TrainingManager to the web layer."""

    def __init__(self, model_dir: str = "models", replay_dir: str = "replays") -> None:
        self.manager = TrainingManager(model_dir=model_dir, replay_dir=replay_dir)

    async def start(
        self,
        hyperparams: dict[str, Any] | None = None,
        bot_level: int = 1,
        total_timesteps: int = 2_000_000,
        n_envs: int = 8,
        title: str = "",
        slug: str = "",
    ) -> str:
        """Start a new training run.

        ``n_envs`` is accepted explicitly (rather than tucked into
        ``hyperparams``) because it drives ``make_vec_env`` — not the
        PPO constructor — and defaults to the manager's 8-env baseline
        when the caller does not specify.

        ``title`` and ``slug`` are allocated by the WS handler layer
        via ``title_service.allocate_title`` + ``slugify``; forwarding
        them here keeps the manager the single owner of the run's
        identity fields.
        """
        return await self.manager.start(
            hyperparams=hyperparams,
            bot_level=bot_level,
            total_timesteps=total_timesteps,
            n_envs=n_envs,
            title=title,
            slug=slug,
        )

    async def stop(self, *, force: bool = True) -> dict[str, Any]:
        """Stop training and return the manager's status dict.

        The previous wrapper discarded the manager's return value, so when
        ``stop()`` was rejected by STOP_PROTECTION_THRESHOLD the caller
        broadcast "stopped" while the training thread kept running. That's
        the exact symptom QA reported ("Stop 버튼 클릭해도 학습 안 멈춤").

        User-initiated Stop carries explicit intent — the UI button click is
        the authoritative "yes I know, stop it" — so the default is
        ``force=True``. Programmatic callers that want the protection path
        can still pass ``force=False`` and inspect the returned dict.
        """
        return await self.manager.stop(force=force)

    async def pause(self) -> dict[str, Any]:
        """Pause the running training thread in place.

        Differs from ``stop``: the SB3 learn() call keeps its model, vec env,
        and RNG state; only the per-step tick blocks until ``resume`` clears
        the pause. That means resume-from-paused doesn't need to reload a
        checkpoint (unlike resume-from-stopped), which is how FE-8's
        Pause/Resume toggle is wired from the user's side.
        """
        return await self.manager.pause()

    async def resume(self) -> dict[str, Any]:
        """Resume training — unpause if paused, otherwise reload checkpoint."""
        return await self.manager.resume()

    def set_bot_level(self, level: int) -> None:
        self.manager.set_bot_level(level)

    def status(self) -> dict[str, Any]:
        """Return the live training status.

        Previously hardcoded ``current_step: 0`` / ``current_episode: 0``,
        which is why the dashboard counters stayed pinned at 0/0 even while
        training was actively stepping. Read the real counters off the
        manager instead.

        Fields beyond the original four (``bot_level``, ``started_at``) are
        added for FE-8 so a page refresh shows the correct bot difficulty
        and session duration without the dashboard having to ask separately.
        ``started_at`` is rendered as ISO-8601 UTC; ``None`` before the first
        training run so FE can distinguish "never started" from a real time.
        """
        started_at = getattr(self.manager, "_started_at_wall", None)
        return {
            "state": self.manager.status,
            "current_step": self.manager.current_step,
            "current_episode": self.manager.current_episode,
            "experiment_id": self.manager._experiment_id or None,
            "bot_level": self.manager._bot_level,
            "started_at": started_at.isoformat() if started_at else None,
            # Title surfaced here so the dashboard header + breadcrumbs
            # (spec §4) can render on /api/training/status alone, no
            # separate fetch. Empty string when no run has started yet.
            "title": getattr(self.manager, "_title", "") or "",
        }

    def last_frame(self) -> dict[str, Any] | None:
        """Return the most recent live-demo frame, or None if none cached.

        Used by ``GET /api/training/current_frame`` so a page refresh can
        repaint the game canvas immediately instead of waiting for the next
        WS ``training:frame`` push.
        """
        return getattr(self.manager, "last_frame", None)
