"""Regression test suite for all discovered bugs (16 issues).

Run against any live environment:
    pytest tests/test_regression.py --base-url http://localhost:8001   # dev
    pytest tests/test_regression.py --base-url http://localhost:8002   # qa
    pytest tests/test_regression.py --base-url http://localhost:8003   # prod

Requires: httpx, websockets, pytest-asyncio
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest
import pytest_asyncio
import websockets

# Live-backend regression suite — every test opens an HTTP/WebSocket
# connection to whatever `--base-url` points at. Module-level marker
# keeps the default `-m 'not e2e'` addopts filter excluding the whole
# file so a plain `pytest backend/tests/` never touches dev/qa/prod.
# See the 2026-04-17 incident note in pyproject.toml.
pytestmark = pytest.mark.e2e

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def base_url(request: pytest.FixtureRequest) -> str:
    return request.config.getoption("--base-url")


@pytest.fixture(scope="session")
def ws_url(base_url: str) -> str:
    return base_url.replace("http://", "ws://").replace("https://", "wss://") + "/ws"


@pytest_asyncio.fixture
async def client(base_url: str):
    async with httpx.AsyncClient(base_url=base_url, timeout=10) as c:
        yield c


async def _ensure_training_stopped(ws_url: str) -> None:
    """Helper: ensure training is stopped before tests that start training."""
    try:
        async with websockets.connect(ws_url, open_timeout=5) as conn:
            await conn.send(json.dumps({"type": "training:stop"}))
            await asyncio.sleep(0.5)
    except Exception:
        pass


# =========================================================================
# CRITICAL — Security issues
# =========================================================================


class TestCriticalSecurity:
    """PROD-SEC-1, SEC-2, SEC-3: Security vulnerabilities."""

    @pytest.mark.asyncio
    async def test_sec1_path_traversal_blocked(self, client: httpx.AsyncClient) -> None:
        """PROD-SEC-1: model_path must reject path traversal."""
        traversal_paths = [
            "../../../etc/passwd",
            "..\\..\\..\\etc\\passwd",
            "models/../../../etc/passwd",
            "%2e%2e%2f%2e%2e%2fetc/passwd",
        ]
        for path in traversal_paths:
            resp = await client.post(
                "/api/evaluation/run",
                json={"model_path": path, "bot_level": 1, "n_games": 1},
            )
            assert resp.status_code != 500, (
                f"Path traversal not blocked for '{path}': got 500 instead of 400/422"
            )
            assert resp.status_code in (400, 422), (
                f"Path traversal '{path}' returned {resp.status_code}, expected 400 or 422"
            )

    @pytest.mark.asyncio
    async def test_sec2_cors_not_wildcard(self, client: httpx.AsyncClient) -> None:
        """PROD-SEC-2: CORS must not allow arbitrary origins with credentials."""
        resp = await client.get(
            "/api/health",
            headers={"Origin": "https://attacker.malicious.site"},
        )
        acao = resp.headers.get("access-control-allow-origin", "")
        acac = resp.headers.get("access-control-allow-credentials", "")
        assert acao != "https://attacker.malicious.site" or acac.lower() != "true", (
            f"CORS allows attacker origin with credentials: "
            f"allow-origin={acao}, allow-credentials={acac}"
        )

    @pytest.mark.asyncio
    async def test_sec3_rate_limiting_exists(self, base_url: str) -> None:
        """PROD-SEC-3: Burst requests must be rate-limited."""
        async with httpx.AsyncClient(base_url=base_url, timeout=10) as c:
            tasks = [c.get("/api/health") for _ in range(100)]
            results = await asyncio.gather(*tasks)
        codes = [r.status_code for r in results]
        has_rate_limit = any(c == 429 for c in codes)
        assert has_rate_limit, (
            f"No rate limiting: 100 burst requests all returned 200 "
            f"(expected some 429 responses)"
        )


# =========================================================================
# HIGH — Functional bugs
# =========================================================================


class TestHighBugs:
    """PROD-BUG-1 through BUG-7: High-severity functional bugs."""

    @pytest.mark.asyncio
    async def test_bug1_no_ghost_training_state(
        self, client: httpx.AsyncClient, ws_url: str,
    ) -> None:
        """PROD-BUG-1: Training must not show 'running' with step=0 indefinitely."""
        await _ensure_training_stopped(ws_url)
        await asyncio.sleep(1)
        resp = await client.get("/api/training/status")
        data = resp.json()
        if data["state"] == "running":
            assert data["current_step"] > 0 or data["current_episode"] > 0, (
                f"Ghost state: training reports running but step={data['current_step']}, "
                f"episode={data['current_episode']}"
            )

    @pytest.mark.asyncio
    async def test_bug2_eval_no_double_zip(self, client: httpx.AsyncClient) -> None:
        """PROD-BUG-2: Evaluation must handle .zip paths correctly."""
        models_resp = await client.get("/api/models")
        models = models_resp.json().get("models", [])
        if not models:
            pytest.skip("No models available for evaluation test")
        model_path = models[0]["path"]
        resp = await client.post(
            "/api/evaluation/run",
            json={"model_path": model_path, "bot_level": 1, "n_games": 1},
        )
        assert resp.status_code != 500, (
            f"Evaluation failed with 500 for model '{model_path}'. "
            f"Likely double .zip extension bug."
        )

    @pytest.mark.asyncio
    async def test_bug3_reject_negative_timesteps(self, ws_url: str) -> None:
        """PROD-BUG-3: Negative total_timesteps must be rejected."""
        await _ensure_training_stopped(ws_url)
        await asyncio.sleep(0.5)
        async with websockets.connect(ws_url, open_timeout=5) as conn:
            await conn.send(json.dumps({
                "type": "training:start",
                "payload": {"hyperparams": {"total_timesteps": -1}, "bot_level": 1},
            }))
            try:
                resp = await asyncio.wait_for(conn.recv(), timeout=5)
                data = json.loads(resp)
                assert data.get("type") == "error" or (
                    data.get("payload", {}).get("state") != "running"
                ), f"Negative timesteps accepted: training started with response {data}"
            except asyncio.TimeoutError:
                pass  # No response = acceptable if training didn't start
            finally:
                try:
                    await conn.send(json.dumps({"type": "training:stop"}))
                    await asyncio.sleep(0.5)
                except Exception:
                    pass

    @pytest.mark.asyncio
    async def test_bug4_ws_missing_data_no_crash(self, ws_url: str) -> None:
        """PROD-BUG-4: WS must not crash on missing payload fields."""
        await _ensure_training_stopped(ws_url)
        payloads = [
            json.dumps({"type": "training:start"}),
            json.dumps({"type": "training:start", "payload": None}),
        ]
        for payload in payloads:
            async with websockets.connect(ws_url, open_timeout=5) as conn:
                await conn.send(payload)
                try:
                    resp = await asyncio.wait_for(conn.recv(), timeout=3)
                    # Got a response — connection survived
                except asyncio.TimeoutError:
                    pass  # No response but alive is OK
                # Verify connection is still alive
                try:
                    await conn.ping()
                except Exception:
                    pytest.fail(
                        f"WS connection died after sending: {payload}"
                    )
            await _ensure_training_stopped(ws_url)
            await asyncio.sleep(0.3)

    @pytest.mark.asyncio
    async def test_bug5_double_start_no_crash(self, ws_url: str) -> None:
        """PROD-BUG-5 (QA BUG-3): Double training:start must not kill WS."""
        await _ensure_training_stopped(ws_url)
        await asyncio.sleep(0.5)
        async with websockets.connect(ws_url, open_timeout=5) as conn:
            await conn.send(json.dumps({
                "type": "training:start",
                "payload": {"bot_level": 1},
            }))
            await asyncio.sleep(2)
            await conn.send(json.dumps({
                "type": "training:start",
                "payload": {"bot_level": 1},
            }))
            # Drain any messages
            try:
                for _ in range(5):
                    await asyncio.wait_for(conn.recv(), timeout=2)
            except asyncio.TimeoutError:
                pass
            # Connection must still be alive
            try:
                await conn.ping()
            except Exception:
                pytest.fail("WS connection died on double training:start")
            finally:
                try:
                    await conn.send(json.dumps({"type": "training:stop"}))
                    await asyncio.sleep(0.5)
                except Exception:
                    pass

    @pytest.mark.asyncio
    async def test_bug6_concurrent_starts_no_crash(self, ws_url: str) -> None:
        """PROD-BUG-6: Concurrent training:start must not crash connections."""
        await _ensure_training_stopped(ws_url)
        await asyncio.sleep(0.5)
        alive = 0

        async def try_start(idx: int) -> bool:
            try:
                async with websockets.connect(ws_url, open_timeout=5) as conn:
                    await conn.send(json.dumps({
                        "type": "training:start",
                        "payload": {"bot_level": 1},
                    }))
                    try:
                        await asyncio.wait_for(conn.recv(), timeout=3)
                    except asyncio.TimeoutError:
                        pass
                    await conn.ping()
                    return True
            except Exception:
                return False

        results = await asyncio.gather(*[try_start(i) for i in range(5)])
        alive = sum(results)
        assert alive == 5, (
            f"Only {alive}/5 connections survived concurrent training:start"
        )
        await _ensure_training_stopped(ws_url)

    @pytest.mark.asyncio
    async def test_bug7_training_pushes_frames(self, ws_url: str) -> None:
        """PROD-BUG-7: Training must push training:frame messages."""
        await _ensure_training_stopped(ws_url)
        await asyncio.sleep(0.5)
        async with websockets.connect(ws_url, open_timeout=5) as conn:
            await conn.send(json.dumps({
                "type": "training:start",
                "payload": {"bot_level": 1},
            }))
            types: dict[str, int] = {}
            try:
                for _ in range(30):
                    msg = await asyncio.wait_for(conn.recv(), timeout=2)
                    data = json.loads(msg)
                    t = data.get("type", "unknown")
                    types[t] = types.get(t, 0) + 1
            except asyncio.TimeoutError:
                pass
            finally:
                try:
                    await conn.send(json.dumps({"type": "training:stop"}))
                    await asyncio.sleep(0.5)
                except Exception:
                    pass
        assert "training:frame" in types, (
            f"No training:frame messages received in 60s. Got: {types}"
        )


# =========================================================================
# MEDIUM — Input validation & error handling
# =========================================================================


class TestMediumBugs:
    """PROD-BUG-8 through BUG-13: Medium-severity issues."""

    @pytest.mark.asyncio
    async def test_bug8_security_headers_present(
        self, client: httpx.AsyncClient,
    ) -> None:
        """PROD-BUG-8: Response must include basic security headers."""
        resp = await client.get("/api/health")
        headers = resp.headers
        required = ["x-content-type-options"]
        missing = [h for h in required if h not in headers]
        assert not missing, f"Missing security headers: {missing}"
        assert headers.get("server", "") != "uvicorn", (
            "Server header exposes 'uvicorn' ��� should be removed or replaced"
        )

    @pytest.mark.asyncio
    async def test_bug9_set_level_applied(self, ws_url: str) -> None:
        """PROD-BUG-9: set_level must change bot_level."""
        await _ensure_training_stopped(ws_url)
        await asyncio.sleep(0.5)
        async with websockets.connect(ws_url, open_timeout=5) as conn:
            await conn.send(json.dumps({
                "type": "training:start",
                "payload": {"bot_level": 1},
            }))
            await asyncio.sleep(2)
            await conn.send(json.dumps({
                "type": "training:set_level",
                "payload": {"level": 3},
            }))
            try:
                for _ in range(10):
                    msg = await asyncio.wait_for(conn.recv(), timeout=2)
                    data = json.loads(msg)
                    if data.get("type") == "training:status":
                        bot_level = data.get("payload", {}).get("bot_level")
                        assert bot_level == 3, (
                            f"set_level(3) not applied: got bot_level={bot_level}"
                        )
                        break
            except asyncio.TimeoutError:
                pytest.fail("No response to set_level")
            finally:
                try:
                    await conn.send(json.dumps({"type": "training:stop"}))
                    await asyncio.sleep(0.5)
                except Exception:
                    pass

    @pytest.mark.asyncio
    async def test_bug10_invalid_game_id_returns_400(
        self, client: httpx.AsyncClient,
    ) -> None:
        """PROD-BUG-10: Invalid game ID must return 400, not 500."""
        invalid_ids = [
            "invalid-id",
            "not-an-objectid",
            "가나다라",
            "';DROP TABLE games;--",
            "A" * 5000,
            "12345",
            "<script>alert(1)</script>",
        ]
        for gid in invalid_ids:
            resp = await client.get(f"/api/games/{gid}")
            assert resp.status_code != 500, (
                f"Invalid game ID '{gid[:50]}' returned 500 instead of 400/404"
            )
            assert resp.status_code in (400, 404, 422), (
                f"Invalid game ID '{gid[:50]}' returned {resp.status_code}"
            )

    @pytest.mark.asyncio
    async def test_bug11_eval_input_validation(
        self, client: httpx.AsyncClient,
    ) -> None:
        """PROD-BUG-11: Eval endpoint must validate inputs."""
        invalid_inputs = [
            {"model_path": "", "bot_level": 1, "n_games": 1},
            {"model_path": "test.zip", "bot_level": -1, "n_games": 1},
            {"model_path": "test.zip", "bot_level": 999, "n_games": 1},
            {"model_path": "test.zip", "bot_level": 1, "n_games": -1},
            {"model_path": "test.zip", "bot_level": 1, "n_games": 0},
            {"model_path": "test.zip", "bot_level": 0, "n_games": 1},
        ]
        for body in invalid_inputs:
            resp = await client.post("/api/evaluation/run", json=body)
            assert resp.status_code != 500, (
                f"Invalid eval input {body} returned 500 instead of 400/422"
            )
            assert resp.status_code in (400, 422), (
                f"Invalid eval input {body} returned {resp.status_code}, expected 400/422"
            )

    @pytest.mark.asyncio
    async def test_bug12_game_replay_consistency(
        self, client: httpx.AsyncClient,
    ) -> None:
        """PROD-BUG-12: Every game in DB should have a matching replay."""
        games_resp = await client.get("/api/games", params={"page": 1, "limit": 10})
        games = games_resp.json().get("data", [])
        if not games:
            pytest.skip("No games in DB to verify")
        missing = []
        for game in games:
            gid = game["_id"]
            replay_resp = await client.get(f"/api/replays/{gid}")
            if replay_resp.status_code == 404:
                missing.append(gid)
        assert not missing, (
            f"Games exist without replay data: {missing}"
        )

    @pytest.mark.asyncio
    async def test_bug13_rally_count_nonzero(
        self, client: httpx.AsyncClient,
    ) -> None:
        """PROD-BUG-13: Completed games with score > 0 should have rally_count > 0."""
        games_resp = await client.get("/api/games", params={"page": 1, "limit": 20})
        games = games_resp.json().get("data", [])
        if not games:
            pytest.skip("No games in DB to verify")
        suspicious = []
        for game in games:
            total_score = game.get("score1", 0) + game.get("score2", 0)
            if total_score > 0 and game.get("rally_count", 0) == 0:
                suspicious.append(
                    f"game={game['_id']} score={game['score1']}-{game['score2']} "
                    f"rally_count=0"
                )
        assert not suspicious, (
            f"Games with score > 0 but rally_count=0: {suspicious}"
        )


# =========================================================================
# WS Robustness — Malformed input handling
# =========================================================================


class TestWSRobustness:
    """Additional WS edge cases from error handling tests."""

    @pytest.mark.asyncio
    async def test_malformed_json_no_crash(self, ws_url: str) -> None:
        """WS must not die on malformed JSON."""
        async with websockets.connect(ws_url, open_timeout=5) as conn:
            await conn.send("not-valid-json{{{")
            try:
                await asyncio.wait_for(conn.recv(), timeout=3)
            except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosedError):
                pass
            try:
                await conn.ping()
            except Exception:
                pytest.fail("WS connection died on malformed JSON input")

    @pytest.mark.asyncio
    async def test_empty_message_no_crash(self, ws_url: str) -> None:
        """WS must not die on empty message."""
        async with websockets.connect(ws_url, open_timeout=5) as conn:
            await conn.send("")
            try:
                await asyncio.wait_for(conn.recv(), timeout=3)
            except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosedError):
                pass
            try:
                await conn.ping()
            except Exception:
                pytest.fail("WS connection died on empty message")

    @pytest.mark.asyncio
    async def test_unknown_type_ignored(self, ws_url: str) -> None:
        """WS must handle unknown message types gracefully."""
        async with websockets.connect(ws_url, open_timeout=5) as conn:
            await conn.send(json.dumps({"type": "nonexistent:command"}))
            try:
                await asyncio.wait_for(conn.recv(), timeout=2)
            except asyncio.TimeoutError:
                pass  # Silent ignore is acceptable
            await conn.ping()  # Must still be alive


# =========================================================================
# REST Error Response Quality
# =========================================================================


class TestErrorResponseQuality:
    """Error responses must be informative, not generic."""

    @pytest.mark.asyncio
    async def test_500_never_returned_for_client_errors(
        self, client: httpx.AsyncClient,
    ) -> None:
        """No client-side error should produce a 500."""
        cases = [
            ("GET", "/api/games/invalid-objectid-format"),
            ("GET", "/api/games/12345"),
            ("POST", "/api/evaluation/run", {"model_path": "", "bot_level": 1, "n_games": 1}),
        ]
        for case in cases:
            method = case[0]
            path = case[1]
            body = case[2] if len(case) > 2 else None
            if method == "GET":
                resp = await client.get(path)
            else:
                resp = await client.post(path, json=body)
            assert resp.status_code != 500, (
                f"{method} {path} returned 500 for a client error. "
                f"Body: {resp.text[:200]}"
            )

    @pytest.mark.asyncio
    async def test_error_responses_have_detail(
        self, client: httpx.AsyncClient,
    ) -> None:
        """Error responses must include a 'detail' field, not bare text."""
        resp = await client.get("/api/games/invalid-id")
        assert resp.status_code != 500, (
            f"Server returned 500 with body: {resp.text[:200]}. "
            f"Expected a 4xx with JSON detail."
        )
        if resp.status_code >= 400:
            try:
                body = resp.json()
            except Exception:
                pytest.fail(
                    f"Error response (HTTP {resp.status_code}) is not valid JSON: "
                    f"{resp.text[:200]}"
                )
            assert "detail" in body, (
                f"Error response missing 'detail' field: {body}"
            )
