"""Async evaluation endpoint — POST 202 + job_id, GET status polling.

Regression guard for the nginx 504 incident: the sync endpoint used to
hold the HTTP connection open for the full evaluation (minutes), and
nginx's 60s upstream timeout cut the response before the evaluator
finished. The async split moves the work into a background task and
surfaces state through a polled status endpoint; these tests pin the
contract that split relies on.
"""

from __future__ import annotations

import asyncio
import time

import pytest


def _poll_until_done(client, job_id: str, timeout: float = 5.0):
    """Poll GET /evaluation/status/{job_id} until state != pending/running."""
    deadline = time.monotonic() + timeout
    last: dict | None = None
    while time.monotonic() < deadline:
        resp = client.get(f"/api/evaluation/status/{job_id}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        last = body
        if body["state"] in ("done", "failed"):
            return body
        time.sleep(0.05)
    raise AssertionError(f"Job {job_id} did not finish within {timeout}s (last={last})")


class TestEvalRunAccepted:
    """POST /api/evaluation/run returns 202 + job_id immediately."""

    def test_post_returns_202_with_job_id(self, client):
        # Use the FakeEvalService backdoor path that passes the sync
        # preflight but fails in the background task — exercises the
        # happy path of the POST (202 + job_id), not the failure path.
        resp = client.post(
            "/api/evaluation/run",
            json={"model_path": "bgfail/model.zip", "bot_level": 1, "n_games": 1},
        )
        assert resp.status_code == 202, resp.text
        body = resp.json()
        assert "job_id" in body
        assert body["state"] == "pending"
        assert isinstance(body["job_id"], str) and len(body["job_id"]) >= 8

    def test_traversal_rejected_synchronously_as_404(self, client):
        """Preflight: bad paths come back 404 on the POST, not 202 then a stale job."""
        resp = client.post(
            "/api/evaluation/run",
            json={"model_path": "../../etc/passwd", "bot_level": 1, "n_games": 1},
        )
        assert resp.status_code == 404
        assert "Invalid model path" in resp.json()["detail"]


class TestEvalStatus:
    """GET /api/evaluation/status/{job_id} — shape + failure propagation."""

    def test_unknown_job_id_returns_404(self, client):
        resp = client.get("/api/evaluation/status/not-a-real-job-id")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Job not found"

    def test_failed_job_surfaces_error_via_status(self, client):
        """Non-traversal bad path is accepted (202), then fails in the bg task.

        This is the key contract the FE polling relies on — a POST that
        returns 202 must eventually transition to state="failed" with an
        error string, not hang in "running" forever.
        """
        # Backdoor path passes preflight; background ``run`` then raises.
        resp = client.post(
            "/api/evaluation/run",
            json={"model_path": "bgfail/model.zip", "bot_level": 1, "n_games": 1},
        )
        assert resp.status_code == 202, resp.text
        job_id = resp.json()["job_id"]
        final = _poll_until_done(client, job_id)
        assert final["state"] == "failed"
        assert final["error"] is not None
        assert "not_found" in final["error"].lower() or "Model" in final["error"]
        # Timestamps must advance through the lifecycle.
        assert final["created_at"] is not None
        assert final["finished_at"] is not None


class TestEvalSemaphore:
    """Only one evaluation runs at a time — 409 on duplicate submit."""

    def test_second_submit_while_running_returns_409(self, client, monkeypatch):
        """Hold the semaphore outside FastAPI so the endpoint sees it locked.

        We bypass the background-task path entirely — this test pins the
        gating logic of the endpoint itself, not the scheduler. The real
        task is covered by the failure-propagation test above.
        """
        from backend.app.api import routes as routes_mod

        loop = asyncio.new_event_loop()
        try:
            # Acquire the semaphore on the same loop the endpoint reads.
            # TestClient runs handlers on its own loop — but _eval_semaphore
            # is a module-level object keyed by the loop it was created
            # on; since the first await binds it to the running loop,
            # acquiring from a different loop would not register. Use the
            # module's ``asyncio.get_running_loop`` path by running a
            # sync acquire via ``run_until_complete``.
            assert routes_mod._eval_semaphore._value == 1, (
                "precondition: semaphore should be idle at test start"
            )
            loop.run_until_complete(routes_mod._eval_semaphore.acquire())
            try:
                resp = client.post(
                    "/api/evaluation/run",
                    json={"model_path": "model.zip", "bot_level": 1, "n_games": 1},
                )
                assert resp.status_code == 409
                assert "already in progress" in resp.json()["detail"].lower()
            finally:
                routes_mod._eval_semaphore.release()
        finally:
            loop.close()


class TestEvalJobRegistry:
    """Unit coverage for the in-memory job registry."""

    def test_lifecycle_pending_running_done(self):
        from backend.app.services.eval_jobs import EvalJobRegistry

        reg = EvalJobRegistry()
        loop = asyncio.new_event_loop()
        try:
            job_id = loop.run_until_complete(reg.create())
            assert loop.run_until_complete(reg.get(job_id))["state"] == "pending"

            loop.run_until_complete(reg.mark_running(job_id, total=5))
            mid = loop.run_until_complete(reg.get(job_id))
            assert mid["state"] == "running"
            assert mid["progress_total"] == 5
            assert mid["started_at"] is not None

            loop.run_until_complete(reg.update_progress(job_id, 3))
            assert loop.run_until_complete(reg.get(job_id))["progress_current"] == 3

            loop.run_until_complete(reg.mark_done(job_id, {"win_rate": 0.5}))
            final = loop.run_until_complete(reg.get(job_id))
            assert final["state"] == "done"
            assert final["result"] == {"win_rate": 0.5}
            assert final["progress_current"] == 5  # clipped up to total on done
            assert final["finished_at"] is not None
        finally:
            loop.close()

    def test_mark_failed_captures_error(self):
        from backend.app.services.eval_jobs import EvalJobRegistry

        reg = EvalJobRegistry()
        loop = asyncio.new_event_loop()
        try:
            job_id = loop.run_until_complete(reg.create())
            loop.run_until_complete(reg.mark_failed(job_id, "boom"))
            job = loop.run_until_complete(reg.get(job_id))
            assert job["state"] == "failed"
            assert job["error"] == "boom"
            assert job["finished_at"] is not None
        finally:
            loop.close()

    def test_lru_eviction_caps_registry_size(self):
        from backend.app.services.eval_jobs import EvalJobRegistry

        reg = EvalJobRegistry(max_jobs=3)
        loop = asyncio.new_event_loop()
        try:
            ids = [loop.run_until_complete(reg.create()) for _ in range(5)]
            # First two should have been evicted by the time the 5th landed.
            assert loop.run_until_complete(reg.get(ids[0])) is None
            assert loop.run_until_complete(reg.get(ids[1])) is None
            # Last three remain.
            for kept in ids[2:]:
                assert loop.run_until_complete(reg.get(kept)) is not None
        finally:
            loop.close()

    def test_get_returns_shallow_copy_not_reference(self):
        """Callers mutating the returned dict must not poison the registry."""
        from backend.app.services.eval_jobs import EvalJobRegistry

        reg = EvalJobRegistry()
        loop = asyncio.new_event_loop()
        try:
            job_id = loop.run_until_complete(reg.create())
            snapshot = loop.run_until_complete(reg.get(job_id))
            snapshot["state"] = "hacked"  # tamper
            fresh = loop.run_until_complete(reg.get(job_id))
            assert fresh["state"] == "pending"  # internal state intact
        finally:
            loop.close()
