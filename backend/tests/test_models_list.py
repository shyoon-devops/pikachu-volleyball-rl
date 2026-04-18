"""GET /api/models with title filter + enriched fields (BE-T8)."""

from __future__ import annotations

from pathlib import Path

import pytest


def _seed_models(model_dir: Path, files: list[str]) -> None:
    """Create zero-byte .zip files under model_dir (can be nested)."""
    model_dir.mkdir(parents=True, exist_ok=True)
    for rel in files:
        p = model_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"")


class TestListModelsNoFilter:
    def test_default_shape_has_legacy_and_enriched_fields(
        self, client, tmp_path, monkeypatch
    ):
        model_dir = tmp_path / "models"
        _seed_models(model_dir, [
            "exp-aaaaaa/run-baseline__abcdef01__200000.zip",
            "exp-bbbbbb/legacy__final.zip",
        ])
        monkeypatch.setenv("MODEL_DIR", str(model_dir))

        resp = client.get("/api/models")
        assert resp.status_code == 200
        rows = resp.json()["models"]
        # Two files, one parseable.
        assert len(rows) == 2
        first = next(r for r in rows if "run-baseline" in r["filename"])
        # Legacy fields preserved.
        assert first["path"].endswith("run-baseline__abcdef01__200000.zip")
        assert first["size_bytes"] == 0
        # Enriched fields.
        assert first["filename"] == "run-baseline__abcdef01__200000.zip"
        assert first["slug"] == "run-baseline"
        assert first["title"] == "run-baseline"
        assert first["step"] == 200000
        assert isinstance(first["created_at"], str)


class TestListModelsTitleFilter:
    def test_title_filters_by_slug(self, client, tmp_path, monkeypatch):
        model_dir = tmp_path / "models"
        _seed_models(model_dir, [
            "exp-1/run-baseline__abcdef01__100000.zip",
            "exp-1/run-baseline__abcdef01__200000.zip",
            "exp-2/run-variant__11111111__500000.zip",
            "exp-3/legacy-noprefix.zip",
        ])
        monkeypatch.setenv("MODEL_DIR", str(model_dir))

        resp = client.get("/api/models?title=run-baseline")
        rows = resp.json()["models"]
        assert len(rows) == 2
        assert all(r["slug"] == "run-baseline" for r in rows)
        # Newest-step-first ordering.
        assert [r["step"] for r in rows] == [200000, 100000]

    def test_title_slugifies_query(self, client, tmp_path, monkeypatch):
        """User types ``Run Baseline`` — slugify to ``run-baseline``."""
        model_dir = tmp_path / "models"
        _seed_models(model_dir, [
            "exp-1/run-baseline__abcdef01__300000.zip",
        ])
        monkeypatch.setenv("MODEL_DIR", str(model_dir))

        resp = client.get("/api/models?title=Run Baseline")
        rows = resp.json()["models"]
        assert len(rows) == 1
        assert rows[0]["slug"] == "run-baseline"

    def test_title_filter_excludes_legacy_names(self, client, tmp_path, monkeypatch):
        model_dir = tmp_path / "models"
        _seed_models(model_dir, [
            "exp-1/run-xyz__abcdef01__100000.zip",
            "exp-2/legacy_no_double_underscore.zip",
        ])
        monkeypatch.setenv("MODEL_DIR", str(model_dir))

        resp = client.get("/api/models?title=legacy")
        rows = resp.json()["models"]
        # Legacy filename can't be matched against a slug filter.
        assert rows == []

    def test_final_checkpoint_sorts_top(self, client, tmp_path, monkeypatch):
        model_dir = tmp_path / "models"
        _seed_models(model_dir, [
            "exp-1/run-x__abcdef01__200000.zip",
            "exp-1/run-x__abcdef01__final.zip",
        ])
        monkeypatch.setenv("MODEL_DIR", str(model_dir))

        resp = client.get("/api/models?title=run-x")
        rows = resp.json()["models"]
        assert len(rows) == 2
        # "final" is a high-sentinel int → sorts first in desc order.
        assert rows[0]["filename"].endswith("__final.zip")

    def test_limit_truncates_results(self, client, tmp_path, monkeypatch):
        model_dir = tmp_path / "models"
        _seed_models(model_dir, [
            f"exp-1/run-x__abcdef01__{i:06d}.zip" for i in range(1, 11)
        ])
        monkeypatch.setenv("MODEL_DIR", str(model_dir))

        resp = client.get("/api/models?title=run-x&limit=3")
        rows = resp.json()["models"]
        assert len(rows) == 3
        # Biggest step first.
        assert rows[0]["step"] == 10
        assert rows[2]["step"] == 8


class TestListModelsEmpty:
    def test_missing_model_dir_returns_empty(
        self, client, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("MODEL_DIR", str(tmp_path / "does-not-exist"))
        resp = client.get("/api/models")
        assert resp.status_code == 200
        assert resp.json() == {"models": []}

    def test_title_filter_no_match_returns_empty(
        self, client, tmp_path, monkeypatch
    ):
        model_dir = tmp_path / "models"
        _seed_models(model_dir, [
            "exp-1/run-alpha__abcdef01__100000.zip",
        ])
        monkeypatch.setenv("MODEL_DIR", str(model_dir))

        resp = client.get("/api/models?title=run-nonexistent")
        assert resp.json() == {"models": []}
