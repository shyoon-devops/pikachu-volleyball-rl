# NOTICE — WS `game:result` broadcast drops fields

**Filed:** 2026-04-12
**Filed by:** Frontend engineer
**Severity:** MEDIUM (user-visible bug; FE has a defensive fallback shipped)
**Owner for fix:** Backend / AI engineer

## Symptom

Recent Games table on the dashboard rendered bot level cells as a
bare capital **"L"** with nothing after it (e.g. `L` instead of `L1`).

## Root cause

The training-loop evaluation callback enqueues a game-result dict that
is missing `bot_level`, `experiment_id`, and `rally_count`:

```python
# backend/rl/callbacks.py:236-243
result = {
    "game_id": game_id,
    "score1": state.score1,
    "score2": state.score2,
    "winner": 1 if state.score1 >= MAX_SCORE else 2,
    "duration_frames": state.frame,
}
_safe_enqueue(self.loop, self.results_queue, result)
```

The results push loop then broadcasts the **raw dict** (not the
validated `GameRecord`) over WebSocket:

```python
# backend/app/ws/handlers.py:315-357
record = GameRecord(
    game_id=data.get("game_id", ""),
    experiment_id=data.get("experiment_id", ""),
    bot_level=data.get("bot_level", 1),        # fallback swallows
    score1=data["score1"],
    score2=data["score2"],
    ...
    rally_count=data.get("rally_count", 0),    # fallback swallows
)
...
await manager.broadcast({"type": "game:result", "payload": data})
#                                                     ^^^^
#                           raw dict, NOT record.model_dump()
```

Consequences:

| Field | In broadcast? | FE behavior before fix |
|---|---|---|
| `bot_level` | ❌ no | `L` (undefined concat) |
| `experiment_id` | ❌ no | (not displayed) |
| `rally_count` | ❌ no | column empty |

REST `/api/games` is unaffected — it returns the DB-persisted
`GameRecord`, which is always validated and has `bot_level` populated
via the `get("bot_level", 1)` fallback at insert time.

## Proposed BE fix (pick one)

**Option 1 — Fix at enqueue (preferred, recommended):**

```python
# backend/rl/callbacks.py:236
result = {
    "game_id": game_id,
    "experiment_id": self.experiment_id,   # populate
    "bot_level": self.bot_level,           # populate
    "score1": state.score1,
    "score2": state.score2,
    "winner": 1 if state.score1 >= MAX_SCORE else 2,
    "duration_frames": state.frame,
    "rally_count": <compute>,              # populate
}
```

This is the correct fix because it makes the enqueued dict match the
`GameRecord` schema so downstream consumers (broadcast, dead-letter,
logs) all see the real values.

**Option 2 — Broadcast the validated record:**

```python
# backend/app/ws/handlers.py:357
await manager.broadcast({
    "type": "game:result",
    "payload": record.model_dump(mode="json", by_alias=False),
})
```

Less invasive but still leaves `bot_level=1` as a silent fallback
whenever the callback skips populating it — i.e. Option 2 **hides**
the underlying miss rather than fixing it.

## FE mitigation (already shipped)

Commit `TBD` on branch `yoon/frontend-engineer`:

- `GameRecord.botLevel` is now `number | undefined` in `lib/types.ts`
  so the type matches the actual WS payload.
- `lib/formatGame.ts::formatBotLevel()` renders `L?` when the field
  is missing so the bug stays visible to users (not silently "L1").
- Dashboard Recent Games and Replay List tables route through the
  helper.

Once the BE fix lands, the field will always be present and the
fallback becomes dead code — we'll leave it in place as a defensive
guard against future regressions.

## Test signal

Repro in dev: start training, play a game, observe `game:result`
frame in browser devtools WebSocket inspector — it lacks `bot_level`.
Refreshing the page then calling `/api/games` returns full records
with `bot_level` populated.
