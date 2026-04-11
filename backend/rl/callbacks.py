"""SB3 callbacks for training metrics, checkpoints, and live frames."""

from __future__ import annotations

import asyncio
import os
import uuid
from collections import deque
from dataclasses import asdict
from pathlib import Path
from typing import Any

import msgpack
import numpy as np
from stable_baselines3.common.callbacks import BaseCallback

from backend.game.bot import RuleBasedBot
from backend.game.constants import MAX_SCORE
from backend.game.engine import PikachuVolleyball, PlayerInput
from backend.rl.env import ACTION_MAP

import logging

_cb_logger = logging.getLogger(__name__)


def _safe_enqueue(queue: asyncio.Queue, item: Any) -> None:
    """put_nowait with drop-oldest on full queue (backpressure)."""
    try:
        queue.put_nowait(item)
    except asyncio.QueueFull:
        try:
            queue.get_nowait()  # drop oldest
        except asyncio.QueueEmpty:
            pass
        try:
            queue.put_nowait(item)
        except asyncio.QueueFull:
            _cb_logger.debug("Queue still full after drop, discarding item")


class MetricsCallback(BaseCallback):
    """Collects training metrics every N steps and pushes to an asyncio.Queue."""

    def __init__(
        self,
        queue: asyncio.Queue[dict[str, Any]],
        loop: asyncio.AbstractEventLoop,
        log_interval: int = 100,
        verbose: int = 0,
    ) -> None:
        super().__init__(verbose)
        self.queue = queue
        self.loop = loop
        self.log_interval = log_interval
        self._episode_rewards: deque[float] = deque(maxlen=100)
        self._episode_wins: deque[bool] = deque(maxlen=100)

    def _on_step(self) -> bool:
        # Track episode completions from monitor infos
        infos = self.locals.get("infos", [])
        for info in infos:
            if "episode" in info:
                self._episode_rewards.append(info["episode"]["r"])
            score1 = info.get("score1", 0)
            score2 = info.get("score2", 0)
            if score1 >= MAX_SCORE:
                self._episode_wins.append(True)
            elif score2 >= MAX_SCORE:
                self._episode_wins.append(False)

        if self.num_timesteps % self.log_interval != 0:
            return True

        mean_reward = float(np.mean(self._episode_rewards)) if self._episode_rewards else 0.0
        win_rate = float(np.mean(self._episode_wins)) if self._episode_wins else 0.0

        # Try to get losses from the logger
        policy_loss = 0.0
        value_loss = 0.0
        if hasattr(self.model, "logger") and self.model.logger is not None:
            name_to_value = getattr(self.model.logger, "name_to_value", {})
            policy_loss = name_to_value.get("train/policy_gradient_loss", 0.0)
            value_loss = name_to_value.get("train/value_loss", 0.0)

        metrics = {
            "step": self.num_timesteps,
            "episode": len(self._episode_rewards),
            "mean_reward": mean_reward,
            "win_rate": win_rate,
            "policy_loss": policy_loss,
            "value_loss": value_loss,
        }

        self.loop.call_soon_threadsafe(_safe_enqueue, self.queue, metrics)
        return True


class CheckpointCallback(BaseCallback):
    """Saves model checkpoints every K steps."""

    def __init__(
        self,
        experiment_id: str,
        model_dir: str = "models",
        save_interval: int = 10000,
        verbose: int = 0,
    ) -> None:
        super().__init__(verbose)
        self.experiment_id = experiment_id
        self.model_dir = model_dir
        self.save_interval = save_interval
        self._checkpoint_dir = Path(model_dir) / experiment_id
        self._checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def _on_step(self) -> bool:
        if self.num_timesteps % self.save_interval == 0:
            path = self._checkpoint_dir / f"{self.num_timesteps}"
            self.model.save(str(path))
        return True


class LiveFrameCallback(BaseCallback):
    """Runs a demo game every M steps and pushes frames + result to queues."""

    def __init__(
        self,
        frames_queue: asyncio.Queue[dict[str, Any]],
        results_queue: asyncio.Queue[dict[str, Any]],
        loop: asyncio.AbstractEventLoop,
        bot_level: int = 1,
        play_interval: int = 5000,
        replay_dir: str = "replays",
        max_replays: int = 1000,
        verbose: int = 0,
    ) -> None:
        super().__init__(verbose)
        self.frames_queue = frames_queue
        self.results_queue = results_queue
        self.loop = loop
        self.bot_level = bot_level
        self.play_interval = play_interval
        self.replay_dir = Path(replay_dir)
        self.max_replays = max_replays
        self.replay_dir.mkdir(parents=True, exist_ok=True)

    def _on_step(self) -> bool:
        if self.num_timesteps % self.play_interval != 0:
            return True

        game = PikachuVolleyball()
        bot = RuleBasedBot(level=self.bot_level)
        state = game.reset()
        frames: list[dict[str, Any]] = []

        while state.score1 < MAX_SCORE and state.score2 < MAX_SCORE:
            frame_data = _serialize_state(state)
            frames.append(frame_data)
            self.loop.call_soon_threadsafe(
                _safe_enqueue,
                self.frames_queue,
                frame_data,
            )

            # Get agent action from model
            obs = self._get_obs(state)
            action, _ = self.model.predict(obs, deterministic=True)
            p1_input = ACTION_MAP[int(action)]

            p2_input = bot.get_action(state, is_player2=True)
            state = game.step(p1_input, p2_input)

        # Final frame
        frames.append(_serialize_state(state))

        game_id = str(uuid.uuid4())
        result = {
            "game_id": game_id,
            "score1": state.score1,
            "score2": state.score2,
            "winner": 1 if state.score1 >= MAX_SCORE else 2,
            "duration_frames": state.frame,
        }
        self.loop.call_soon_threadsafe(_safe_enqueue, self.results_queue, result)

        # Save replay
        self._save_replay(game_id, frames)

        return True

    def _get_obs(self, state: Any) -> np.ndarray:
        """Build observation vector matching PikachuVolleyballEnv._get_obs."""
        from backend.game.constants import GROUND_HEIGHT, GROUND_WIDTH

        w = float(GROUND_WIDTH)
        h = float(GROUND_HEIGHT)
        max_v = 20.0
        return np.array(
            [
                state.player1.x / w * 2 - 1,
                state.player1.y / h * 2 - 1,
                np.clip(state.player1.vx / max_v, -1, 1),
                np.clip(state.player1.vy / max_v, -1, 1),
                state.player2.x / w * 2 - 1,
                state.player2.y / h * 2 - 1,
                state.ball.x / w * 2 - 1,
                state.ball.y / h * 2 - 1,
                np.clip(state.ball.vx / max_v, -1, 1),
                np.clip(state.ball.vy / max_v, -1, 1),
                np.clip((state.score1 - state.score2) / MAX_SCORE, -1, 1),
                1.0 if state.serving_player == 1 else -1.0,
            ],
            dtype=np.float32,
        )

    def _save_replay(self, game_id: str, frames: list[dict[str, Any]]) -> None:
        """Save replay as msgpack and enforce max_replays limit."""
        replay_path = self.replay_dir / f"{game_id}.msgpack"
        packed = msgpack.packb(frames, use_bin_type=True)
        replay_path.write_bytes(packed)

        # Cleanup old replays beyond limit
        replay_files = sorted(
            self.replay_dir.glob("*.msgpack"),
            key=lambda p: p.stat().st_mtime,
        )
        while len(replay_files) > self.max_replays:
            replay_files.pop(0).unlink()


def _serialize_state(state: Any) -> dict[str, Any]:
    """Serialize a GameState to a plain dict."""
    return {
        "player1": {
            "x": state.player1.x,
            "y": state.player1.y,
            "vx": state.player1.vx,
            "vy": state.player1.vy,
            "is_jumping": state.player1.is_jumping,
            "is_diving": state.player1.is_diving,
            "is_power_hitting": state.player1.is_power_hitting,
        },
        "player2": {
            "x": state.player2.x,
            "y": state.player2.y,
            "vx": state.player2.vx,
            "vy": state.player2.vy,
            "is_jumping": state.player2.is_jumping,
            "is_diving": state.player2.is_diving,
            "is_power_hitting": state.player2.is_power_hitting,
        },
        "ball": {
            "x": state.ball.x,
            "y": state.ball.y,
            "vx": state.ball.vx,
            "vy": state.ball.vy,
            "rotation": state.ball.rotation,
        },
        "score1": state.score1,
        "score2": state.score2,
        "frame": state.frame,
    }
