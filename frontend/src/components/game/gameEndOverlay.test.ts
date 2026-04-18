import { describe, it, expect } from 'vitest'
import { computeGameEndOverlay } from './gameEndOverlay'

// The original game_end.png sprite is 144×32. We use those exact
// dimensions so the assertions read the same as view.js would.
const W = 144
const H = 32

describe('computeGameEndOverlay', () => {
  it('is invisible while the match is still live', () => {
    const result = computeGameEndOverlay({
      isGameEnded: false,
      frameCounter: 0,
      textureWidth: W,
      textureHeight: H,
    })
    expect(result.visible).toBe(false)
  })

  it('enters the intro phase at frame 0 — oversized, centered', () => {
    // At frameCounter=0, halfWidthIncrement = 2 * floor((50 * 144) / 50) = 288
    // width = 144 + 2*288 = 720, x = 216 - 72 - 288 = -144.
    const result = computeGameEndOverlay({
      isGameEnded: true,
      frameCounter: 0,
      textureWidth: W,
      textureHeight: H,
    })
    expect(result.visible).toBe(true)
    expect(result.width).toBe(720)
    expect(result.x).toBe(-144)
    expect(result.height).toBe(32 + 2 * 64) // halfHeightIncrement = 64
    expect(result.y).toBe(50 - 64)
  })

  it('shrinks each frame through the 50-frame intro (monotonic)', () => {
    // Sanity check: width at frame=0 > frame=25 > frame=49.
    const w0 = computeGameEndOverlay({
      isGameEnded: true,
      frameCounter: 0,
      textureWidth: W,
      textureHeight: H,
    }).width
    const w25 = computeGameEndOverlay({
      isGameEnded: true,
      frameCounter: 25,
      textureWidth: W,
      textureHeight: H,
    }).width
    const w49 = computeGameEndOverlay({
      isGameEnded: true,
      frameCounter: 49,
      textureWidth: W,
      textureHeight: H,
    }).width
    expect(w0).toBeGreaterThan(w25)
    expect(w25).toBeGreaterThan(w49)
  })

  it('holds at natural size from frame 50 through frame 210', () => {
    for (const f of [50, 100, 150, 210]) {
      const result = computeGameEndOverlay({
        isGameEnded: true,
        frameCounter: f,
        textureWidth: W,
        textureHeight: H,
      })
      expect(result.visible).toBe(true)
      expect(result.width).toBe(W)
      expect(result.height).toBe(H)
      expect(result.x).toBe(216 - W / 2)
      expect(result.y).toBe(50)
    }
  })

  it('still produces a valid frame past the 211-frame window (defensive)', () => {
    // BE caps at 210 but the FE stays tolerant — any frameCounter ≥ 50
    // draws at natural size. No negative widths, no NaN.
    const result = computeGameEndOverlay({
      isGameEnded: true,
      frameCounter: 9999,
      textureWidth: W,
      textureHeight: H,
    })
    expect(result.visible).toBe(true)
    expect(result.width).toBe(W)
    expect(result.height).toBe(H)
  })
})
