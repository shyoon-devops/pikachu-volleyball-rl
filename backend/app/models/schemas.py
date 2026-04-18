"""MongoDB document schemas (Pydantic v2)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, computed_field


class GameRecord(BaseModel):
    """Single game result document."""

    id: str | None = Field(None, alias="_id")
    game_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    experiment_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    bot_level: int = Field(ge=1, le=5)
    score1: int = Field(ge=0)
    score2: int = Field(ge=0)
    winner: int = Field(ge=1, le=2)
    duration_frames: int = Field(ge=0)
    rally_count: int = Field(ge=0)
    # Which RL environment produced this game. "demo" marks the single
    # standalone demo game LiveFrameCallback plays every play_interval
    # steps; "0".."7" (string, stable across FE queries) marks one of the
    # n_envs parallel gradient envs. Optional so legacy pre-A2 records
    # (all demo-only) still validate — missing value is treated as "demo"
    # by downstream consumers.
    env_id: str | None = None
    # Denormalised training title snapshot. Carries the human label from
    # the time the match was saved so later renames don't retroactively
    # orphan history (spec §5). None for pre-title legacy records — FE
    # renders "-".
    title: str | None = Field(default=None, max_length=60)

    model_config = {"populate_by_name": True}


class MetricRecord(BaseModel):
    """Training metric snapshot document."""

    id: str | None = Field(None, alias="_id")
    experiment_id: str
    step: int = Field(ge=0)
    episode: int = Field(ge=0)
    reward: float
    win_rate: float = Field(ge=0.0, le=1.0)
    loss: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"populate_by_name": True}


class EvaluationRecord(BaseModel):
    """Model evaluation result document."""

    id: str | None = Field(None, alias="_id")
    model_path: str
    bot_level: int = Field(ge=1, le=5)
    n_games: int = Field(ge=1)
    win_rate: float = Field(ge=0.0, le=1.0)
    avg_score: float
    avg_rally_length: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    # Denormalised snapshot of the source training's title at eval time
    # (spec §5). Stored here rather than joined so a later title rename
    # doesn't retroactively rewrite historical evaluation rows. None
    # for evals of legacy pre-title models.
    training_title: str | None = Field(default=None, max_length=60)

    model_config = {"populate_by_name": True, "protected_namespaces": ()}


class PaginatedResponse(BaseModel):
    """Unified envelope for paginated list endpoints.

    ``has_more`` is derived from (page, limit, total) rather than stored
    directly, so callers cannot supply an inconsistent value. Emitted as a
    regular field via ``computed_field`` so OpenAPI reflects it.
    """

    data: list
    total: int
    page: int
    limit: int

    @computed_field  # type: ignore[prop-decorator]
    @property
    def has_more(self) -> bool:
        if self.limit <= 0:
            return False
        return self.page * self.limit < self.total


# --- WebSocket message schemas ---
#
# All incoming WS messages share the envelope `{type: str, payload: object}`.
# Each known type has a dedicated payload schema. The parse_ws_message helper
# validates envelope + payload in one step and returns a discriminated union,
# so handlers only receive already-validated data.


class WsTrainingStartPayload(BaseModel):
    # Human-readable label the user assigns to this training run
    # (DESIGN-TRAINING-TITLE.md §0). Optional — empty / whitespace /
    # missing → the server auto-generates ``run-{adj}-{noun}-{4hex}``
    # via ``title_service.allocate_title``. Max 60 chars matches the
    # FE input's maxlength so over-length payloads fail parse-side and
    # never hit the handler.
    title: str | None = Field(default=None, max_length=60)
    hyperparams: dict | None = None
    # Bot level is optional so the frontend can own the difficulty dial
    # exclusively via training:set_level / PATCH /api/training/level. When
    # the FE drops bot_level from the start form (Option A), the dispatcher
    # falls back to the current ``status.bot_level`` — no implicit reset
    # to L1. Range check still applies when the field is supplied.
    bot_level: int | None = Field(default=None, ge=1, le=5)
    # total_timesteps range tightened 2026-04-18: ge=100_000 so a typo
    # like `1000` doesn't silently burn a GPU slot on a run that would
    # learn nothing; le=10_000_000 to cap unintended runaway runs. FE
    # default stays at 2M (see chore(training) commit).
    total_timesteps: int = Field(default=2_000_000, ge=100_000, le=10_000_000)
    # Parallel env count — PPO rollout width. More envs = more gradient
    # samples per update but also more GPU memory + more WS env-frame
    # broadcast bandwidth. 32 caps pragmatically given the 4070 Ti headroom.
    n_envs: int | None = Field(default=None, ge=1, le=32)
    # PPO epochs per rollout. Low values under-fit; high values over-fit
    # on stale rollout data and wreck convergence. 30 is well past
    # diminishing returns.
    n_epochs: int | None = Field(default=None, ge=1, le=30)
    # Entropy bonus coefficient. 0.0 disables exploration bonus entirely
    # (policy can collapse). 0.05 upper cap picked so exploration can't
    # swamp the task-reward signal.
    ent_coef: float | None = Field(default=None, ge=0.0, le=0.05)
    # GAE lambda — advantage-estimator bias/variance knob. 0.9 is the
    # aggressively-biased end; 1.0 is plain discounted returns.
    gae_lambda: float | None = Field(default=None, ge=0.9, le=1.0)


class WsSetLevelPayload(BaseModel):
    level: int = Field(ge=1, le=5)


class WsReplayRequestPayload(BaseModel):
    game_id: str = Field(min_length=1, max_length=128)


class WsEmptyPayload(BaseModel):
    """Payload schema for messages that carry no data (e.g. ping, stop)."""

    model_config = {"extra": "ignore"}


# Mapping of known message type -> payload schema. `None` means the message
# carries no inspectable payload (pong is a liveness signal, not a handler
# invocation; empty payloads use WsEmptyPayload).
WS_MESSAGE_SCHEMAS: dict[str, type[BaseModel] | None] = {
    "ping": WsEmptyPayload,
    "pong": WsEmptyPayload,
    "training:start": WsTrainingStartPayload,
    "training:stop": WsEmptyPayload,
    "training:pause": WsEmptyPayload,
    "training:resume": WsEmptyPayload,
    "training:set_level": WsSetLevelPayload,
    "replay:request": WsReplayRequestPayload,
}


class WsEnvelope(BaseModel):
    """Outer envelope shared by every inbound WS message."""

    type: str = Field(min_length=1, max_length=64)
    payload: dict | None = None

    model_config = {"extra": "ignore"}
