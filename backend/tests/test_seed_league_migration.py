"""Migration script — seed_league_from_v1_models (B-impl-6)."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.models.league import (
    ANCHOR_RATINGS,
    LEAGUE_POOL_SIZE,
    SEED_ELO,
)
from scripts.seed_league_from_v1_models import (
    build_anchor_rows,
    build_checkpoint_row,
    discover_checkpoints,
    parse_checkpoint_filename,
    seed_manifest,
)


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")


class TestParseCheckpointFilename:
    def test_t2_format(self):
        slug, step = parse_checkpoint_filename(
            "run-baseline__abcdef01__200000"
        )
        assert slug == "run-baseline"
        assert step == 200_000

    def test_final_uses_sentinel(self):
        _, step = parse_checkpoint_filename(
            "run-baseline__abcdef01__final"
        )
        assert step == 10**12

    def test_legacy_name_returns_none(self):
        slug, step = parse_checkpoint_filename("final")
        assert slug is None and step is None
        slug, step = parse_checkpoint_filename("200000")
        assert slug is None and step is None

    def test_malformed_exp8_rejected(self):
        # exp8 must be exactly 8 hex chars.
        assert parse_checkpoint_filename("slug__notahex__200") == (None, None)
        assert parse_checkpoint_filename("slug__abcdef0__200") == (None, None)


class TestDiscoverCheckpoints:
    def test_picks_up_nested_zips(self, tmp_path):
        _touch(tmp_path / "exp-a" / "run-a__abcdef01__100.zip")
        _touch(tmp_path / "exp-b" / "run-b__abcdef02__final.zip")
        paths = discover_checkpoints(tmp_path)
        assert len(paths) == 2

    def test_skips_league_subdir(self, tmp_path):
        """A re-run must NOT admit migration artefacts as legacy rows."""
        _touch(tmp_path / "exp-a" / "run-a__abcdef01__100.zip")
        _touch(tmp_path / "league" / "run-a__abcdef01__100.zip")
        paths = discover_checkpoints(tmp_path)
        assert len(paths) == 1
        # The surviving path is the exp-a one, not the league-subdir copy.
        assert paths[0].parent.name == "exp-a"

    def test_missing_dir_returns_empty(self, tmp_path):
        assert discover_checkpoints(tmp_path / "absent") == []


class TestBuildRow:
    def test_sets_v1_legacy_source(self, tmp_path):
        model_dir = tmp_path / "models"
        p = model_dir / "exp-a" / "run-a__abcdef01__200000.zip"
        _touch(p)
        row = build_checkpoint_row(p, model_dir, admitted_at="2026-01-01T00:00:00+00:00")
        assert row.source == "v1_legacy"
        assert row.elo == SEED_ELO
        assert row.step == 200_000
        assert row.experiment_id == "exp-a"
        assert row.id == "run-a__abcdef01__200000"

    def test_legacy_name_still_admitted_with_null_step(self, tmp_path):
        model_dir = tmp_path / "models"
        p = model_dir / "exp-old" / "final.zip"
        _touch(p)
        row = build_checkpoint_row(p, model_dir, admitted_at="2026-01-01T00:00:00+00:00")
        assert row.step is None
        assert row.experiment_id == "exp-old"
        assert row.source == "v1_legacy"

    def test_file_at_root_has_no_experiment_id(self, tmp_path):
        model_dir = tmp_path / "models"
        p = model_dir / "loose__abcdef01__100.zip"
        _touch(p)
        row = build_checkpoint_row(p, model_dir, admitted_at="2026-01-01T00:00:00+00:00")
        assert row.experiment_id is None


class TestBuildAnchorRows:
    def test_three_anchors_at_adr_ratings(self):
        rows = build_anchor_rows(admitted_at="2026-01-01T00:00:00+00:00")
        by_id = {r.id: r for r in rows}
        assert set(by_id) == set(ANCHOR_RATINGS)
        for name, rating in ANCHOR_RATINGS.items():
            assert by_id[name].elo == rating
            assert by_id[name].source == "anchor"


class TestSeedManifest:
    def test_writes_manifest_with_anchors_plus_legacy(self, tmp_path):
        model_dir = tmp_path / "models"
        _touch(model_dir / "exp-a" / "run-a__abcdef01__100.zip")
        _touch(model_dir / "exp-a" / "run-a__abcdef01__200.zip")
        _touch(model_dir / "exp-b" / "run-b__abcdef02__final.zip")

        league_dir = tmp_path / "league"
        manifest = seed_manifest(model_dir, league_dir, dry_run=False)

        # 3 anchors + 3 legacy.
        assert len(manifest.checkpoints) == 6
        anchors = [c for c in manifest.checkpoints if c.source == "anchor"]
        assert len(anchors) == 3
        legacy = [c for c in manifest.checkpoints if c.source == "v1_legacy"]
        assert len(legacy) == 3
        # champion_id is null at seed time (no matches played yet).
        assert manifest.champion_id is None
        assert manifest.generation == 0
        assert manifest.pool_size == LEAGUE_POOL_SIZE
        # File actually written.
        assert (league_dir / "manifest.json").exists()

    def test_dry_run_does_not_write(self, tmp_path):
        model_dir = tmp_path / "models"
        _touch(model_dir / "exp-a" / "run-a__abcdef01__100.zip")

        league_dir = tmp_path / "league"
        manifest = seed_manifest(model_dir, league_dir, dry_run=True)
        # Manifest object returned, but nothing on disk.
        assert len(manifest.checkpoints) >= 1
        assert not (league_dir / "manifest.json").exists()

    def test_idempotent_rerun_does_not_duplicate_rows(self, tmp_path):
        """Re-running against the same models should produce the same
        set of rows (same ids), not double them.
        """
        model_dir = tmp_path / "models"
        _touch(model_dir / "exp-a" / "run-a__abcdef01__100.zip")

        league_dir = tmp_path / "league"
        first = seed_manifest(model_dir, league_dir, dry_run=False)
        second = seed_manifest(model_dir, league_dir, dry_run=False)
        assert {c.id for c in first.checkpoints} == {c.id for c in second.checkpoints}
        assert len(first.checkpoints) == len(second.checkpoints)
