import type { PlayerState } from '../../lib/types'

/**
 * Map a player's current state to an index into the pikachu sprite
 * sheet's 28-frame texture array. Pure so the fallback logic stays
 * testable without a PixiJS stage.
 *
 * Original reference: `physics.js` and `view.js::getFrameNumberForPlayerAnimatedSprite`.
 * The sheet packs states sequentially:
 *
 *   idle       (state 0, 5 frames) → indices 0..4
 *   jumping    (state 1, 5 frames) → indices 5..9
 *   power-hit  (state 2, 5 frames) → indices 10..14
 *   diving     (state 3, 2 frames) → indices 15..16
 *   lying      (state 4, 1 frame)  → index 17
 *   win/lose   (state 5..6)        → not emitted by the RL engine
 *
 * BE sends `is_jumping`, `is_diving`, `is_power_hitting` flags but no
 * explicit `state` / `frameNumber` fields, so we derive the state from
 * the flags in original-game priority order (power_hit > dive > jump >
 * idle) — matching how physics.js prioritizes transitions within a
 * single tick. `frameCounter` is the FE's own incrementing counter so
 * the animation plays forward deterministically regardless of WS
 * arrival cadence.
 *
 * Why diving checks the flag first and not `vy !== 0`: a diving player
 * has upward velocity (`yVelocity = -5` per physics.js:598) so the
 * old velocity-only heuristic mapped dives to the jump frames, and
 * the dive pose never rendered. Reading `is_diving` directly fixes
 * that silent miss.
 */
export function inferPlayerFrame(p: PlayerState, frameCounter: number): number {
  if (p.isPowerHitting) {
    return 10 + (frameCounter % 5)
  }
  if (p.isDiving) {
    return 15 + (frameCounter % 2)
  }
  if (p.isJumping || p.vy !== 0) {
    return 5 + (frameCounter % 5)
  }
  // Idle / walk both use state=0; BE sets vx to walk direction but the
  // sheet reuses idle frames for the 5-frame loop (view.js does the
  // same — there's no separate walk sheet).
  return frameCounter % 5
}
