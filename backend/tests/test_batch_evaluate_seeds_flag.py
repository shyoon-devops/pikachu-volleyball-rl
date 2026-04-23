"""``batch_evaluate --seeds`` CLI flag + run_batch multi-seed expansion.

bench-B curve-eval plan: 5 ckpt × 3 level × **5 seed** × 100 games =
7,500 matches for variance estimates. Without ``--seeds`` the harness
can only run the single-seed point estimate. These tests pin the CLI
surface + task expansion so that harness plan can execute.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

from backend.rl.batch_evaluate import (
    DEFAULT_SEEDS,
    BatchTask,
    build_arg_parser,
    run_batch,
)
from backend.rl.env import PikachuVolleyballEnv


def _train_tiny_ppo(tmp_path: Path) -> Path:
    from stable_baselines3 import PPO
    from stable_baselines3.common.monitor import Monitor
    from stable_baselines3.common.vec_env import DummyVecEnv

    env = DummyVecEnv([lambda: Monitor(PikachuVolleyballEnv(bot_level=1))])
    m = PPO(
        "MlpPolicy", env, n_steps=16, batch_size=4, n_epochs=1,
        verbose=0, policy_kwargs={"net_arch": [16, 16]},
    )
    m.learn(total_timesteps=16)
    p = tmp_path / "tiny_ppo"
    m.save(str(p))
    return tmp_path / "tiny_ppo.zip"


class TestSeedsCliFlag:
    """``--seeds N [N ...]`` surfaces + defaults to the single-seed
    back-compat value ``(42,)``."""

    def test_default_seeds_single_value(self) -> None:
        args = build_arg_parser().parse_args(["models/"])
        assert args.seeds == list(DEFAULT_SEEDS) == [42]

    def test_single_seed(self) -> None:
        args = build_arg_parser().parse_args(["models/", "--seeds", "7"])
        assert args.seeds == [7]

    def test_multiple_seeds(self) -> None:
        # The curve-eval scenario: 5 distinct seeds.
        args = build_arg_parser().parse_args(
            ["models/", "--seeds", "1", "2", "3", "4", "5"]
        )
        assert args.seeds == [1, 2, 3, 4, 5]

    def test_algorithm_flag_default_none(self) -> None:
        args = build_arg_parser().parse_args(["models/"])
        assert args.algorithm is None

    def test_algorithm_flag_explicit(self) -> None:
        args = build_arg_parser().parse_args(
            ["models/", "--algorithm", "dreamer_v3"]
        )
        assert args.algorithm == "dreamer_v3"

    def test_algorithm_rejects_unknown(self) -> None:
        with pytest.raises(SystemExit):
            build_arg_parser().parse_args(
                ["models/", "--algorithm", "a2c"]
            )


class TestRunBatchSeedExpansion:
    """``run_batch`` multiplies tasks by the seed axis so downstream
    variance estimates see independent trajectories. This is
    load-bearing for the 7500-match curve plan."""

    def test_task_count_scales_with_seeds(self, tmp_path: Path) -> None:
        ckpt = _train_tiny_ppo(tmp_path)
        # 1 ckpt × 2 levels × 3 seeds = 6 tasks, each producing a result.
        report = run_batch(
            [str(ckpt)],
            levels=(1, 2),
            n_games=1,
            seeds=(11, 22, 33),
            algorithm="ppo",
            executor_factory=ThreadPoolExecutor,
            workers=1,
        )
        assert len(report.results) + len(report.failures) == 6

    def test_multi_seed_trajectories_differ(self, tmp_path: Path) -> None:
        """Running the same checkpoint at two different seeds must
        produce non-identical trajectories — the whole point of the
        flag is variance estimation."""
        ckpt = _train_tiny_ppo(tmp_path)
        report = run_batch(
            [str(ckpt)],
            levels=(1,),
            # Enough games for PPO determinism + env seed variation
            # to actually produce different results across seeds.
            n_games=8,
            seeds=(100, 200, 300),
            algorithm="ppo",
            executor_factory=ThreadPoolExecutor,
            workers=1,
        )
        # Pair each seed with its result.
        by_seed: dict[int, Any] = {}
        for t, r in zip(
            [BatchTask(str(ckpt), 1, 8, s, "ppo") for s in (100, 200, 300)],
            report.results,
        ):
            by_seed[t.seed] = r
        # At least one of (avg_score, avg_opponent_score,
        # avg_episode_length) differs across seeds — env.reset(seed)
        # flips initial ball position / serve side, producing
        # different deterministic PPO trajectories. Use a loose
        # disjunction because a tiny 16-step PPO + 8 games is noisy.
        scores = {r.avg_score for r in report.results}
        ep_lens = {r.avg_episode_length for r in report.results}
        opp_scores = {r.avg_opponent_score for r in report.results}
        assert (
            len(scores) > 1 or len(ep_lens) > 1 or len(opp_scores) > 1
        ), (
            "--seeds produced identical trajectories — seed is not "
            "being forwarded into env.reset / predict"
        )

    def test_empty_seeds_rejected(self, tmp_path: Path) -> None:
        ckpt = _train_tiny_ppo(tmp_path)
        with pytest.raises(ValueError, match="seeds"):
            run_batch(
                [str(ckpt)],
                levels=(1,),
                n_games=1,
                seeds=(),
                executor_factory=ThreadPoolExecutor,
            )


class TestBatchTaskSeedField:
    """``BatchTask`` carries seed + algorithm so workers in
    ProcessPool children have all info to reproduce the run."""

    def test_batch_task_default_seed_42(self) -> None:
        t = BatchTask(model_path="/x.zip", bot_level=1, n_games=5)
        assert t.seed == 42
        assert t.algorithm is None

    def test_batch_task_explicit_seed_and_algorithm(self) -> None:
        t = BatchTask(
            model_path="/x.zip", bot_level=1, n_games=5,
            seed=7, algorithm="dreamer_v3",
        )
        assert t.seed == 7
        assert t.algorithm == "dreamer_v3"
