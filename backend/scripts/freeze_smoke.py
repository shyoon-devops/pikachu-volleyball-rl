"""60-second local self-play smoke that dumps timing data to CSV.

Runs end-to-end inside this process (no WS, no Mongo, no dev contact)
so the test-isolation rule is respected. Writes raw timing events to
``$FREEZE_DIAG_FILE`` (default /tmp/freeze.csv); pair with
``freeze_analyze.py`` for aggregate statistics.

Pool composition:
- 3 anchor entries (RuleBasedBot L1 / L3 / L5) — cheap baseline.
- 2 untrained PPO snapshots built on-the-fly — gives realistic
  LoadedPolicyBot inference cost without needing a pretrained model.

Usage:
    FREEZE_DIAG_FILE=/tmp/freeze.csv python -m backend.scripts.freeze_smoke
"""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

import numpy as np
from stable_baselines3 import PPO
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.vec_env import DummyVecEnv

from backend.rl.env import PikachuVolleyballEnv
from backend.rl.opponent import FixedBotProvider, PFSPProvider


def main() -> None:
    out_path = os.environ.get("FREEZE_DIAG_FILE", "/tmp/freeze.csv")
    os.environ.setdefault("FREEZE_DIAG_FILE", out_path)
    # Clear any prior run.
    Path(out_path).write_text("")

    with tempfile.TemporaryDirectory(prefix="freeze_smoke_") as tmp:
        models_base = Path(tmp) / "models"
        models_base.mkdir()

        # 1. Build two untrained PPO snapshots (structurally identical
        #    to real checkpoints; weights are random but inference
        #    cost is the same).
        seed_env = DummyVecEnv([lambda: Monitor(
            PikachuVolleyballEnv(bot_level=1)
        )])
        for exp_id, step in [("exp_seed_a", 100000), ("exp_seed_b", 200000)]:
            exp_dir = models_base / exp_id
            exp_dir.mkdir()
            seed_model = PPO("MlpPolicy", seed_env, verbose=0)
            seed_model.save(str(exp_dir / f"{step}"))
        seed_env.close()

        # 2. Pool of 5 entries: 3 anchors + 2 learned.
        class _Entry:
            def __init__(
                self, id_: str, elo: float,
                source: str, exp: str | None = None, step: int | None = None,
            ) -> None:
                self.id = id_
                self.elo = elo
                self.source = source
                self.experiment_id = exp
                self.step = step

        pool = [
            _Entry("L1", 600.0, "anchor"),
            _Entry("L3", 900.0, "anchor"),
            _Entry("L5", 1200.0, "anchor"),
            _Entry("ck_a", 1100.0, "new", "exp_seed_a", 100000),
            _Entry("ck_b", 1250.0, "new", "exp_seed_b", 200000),
        ]
        provider = PFSPProvider(
            pool=pool,
            rating_store=None,
            strategy="pfsp",
            min_pool_for_pfsp=4,
            models_base_dir=models_base,
            mirror_factory=lambda: FixedBotProvider(level=1).get_opponent(0),
            mirror_rate=0.10,
            rng_seed=42,
        )

        # 3. VecEnv + PPO.
        def _make(i: int):
            def _f():
                return Monitor(PikachuVolleyballEnv(
                    bot_level=1,
                    opponent_provider=provider,
                    env_index=i,
                ))
            return _f

        env = DummyVecEnv([_make(i) for i in range(8)])
        model = PPO(
            "MlpPolicy",
            env,
            n_steps=2048,
            batch_size=64,
            verbose=0,
        )

        # 4. Run for 60s. SB3 learn() is blocking; we cap by
        #    total_timesteps scaled to roughly 60s throughput.
        #    Empirically ~2-3k steps/s at n_envs=8 → use 120k as cap
        #    and let wall-clock termination via a callback cut it.
        from stable_baselines3.common.callbacks import BaseCallback  # noqa: PLC0415

        class _TimeCutoff(BaseCallback):
            def __init__(self, budget_s: float) -> None:
                super().__init__(verbose=0)
                self._deadline: float = 0.0
                self._budget = budget_s

            def _on_training_start(self) -> None:
                self._deadline = time.perf_counter() + self._budget

            def _on_step(self) -> bool:
                return time.perf_counter() < self._deadline

        model.learn(
            total_timesteps=500_000,
            callback=_TimeCutoff(budget_s=60.0),
        )
        env.close()

    print(f"smoke complete — timings at {out_path}")


if __name__ == "__main__":
    main()
