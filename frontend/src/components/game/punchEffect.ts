import type { BallState } from '../../lib/types'

/**
 * Port of `view.js::GameView.drawPlayersAndBall` lines 501-511 — the
 * shrinking radial ring drawn on a successful hit.
 *
 * BE owns the animation lifecycle: on impact `punch_effect_radius` is
 * seeded to BALL_RADIUS (≈20) and decays by 2 per engine tick (see
 * `backend/game/engine.py` + physics.js:502-511 FUN_00402ee0). The FE
 * just reads the authoritative value and draws a `2 * radius` sized
 * sprite anchored on `(punch_effect_x, punch_effect_y)`.
 *
 * Kept as a pure function so the sizing math can be tested without a
 * PixiJS stage — mirrors the `computePowerHitTrail` split.
 *
 * The `ball.x/y` fallback for x/y is intentional: pre-port replays and
 * any FE ingest that drops the punch_effect_* fields will still draw
 * the ring at the ball's current position (one-frame visual artifact,
 * no crash) rather than spawning at (0, 0).
 */
export interface PunchEffect {
  visible: boolean
  x: number
  y: number
  /** Sprite width — 2 × radius to match view.js:504. */
  width: number
  height: number
}

export function computePunchEffect(ball: BallState): PunchEffect {
  const radius = ball.punchEffectRadius ?? 0
  if (radius <= 0) {
    return { visible: false, x: 0, y: 0, width: 0, height: 0 }
  }
  return {
    visible: true,
    x: ball.punchEffectX ?? ball.x,
    y: ball.punchEffectY ?? ball.y,
    width: 2 * radius,
    height: 2 * radius,
  }
}
