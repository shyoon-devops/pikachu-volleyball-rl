"""Shim over ``backend.rl.dreamer_runner``."""

from backend.rl.dreamer_runner import (  # noqa: F401 — re-export
    DREAMER_DEFAULT_KWARGS,
    DreamerAgent,
)

__all__ = ["DREAMER_DEFAULT_KWARGS", "DreamerAgent"]
