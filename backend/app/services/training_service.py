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
        total_timesteps: int = 1_000_000,
    ) -> str:
        return await self.manager.start(
            hyperparams=hyperparams,
            bot_level=bot_level,
            total_timesteps=total_timesteps,
        )

    async def stop(self, *, force: bool = False) -> dict[str, Any]:
        return await self.manager.stop(force=force)

    async def resume(self) -> None:
        await self.manager.resume()

    def set_bot_level(self, level: int) -> None:
        self.manager.set_bot_level(level)

    def status(self) -> dict[str, Any]:
        return {
            "state": self.manager.status,
            "current_step": self.manager.current_step,
            "current_episode": self.manager.current_episode,
        }
