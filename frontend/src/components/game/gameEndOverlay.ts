/**
 * Port of `view.js::GameView.drawGameEndMessage` lines 622-645 — the
 * expanding "GAME END" overlay shown during the 211-frame gameEnd
 * window (`pikavolley.js::frameTotal.gameEnd`).
 *
 * The original animates for the first 50 frames by inflating the
 * sprite's width/height around a centered anchor, then holds at
 * natural size for the remaining 161 frames. The engine drives the
 * animation by emitting `gameEndFrameCounter` (0..210 inclusive) on
 * every frame while `isGameEnded === true`.
 *
 * Pulled into a pure helper (no Pixi imports) so the math is testable
 * without a stage — matches the `punchEffect.ts` split.
 *
 * The input sprite's natural width/height must be provided by the
 * caller, since Pixi sprite textures aren't available in unit tests
 * without a WebGL context. In the renderer they come straight from
 * `sprite.texture.width/height`, matching view.js:624-625.
 */
export interface GameEndOverlayProps {
  visible: boolean
  x: number
  y: number
  width: number
  height: number
}

/** Horizontal centre of the court in the 432×304 original grid. */
const COURT_CENTER_X = 216

export function computeGameEndOverlay(params: {
  isGameEnded: boolean
  frameCounter: number
  textureWidth: number
  textureHeight: number
}): GameEndOverlayProps {
  const { isGameEnded, frameCounter, textureWidth: w, textureHeight: h } = params

  if (!isGameEnded) {
    return { visible: false, x: 0, y: 0, width: 0, height: 0 }
  }

  // Phase 1 — inflating intro, frames 0..49. The `(50 - frameCounter)`
  // term shrinks the outward increment each tick, so the sprite starts
  // huge and converges toward natural size at frame 50. Integer math +
  // ×2 doubling mirror view.js:631-638 exactly.
  if (frameCounter < 50) {
    const halfWidthIncrement = 2 * Math.floor(((50 - frameCounter) * w) / 50)
    const halfHeightIncrement = 2 * Math.floor(((50 - frameCounter) * h) / 50)
    return {
      visible: true,
      x: COURT_CENTER_X - w / 2 - halfWidthIncrement,
      y: 50 - halfHeightIncrement,
      width: w + 2 * halfWidthIncrement,
      height: h + 2 * halfHeightIncrement,
    }
  }

  // Phase 2 — hold at natural size for the remaining 161 frames
  // (50..210). Matches view.js:639-643.
  return {
    visible: true,
    x: COURT_CENTER_X - w / 2,
    y: 50,
    width: w,
    height: h,
  }
}
