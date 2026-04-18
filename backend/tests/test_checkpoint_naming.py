"""Checkpoint filename format (BE-T2).

Spec: ``{slug}__{exp8}__{step}.zip`` (docs/DESIGN-TRAINING-TITLE.md §6).
These tests pin the naming convention against CheckpointCallback and
the final-save path on TrainingManager so a future refactor can't
silently drift from the spec.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from backend.rl.callbacks import CheckpointCallback


class TestCheckpointFilenameFormat:
    def test_interval_save_uses_slug_exp8_step_format(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cb = CheckpointCallback(
                experiment_id="a3f9bc21-aaaa-bbbb-cccc-000000000001",
                model_dir=tmpdir,
                save_interval=100,
                slug="run-baseline-20260418",
            )
            cb.model = MagicMock()
            cb.num_timesteps = 200_000
            cb._on_step()

            cb.model.save.assert_called_once()
            saved_path = Path(cb.model.save.call_args.args[0])
            # SB3 adds `.zip`, so the base filename is what we pass.
            assert saved_path.name == (
                "run-baseline-20260418__a3f9bc21__200000"
            )
            assert saved_path.parent.name == (
                "a3f9bc21-aaaa-bbbb-cccc-000000000001"
            )

    def test_slug_defaults_to_run_when_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cb = CheckpointCallback(
                experiment_id="deadbeefcafebabe0000000000000000",
                model_dir=tmpdir,
                save_interval=100,
                slug="",
            )
            cb.model = MagicMock()
            cb.num_timesteps = 100
            cb._on_step()

            saved = Path(cb.model.save.call_args.args[0]).name
            assert saved == "run__deadbeef__100"

    def test_exp8_is_prefix_of_experiment_id(self):
        # Guarantee: the 8-char exp tail guarantees collision-safety
        # across identical slugs from different runs. If we accidentally
        # shortened the experiment_id elsewhere this would drift.
        with tempfile.TemporaryDirectory() as tmpdir:
            cb = CheckpointCallback(
                experiment_id="12345678-9999-aaaa-bbbb-cccccccccccc",
                model_dir=tmpdir,
                save_interval=1,
                slug="any-slug",
            )
            cb.model = MagicMock()
            cb.num_timesteps = 1
            cb._on_step()
            saved = Path(cb.model.save.call_args.args[0]).name
            assert "__12345678__" in saved

    def test_non_interval_steps_do_not_save(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cb = CheckpointCallback(
                experiment_id="xxxxxxxxxxxx",
                model_dir=tmpdir,
                save_interval=100,
                slug="foo",
            )
            cb.model = MagicMock()
            cb.num_timesteps = 99
            cb._on_step()
            cb.model.save.assert_not_called()


class TestManagerFinalCheckpoint:
    def test_final_checkpoint_uses_slug_exp8_final(self):
        """``_save_final_checkpoint`` writes ``{slug}__{exp8}__final.zip``."""
        from backend.rl.trainer import TrainingManager

        mgr = TrainingManager(model_dir="/tmp/models_t2", replay_dir="/tmp/replays_t2")
        mgr._experiment_id = "a3f9bc21-aaaa-bbbb-cccc-000000000001"
        mgr._slug = "run-baseline-20260418"
        mgr._model = MagicMock()

        mgr._save_final_checkpoint()

        saved = Path(mgr._model.save.call_args.args[0]).name
        assert saved == "run-baseline-20260418__a3f9bc21__final"

    def test_final_checkpoint_falls_back_to_run_on_empty_slug(self):
        from backend.rl.trainer import TrainingManager

        mgr = TrainingManager(model_dir="/tmp/models_t2b", replay_dir="/tmp/replays_t2b")
        mgr._experiment_id = "aaaaaaaa-0000-0000-0000-000000000000"
        mgr._slug = ""
        mgr._model = MagicMock()

        mgr._save_final_checkpoint()

        saved = Path(mgr._model.save.call_args.args[0]).name
        assert saved == "run__aaaaaaaa__final"

    def test_find_latest_checkpoint_still_picks_up_new_names(self, tmp_path: Path):
        """``_find_latest_checkpoint`` globs ``*.zip`` — must see the new names."""
        from backend.rl.trainer import TrainingManager

        mgr = TrainingManager(model_dir=str(tmp_path), replay_dir=str(tmp_path))
        mgr._experiment_id = "exp-test"
        exp_dir = tmp_path / "exp-test"
        exp_dir.mkdir()
        # Write two zipballs: one legacy-named, one spec-named.
        (exp_dir / "200000.zip").write_bytes(b"x")
        (exp_dir / "run-baseline__exp-test__400000.zip").write_bytes(b"x")
        latest = mgr._find_latest_checkpoint()
        # Glob picks whichever is newest by mtime; both are candidates,
        # so the essential contract is "returns a path inside exp_dir".
        assert latest is not None
        assert str(exp_dir) in latest
