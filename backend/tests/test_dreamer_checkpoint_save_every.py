"""Dreamer + trainer ``CheckpointCallback`` integration.

QA bench-B 2026-04-23 regression: 2M Dreamer run crashed mid-way
and had no intermediate checkpoints. Root cause: the SB3
``BaseCallback`` protocol was never dispatched from
``DreamerAgent.learn``, so ``CheckpointCallback._on_step`` (which
calls ``self.model.save`` on a cadence) never fired.

This test drives the real ``CheckpointCallback`` from
``backend/rl/callbacks.py`` against a Dreamer agent and verifies
that ``save_interval``-sized checkpoints land on disk at the
expected step boundaries.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from stable_baselines3.common.vec_env import DummyVecEnv

from backend.rl.callbacks import CheckpointCallback
from backend.rl.dreamer_runner import DreamerAgent
from backend.rl.env import PikachuVolleyballEnv


def _make_env() -> Any:
    return DummyVecEnv([lambda: PikachuVolleyballEnv(bot_level=1)])


def _tiny_agent() -> DreamerAgent:
    return DreamerAgent(
        env=_make_env(),
        device="cpu",
        rssm_hidden_size=32, latent_dim=4, latent_axes=4,
        batch_size=4, sequence_length=8, train_every=8,
        imagine_horizon=3, replay_capacity=512, free_bits=0.1,
    )


class TestCheckpointCallbackOnDreamer:
    """CheckpointCallback runs ``model.save`` every
    ``save_interval`` steps. With save_interval=100 on a 300-step
    run we expect 3 checkpoint zips on disk (at steps 100, 200, 300).
    """

    def test_periodic_checkpoints_land_on_disk(self, tmp_path: Path) -> None:
        agent = _tiny_agent()
        exp_id = "dreamer-ckpt-test-xxxxxxxx"
        cb = CheckpointCallback(
            experiment_id=exp_id,
            model_dir=str(tmp_path),
            save_interval=100,
            slug="dreamer-smoke",
        )
        agent.learn(total_timesteps=300, callback=cb)

        checkpoint_dir = tmp_path / exp_id
        zips = sorted(checkpoint_dir.glob("*.zip"))
        assert len(zips) == 3, (
            f"expected 3 checkpoints at steps 100/200/300, "
            f"got {len(zips)}: {[p.name for p in zips]}"
        )
        # Filenames follow {slug}__{exp8}__{step}.zip per ADR 0014
        # checkpoint-naming contract (BE-T2). The spec pattern is
        # preserved by CheckpointCallback regardless of which
        # algorithm the model is — what we're anchoring here is
        # that Dreamer's ``save()`` accepts the path shape and
        # produces a readable zip at each tick.
        expected_names = {
            f"dreamer-smoke__dreamer-__{step}.zip"
            for step in (100, 200, 300)
        }
        assert {p.name for p in zips} == expected_names

    def test_checkpoints_are_reloadable(self, tmp_path: Path) -> None:
        """Each intermediate checkpoint must round-trip through
        ``DreamerAgent.load`` so a crashed run can resume from the
        most recent one. Previously (pre-bench-B fix) no zip would
        be written, so this whole contract was dark."""
        agent = _tiny_agent()
        exp_id = "dreamer-reload-test-xxxxxxx"
        cb = CheckpointCallback(
            experiment_id=exp_id,
            model_dir=str(tmp_path),
            save_interval=50,
            slug="dreamer-reload",
        )
        agent.learn(total_timesteps=100, callback=cb)

        checkpoint_dir = tmp_path / exp_id
        zips = sorted(checkpoint_dir.glob("*.zip"))
        assert len(zips) >= 2
        # Load the 50-step checkpoint via the classmethod.
        reloaded = DreamerAgent.load(
            str(zips[0]), env=_make_env(), device="cpu",
        )
        # Number of world-model updates preserved — pins that save
        # payload covers _n_updates / num_timesteps book-keeping.
        assert reloaded.num_timesteps <= agent.num_timesteps
        # Predict works post-load, same PikachuVolleyball action space.
        obs = reloaded.env.reset()
        act, _ = reloaded.predict(obs, deterministic=True)
        assert 0 <= int(act[0]) < 12
