"""/api/evaluation/results title backfill for legacy rows (BE-T12)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock


class _FakeEvalService:
    """Minimal eval service — just serves a canned list of docs."""

    def __init__(self, docs: list[dict]) -> None:
        self._docs = docs

    async def get_results(self) -> dict:
        return {"data": list(self._docs)}


def _wire(client, docs: list[dict], runs_lookup: dict[str, dict]) -> None:
    """Override app.state with a canned eval service + runs service."""
    client.app.state.eval_service = _FakeEvalService(docs)
    runs_service = MagicMock()
    runs_service.get_by_experiment_ids = AsyncMock(return_value=runs_lookup)
    client.app.state.training_runs_service = runs_service


class TestEvaluationResultsTitleBackfill:
    def test_new_record_passes_through_title_unchanged(self, client):
        _wire(client, docs=[
            {
                "model_path": "exp-a/x__abc__1.zip",
                "bot_level": 1, "n_games": 10,
                "win_rate": 0.5, "avg_score": 7.0,
                "avg_rally_length": 55.0,
                "timestamp": "2026-04-18T00:00:00+00:00",
                "title": "run-new", "experiment_id": "exp-a",
            }
        ], runs_lookup={})
        resp = client.get("/api/evaluation/results")
        row = resp.json()["data"][0]
        assert row["title"] == "run-new"
        # runs lookup shouldn't even be hit since title is present.
        client.app.state.training_runs_service.get_by_experiment_ids.assert_not_awaited()

    def test_legacy_record_gets_title_from_runs_collection(self, client):
        """Pre-T11 doc has no title, no exp_id field — parsed from path."""
        _wire(
            client,
            docs=[{
                "model_path": "exp-legacy/final.zip",
                "bot_level": 1, "n_games": 50,
                "win_rate": 0.4, "avg_score": 6.0,
                "avg_rally_length": 45.0,
                "timestamp": "2026-04-01T00:00:00+00:00",
            }],
            runs_lookup={
                "exp-legacy": {
                    "experiment_id": "exp-legacy",
                    "title": "run-from-db",
                }
            },
        )
        resp = client.get("/api/evaluation/results")
        row = resp.json()["data"][0]
        assert row["title"] == "run-from-db"
        assert row["training_title"] == "run-from-db"  # mirror kept consistent
        assert row["experiment_id"] == "exp-legacy"

    def test_legacy_record_with_experiment_id_field_skips_path_parse(self, client):
        """Row already has experiment_id — use it directly."""
        _wire(
            client,
            docs=[{
                "model_path": "something/else.zip",
                "experiment_id": "exp-direct",
                "bot_level": 2, "n_games": 20,
                "win_rate": 0.3, "avg_score": 4.0,
                "avg_rally_length": 30.0,
                "timestamp": "2026-04-10T00:00:00+00:00",
            }],
            runs_lookup={
                "exp-direct": {
                    "experiment_id": "exp-direct",
                    "title": "run-direct",
                }
            },
        )
        resp = client.get("/api/evaluation/results")
        row = resp.json()["data"][0]
        assert row["title"] == "run-direct"
        assert row["experiment_id"] == "exp-direct"

    def test_missing_run_doc_leaves_title_absent(self, client):
        _wire(
            client,
            docs=[{
                "model_path": "exp-orphan/x__abc__1.zip",
                "bot_level": 1, "n_games": 10,
                "win_rate": 0.5, "avg_score": 7.0,
                "avg_rally_length": 50.0,
                "timestamp": "2026-04-18T00:00:00+00:00",
            }],
            runs_lookup={},
        )
        resp = client.get("/api/evaluation/results")
        row = resp.json()["data"][0]
        assert "title" not in row or row["title"] is None
        # exp_id still surfaced from model_path so FE can link out.
        assert row["experiment_id"] == "exp-orphan"

    def test_flat_path_no_experiment_id_no_backfill(self, client):
        _wire(
            client,
            docs=[{
                "model_path": "final.zip",
                "bot_level": 1, "n_games": 5,
                "win_rate": 0.2, "avg_score": 3.0,
                "avg_rally_length": 20.0,
                "timestamp": "2026-03-15T00:00:00+00:00",
            }],
            runs_lookup={"exp-whatever": {"title": "nope"}},
        )
        resp = client.get("/api/evaluation/results")
        row = resp.json()["data"][0]
        assert "title" not in row or row["title"] is None
        assert "experiment_id" not in row or row["experiment_id"] is None

    def test_runs_service_failure_does_not_break_endpoint(self, client):
        client.app.state.eval_service = _FakeEvalService([{
            "model_path": "exp-a/x__abc__1.zip",
            "bot_level": 1, "n_games": 10,
            "win_rate": 0.5, "avg_score": 7.0,
            "avg_rally_length": 50.0,
            "timestamp": "2026-04-18T00:00:00+00:00",
        }])
        broken = MagicMock()
        broken.get_by_experiment_ids = AsyncMock(side_effect=RuntimeError("mongo down"))
        client.app.state.training_runs_service = broken

        resp = client.get("/api/evaluation/results")
        # Endpoint still returns 200 — backfill degraded silently.
        assert resp.status_code == 200
        row = resp.json()["data"][0]
        # exp_id still came from the path parse (happens before the lookup).
        assert row["experiment_id"] == "exp-a"

    def test_bulk_lookup_deduplicates_experiment_ids(self, client):
        """Two legacy rows from the same experiment → one runs lookup."""
        _wire(
            client,
            docs=[
                {
                    "model_path": "exp-shared/a__abc__1.zip",
                    "bot_level": 1, "n_games": 10,
                    "win_rate": 0.5, "avg_score": 7.0,
                    "avg_rally_length": 50.0,
                    "timestamp": "2026-04-18T00:00:00+00:00",
                },
                {
                    "model_path": "exp-shared/b__abc__2.zip",
                    "bot_level": 2, "n_games": 20,
                    "win_rate": 0.6, "avg_score": 9.0,
                    "avg_rally_length": 60.0,
                    "timestamp": "2026-04-18T01:00:00+00:00",
                },
            ],
            runs_lookup={
                "exp-shared": {
                    "experiment_id": "exp-shared",
                    "title": "run-shared",
                }
            },
        )
        resp = client.get("/api/evaluation/results")
        rows = resp.json()["data"]
        assert all(r["title"] == "run-shared" for r in rows)
        # Exactly one lookup call despite two rows.
        svc = client.app.state.training_runs_service
        svc.get_by_experiment_ids.assert_awaited_once()
        args = svc.get_by_experiment_ids.await_args.args
        assert len(args[0]) == 1
        assert args[0][0] == "exp-shared"
