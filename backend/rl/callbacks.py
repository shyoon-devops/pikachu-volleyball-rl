"""SB3 callbacks for training metrics, checkpoints, and live frames."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import deque
from pathlib import Path
from typing import Any

import msgpack
import numpy as np
from stable_baselines3.common.callbacks import BaseCallback

from backend.game.bot import RuleBasedBot
from backend.game.constants import MAX_SCORE, NET_PILLAR_X
from backend.game.engine import PikachuVolleyball
from backend.rl.env import ACTION_MAP

logger = logging.getLogger(__name__)


# Backpressure bookkeeping for _enqueue_with_drop (BUG-1).
_DROP_COUNTERS: dict[int, int] = {}
_DROP_LOG_EVERY = 100  # log a WARNING every N drops per queue


def _enqueue_with_drop(queue: asyncio.Queue, item: Any) -> None:
    """Put with drop-oldest on full (runs inside the event loop)."""
    try:
        queue.put_nowait(item)
        return
    except asyncio.QueueFull:
        pass

    # Queue full: drop oldest, retry.
    try:
        queue.get_nowait()
    except asyncio.QueueEmpty:
        pass
    try:
        queue.put_nowait(item)
    except asyncio.QueueFull:
        pass

    qid = id(queue)
    count = _DROP_COUNTERS.get(qid, 0) + 1
    _DROP_COUNTERS[qid] = count
    if count == 1 or count % _DROP_LOG_EVERY == 0:
        logger.warning(
            "WS queue backpressure: dropped %d item(s) on queue id=%d (maxsize=%d)",
            count, qid, queue.maxsize,
        )


def _safe_enqueue(
    loop: asyncio.AbstractEventLoop,
    queue: asyncio.Queue[dict[str, Any]],
    data: dict[str, Any],
) -> None:
    """Cross-thread enqueue with drop-oldest backpressure.

    Called from the training thread; marshals onto the event loop via
    ``call_soon_threadsafe`` so queue operations stay on the loop.
    Silently drops when the loop is closed (client disconnected).
    """
    try:
        loop.call_soon_threadsafe(_enqueue_with_drop, queue, data)
    except RuntimeError:
        # Event loop was closed (e.g., shutdown). Training continues.
        pass


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

        # NOTE: Do NOT include a "type" key here — handlers.metrics_push_loop
        # wraps the payload with {"type": "training:metrics", "payload": ...}.
        metrics = {
            "step": self.num_timesteps,
            "episode": len(self._episode_rewards),
            "mean_reward": mean_reward,
            "win_rate": win_rate,
            "policy_loss": policy_loss,
            "value_loss": value_loss,
        }

        _safe_enqueue(self.loop, self.queue, metrics)
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
    """Runs a demo game every M steps and pushes frames + result to queues.

    A reference back to ``TrainingManager`` is optional: when supplied, each
    serialized frame is also cached on ``manager.last_frame`` so the
    ``GET /api/training/current_frame`` endpoint can repaint the game canvas
    instantly on a page refresh, before any WebSocket frame arrives. The
    callback still works in isolation (tests construct it without a manager).
    """

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
        manager: Any | None = None,
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
        # ``Any`` rather than TrainingManager to avoid a circular import —
        # trainer.py already imports this module at construction time.
        self._manager = manager

    def _on_step(self) -> bool:
        if self.num_timesteps % self.play_interval != 0:
            return True

        game = PikachuVolleyball()
        bot = RuleBasedBot(level=self.bot_level)
        state = game.reset()
        frames: list[dict[str, Any]] = []
        prev_ball_x = float(state.ball.x)
        prev_ball_y = float(state.ball.y)

        while state.score1 < MAX_SCORE and state.score2 < MAX_SCORE:
            frame_data = _serialize_state(state)
            frames.append(frame_data)
            # No "type" key — handlers.frames_push_loop wraps the payload.
            _safe_enqueue(self.loop, self.frames_queue, frame_data)
            if self._manager is not None:
                # Overwrite (not append) — the REST endpoint only wants the
                # newest frame. Assignment of a reference is atomic in
                # CPython so cross-thread reads observe either the old or
                # the new frame, never a partially-written dict.
                self._manager.last_frame = frame_data

            obs = self._get_obs(state, prev_ball_x, prev_ball_y)
            action, _ = self.model.predict(obs, deterministic=True)
            p1_input = ACTION_MAP[int(action)]

            prev_ball_x = float(state.ball.x)
            prev_ball_y = float(state.ball.y)

            p2_input = bot.get_action(state, is_player2=True)
            state = game.step(p1_input, p2_input)

        # Final frame — also cache so /current_frame reports the terminal
        # state (winner's score, not a stale in-play frame) until the next
        # demo game starts.
        final_frame = _serialize_state(state)
        frames.append(final_frame)
        if self._manager is not None:
            self._manager.last_frame = final_frame

        game_id = str(uuid.uuid4())
        # No "type" key — handlers.results_push_loop wraps the payload.
        result = {
            "game_id": game_id,
            "score1": state.score1,
            "score2": state.score2,
            "winner": 1 if state.score1 >= MAX_SCORE else 2,
            "duration_frames": state.frame,
        }
        _safe_enqueue(self.loop, self.results_queue, result)

        # Save replay
        self._save_replay(game_id, frames)

        return True

    def _get_obs(
        self, state: Any, prev_ball_x: float, prev_ball_y: float,
    ) -> np.ndarray:
        """Build 18-element observation matching PikachuVolleyballEnv._get_obs."""
        from backend.game.constants import GROUND_HEIGHT, GROUND_WIDTH

        w = float(GROUND_WIDTH)
        h = float(GROUND_HEIGHT)
        max_v = 20.0

        if state.player1.is_jumping:
            p1_air = 1.0
        elif state.player1.is_diving:
            p1_air = -1.0
        else:
            p1_air = 0.0

        return np.array(
            [
                state.player1.x / w * 2 - 1,
                state.player1.y / h * 2 - 1,
                np.clip(state.player1.vx / max_v, -1, 1),
                np.clip(state.player1.vy / max_v, -1, 1),
                p1_air,
                state.player2.x / w * 2 - 1,
                state.player2.y / h * 2 - 1,
                np.clip(state.player2.vy / max_v, -1, 1),
                state.ball.x / w * 2 - 1,
                state.ball.y / h * 2 - 1,
                np.clip(state.ball.vx / max_v, -1, 1),
                np.clip(state.ball.vy / max_v, -1, 1),
                np.clip((float(state.ball.x) - prev_ball_x) / max_v, -1, 1),
                np.clip((float(state.ball.y) - prev_ball_y) / max_v, -1, 1),
                np.clip(
                    (float(state.ball.x) - float(state.player1.x)) / w, -1, 1,
                ),
                1.0 if state.ball.x <= NET_PILLAR_X else -1.0,
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
    """Serialize a GameState to a plain dict for WS frames / replay storage."""
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
