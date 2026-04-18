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
        path = self._safe_path(game_id)
        if path is None:
            raise ValueError(f"Invalid game_id: {game_id}")
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

    def _safe_path(self, game_id: str) -> Path | None:
        """Resolve path and reject traversal attempts."""
        if not game_id or "/" in game_id or "\\" in game_id or ".." in game_id:
            return None
        path = (self._dir / f"{game_id}.msgpack").resolve()
        if not str(path).startswith(str(self._dir.resolve())):
            return None
        return path

    async def load_replay(self, game_id: str) -> list[dict[str, Any]]:
        path = self._safe_path(game_id)
        if path is None or not path.exists():
            return []
        raw = await asyncio.to_thread(path.read_bytes)
        frames = msgpack.unpackb(raw, raw=False)
        return [_backfill_frame(f) for f in frames]

    async def cleanup_old_replays(self) -> None:
        files = sorted(self._dir.glob("*.msgpack"), key=lambda p: p.stat().st_mtime)
        while len(files) > self._max_count:
            files.pop(0).unlink()


_PLAYER_DEFAULTS = {
    "is_jumping": False,
    "is_diving": False,
    "is_power_hitting": False,
    "diving_direction": 0,
    # Pikachu sprite state for the FE renderer. Defaulted on legacy
    # replays pickled before the engine emitted these — without the
    # back-fill the FE renderer would KeyError during scrubbing.
    "state": 0,
    "frame_number": 0,
    "is_winner": False,
    "game_ended": False,
}
_BALL_DEFAULTS = {
    "rotation": 0,
    "is_power_hit": False,
    "punch_effect_x": 0,
    "punch_effect_y": 0,
    "punch_effect_radius": 0,
}
# ``post_score_freeze_frames`` is kept in the back-fill defaults for legacy
# replays pickled before the view port. Live replays no longer emit the
# field; new fields (``is_game_ended`` / ``game_end_frame_counter``) plus
# the display-state-machine fields (``state_name`` / ``slow_motion_frames_
# left`` / ``fade_black_alpha`` / ``ready_message_visible``) added by
# ``port(engine-state)`` are defaulted alongside so the frontend gets a
# consistent schema regardless of replay vintage.
_FRAME_DEFAULTS = {
    "is_round_over": False,
    "post_score_freeze_frames": 0,
    "is_game_ended": False,
    "game_end_frame_counter": 0,
    "state_name": "round",
    "slow_motion_frames_left": 0,
    "fade_black_alpha": 0.0,
    "ready_message_visible": False,
    # Pre-FPS-fix replays were emitted at 30fps. Back-fill matches the
    # constant the FE used to hard-code so old replays scrub at the
    # rate they were originally recorded at.
    "tick_rate": 30,
}
# Per-frame SFX triggers added by the be-sfx port. Legacy replays predate
# all five flags; back-fill False so FE readers never KeyError.
_SOUNDS_DEFAULTS = {
    "pika": False,
    "chu": False,
    "pipikachu": False,
    "power_hit": False,
    "ball_touches_ground": False,
}


def _backfill_frame(frame: dict[str, Any]) -> dict[str, Any]:
    """Fill missing fields in legacy replay frames for frontend compatibility."""
    for key in ("player1", "player2"):
        if key in frame:
            for field, default in _PLAYER_DEFAULTS.items():
                frame[key].setdefault(field, default)
    if "ball" in frame:
        for field, default in _BALL_DEFAULTS.items():
            frame["ball"].setdefault(field, default)
    for field, default in _FRAME_DEFAULTS.items():
        frame.setdefault(field, default)
    sounds = frame.setdefault("sounds", {})
    for field, default in _SOUNDS_DEFAULTS.items():
        sounds.setdefault(field, default)
    return frame
