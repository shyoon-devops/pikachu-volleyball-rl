"""Extended hyperparam acceptance on training:start (BE-H1).

Pins the contract for the 5 fields the PM spec added:
  total_timesteps, n_envs, n_epochs, ent_coef, gae_lambda

Three layers to verify:
  1. Schema validation — Pydantic rejects out-of-range values with
     ``payload_invalid`` so the client sees a structured WS error.
  2. Handler forwarding — top-level fields (n_epochs, ent_coef,
     gae_lambda) get merged into the hyperparams dict before hitting
     the service; explicit top-level values win over the free-form blob.
  3. Service signature — ``n_envs`` passes through as its own kwarg
     (not via hyperparams) because it configures ``make_vec_env``,
     not the PPO constructor.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from backend.app.models.schemas import WsTrainingStartPayload


# ---------------------------------------------------------------------------
# Schema-level validation
# ---------------------------------------------------------------------------


class TestSchemaAcceptsValidValues:
    def test_accepts_all_new_params_at_midrange(self):
        p = WsTrainingStartPayload(
            total_timesteps=2_000_000,
            n_envs=16,
            n_epochs=10,
            ent_coef=0.01,
            gae_lambda=0.95,
        )
        assert p.n_envs == 16
        assert p.n_epochs == 10
        assert p.ent_coef == pytest.approx(0.01)
        assert p.gae_lambda == pytest.approx(0.95)

    def test_all_new_params_optional_none_default(self):
        p = WsTrainingStartPayload()
        # None = "use BE default" — the handler/trainer layer fills these in.
        assert p.n_envs is None
        assert p.n_epochs is None
        assert p.ent_coef is None
        assert p.gae_lambda is None

    def test_total_timesteps_minimum_is_100k(self):
        # Floor bumped from 1_000 to 100_000 so a digit-slipped payload
        # doesn't burn a GPU slot on a training run that learns nothing.
        p = WsTrainingStartPayload(total_timesteps=100_000)
        assert p.total_timesteps == 100_000
        with pytest.raises(ValidationError):
            WsTrainingStartPayload(total_timesteps=99_999)

    def test_total_timesteps_maximum_is_10m(self):
        WsTrainingStartPayload(total_timesteps=10_000_000)
        with pytest.raises(ValidationError):
            WsTrainingStartPayload(total_timesteps=10_000_001)


class TestSchemaRejectsOutOfRange:
    @pytest.mark.parametrize(
        "field, bad_value",
        [
            ("n_envs", 0),
            ("n_envs", 33),
            ("n_epochs", 0),
            ("n_epochs", 31),
            ("ent_coef", -0.001),
            ("ent_coef", 0.0501),
            ("gae_lambda", 0.89),
            ("gae_lambda", 1.01),
        ],
    )
    def test_out_of_range_raises_validation_error(self, field, bad_value):
        with pytest.raises(ValidationError):
            WsTrainingStartPayload(**{field: bad_value})


# ---------------------------------------------------------------------------
# WS parse layer — out-of-range surfaces as payload_invalid (not a crash)
# ---------------------------------------------------------------------------


class TestParseRejectsOutOfRange:
    def test_n_envs_too_large_yields_validation_failure(self):
        from backend.app.ws.validation import ValidationFailure, parse_ws_message

        result = parse_ws_message(
            {"type": "training:start", "payload": {"n_envs": 64}}
        )
        assert isinstance(result, ValidationFailure)
        assert result.code == "payload_invalid"
        # validation.py wraps Pydantic errors in a generic message; field
        # specifics land in logs. Client-visible code is the contract here.

    def test_ent_coef_negative_yields_validation_failure(self):
        from backend.app.ws.validation import ValidationFailure, parse_ws_message

        result = parse_ws_message(
            {"type": "training:start", "payload": {"ent_coef": -0.5}}
        )
        assert isinstance(result, ValidationFailure)
        assert result.code == "payload_invalid"


# ---------------------------------------------------------------------------
# Handler forwarding — top-level fields merge into hyperparams
# ---------------------------------------------------------------------------


class TestHandlerForwardsExtendedParams:
    @staticmethod
    def _fake_training_service(initial_state: str = "stopped"):
        svc = MagicMock()
        svc.status.return_value = {
            "state": initial_state,
            "current_step": 0,
            "current_episode": 0,
            "experiment_id": None,
            "bot_level": 1,
            "started_at": None,
        }
        svc.start = AsyncMock(return_value="exp-123")
        return svc

    @pytest.mark.asyncio
    async def test_top_level_fields_merge_into_hyperparams(self):
        from backend.app.models.schemas import WsTrainingStartPayload
        from backend.app.ws.handlers import _dispatch
        from backend.app.ws.validation import ParsedMessage

        svc = self._fake_training_service()
        parsed = ParsedMessage(
            type="training:start",
            payload=WsTrainingStartPayload(
                total_timesteps=500_000,
                n_envs=4,
                n_epochs=20,
                ent_coef=0.02,
                gae_lambda=0.97,
            ),
        )
        # WS + ConnectionManager stand-ins; dispatch only reads / awaits the svc.
        ws = MagicMock()
        ws.send_json = AsyncMock()
        manager = MagicMock()
        manager.broadcast = AsyncMock()
        replay_service = MagicMock()

        await _dispatch(ws, parsed, svc, replay_service, manager)

        svc.start.assert_awaited_once()
        kwargs = svc.start.await_args.kwargs
        assert kwargs["total_timesteps"] == 500_000
        assert kwargs["n_envs"] == 4
        # Top-level fields merged into hyperparams dict.
        hp = kwargs["hyperparams"]
        assert hp["n_epochs"] == 20
        assert hp["ent_coef"] == pytest.approx(0.02)
        assert hp["gae_lambda"] == pytest.approx(0.97)

    @pytest.mark.asyncio
    async def test_top_level_wins_over_hyperparams_blob(self):
        """If the client sends both top-level ``ent_coef`` and
        ``hyperparams.ent_coef``, the explicit top-level field wins.
        Prevents a typo in the blob from silently overriding the
        validated field.
        """
        from backend.app.models.schemas import WsTrainingStartPayload
        from backend.app.ws.handlers import _dispatch
        from backend.app.ws.validation import ParsedMessage

        svc = self._fake_training_service()
        parsed = ParsedMessage(
            type="training:start",
            payload=WsTrainingStartPayload(
                ent_coef=0.02,
                hyperparams={"ent_coef": 999.0, "learning_rate": 1e-4},
            ),
        )
        ws = MagicMock()
        ws.send_json = AsyncMock()
        manager = MagicMock()
        manager.broadcast = AsyncMock()

        await _dispatch(ws, parsed, svc, MagicMock(), manager)

        hp = svc.start.await_args.kwargs["hyperparams"]
        # Validated top-level wins; the free-form learning_rate passes through.
        assert hp["ent_coef"] == pytest.approx(0.02)
        assert hp["learning_rate"] == pytest.approx(1e-4)

    @pytest.mark.asyncio
    async def test_n_envs_omitted_uses_service_default(self):
        """When ``n_envs`` is absent, the handler must NOT supply it —
        the service's default kwarg (8) is the source of truth.
        """
        from backend.app.models.schemas import WsTrainingStartPayload
        from backend.app.ws.handlers import _dispatch
        from backend.app.ws.validation import ParsedMessage

        svc = self._fake_training_service()
        parsed = ParsedMessage(
            type="training:start",
            payload=WsTrainingStartPayload(total_timesteps=500_000),
        )
        ws = MagicMock()
        ws.send_json = AsyncMock()
        manager = MagicMock()
        manager.broadcast = AsyncMock()

        await _dispatch(ws, parsed, svc, MagicMock(), manager)

        kwargs = svc.start.await_args.kwargs
        assert "n_envs" not in kwargs


# ---------------------------------------------------------------------------
# Service layer — n_envs flows to TrainingManager.start
# ---------------------------------------------------------------------------


class TestServiceForwardsNEnvs:
    @pytest.mark.asyncio
    async def test_wrapper_forwards_n_envs(self):
        from backend.app.services.training_service import TrainingServiceWrapper

        wrapper = TrainingServiceWrapper.__new__(TrainingServiceWrapper)
        wrapper.manager = MagicMock()
        wrapper.manager.start = AsyncMock(return_value="exp-x")
        await wrapper.start(bot_level=2, total_timesteps=500_000, n_envs=16)
        wrapper.manager.start.assert_awaited_once()
        kwargs = wrapper.manager.start.await_args.kwargs
        assert kwargs["n_envs"] == 16
        assert kwargs["bot_level"] == 2
        assert kwargs["total_timesteps"] == 500_000

    @pytest.mark.asyncio
    async def test_wrapper_default_n_envs_is_8(self):
        from backend.app.services.training_service import TrainingServiceWrapper

        wrapper = TrainingServiceWrapper.__new__(TrainingServiceWrapper)
        wrapper.manager = MagicMock()
        wrapper.manager.start = AsyncMock(return_value="exp-x")
        await wrapper.start()  # nothing supplied
        kwargs = wrapper.manager.start.await_args.kwargs
        assert kwargs["n_envs"] == 8
