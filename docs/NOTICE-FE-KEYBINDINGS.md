# Notice to Frontend: Keyboard input spec (original-faithful)

**From:** AI Engineer (backend/game)
**To:** Frontend (GameControls / GameCanvas owner)
**Status:** Blocking human-play feature; non-blocking for spectator-only
**Related:** `backend/game/engine.py` already ports power-hit logic; FE must
supply correctly-shaped `PlayerInput` when a human takes control.

---

## Why this notice exists

User feedback: "원본 게임에 Enter 키 '세게 치기(강타)' 있음."

This was investigated. The key exists. It is **not a separate attack tier**;
it is the `powerHit` input slot bound to `Enter` for Player 2 (and `Z` for
Player 1). Backend already handles it correctly. The missing piece is the
**FE keyboard handler** — currently the FE is spectator-only and ingests
zero keyboard input for gameplay.

---

## What the original does (ground truth)

From `gorisanson/pikachu-volleyball` (reverse-engineered from the 1997
Windows original):

### Key bindings (`src/resources/js/pikavolley.js:42`)

| Input           | Player 1   | Player 2     |
| --------------- | ---------- | ------------ |
| left            | `KeyD`     | `ArrowLeft`  |
| right           | `KeyG`     | `ArrowRight` |
| up (jump)       | `KeyR`     | `ArrowUp`    |
| down (crouch)   | `KeyV`     | `ArrowDown`  |
| **power hit**   | **`KeyZ`** | **`Enter`**  |
| down-right alt¹ | `KeyF`     | —            |

¹ P1-only convenience key: pressing it has the same effect as pressing
`down + right` simultaneously.

### Edge-triggering (`src/resources/js/keyboard.js:71-77`)

`powerHit` is emitted as `1` **only on the frame the key transitions from
up → down**. If the user holds the key, subsequent frames see `powerHit=0`.
This matters: without edge-triggering a held key would re-trigger a dive /
power hit every frame.

```js
const isDown = this.powerHitKey.isDown;
if (!this.powerHitKeyIsDownPrevious && isDown) {
  this.powerHit = 1;
} else {
  this.powerHit = 0;
}
this.powerHitKeyIsDownPrevious = isDown;
```

### What pressing power-hit does in the engine

(`src/resources/js/physics.js:581-604` — already ported into
`backend/game/engine.py`.)

| Player state when power-hit pressed | Resulting action                          |
| ----------------------------------- | ----------------------------------------- |
| `state=1` jumping                   | Enters `state=2` (jumping + power hitting); next ball collision uses the power formula: `vx = ±(|xDir|+1)*10`, `vy = |vy|*yDir*2` |
| `state=0` grounded, `xDir ≠ 0`      | Triggers a **dive** in the `xDir` direction (`state=3`) |
| `state=0` grounded, `xDir == 0`     | No-op                                     |
| any other state                     | Ignored                                   |

**There is only one tier of power hit.** The `isPowerHit` flag that appears
on `ball` is cosmetic only — it drives the `ballHyper` and `ballTrail`
sprite trails in `view.js:513`. No gameplay difference.

---

## Backend readiness

`backend/game/engine.py` already:

- Exposes `PlayerInput(x_dir, y_dir, power_hit)` as the canonical frame
  input (`engine.py:95`).
- Dispatches to the same two branches as the original: dive-on-ground vs
  power-hit-on-jump (`engine.py:297-310`).
- Produces the original's collision velocities when
  `power_hit AND is_jumping` (`engine.py:361-368`).

**Gap: `ball.is_power_hit` flag for cosmetic trail rendering is not yet
plumbed through.** Low priority — only needed once FE actually renders the
hyper/trail sprites. Can follow up if FE wants a pixel-faithful look.

---

## What FE needs to build (when/if human-play surface is added)

1. **`useGameKeyboard` hook** that listens for `keydown` / `keyup` on
   `window` and maintains per-player state:

   ```ts
   type PlayerInput = { x_dir: -1|0|1; y_dir: -1|0|1; power_hit: boolean };
   ```

   One hook instance per player; bindings configurable but should default
   to the original map above.

2. **Edge-detect `power_hit`.** Emit `power_hit=true` on the frame the
   bound key transitions from up → down; `false` otherwise — including
   while the key stays held. Match `keyboard.js:71-77` exactly.

3. **`preventDefault`** on key events (especially `ArrowUp/Down` and
   `Enter`) so the browser doesn't scroll / trigger form submission.

4. **Send `PlayerInput` over the existing WebSocket** — backend already
   knows how to apply it.

5. **Focus gate**: only process keyboard when the game canvas has focus,
   to avoid stealing typing input from dashboard controls.

### Optional but original-faithful

- KeyV/KeyF distinction for P1 (see Tip 2 in original `src/en/index.html`).
- "Z selects P1, Enter selects P2" menu-selection semantic (cosmetic).

---

## Tests FE should add

- Holding `Z` for N frames produces exactly **one** frame with
  `power_hit=true` followed by `power_hit=false` (edge-trigger test).
- `ArrowUp` sets `y_dir=-1`, `ArrowDown` sets `y_dir=+1`, neither sets `0`.
- `ArrowLeft + ArrowDown` simultaneously yields
  `(x_dir=-1, y_dir=+1)`.
- Ctrl/Alt/Meta modifiers do not dispatch game input (don't break OS
  shortcuts).

---

## Owner / follow-up

- **Backend:** no further action needed for physics correctness. Will ship
  `ball.is_power_hit` cosmetic flag once FE asks for it.
- **Frontend:** please acknowledge this spec and schedule a keyboard-input
  PR when the human-play surface becomes a priority. Ping backend if any
  `PlayerInput` field needs extending.
- **PM:** update roadmap — "human-play against trained model" depends on
  this FE work; until then the dashboard remains spectator-only.
