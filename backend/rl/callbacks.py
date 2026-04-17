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

    # 256 strikes the resolution/throughput balance PM requested:
    #   * 100 (prev default) → with n_steps=2048 FE sees ~20 points per
    #     rollout — too sparse to track convergence curves.
    #   * 256 → ~8 points per 2048-step rollout = 8x the prior resolution.
    #   * 128 or below → Mongo insert rate doubles (16x at 128) for
    #     marginal visual gain. 256 held as the sweet spot.
    def __init__(
        self,
        queue: asyncio.Queue[dict[str, Any]],
        loop: asyncio.AbstractEventLoop,
        log_interval: int = 256,
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

    def _on_training_start(self) -> None:
        """Seed ``manager.last_frame`` so ``/current_frame`` returns 200 immediately.

        Without this, the endpoint returns 404 for the full warm-up window
        (``play_interval`` steps, default 5000). Designers hitting refresh
        during that window saw a blank canvas even though training was
        running. Seeding a canonical reset snapshot lets the FE paint
        something the instant training begins; later demo ticks overwrite
        it with live play frames.
        """
        if self._manager is None:
            return
        initial_state = PikachuVolleyball().reset()
        self._manager.last_frame = _serialize_state(initial_state)

    def _on_step(self) -> bool:
        if self.num_timesteps % self.play_interval != 0:
            return True

        # Snapshot the level + experiment id at demo-start so that (a) a
        # mid-run set_bot_level picks up *here* for the in-process demo
        # opponent without needing a vec-env restart, and (b) the saved
        # GameRecord reflects what was actually played this demo — not
        # a stale __init__ cache (the silent-L1 bug prior to this fix).
        if self._manager is not None:
            current_bot_level = int(getattr(self._manager, "_bot_level", self.bot_level))
            current_experiment_id = str(getattr(self._manager, "_experiment_id", "") or "")
        else:
            current_bot_level = self.bot_level
            current_experiment_id = ""

        # Replay viewer needs the full pikavolley.js display state machine —
        # slow-motion on score, 5f fade-out, 30f ready-message ramp, 211f
        # gameEnd window — so the FE can render them. The RL training env
        # opts out (default False) to avoid feeding no-op frames to the agent.
        game = PikachuVolleyball(display_state_machine=True)
        bot = RuleBasedBot(level=current_bot_level)
        state = game.reset()
        frames: list[dict[str, Any]] = []
        prev_ball_x = float(state.ball.x)
        prev_ball_y = float(state.ball.y)

        # Rally counter — increments whenever the ball crosses the net.
        # Same definition the offline evaluator uses (rl/evaluator.py:82-85)
        # so the dashboard "Rallies" stat is comparable to the eval report's
        # avg_rally_length. A rally is a back-and-forth across the net,
        # NOT a single hit; ball touching the ground ends the rally and
        # is captured by the score change instead.
        rally_count = 0
        prev_ball_side_right = state.ball.x > NET_PILLAR_X

        # Keep emitting frames while the match is live OR while the engine
        # is still inside the post-MAX_SCORE gameEnd window (211 frames of
        # physics running with winner/loser poses playing out — port of
        # pikavolley.js ``frameTotal.gameEnd``). Without the second clause
        # the final scoring moment would vanish a frame after it happens
        # and the viewer would miss the winner pose entirely.
        while (
            state.score1 < MAX_SCORE and state.score2 < MAX_SCORE
        ) or (
            state.is_game_ended
            and state.game_end_frame_counter < PikachuVolleyball.GAME_END_FRAMES
        ):
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

            # Net-crossing detector — checked AFTER the step so the new
            # ball.x reflects this frame's movement.
            ball_side_right = state.ball.x > NET_PILLAR_X
            if ball_side_right != prev_ball_side_right:
                rally_count += 1
            prev_ball_side_right = ball_side_right

        # Final frame — also cache so /current_frame reports the terminal
        # state (winner's score, not a stale in-play frame) until the next
        # demo game starts.
        final_frame = _serialize_state(state)
        frames.append(final_frame)
        if self._manager is not None:
            self._manager.last_frame = final_frame

        game_id = str(uuid.uuid4())
        # No "type" key — handlers.results_push_loop wraps the payload.
        # bot_level and experiment_id MUST be present: the ws handler no
        # longer coerces missing values to a silent L1 default (that was
        # the root cause of every saved game appearing as L1 in
        # /api/games regardless of the user's actual training level).
        result = {
            "game_id": game_id,
            "experiment_id": current_experiment_id,
            "bot_level": current_bot_level,
            "score1": state.score1,
            "score2": state.score2,
            "winner": 1 if state.score1 >= MAX_SCORE else 2,
            "duration_frames": state.frame,
            # Net-crossing total over the whole match. The dashboard
            # "Rallies" counter and the GameRecord doc both pull this
            # field; the handler used to default to 0, which is why every
            # game in /api/games showed 0 rallies.
            "rally_count": rally_count,
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
            # Signed dive direction (-1 left, 0 none, +1 right).
            # Mirrors original physics.js:138 (init) / :597 (set on dive
            # trigger) / :522 (drives dive horizontal velocity). FE needs
            # this to render the dive pose facing the correct side — vx
            # sign was being used as a fallback and flipped wrong when the
            # diving player's x-velocity was clamped against a wall.
            "diving_direction": int(
                getattr(state.player1, "diving_direction", 0)
            ),
            # Pikachu sprite state (port of physics.js Player.state at 0xC0):
            # 0=normal, 1=jumping, 2=jumping+power_hit, 3=diving,
            # 4=lying_down, 5=win, 6=lose. The FE picks the pikachu sprite
            # frame from (state, frame_number); without these the 5/6
            # winner/loser poses during the 211f gameEnd window have no
            # data to render against.
            "state": int(getattr(state.player1, "state", 0)),
            "frame_number": int(getattr(state.player1, "frame_number", 0)),
            "is_winner": bool(getattr(state.player1, "is_winner", False)),
            "game_ended": bool(getattr(state.player1, "game_ended", False)),
        },
        "player2": {
            "x": state.player2.x,
            "y": state.player2.y,
            "vx": state.player2.vx,
            "vy": state.player2.vy,
            "is_jumping": state.player2.is_jumping,
            "is_diving": state.player2.is_diving,
            "is_power_hitting": state.player2.is_power_hitting,
            "diving_direction": int(
                getattr(state.player2, "diving_direction", 0)
            ),
            "state": int(getattr(state.player2, "state", 0)),
            "frame_number": int(getattr(state.player2, "frame_number", 0)),
            "is_winner": bool(getattr(state.player2, "is_winner", False)),
            "game_ended": bool(getattr(state.player2, "game_ended", False)),
        },
        "ball": {
            "x": state.ball.x,
            "y": state.ball.y,
            "vx": state.ball.vx,
            "vy": state.ball.vy,
            "rotation": state.ball.rotation,
            # Gate for FE hyper-ball / trail rendering on power-hit frames.
            # Defensive getattr so replays pickled before this field was
            # added still decode; missing → treat as not a power hit.
            "is_power_hit": bool(getattr(state.ball, "is_power_hit", False)),
            # Punch-effect markers for the white radial ring drawn when
            # the ball slams the ground or a power hit connects
            # (original view.js:502-507). Radius starts at BALL_RADIUS and
            # decays by 2 per frame in the engine. punch_effect_x/y locate
            # the centre; FE draws a 2*radius-sized sprite.
            "punch_effect_x": int(getattr(state.ball, "punch_effect_x", 0)),
            "punch_effect_y": int(getattr(state.ball, "punch_effect_y", 0)),
            "punch_effect_radius": int(
                getattr(state.ball, "punch_effect_radius", 0)
            ),
        },
        "score1": state.score1,
        "score2": state.score2,
        "frame": state.frame,
        # Signals for the FE to render scoring / game-end overlays.
        # Defensive getattr keeps old replays decoding without KeyError.
        # `is_round_over` latches True from the scoring frame onward
        # (through the gameEnd window). `is_game_ended` + counter drives
        # the final winner/loser pose animation on the FE.
        "is_round_over": bool(getattr(state, "is_round_over", False)),
        "is_game_ended": bool(getattr(state, "is_game_ended", False)),
        "game_end_frame_counter": int(
            getattr(state, "game_end_frame_counter", 0)
        ),
        # Per-frame SFX triggers. Flat bool dict — each True means the
        # corresponding audio cue fired *on this frame*. Consumers play
        # once and move on; the engine clears every flag at the top of
        # the next step(). Ports physics.js sound flags:
        #   - pika / chu / pipikachu: player.sound (physics.js:162-166)
        #   - power_hit / ball_touches_ground: ball.sound (physics.js:263-266)
        # Player-side flags are OR'd across both players; stereo panning
        # (pikavolley.js:465) can be derived from player x if needed.
        # NOTE: `pi` and `pikachu` are menu-layer sounds in pikavolley.js
        # (withWhoAreWeGoingToPlay L211/220/241) — they are NOT physics
        # events and are intentionally not emitted by the engine.
        "sounds": {
            "pika": bool(
                getattr(state.player1, "sound_pika", False)
                or getattr(state.player2, "sound_pika", False)
            ),
            "chu": bool(
                getattr(state.player1, "sound_chu", False)
                or getattr(state.player2, "sound_chu", False)
            ),
            "pipikachu": bool(
                getattr(state.player1, "sound_pipikachu", False)
                or getattr(state.player2, "sound_pipikachu", False)
            ),
            "power_hit": bool(getattr(state.ball, "sound_power_hit", False)),
            "ball_touches_ground": bool(
                getattr(state.ball, "sound_ball_touches_ground", False)
            ),
        },
        # Display state-machine fields (port of pikavolley.js round /
        # afterEndOfRound / beforeStartOfNextRound). The FE renders the
        # black fade overlay using fade_black_alpha, blinks the READY
        # message via ready_message_visible, and shifts physics-frame
        # interpolation timing during the slow-motion window.
        "state_name": str(getattr(state, "state_name", "round")),
        "slow_motion_frames_left": int(
            getattr(state, "slow_motion_frames_left", 0)
        ),
        "fade_black_alpha": float(getattr(state, "fade_black_alpha", 0.0)),
        "ready_message_visible": bool(
            getattr(state, "ready_message_visible", False)
        ),
    }
