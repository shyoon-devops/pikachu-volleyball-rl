"""Replay storage service — msgpack serialization to filesystem."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import msgpack


class ReplayService:
    def __init__(self, replay_dir: str = "replays", max_count: int = 1000) -> None:
        self._dir = Path(replay_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._max_count = max_count

    async def save_replay(self, game_id: str, frames: list[dict[str, Any]]) -> None:
        path = self._dir / f"{game_id}.msgpack"
        packed = msgpack.packb(frames, use_bin_type=True)
        await asyncio.to_thread(path.write_bytes, packed)
        await self.cleanup_old_replays()

    async def list_replays(self) -> list[dict[str, Any]]:
        files = sorted(self._dir.glob("*.msgpack"), key=lambda p: p.stat().st_mtime, reverse=True)
        return [
            {
                "game_id": f.stem,
                "size_bytes": f.stat().st_size,
                "created_at": f.stat().st_mtime,
            }
            for f in files
        ]

    async def load_replay(self, game_id: str) -> list[dict[str, Any]]:
        path = self._dir / f"{game_id}.msgpack"
        if not path.exists():
            return []
        raw = await asyncio.to_thread(path.read_bytes)
        frames = msgpack.unpackb(raw, raw=False)
        return [_backfill_frame(f) for f in frames]

    async def cleanup_old_replays(self) -> None:
        files = sorted(self._dir.glob("*.msgpack"), key=lambda p: p.stat().st_mtime)
        while len(files) > self._max_count:
            files.pop(0).unlink()


_PLAYER_DEFAULTS = {"is_jumping": False, "is_diving": False, "is_power_hitting": False}
_BALL_DEFAULTS = {"rotation": 0}


def _backfill_frame(frame: dict[str, Any]) -> dict[str, Any]:
    """Fill missing fields in legacy replay frames for frontend compatibility."""
    for key in ("player1", "player2"):
        if key in frame:
            for field, default in _PLAYER_DEFAULTS.items():
                frame[key].setdefault(field, default)
    if "ball" in frame:
        for field, default in _BALL_DEFAULTS.items():
            frame["ball"].setdefault(field, default)
    return frame
