"""Correlation / request ID middleware.

Reads ``X-Request-ID`` from the incoming request (trusted clients may supply
their own so the value flows across services) or generates a fresh id, then
stores it in ``correlation_id_var`` for the duration of the request so every
log emitted during the request is tagged with it. The same value is echoed
back on the response so callers can quote it in bug reports.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from backend.app.logging_config import correlation_id_var, new_correlation_id

HEADER_NAME = "X-Request-ID"
# Bound input length so a bogus client cannot poison our log files with
# an arbitrary-sized identifier.
_MAX_INBOUND_LEN = 128


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Ensure every request has a correlation id and it is returned to the caller."""

    async def dispatch(self, request: Request, call_next) -> Response:
        incoming = request.headers.get(HEADER_NAME, "").strip()
        if incoming and len(incoming) <= _MAX_INBOUND_LEN and incoming.isprintable():
            cid = incoming
        else:
            cid = new_correlation_id()

        token = correlation_id_var.set(cid)
        try:
            response = await call_next(request)
        finally:
            correlation_id_var.reset(token)

        response.headers[HEADER_NAME] = cid
        return response
