import type { GameState } from '../../lib/types'

/**
 * Compute the power-hit trail sprite positions and visibility for a
 * given ball state + server-frame history. Pure function so it can be
 * unit-tested without a PixiJS stage (hence its own module — keeps
 * GameCanvas.tsx a component-only file for react-refresh).
 *
 * Original reference: `view.js:513-524` renders `ballHyper` at
 * `ball.previousX/Y` (t-1) and `ballTrail` at `ball.previousPreviousX/Y`
 * (t-2) while `ball.isPowerHit === true`. Both invisible otherwise.
 *
 * BE ships `is_power_hit` authoritatively. When BE also includes
 * `previousX/Y` and `previousPreviousX/Y` inline (not currently — see
 * 2026-04-12 Mode B decision) we prefer those. When they are absent we
 * fall back to the FE-maintained ring buffer. When the buffer is too
 * short (first 1-2 frames of a session) we fall back to the current
 * ball position so the sprites simply overlap the ball — harmless
 * single-frame artifact, no crash.
 *
 * When `isPowerHit` is `undefined` (e.g. an old replay payload that
 * pre-dates the field) the trail stays hidden. No velocity heuristic:
 * PM decision was to trust BE and not render speculative effects.
 */

export interface BallHistoryPoint {
  x: number
  y: number
}

export interface PowerHitTrail {
  visible: boolean
  hyper: BallHistoryPoint
  trail: BallHistoryPoint
}

export function computePowerHitTrail(
  ball: GameState['ball'],
  history: readonly BallHistoryPoint[],
): PowerHitTrail {
  const curr: BallHistoryPoint = { x: ball.x, y: ball.y }
  if (ball.isPowerHit !== true) {
    return { visible: false, hyper: curr, trail: curr }
  }

  const hyperFromBE =
    ball.previousX !== undefined && ball.previousY !== undefined
      ? { x: ball.previousX, y: ball.previousY }
      : null
  const trailFromBE =
    ball.previousPreviousX !== undefined &&
    ball.previousPreviousY !== undefined
      ? { x: ball.previousPreviousX, y: ball.previousPreviousY }
      : null

  // Ring buffer layout when full: [t-2, t-1, t]. Read from the tail
  // so the math works regardless of length (1, 2, or 3).
  const prev = history[history.length - 2] ?? history[history.length - 1] ?? curr
  const prevPrev = history[history.length - 3] ?? prev

  return {
    visible: true,
    hyper: hyperFromBE ?? prev,
    trail: trailFromBE ?? prevPrev,
  }
}
