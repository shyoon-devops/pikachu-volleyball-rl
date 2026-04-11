"""MongoDB document schemas (Pydantic v2)."""

from datetime import datetime

from pydantic import BaseModel, Field


class GameRecord(BaseModel):
    """Single game result document."""

    id: str | None = Field(None, alias="_id")
    experiment_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    bot_level: int = Field(ge=1, le=5)
    score1: int = Field(ge=0)
    score2: int = Field(ge=0)
    winner: int = Field(ge=1, le=2)
    duration_frames: int = Field(ge=0)
    rally_count: int = Field(ge=0)

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

    model_config = {"populate_by_name": True}


class PaginatedResponse(BaseModel):
    """Envelope for paginated list endpoints."""

    data: list
    total: int
    page: int
    limit: int
