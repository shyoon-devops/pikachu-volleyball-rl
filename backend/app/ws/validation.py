"""WebSocket message parsing and validation.

Every inbound WS message goes through parse_ws_message(), which returns a
ParsedMessage on success or a ValidationFailure describing what went wrong.
Handlers never see raw dicts — only already-validated, typed payloads.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from backend.app.models.schemas import WS_MESSAGE_SCHEMAS, WsEnvelope


@dataclass(frozen=True)
class ParsedMessage:
    """Successfully validated inbound WS message."""

    type: str
    payload: BaseModel


@dataclass(frozen=True)
class ValidationFailure:
    """Validation failed — includes a user-safe message and an error code."""

    code: str
    message: str


def parse_ws_message(raw: Any) -> ParsedMessage | ValidationFailure:
    """Validate the envelope and dispatch the payload to its schema.

    Returns ValidationFailure (with code ∈ {envelope_invalid, unknown_type,
    payload_invalid}) when the input is malformed. Handlers decide how to
    surface that to the client.
    """
    if not isinstance(raw, dict):
        return ValidationFailure(
            code="envelope_invalid",
            message="Message must be a JSON object",
        )

    try:
        envelope = WsEnvelope(**raw)
    except ValidationError as e:
        return ValidationFailure(
            code="envelope_invalid",
            message=f"Invalid envelope: {e.error_count()} errors",
        )

    schema = WS_MESSAGE_SCHEMAS.get(envelope.type)
    if schema is None:
        return ValidationFailure(
            code="unknown_type",
            message=f"Unknown message type: {envelope.type!r}",
        )

    try:
        payload_model = schema(**(envelope.payload or {}))
    except ValidationError as e:
        return ValidationFailure(
            code="payload_invalid",
            message=f"Invalid payload for {envelope.type!r}: {e.error_count()} errors",
        )

    return ParsedMessage(type=envelope.type, payload=payload_model)
