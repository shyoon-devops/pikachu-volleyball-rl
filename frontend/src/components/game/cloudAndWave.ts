/**
 * 1:1 port of `cloud_and_wave.js` from the original pikachu-volleyball
 * (gorisanson/pikachu-volleyball, MIT). The module models the cloud
 * drift across the sky and the wave line at the bottom of the court.
 *
 * Kept as a separate module (instead of inlined in `GameCanvas.tsx`)
 * so the state-transition functions stay unit-testable without a
 * PixiJS stage, matching the pattern of `powerHitTrail.ts` and
 * `punchEffect.ts`.
 *
 * Original files referenced by line number below:
 *   - cloud_and_wave.js (Cloud, Wave, cloudAndWaveEngine)
 *   - rand.js           (rand() — 15-bit integer RNG)
 */

/** Number of clouds in the sky — matches view.js NUM_OF_CLOUDS. */
export const NUM_OF_CLOUDS = 10
/** Court width in pixels (original engine constant). */
const GROUND_WIDTH = 432
/** Wave tile width in pixels (16 wide × 27 tiles = 432). */
const WAVE_TILE_WIDTH = 16
const WAVE_TILE_COUNT = GROUND_WIDTH / WAVE_TILE_WIDTH // 27

/**
 * Port of `rand.js::rand()`. Returns an integer in [0, 32767]. The
 * original used VS2017's `rand()` to match the reverse-engineered
 * assembly; we delegate to `Math.random()` because FE visuals don't
 * need bit-exact determinism (replays are driven by BE frames, not
 * FE RNG).
 */
function rand(): number {
  return Math.floor(32768 * Math.random())
}

/**
 * Port of `cloud_and_wave.js::Cloud`. A cloud drifts right at
 * 1-2 px/frame and cycles through a sawtooth size pattern so it
 * appears to pulse as it moves.
 */
export class Cloud {
  topLeftPointX: number
  topLeftPointY: number
  topLeftPointXVelocity: number
  sizeDiffTurnNumber: number

  constructor() {
    // Spawn anywhere across an extended horizontal range so clouds are
    // already mid-screen at boot (prevents a blank sky on first frame).
    this.topLeftPointX = -68 + (rand() % (GROUND_WIDTH + 68))
    this.topLeftPointY = rand() % 152
    this.topLeftPointXVelocity = 1 + (rand() % 2)
    this.sizeDiffTurnNumber = rand() % 11
  }

  /**
   * Triangle wave 0→5→0 over 11 steps — same as
   *   `[0,1,2,3,4,5,4,3,2,1,0][sizeDiffTurnNumber]`.
   */
  get sizeDiff(): number {
    return 5 - Math.abs(this.sizeDiffTurnNumber - 5)
  }

  get spriteTopLeftPointX(): number {
    return this.topLeftPointX - this.sizeDiff
  }

  get spriteTopLeftPointY(): number {
    return this.topLeftPointY - this.sizeDiff
  }

  get spriteWidth(): number {
    return 48 + 2 * this.sizeDiff
  }

  get spriteHeight(): number {
    return 24 + 2 * this.sizeDiff
  }
}

/**
 * Port of `cloud_and_wave.js::Wave`. Tracks one oscillating vertical
 * offset plus per-tile y-coords, which view.js assigns to 27 wave
 * sprites across the bottom of the court.
 */
export class Wave {
  verticalCoord: number
  verticalCoordVelocity: number
  yCoords: number[]

  constructor() {
    this.verticalCoord = 0
    this.verticalCoordVelocity = 2
    this.yCoords = new Array(WAVE_TILE_COUNT).fill(314)
  }
}

/**
 * FUN_00404770 — moves clouds + wave one tick.
 *
 * 1:1 port of cloud_and_wave.js:65-89. Mutates in place (same as the
 * original) because callers hold references to the same instances
 * across frames — allocating a fresh array per tick would be wasteful
 * for a 60fps loop.
 */
export function cloudAndWaveEngine(cloudArray: Cloud[], wave: Wave): void {
  for (let i = 0; i < NUM_OF_CLOUDS; i++) {
    const c = cloudArray[i]
    if (!c) continue
    c.topLeftPointX += c.topLeftPointXVelocity
    if (c.topLeftPointX > GROUND_WIDTH) {
      c.topLeftPointX = -68
      c.topLeftPointY = rand() % 152
      c.topLeftPointXVelocity = 1 + (rand() % 2)
    }
    c.sizeDiffTurnNumber = (c.sizeDiffTurnNumber + 1) % 11
  }

  wave.verticalCoord += wave.verticalCoordVelocity
  if (wave.verticalCoord > 32) {
    wave.verticalCoord = 32
    wave.verticalCoordVelocity = -1
  } else if (wave.verticalCoord < 0 && wave.verticalCoordVelocity < 0) {
    wave.verticalCoordVelocity = 2
    wave.verticalCoord = -(rand() % 40)
  }

  for (let i = 0; i < WAVE_TILE_COUNT; i++) {
    wave.yCoords[i] = 314 - wave.verticalCoord + (rand() % 3)
  }
}
