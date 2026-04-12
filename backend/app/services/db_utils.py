"""MongoDB client factory and transient-error retry helpers.

Motor wraps PyMongo, which raises a well-defined set of transient errors
(AutoReconnect, ConnectionFailure, NetworkTimeout, ServerSelectionTimeoutError)
for recoverable failures. This module:

  1. Builds AsyncIOMotorClient with sensible pool + timeout defaults.
  2. Provides with_mongo_retry() to wrap any coroutine call that touches
     the database, using exponential backoff.

Configuration is env-driven so ops can tune per environment without code
changes.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Awaitable, Callable, TypeVar

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import (
    AutoReconnect,
    ConnectionFailure,
    NetworkTimeout,
    ServerSelectionTimeoutError,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Transient errors that are safe to retry without side effects.
TRANSIENT_ERRORS: tuple[type[Exception], ...] = (
    AutoReconnect,
    ConnectionFailure,
    NetworkTimeout,
    ServerSelectionTimeoutError,
)


def build_mongo_client(url: str) -> AsyncIOMotorClient:
    """Build AsyncIOMotorClient with pool + timeout settings from env.

    Env overrides:
      MONGO_MAX_POOL_SIZE (default 50)
      MONGO_MIN_POOL_SIZE (default 5)
      MONGO_SERVER_SELECTION_TIMEOUT_MS (default 5000)
      MONGO_CONNECT_TIMEOUT_MS (default 5000)
      MONGO_SOCKET_TIMEOUT_MS (default 20000)
      MONGO_WAIT_QUEUE_TIMEOUT_MS (default 5000)
      MONGO_RETRY_WRITES (default true) — server-side retryable writes
    """
    return AsyncIOMotorClient(
        url,
        maxPoolSize=int(os.getenv("MONGO_MAX_POOL_SIZE", "50")),
        minPoolSize=int(os.getenv("MONGO_MIN_POOL_SIZE", "5")),
        serverSelectionTimeoutMS=int(
            os.getenv("MONGO_SERVER_SELECTION_TIMEOUT_MS", "5000")
        ),
        connectTimeoutMS=int(os.getenv("MONGO_CONNECT_TIMEOUT_MS", "5000")),
        socketTimeoutMS=int(os.getenv("MONGO_SOCKET_TIMEOUT_MS", "20000")),
        waitQueueTimeoutMS=int(os.getenv("MONGO_WAIT_QUEUE_TIMEOUT_MS", "5000")),
        retryWrites=os.getenv("MONGO_RETRY_WRITES", "true").lower() == "true",
    )


async def with_mongo_retry(
    op: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    base_delay: float = 0.1,
    op_name: str = "mongo_op",
) -> T:
    """Run a Mongo coroutine with exponential backoff on transient errors.

    Only transient errors (connection/timeout/autoreconnect) are retried.
    Business logic errors (duplicate key, validation) propagate immediately.
    """
    last_err: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await op()
        except TRANSIENT_ERRORS as e:
            last_err = e
            logger.warning(
                "%s attempt %d/%d failed with transient error: %s: %s",
                op_name, attempt, attempts, type(e).__name__, e,
            )
            if attempt < attempts:
                await asyncio.sleep(base_delay * (2 ** (attempt - 1)))
    assert last_err is not None  # loop guarantees at least one exception
    logger.error(
        "%s exhausted %d retries; raising last error: %s",
        op_name, attempts, last_err,
    )
    raise last_err
