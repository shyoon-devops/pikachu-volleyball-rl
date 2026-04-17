import { describe, it, expect } from 'vitest'
import { inferPlayerFrame, frameForState } from './playerFrame'
import type { PlayerState } from '../../lib/types'

// Builds a PlayerState with sensible defaults so each test can override
// just the field under inspection — keeps the priority-order tests
// readable (no 7-field literal repeated inline).
function buildPlayer(overrides: Partial<PlayerState> = {}): PlayerState {
  return {
    x: 100,
    y: 244,
    vx: 0,
    vy: 0,
    isJumping: false,
    isDiving: false,
    isPowerHitting: false,
    ...overrides,
  }
}

describe('inferPlayerFrame', () => {
  describe('idle state (state=0, 5 frames, indices 0..4)', () => {
    it('maps a stationary player to indices 0..4', () => {
      const p = buildPlayer()
      expect(inferPlayerFrame(p, 0)).toBe(0)
      expect(inferPlayerFrame(p, 3)).toBe(3)
      expect(inferPlayerFrame(p, 4)).toBe(4)
      // wraps at 5
      expect(inferPlayerFrame(p, 5)).toBe(0)
      expect(inferPlayerFrame(p, 12)).toBe(2)
    })

    it('maps a walking player (vx != 0) to idle-range frames', () => {
      // The original sheet has no dedicated walk frames — view.js reuses
      // state=0 for both idle and walk, and so do we.
      const p = buildPlayer({ vx: 3 })
      expect(inferPlayerFrame(p, 0)).toBe(0)
      expect(inferPlayerFrame(p, 7)).toBe(2)
    })
  })

  describe('jumping state (state=1, 5 frames, indices 5..9)', () => {
    it('maps isJumping=true to indices 5..9', () => {
      const p = buildPlayer({ isJumping: true })
      expect(inferPlayerFrame(p, 0)).toBe(5)
      expect(inferPlayerFrame(p, 4)).toBe(9)
      expect(inferPlayerFrame(p, 5)).toBe(5)
    })

    it('falls back to jump frames when only vy != 0', () => {
      // Older flag-less servers (or transitional frames between flag
      // toggles) might send vy without isJumping. Keep the velocity
      // fallback so air-time still renders as a jump instead of idle.
      const p = buildPlayer({ vy: -7 })
      expect(inferPlayerFrame(p, 0)).toBe(5)
      expect(inferPlayerFrame(p, 2)).toBe(7)
    })
  })

  describe('power-hit state (state=2, 5 frames, indices 10..14)', () => {
    it('maps isPowerHitting=true to indices 10..14', () => {
      const p = buildPlayer({ isPowerHitting: true })
      expect(inferPlayerFrame(p, 0)).toBe(10)
      expect(inferPlayerFrame(p, 4)).toBe(14)
      expect(inferPlayerFrame(p, 5)).toBe(10)
    })
  })

  describe('diving state (state=3, 2 frames, indices 15..16)', () => {
    it('maps isDiving=true to indices 15..16', () => {
      const p = buildPlayer({ isDiving: true })
      expect(inferPlayerFrame(p, 0)).toBe(15)
      expect(inferPlayerFrame(p, 1)).toBe(16)
      // wraps at 2, not 5
      expect(inferPlayerFrame(p, 2)).toBe(15)
      expect(inferPlayerFrame(p, 3)).toBe(16)
    })

    it('renders the dive pose even when vy != 0 (regression)', () => {
      // Prior velocity-only heuristic read `vy !== 0` first and so
      // mapped dives (which have yVelocity = -5 per physics.js:598)
      // into the jump range 5..9 — the dive sprite never rendered.
      // This test locks in that the flag takes priority over vy.
      const p = buildPlayer({ isDiving: true, vy: -5 })
      expect(inferPlayerFrame(p, 0)).toBe(15)
      expect(inferPlayerFrame(p, 1)).toBe(16)
    })
  })

  describe('engine-authoritative state + frameNumber (port path)', () => {
    // When the ported engine provides `state` and `frameNumber`, the
    // fallback flag heuristic is skipped entirely — we delegate to
    // `frameForState`, a 1:1 port of view.js:958-966. These cover the
    // full 28-frame sheet layout.
    it('routes state=0..2 through frameForState (5 frames each)', () => {
      expect(inferPlayerFrame({ ...buildPlayer(), state: 0, frameNumber: 0 }, 0)).toBe(0)
      expect(inferPlayerFrame({ ...buildPlayer(), state: 0, frameNumber: 4 }, 0)).toBe(4)
      expect(inferPlayerFrame({ ...buildPlayer(), state: 1, frameNumber: 0 }, 0)).toBe(5)
      expect(inferPlayerFrame({ ...buildPlayer(), state: 2, frameNumber: 4 }, 0)).toBe(14)
    })

    it('routes state=3 through the 2-frame dive range 15..16', () => {
      expect(inferPlayerFrame({ ...buildPlayer(), state: 3, frameNumber: 0 }, 0)).toBe(15)
      expect(inferPlayerFrame({ ...buildPlayer(), state: 3, frameNumber: 1 }, 0)).toBe(16)
    })

    it('routes state=4 to the single lying frame 17', () => {
      expect(inferPlayerFrame({ ...buildPlayer(), state: 4, frameNumber: 0 }, 0)).toBe(17)
    })

    it('routes state=5..6 through the win/lose ranges 18..27', () => {
      expect(inferPlayerFrame({ ...buildPlayer(), state: 5, frameNumber: 0 }, 0)).toBe(18)
      expect(inferPlayerFrame({ ...buildPlayer(), state: 5, frameNumber: 4 }, 0)).toBe(22)
      expect(inferPlayerFrame({ ...buildPlayer(), state: 6, frameNumber: 0 }, 0)).toBe(23)
      expect(inferPlayerFrame({ ...buildPlayer(), state: 6, frameNumber: 4 }, 0)).toBe(27)
    })

    it('ignores the flag heuristic when state is present (state wins)', () => {
      // BE sends state=0 (idle) but the old flag is stale on isPowerHitting.
      // The port-path branch must trust engine state, not the flag.
      const p = { ...buildPlayer({ isPowerHitting: true }), state: 0, frameNumber: 2 }
      expect(inferPlayerFrame(p, 99)).toBe(2)
    })
  })

  describe('frameForState (direct port of view.js:958-966)', () => {
    it('matches the original piecewise formula across all 28 indices', () => {
      // state 0..2: 5 * state + n
      expect(frameForState(0, 0)).toBe(0)
      expect(frameForState(0, 4)).toBe(4)
      expect(frameForState(2, 0)).toBe(10)
      // state 3: 15..16
      expect(frameForState(3, 0)).toBe(15)
      expect(frameForState(3, 1)).toBe(16)
      // state 4: 17
      expect(frameForState(4, 0)).toBe(17)
      // state 5..6: 18 + 5*(state-5) + n
      expect(frameForState(5, 0)).toBe(18)
      expect(frameForState(6, 4)).toBe(27)
    })
  })

  describe('priority order (power_hit > dive > jump > idle)', () => {
    it('power-hit wins over diving', () => {
      const p = buildPlayer({ isPowerHitting: true, isDiving: true })
      expect(inferPlayerFrame(p, 0)).toBe(10)
    })

    it('power-hit wins over jumping', () => {
      const p = buildPlayer({ isPowerHitting: true, isJumping: true })
      expect(inferPlayerFrame(p, 0)).toBe(10)
    })

    it('diving wins over jumping', () => {
      // Physically unusual (can't dive from a jump in the original
      // engine) but the priority rule still has to be well-defined so
      // transitional frames don't flicker.
      const p = buildPlayer({ isDiving: true, isJumping: true })
      expect(inferPlayerFrame(p, 0)).toBe(15)
    })
  })
})
