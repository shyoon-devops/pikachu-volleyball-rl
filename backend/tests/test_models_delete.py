"""DELETE /api/models bulk (BE-T9).

Covers the happy path (deletion), three rejection branches (not found,
path traversal, not a file), and the 409 active-run protection.
"""

from __future__ import annotations

from pathlib import Path


def _seed(model_dir: Path, files: list[str]) -> None:
    model_dir.mkdir(parents=True, exist_ok=True)
    for rel in files:
        p = model_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")


class TestDeleteModelsHappyPath:
    def test_deletes_listed_files(self, client, tmp_path, monkeypatch):
        model_dir = tmp_path / "models"
        _seed(model_dir, [
            "exp-1/a__abcdef01__100.zip",
            "exp-1/a__abcdef01__200.zip",
        ])
        monkeypatch.setenv("MODEL_DIR", str(model_dir))

        resp = client.request(
            "DELETE",
            "/api/models",
            json={"paths": [
                "exp-1/a__abcdef01__100.zip",
                "exp-1/a__abcdef01__200.zip",
            ]},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert sorted(body["deleted"]) == [
            "exp-1/a__abcdef01__100.zip",
            "exp-1/a__abcdef01__200.zip",
        ]
        assert body["failed"] == []
        # Files are actually gone.
        assert not (model_dir / "exp-1" / "a__abcdef01__100.zip").exists()
        assert not (model_dir / "exp-1" / "a__abcdef01__200.zip").exists()

    def test_strips_leading_models_prefix(self, client, tmp_path, monkeypatch):
        """FE may send ``models/…`` prefixes — the endpoint normalises."""
        model_dir = tmp_path / "models"
        _seed(model_dir, ["exp-1/x__abcdef01__1.zip"])
        monkeypatch.setenv("MODEL_DIR", str(model_dir))

        resp = client.request(
            "DELETE",
            "/api/models",
            json={"paths": ["models/exp-1/x__abcdef01__1.zip"]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["deleted"] == ["models/exp-1/x__abcdef01__1.zip"]

    def test_empty_list_is_noop(self, client, tmp_path, monkeypatch):
        monkeypatch.setenv("MODEL_DIR", str(tmp_path / "models"))
        resp = client.request("DELETE", "/api/models", json={"paths": []})
        assert resp.status_code == 200
        assert resp.json() == {"deleted": [], "failed": []}


class TestDeleteModelsRejects:
    def test_traversal_rejected_with_reason(self, client, tmp_path, monkeypatch):
        model_dir = tmp_path / "models"
        model_dir.mkdir()
        # Create a target OUTSIDE model_dir the traversal attempts.
        outside = tmp_path / "outside.zip"
        outside.write_bytes(b"sensitive")
        monkeypatch.setenv("MODEL_DIR", str(model_dir))

        resp = client.request(
            "DELETE",
            "/api/models",
            json={"paths": ["../outside.zip"]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["deleted"] == []
        assert len(body["failed"]) == 1
        assert body["failed"][0]["reason"] == "outside_model_dir"
        # The outside file must still exist.
        assert outside.exists()

    def test_missing_file_reports_not_found(self, client, tmp_path, monkeypatch):
        model_dir = tmp_path / "models"
        model_dir.mkdir()
        monkeypatch.setenv("MODEL_DIR", str(model_dir))

        resp = client.request(
            "DELETE",
            "/api/models",
            json={"paths": ["exp-1/does-not-exist.zip"]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["deleted"] == []
        assert body["failed"][0]["reason"] == "not_found"

    def test_empty_path_rejected(self, client, tmp_path, monkeypatch):
        monkeypatch.setenv("MODEL_DIR", str(tmp_path / "models"))
        resp = client.request("DELETE", "/api/models", json={"paths": ["   "]})
        body = resp.json()
        assert body["deleted"] == []
        assert body["failed"][0]["reason"] == "empty_path"

    def test_not_a_file_rejected(self, client, tmp_path, monkeypatch):
        model_dir = tmp_path / "models"
        (model_dir / "exp-dir").mkdir(parents=True)
        monkeypatch.setenv("MODEL_DIR", str(model_dir))

        resp = client.request(
            "DELETE",
            "/api/models",
            json={"paths": ["exp-dir"]},
        )
        body = resp.json()
        assert body["deleted"] == []
        assert body["failed"][0]["reason"] == "not_a_file"

    def test_payload_cap_enforced(self, client, tmp_path, monkeypatch):
        """>100 paths is a parse-time 422."""
        monkeypatch.setenv("MODEL_DIR", str(tmp_path / "models"))
        resp = client.request(
            "DELETE",
            "/api/models",
            json={"paths": [f"exp-{i}/x.zip" for i in range(101)]},
        )
        assert resp.status_code == 422


class TestDeleteModelsActiveRunProtection:
    def test_active_run_files_return_409(
        self, client, tmp_path, monkeypatch
    ):
        model_dir = tmp_path / "models"
        _seed(model_dir, [
            "exp-running/a__abcdef01__100.zip",
            "exp-other/b__abcdef01__200.zip",
        ])
        monkeypatch.setenv("MODEL_DIR", str(model_dir))

        # Simulate a running training — wire the FakeGameService-style
        # mock to report that state.
        client.app.state.training_service.status = lambda: {
            "state": "running",
            "current_step": 10,
            "current_episode": 1,
            "experiment_id": "exp-running",
            "bot_level": 1,
            "started_at": None,
            "title": "run-protect",
        }

        resp = client.request(
            "DELETE",
            "/api/models",
            json={"paths": [
                "exp-running/a__abcdef01__100.zip",
                "exp-other/b__abcdef01__200.zip",
            ]},
        )
        assert resp.status_code == 409
        detail = resp.json()["detail"]
        assert "protected" in detail
        assert detail["protected"] == ["exp-running/a__abcdef01__100.zip"]
        # Neither file was deleted (whole-batch reject).
        assert (model_dir / "exp-running" / "a__abcdef01__100.zip").exists()
        assert (model_dir / "exp-other" / "b__abcdef01__200.zip").exists()

    def test_stopped_run_can_be_deleted(
        self, client, tmp_path, monkeypatch
    ):
        """Once training stops, the protection lifts."""
        model_dir = tmp_path / "models"
        _seed(model_dir, ["exp-old/c__abcdef01__100.zip"])
        monkeypatch.setenv("MODEL_DIR", str(model_dir))

        # Default client status is ``state="stopped"`` — no protection.
        resp = client.request(
            "DELETE",
            "/api/models",
            json={"paths": ["exp-old/c__abcdef01__100.zip"]},
        )
        assert resp.status_code == 200
        assert resp.json()["deleted"] == [
            "exp-old/c__abcdef01__100.zip"
        ]
