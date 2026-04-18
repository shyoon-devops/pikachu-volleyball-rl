import { describe, it, expect } from 'vitest'
import {
  computePowerHitTrail,
  type BallHistoryPoint,
} from './powerHitTrail'
import type { GameState } from '../../lib/types'

/**
 * Tests for the pure power-hit trail helper. The helper encapsulates
 * the fallback logic between BE-provided history fields, the FE ring
 * buffer, and the current ball position — the real PixiJS sprite
 * assignment just consumes its output.
 *
 * The helper was extracted 2026-04-12 after PM approved Mode B
 * (BE sends `is_power_hit` only; FE maintains a 3-slot ring buffer
 * of server ball positions for the trail).
 */

function makeBall(overrides: Partial<GameState['ball']> = {}): GameState['ball'] {
  return {
    x: 100,
    y: 100,
    vx: 0,
    vy: 0,
    rotation: 0,
    ...overrides,
  }
}

describe('computePowerHitTrail', () => {
  it('is invisible when isPowerHit is false', () => {
    const result = computePowerHitTrail(
      makeBall({ isPowerHit: false }),
      [{ x: 0, y: 0 }, { x: 50, y: 50 }, { x: 100, y: 100 }],
    )
    expect(result.visible).toBe(false)
  })

  it('is invisible when isPowerHit is undefined (old payload — no heuristic)', () => {
    // Regression guard: the old velocity heuristic would have rendered
    // a trail here. After Mode B we trust BE only.
    const result = computePowerHitTrail(
      makeBall({ vx: 99, vy: 99 }), // high speed
      [{ x: 0, y: 0 }, { x: 50, y: 50 }, { x: 100, y: 100 }],
    )
    expect(result.visible).toBe(false)
  })

  it('renders trail from ring buffer when BE omits previousX/Y', () => {
    const history: BallHistoryPoint[] = [
      { x: 10, y: 10 }, // t-2
      { x: 50, y: 50 }, // t-1
      { x: 100, y: 100 }, // t
    ]
    const result = computePowerHitTrail(
      makeBall({ x: 100, y: 100, isPowerHit: true }),
      history,
    )
    expect(result.visible).toBe(true)
    // hyper = t-1, trail = t-2 (matches original view.js:513-517)
    expect(result.hyper).toEqual({ x: 50, y: 50 })
    expect(result.trail).toEqual({ x: 10, y: 10 })
  })

  it('prefers BE previousX/Y when present', () => {
    // BE values should win over FE ring buffer — BE is authoritative
    // for the exact engine positions while FE buffer is a best-effort
    // reconstruction from sampled WS frames.
    const result = computePowerHitTrail(
      makeBall({
        isPowerHit: true,
        previousX: 200,
        previousY: 200,
        previousPreviousX: 300,
        previousPreviousY: 300,
      }),
      [
        { x: 10, y: 10 }, // would be used, but BE overrides
        { x: 50, y: 50 },
        { x: 100, y: 100 },
      ],
    )
    expect(result.visible).toBe(true)
    expect(result.hyper).toEqual({ x: 200, y: 200 })
    expect(result.trail).toEqual({ x: 300, y: 300 })
  })

  it('falls back to current position on the very first power-hit frame (empty history)', () => {
    // No crash, sprites overlap the ball — acceptable single-frame
    // artifact while the ring buffer warms up.
    const result = computePowerHitTrail(
      makeBall({ x: 100, y: 100, isPowerHit: true }),
      [],
    )
    expect(result.visible).toBe(true)
    expect(result.hyper).toEqual({ x: 100, y: 100 })
    expect(result.trail).toEqual({ x: 100, y: 100 })
  })

  it('handles single-entry history (second server frame)', () => {
    // At length 1 the only entry IS the current position, so both
    // fall back to current. No negative indices, no undefined reads.
    const result = computePowerHitTrail(
      makeBall({ x: 100, y: 100, isPowerHit: true }),
      [{ x: 100, y: 100 }],
    )
    expect(result.visible).toBe(true)
    expect(result.hyper).toEqual({ x: 100, y: 100 })
    expect(result.trail).toEqual({ x: 100, y: 100 })
  })

  it('handles two-entry history (third server frame) — trail collapses to hyper', () => {
    const result = computePowerHitTrail(
      makeBall({ x: 100, y: 100, isPowerHit: true }),
      [
        { x: 50, y: 50 }, // becomes hyper (t-1)
        { x: 100, y: 100 }, // current
      ],
    )
    expect(result.visible).toBe(true)
    expect(result.hyper).toEqual({ x: 50, y: 50 })
    // trail has no t-2 yet so it collapses onto hyper — visually fine
    // for a single frame until the buffer catches up.
    expect(result.trail).toEqual({ x: 50, y: 50 })
  })

  it('mixes BE + FE — uses BE previous when present, FE prevPrev when BE omits it', () => {
    // Hypothetical: BE adds previousX/Y but not previousPreviousX/Y.
    // Helper should take what BE gives and fill the rest from buffer.
    const result = computePowerHitTrail(
      makeBall({
        isPowerHit: true,
        previousX: 200,
        previousY: 200,
        // previousPreviousX/Y intentionally omitted
      }),
      [
        { x: 10, y: 10 }, // t-2 from FE
        { x: 50, y: 50 }, // t-1 from FE (ignored — BE override)
        { x: 100, y: 100 }, // t
      ],
    )
    expect(result.hyper).toEqual({ x: 200, y: 200 }) // BE
    expect(result.trail).toEqual({ x: 10, y: 10 }) // FE ring buffer t-2
  })
})
