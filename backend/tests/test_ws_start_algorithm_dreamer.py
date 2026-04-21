"""WsTrainingStartPayload.algorithm extension to include dreamer_v3
(ADR 0018 S5).

Schema-level widening of the Literal membership. No migration, no
wrapper/manager change — the S4 plumbing already forwards the value
as a plain string, so the only surface that needs regression is the
boundary validator.

Guardrails verified here:
  1. dreamer_v3 parses through the same WS path as ppo/sac.
  2. Default still resolves to "ppo" (S4 contract unchanged).
  3. policy_type coexists with dreamer_v3 at the boundary — the AI
     factory ignores it at runtime, but the schema must still accept
     the combination so a FE form that carries both fields succeeds.
  4. The PM-listed rejection cases (invalid strings, case mismatch,
     non-string) still fail after the extension.
  5. /api/training/runs decoration surfaces ``algorithm="dreamer_v3"``
     verbatim (existing decorate helper is value-agnostic).
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.app.models.schemas import WsTrainingStartPayload
from backend.app.services.training_service import TrainingServiceWrapper
from backend.app.ws.validation import (
    ParsedMessage,
    ValidationFailure,
    parse_ws_message,
)


class TestDreamerV3Accepted:
    def test_model_accepts_dreamer_v3(self):
        payload = WsTrainingStartPayload(algorithm="dreamer_v3")
        assert payload.algorithm == "dreamer_v3"

    def test_ws_parse_accepts_dreamer_v3(self):
        result = parse_ws_message(
            {"type": "training:start", "payload": {"algorithm": "dreamer_v3"}}
        )
        assert isinstance(result, ParsedMessage)
        assert result.payload.algorithm == "dreamer_v3"

    def test_dreamer_accepted_with_any_policy_type(self):
        """PM contract: ``policy_type`` is still accepted with
        dreamer_v3; the AI factory ignores it at runtime (Dreamer
        builds its own actor off the RSSM latent). Schema must not
        cross-field-reject."""
        for pt in ("mlp_v1", "lstm_v1", "gru_v1", "transformer_v1"):
            payload = WsTrainingStartPayload(
                algorithm="dreamer_v3", policy_type=pt
            )
            assert payload.algorithm == "dreamer_v3"
            assert payload.policy_type == pt

    def test_dreamer_accepted_with_any_reward_model(self):
        for rm in ("shaped_v1", "sparse_v1", "learned_shaped_v1"):
            payload = WsTrainingStartPayload(
                algorithm="dreamer_v3", reward_model=rm
            )
            assert payload.algorithm == "dreamer_v3"
            assert payload.reward_model == rm


class TestS4RegressionUnchanged:
    """S4 contract must not drift — default, ppo + sac acceptance, and
    known rejection cases all stay identical after the extension."""

    def test_default_still_ppo(self):
        assert WsTrainingStartPayload().algorithm == "ppo"

    @pytest.mark.parametrize("value", ["ppo", "sac"])
    def test_s4_values_still_accepted(self, value):
        assert WsTrainingStartPayload(algorithm=value).algorithm == value

    @pytest.mark.parametrize(
        "value", ["invalid", "", "Dreamer_V3", "dreamerv3", "dreamer"]
    )
    def test_near_miss_rejections(self, value):
        """Literal is case-sensitive and exact; lookalikes of
        ``dreamer_v3`` must still fail."""
        result = parse_ws_message(
            {"type": "training:start", "payload": {"algorithm": value}}
        )
        assert isinstance(result, ValidationFailure)
        assert result.code == "payload_invalid"

    def test_unreserved_future_values_still_reject(self):
        """ADR 0017 §3 reserved names — still not in the Literal until
        a future sprint adds them. Guards against silent enum drift."""
        for reserved in ("dqn", "ppo_mask", "sac_crossq", "sac_continuous"):
            result = parse_ws_message({
                "type": "training:start",
                "payload": {"algorithm": reserved},
            })
            assert isinstance(result, ValidationFailure), (
                f"{reserved!r} unexpectedly parsed after S5 extension"
            )


class TestDreamerForwardsThroughService:
    """The S4 wrapper→manager plumbing forwards dreamer_v3 unchanged —
    the kwarg layer is value-agnostic so no code change is needed, only
    regression coverage."""

    @pytest.mark.asyncio
    async def test_wrapper_forwards_dreamer_v3_to_manager(self, tmp_path):
        w = TrainingServiceWrapper(
            model_dir=str(tmp_path / "models"),
            replay_dir=str(tmp_path / "replays"),
        )
        w.manager.start = AsyncMock(return_value="exp-dreamer")
        await w.start(algorithm="dreamer_v3")
        kwargs = w.manager.start.await_args.kwargs
        assert kwargs["algorithm"] == "dreamer_v3"

    # The manager's real ``start`` validates against
    # ``policy_factory.VALID_ALGORITHMS`` — widened by AI Sprint-5 in a
    # parallel branch. Until that lands, the manager-store path would
    # ValueError on "dreamer_v3"; the wrapper forwarding test above is
    # the BE-side proof of plumbing, while the runtime-admission test
    # correctly lives on AI's branch alongside the tuple extension.


class TestApiDecorationSurfacesDreamer:
    """``/api/training/runs`` + single-run endpoint must surface the
    new value verbatim — the decorate helper uses ``or "ppo"`` which
    passes any truthy string straight through, so this is a regression
    check rather than a behaviour add."""

    def _seed(self, client, games):
        svc = client.app.state.game_service
        for g in games:
            svc._games.append({"_id": str(len(svc._games)), **g})

    def _base_game(self, **overrides):
        base = {
            "game_id": "g1",
            "experiment_id": "exp-dreamer",
            "timestamp": datetime(2026, 4, 22, tzinfo=timezone.utc),
            "bot_level": 1,
            "score1": 15,
            "score2": 10,
            "winner": 1,
            "duration_frames": 1000,
            "rally_count": 20,
            "title": "run-dreamer",
        }
        base.update(overrides)
        return base

    def _fake_runs_service(self, lookup):
        svc = MagicMock()
        svc.get_by_experiment_ids = AsyncMock(return_value=lookup)
        return svc

    def test_list_endpoint_surfaces_dreamer_v3(self, client):
        self._seed(client, [self._base_game()])
        client.app.state.training_runs_service = self._fake_runs_service({
            "exp-dreamer": {
                "experiment_id": "exp-dreamer",
                "algorithm": "dreamer_v3",
            }
        })
        resp = client.get("/api/training/runs")
        assert resp.status_code == 200
        assert resp.json()["data"][0]["algorithm"] == "dreamer_v3"

    def test_single_run_endpoint_surfaces_dreamer_v3(self, client):
        self._seed(client, [self._base_game()])
        client.app.state.training_runs_service = self._fake_runs_service({
            "exp-dreamer": {
                "experiment_id": "exp-dreamer",
                "algorithm": "dreamer_v3",
            }
        })
        resp = client.get("/api/training/runs/run-dreamer")
        assert resp.status_code == 200
        assert resp.json()["algorithm"] == "dreamer_v3"
