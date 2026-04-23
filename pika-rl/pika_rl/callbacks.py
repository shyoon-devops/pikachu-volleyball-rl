"""Shim over ``backend.rl.callbacks``.

MineRL repo reuses ``MetricsCallback`` + ``CheckpointCallback`` +
``UpdateWindowCallback`` largely unchanged; the env-facing ones
(``EnvFrameCallback``, ``EnvResultCallback``, ``LiveFrameCallback``)
reach into PikachuVolleyball-specific helpers and will need
abstract replacements in Phase 2 — see PIKA-RL-EXTRACTION.md §3.
We still re-export them here so the shim stays complete.
"""

from backend.rl.callbacks import (  # noqa: F401 — re-export
    CheckpointCallback,
    EnvFrameCallback,
    EnvResultCallback,
    LiveFrameCallback,
    MetricsCallback,
    UpdateWindowCallback,
)

__all__ = [
    "CheckpointCallback",
    "EnvFrameCallback",
    "EnvResultCallback",
    "LiveFrameCallback",
    "MetricsCallback",
    "UpdateWindowCallback",
]
