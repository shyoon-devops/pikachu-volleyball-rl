"""Temporary timing instrumentation for freeze-cause diagnosis.

This module is DELIBERATELY isolated so the whole diagnostic layer can
be reverted with a single-file delete once analysis is complete. Every
instrumentation point in env.py, loaded_policy_bot.py, opponent.py,
callbacks.py reads from this module — if you're looking at this file
in production code, file a ticket: it should have been reverted.

Usage (local smoke):
    FREEZE_DIAG_FILE=/tmp/freeze.csv python -m backend.scripts.freeze_smoke

The CSV schema is `event,env_index,duration_ms,extra` (one line per
measurement). ``extra`` is an opaque context string, stripped in the
aggregator. A trailing NaN column means "no duration — event point
marker only" (e.g. rollout boundaries).
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any

_FILE_PATH = os.environ.get("FREEZE_DIAG_FILE", "")
_LOCK = threading.Lock()
_FILE: Any = None


def _open_if_needed() -> Any:
    global _FILE
    if _FILE is not None or not _FILE_PATH:
        return _FILE
    with _LOCK:
        if _FILE is None and _FILE_PATH:
            _FILE = open(_FILE_PATH, "a", buffering=1)
            _FILE.write("ts_ms,event,env_index,duration_ms,extra\n")
    return _FILE


def record(
    event: str,
    *,
    env_index: int = -1,
    duration_ms: float | None = None,
    extra: str = "",
) -> None:
    """Append one measurement line to the configured CSV.

    No-op when ``FREEZE_DIAG_FILE`` is unset — so leaving the instrumentation
    import in place during a normal run costs ~one function call + env
    lookup per site.
    """
    f = _open_if_needed()
    if f is None:
        return
    ts_ms = time.perf_counter() * 1000
    d = f"{duration_ms:.3f}" if duration_ms is not None else ""
    line = f"{ts_ms:.3f},{event},{env_index},{d},{extra}\n"
    with _LOCK:
        f.write(line)


def timed(event: str, *, env_index: int = -1, extra: str = ""):
    """Context manager that records elapsed time for a code block."""

    class _Ctx:
        __slots__ = ("_t0",)

        def __enter__(self) -> "_Ctx":
            self._t0 = time.perf_counter()
            return self

        def __exit__(self, *_exc: Any) -> None:
            elapsed_ms = (time.perf_counter() - self._t0) * 1000
            record(
                event, env_index=env_index, duration_ms=elapsed_ms, extra=extra
            )

    return _Ctx()


def mark(event: str, *, extra: str = "") -> None:
    """Record a zero-duration event (phase boundary, etc)."""
    record(event, extra=extra)
