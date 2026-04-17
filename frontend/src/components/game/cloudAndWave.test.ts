import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import {
  Cloud,
  Wave,
  cloudAndWaveEngine,
  NUM_OF_CLOUDS,
} from './cloudAndWave'

// The port uses Math.random() via rand(). Stub it with a deterministic
// sequence so state transitions are reproducible without freezing the
// module-level generator.
function stubRandom(values: number[]): void {
  let i = 0
  vi.spyOn(Math, 'random').mockImplementation(() => {
    const v = values[i % values.length] ?? 0
    i += 1
    return v
  })
}

describe('Cloud', () => {
  beforeEach(() => {
    // Value chosen so `rand() = floor(32768 * 0.5) = 16384` keeps every
    // modulo result predictable (e.g. 16384 % 11 = 5, 16384 % 152 = 72).
    stubRandom([0.5])
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('constructs with deterministic bounds (with stubbed rand)', () => {
    const c = new Cloud()
    expect(c.topLeftPointX).toBe(-68 + (16384 % (432 + 68)))
    expect(c.topLeftPointY).toBe(16384 % 152)
    expect(c.topLeftPointXVelocity).toBe(1 + (16384 % 2))
    expect(c.sizeDiffTurnNumber).toBe(16384 % 11)
  })

  it('sizeDiff is a triangle wave 0→5→0 across the 11 turn numbers', () => {
    // Mirror cloud_and_wave.js:24 — `[0,1,2,3,4,5,4,3,2,1,0][n]`.
    const expected = [0, 1, 2, 3, 4, 5, 4, 3, 2, 1, 0]
    const c = new Cloud()
    for (let n = 0; n < expected.length; n++) {
      c.sizeDiffTurnNumber = n
      expect(c.sizeDiff).toBe(expected[n])
    }
  })

  it('spriteTopLeftPoint anchors are shifted by -sizeDiff (so growth centers visually)', () => {
    const c = new Cloud()
    c.topLeftPointX = 100
    c.topLeftPointY = 50
    c.sizeDiffTurnNumber = 5 // peak, sizeDiff = 5
    expect(c.spriteTopLeftPointX).toBe(95)
    expect(c.spriteTopLeftPointY).toBe(45)
    expect(c.spriteWidth).toBe(58) // 48 + 2*5
    expect(c.spriteHeight).toBe(34) // 24 + 2*5
  })
})

describe('Wave', () => {
  it('initializes with 27 tiles at y=314 and 2 px/frame velocity', () => {
    const w = new Wave()
    expect(w.verticalCoord).toBe(0)
    expect(w.verticalCoordVelocity).toBe(2)
    expect(w.yCoords).toHaveLength(27) // 432 / 16
    expect(w.yCoords.every((y) => y === 314)).toBe(true)
  })
})

describe('cloudAndWaveEngine', () => {
  beforeEach(() => {
    stubRandom([0.5])
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('advances each cloud by its xVelocity', () => {
    const clouds = [new Cloud()]
    // Force the remaining slots so NUM_OF_CLOUDS iterations are safe —
    // the engine loops 10 times regardless of array length, so we
    // pre-fill to avoid undefined reads during the tick.
    while (clouds.length < NUM_OF_CLOUDS) clouds.push(new Cloud())
    const c = clouds[0]
    c.topLeftPointX = 100
    c.topLeftPointXVelocity = 2
    const wave = new Wave()
    cloudAndWaveEngine(clouds, wave)
    expect(c.topLeftPointX).toBe(102)
  })

  it('respawns a cloud at x=-68 when it drifts past the right edge', () => {
    const clouds: Cloud[] = []
    while (clouds.length < NUM_OF_CLOUDS) clouds.push(new Cloud())
    const c = clouds[0]
    c.topLeftPointX = 500 // past 432
    c.topLeftPointXVelocity = 1
    const wave = new Wave()
    cloudAndWaveEngine(clouds, wave)
    expect(c.topLeftPointX).toBe(-68)
  })

  it('advances sizeDiffTurnNumber modulo 11 (triangle wave cycle)', () => {
    const clouds: Cloud[] = []
    while (clouds.length < NUM_OF_CLOUDS) clouds.push(new Cloud())
    const c = clouds[0]
    c.sizeDiffTurnNumber = 10
    cloudAndWaveEngine(clouds, new Wave())
    expect(c.sizeDiffTurnNumber).toBe(0)
  })

  it('inverts wave velocity at the top of its arc (verticalCoord > 32)', () => {
    const w = new Wave()
    w.verticalCoord = 31
    w.verticalCoordVelocity = 2
    const clouds: Cloud[] = []
    while (clouds.length < NUM_OF_CLOUDS) clouds.push(new Cloud())
    cloudAndWaveEngine(clouds, w)
    // 31 + 2 = 33 → clamps to 32, velocity flips to -1
    expect(w.verticalCoord).toBe(32)
    expect(w.verticalCoordVelocity).toBe(-1)
  })

  it('resets wave with a random negative offset at the bottom (verticalCoord < 0, vel < 0)', () => {
    const w = new Wave()
    w.verticalCoord = -1
    w.verticalCoordVelocity = -1
    const clouds: Cloud[] = []
    while (clouds.length < NUM_OF_CLOUDS) clouds.push(new Cloud())
    cloudAndWaveEngine(clouds, w)
    // velocity flips back to 2, verticalCoord = -(rand() % 40)
    expect(w.verticalCoordVelocity).toBe(2)
    expect(w.verticalCoord).toBeLessThanOrEqual(0)
    expect(w.verticalCoord).toBeGreaterThan(-40)
  })

  it('recomputes yCoords from verticalCoord every tick (all 27 tiles)', () => {
    const w = new Wave()
    w.verticalCoord = 10
    w.verticalCoordVelocity = 2
    const clouds: Cloud[] = []
    while (clouds.length < NUM_OF_CLOUDS) clouds.push(new Cloud())
    cloudAndWaveEngine(clouds, w)
    // After tick: verticalCoord = 12, yCoords[i] = 314 - 12 + (rand() % 3)
    // Stubbed rand → 16384, 16384 % 3 = 1 → yCoords[i] = 303
    expect(w.yCoords.length).toBe(27)
    for (const y of w.yCoords) {
      expect(y).toBeGreaterThanOrEqual(302)
      expect(y).toBeLessThanOrEqual(304)
    }
  })
})
