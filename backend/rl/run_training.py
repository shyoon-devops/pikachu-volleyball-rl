"""Headless training runner for standalone PPO training.

Skips the asyncio queue plumbing used by the FastAPI-hosted TrainingManager
and runs SB3 PPO directly with TensorBoard logging and a win-rate tracker
callback. Progress is written to a plain-text progress log for external
monitoring.

Usage:
    python3 -m backend.rl.run_training --bot-level 1 --total-timesteps 500000
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import logging
import subprocess
import sys
import time
import uuid
from collections import deque
from pathlib import Path

from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback, CallbackList
from stable_baselines3.common.env_util import make_vec_env
from stable_baselines3.common.vec_env import SubprocVecEnv

from backend.rl.env import PikachuVolleyballEnv

logger = logging.getLogger(__name__)

DEFAULT_HYPERPARAMS = {
    "learning_rate": 3e-4,
    "n_steps": 2048,
    "batch_size": 64,
    "n_epochs": 10,
    "gamma": 0.99,
    "gae_lambda": 0.95,
    "clip_range": 0.2,
    "ent_coef": 0.01,
}
DEFAULT_NET_ARCH = [256, 256]


class ProgressCallback(BaseCallback):
    """Tracks win rate + mean reward and writes to a progress log."""

    def __init__(
        self,
        progress_path: Path,
        checkpoint_dir: Path,
        checkpoint_interval: int = 20_000,
        report_interval: int = 2_048,
        win_window: int = 100,
    ) -> None:
        super().__init__(verbose=0)
        self._progress_path = progress_path
        self._checkpoint_dir = checkpoint_dir
        self._checkpoint_interval = checkpoint_interval
        self._report_interval = report_interval
        self._last_report_step = 0
        self._last_checkpoint_step = 0
        self._wins: deque[int] = deque(maxlen=win_window)
        self._rewards: deque[float] = deque(maxlen=win_window)
        self._episode_reward_sum: dict[int, float] = {}
        self._started_at = time.monotonic()

    def _on_training_start(self) -> None:
        self._checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self._write_line(
            f"training_start ts={_dt.datetime.now(_dt.timezone.utc).isoformat()}"
        )

    def _write_line(self, text: str) -> None:
        with self._progress_path.open("a") as f:
            f.write(text + "\n")

    def _on_step(self) -> bool:
        # SB3 VecEnv info — check for episode completion per env.
        infos = self.locals.get("infos", [])
        rewards = self.locals.get("rewards", [])
        dones = self.locals.get("dones", [])

        for idx, (info, r, done) in enumerate(zip(infos, rewards, dones)):
            self._episode_reward_sum[idx] = (
                self._episode_reward_sum.get(idx, 0.0) + float(r)
            )
            if not done:
                continue

            ep_reward = self._episode_reward_sum.pop(idx, 0.0)
            self._rewards.append(ep_reward)

            # Winner detection: env info exposes score1/score2. Count as a win
            # only on a terminated episode (game reached MAX_SCORE), not on
            # a truncated rally-timeout.
            score1 = info.get("score1")
            score2 = info.get("score2")
            if score1 is not None and score2 is not None:
                if score1 > score2:
                    self._wins.append(1)
                elif score2 > score1:
                    self._wins.append(0)
                # Tie (rally truncation) — do not count.

        step = self.num_timesteps
        if step - self._last_report_step >= self._report_interval:
            self._last_report_step = step
            win_rate = (sum(self._wins) / len(self._wins)) if self._wins else 0.0
            mean_reward = (
                sum(self._rewards) / len(self._rewards) if self._rewards else 0.0
            )
            elapsed = time.monotonic() - self._started_at
            sps = step / max(elapsed, 1e-6)
            line = (
                f"step={step} episodes={len(self._wins)} "
                f"win_rate={win_rate:.3f} mean_reward={mean_reward:.3f} "
                f"sps={sps:.1f} elapsed_s={elapsed:.1f}"
            )
            self._write_line(line)
            print(line, flush=True)

            if self.model is not None and self.logger is not None:
                self.logger.record("custom/win_rate", win_rate)
                self.logger.record("custom/mean_episode_reward", mean_reward)

        if step - self._last_checkpoint_step >= self._checkpoint_interval:
            self._last_checkpoint_step = step
            ckpt = self._checkpoint_dir / f"checkpoint_{step}"
            if self.model is not None:
                self.model.save(str(ckpt))
                self._write_line(f"checkpoint_saved step={step} path={ckpt}.zip")
                print(f"checkpoint saved: {ckpt}.zip", flush=True)

        return True

    def _on_training_end(self) -> None:
        final = self._checkpoint_dir / "final"
        if self.model is not None:
            self.model.save(str(final))
        self._write_line(
            f"training_end step={self.num_timesteps} "
            f"ts={_dt.datetime.now(_dt.timezone.utc).isoformat()}"
        )


def _git_commit() -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=2, check=False,
        )
        if r.returncode == 0:
            return r.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(description="Headless PPO training runner")
    parser.add_argument("--bot-level", type=int, default=1)
    parser.add_argument("--total-timesteps", type=int, default=500_000)
    parser.add_argument("--n-envs", type=int, default=8)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--model-dir", type=str, default="models")
    parser.add_argument("--tb-dir", type=str, default="tensorboard_logs")
    parser.add_argument("--progress-dir", type=str, default="logs/training")
    parser.add_argument("--experiment-id", type=str, default="")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    exp_id = args.experiment_id or str(uuid.uuid4())[:8]
    checkpoint_dir = Path(args.model_dir) / exp_id
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    tb_run_dir = Path(args.tb_dir) / exp_id
    tb_run_dir.mkdir(parents=True, exist_ok=True)

    progress_dir = Path(args.progress_dir)
    progress_dir.mkdir(parents=True, exist_ok=True)
    progress_path = progress_dir / f"{exp_id}.log"

    config = {
        "experiment_id": exp_id,
        "bot_level": args.bot_level,
        "seed": args.seed,
        "total_timesteps": args.total_timesteps,
        "n_envs": args.n_envs,
        "hyperparams": DEFAULT_HYPERPARAMS,
        "obs_space_shape": [18],
        "action_space_n": 12,
        "net_arch": DEFAULT_NET_ARCH,
        "started_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "git_commit": _git_commit(),
        "tensorboard_log": str(tb_run_dir),
        "progress_log": str(progress_path),
    }
    (checkpoint_dir / "config.json").write_text(json.dumps(config, indent=2))

    print(f"experiment_id={exp_id}", flush=True)
    print(f"checkpoint_dir={checkpoint_dir}", flush=True)
    print(f"progress_log={progress_path}", flush=True)
    print(f"tensorboard_log={tb_run_dir}", flush=True)

    env = make_vec_env(
        PikachuVolleyballEnv,
        n_envs=args.n_envs,
        env_kwargs={"bot_level": args.bot_level},
        vec_env_cls=SubprocVecEnv,
        seed=args.seed,
    )

    model = PPO(
        policy="MlpPolicy",
        env=env,
        learning_rate=DEFAULT_HYPERPARAMS["learning_rate"],
        n_steps=DEFAULT_HYPERPARAMS["n_steps"],
        batch_size=DEFAULT_HYPERPARAMS["batch_size"],
        n_epochs=DEFAULT_HYPERPARAMS["n_epochs"],
        gamma=DEFAULT_HYPERPARAMS["gamma"],
        gae_lambda=DEFAULT_HYPERPARAMS["gae_lambda"],
        clip_range=DEFAULT_HYPERPARAMS["clip_range"],
        ent_coef=DEFAULT_HYPERPARAMS["ent_coef"],
        seed=args.seed,
        verbose=0,
        policy_kwargs={"net_arch": DEFAULT_NET_ARCH},
        tensorboard_log=str(tb_run_dir),
    )

    callbacks = CallbackList([
        ProgressCallback(
            progress_path=progress_path,
            checkpoint_dir=checkpoint_dir,
            checkpoint_interval=20_000,
            report_interval=2_048,
        ),
    ])

    try:
        model.learn(
            total_timesteps=args.total_timesteps,
            callback=callbacks,
            tb_log_name="ppo",
            progress_bar=False,
        )
    finally:
        try:
            env.close()
        except Exception:
            logger.exception("env.close failed")

    print(f"training complete exp_id={exp_id}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
