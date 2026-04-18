import type { PlayerState } from '../../lib/types'

/**
 * Map a player's engine state to an index into the 28-frame pikachu
 * texture array. 1:1 port of
 * `view.js::getFrameNumberForPlayerAnimatedSprite` (lines 948-966):
 *
 *   state < 4   → 5 * state + frameNumber   (0..14)
 *   state === 4 → 17 + frameNumber          (17)
 *   state > 4   → 18 + 5 * (state - 5) + frameNumber  (18..27)
 *
 * Sheet layout (matching `makePlayerAnimatedSprites`):
 *   0 idle        (5 frames)  → 0..4
 *   1 jumping     (5 frames)  → 5..9
 *   2 power-hit   (5 frames)  → 10..14
 *   3 diving      (2 frames)  → 15..16
 *   4 lying       (1 frame)   → 17
 *   5 winning     (5 frames)  → 18..22
 *   6 losing      (5 frames)  → 23..27
 */
export function frameForState(state: number, frameNumber: number): number {
  if (state < 4) {
    return 5 * state + frameNumber
  }
  if (state === 4) {
    return 17 + frameNumber
  }
  return 18 + 5 * (state - 5) + frameNumber
}

/**
 * Resolve the sprite index for a player.
 *
 * Preferred path: the ported engine emits authoritative `state` + `frameNumber`
 * on every WS frame, so we delegate to `frameForState`. The physics port
 * advances `frame_number` deterministically based on
 * `delay_before_next_frame` (physics.js:2xx), giving a faithful
 * reproduction of the original animation cadence.
 *
 * Fallback path: pre-port replays and any transport that strips these
 * fields (older mock frames, truncated payloads) land here. We derive
 * state from the boolean flags in the same priority order physics.js
 * uses when resolving transitions within a single tick:
 * power_hit > dive > jump > idle. The FE-local `frameCounter` drives
 * the cycle, so the animation still plays — it just won't share the
 * engine's exact delay schedule. Losing half a frame of timing is
 * acceptable here; flags-only inputs are intentionally a degraded
 * mode, not parity.
 */
export function inferPlayerFrame(p: PlayerState, frameCounter: number): number {
  if (typeof p.state === 'number' && typeof p.frameNumber === 'number') {
    return frameForState(p.state, p.frameNumber)
  }
  if (p.isPowerHitting) {
    return frameForState(2, frameCounter % 5)
  }
  if (p.isDiving) {
    return frameForState(3, frameCounter % 2)
  }
  if (p.isJumping || p.vy !== 0) {
    return frameForState(1, frameCounter % 5)
  }
  return frameForState(0, frameCounter % 5)
}
