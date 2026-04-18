import { describe, it, expect } from 'vitest'
import { computePunchEffect } from './punchEffect'
import type { BallState } from '../../lib/types'

function makeBall(overrides: Partial<BallState> = {}): BallState {
  return {
    x: 216,
    y: 200,
    vx: 0,
    vy: 0,
    rotation: 0,
    ...overrides,
  }
}

describe('computePunchEffect', () => {
  it('is invisible when punchEffectRadius is undefined (pre-port payload)', () => {
    expect(computePunchEffect(makeBall()).visible).toBe(false)
  })

  it('is invisible when radius is 0 (effect finished / never started)', () => {
    expect(
      computePunchEffect(makeBall({ punchEffectRadius: 0 })).visible,
    ).toBe(false)
  })

  it('is invisible when radius is negative (defensive — should never happen engine-side)', () => {
    // Engine clamps to 0 (engine.py:304-306) but we defend here because
    // it's cheap and prevents a backwards "growing" sprite if a bug ships.
    expect(
      computePunchEffect(makeBall({ punchEffectRadius: -2 })).visible,
    ).toBe(false)
  })

  it('renders a 2*radius sprite centered on punchEffect coords (view.js:504-506)', () => {
    const result = computePunchEffect(
      makeBall({
        punchEffectX: 120,
        punchEffectY: 90,
        punchEffectRadius: 20,
      }),
    )
    expect(result).toEqual({
      visible: true,
      x: 120,
      y: 90,
      width: 40,
      height: 40,
    })
  })

  it('shrinks proportionally as BE decays radius (2px/frame in engine)', () => {
    // Simulates four consecutive frames after impact — the FE just
    // reflects what BE sends; no client-side animation.
    const frames = [20, 18, 16, 14].map((r) =>
      computePunchEffect(
        makeBall({
          punchEffectX: 100,
          punchEffectY: 100,
          punchEffectRadius: r,
        }),
      ),
    )
    expect(frames.map((f) => f.width)).toEqual([40, 36, 32, 28])
    expect(frames.every((f) => f.visible)).toBe(true)
  })

  it('falls back to ball x/y when punch coords are omitted', () => {
    const result = computePunchEffect(
      makeBall({ x: 250, y: 150, punchEffectRadius: 10 }),
    )
    // No crash, no (0, 0) spawn — sprite appears at ball's current
    // position. Acceptable one-frame artifact for incomplete payloads.
    expect(result.x).toBe(250)
    expect(result.y).toBe(150)
    expect(result.width).toBe(20)
  })
})
