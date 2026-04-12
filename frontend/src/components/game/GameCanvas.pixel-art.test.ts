import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

// Regression test for the sky-sprite RGB vertical stripe bug (Designer report
// 2026-04-12). The fix relies on three pixel-art rendering settings in
// GameCanvas.tsx. Full PixiJS rendering cannot be exercised under jsdom, so
// this test pins the configuration lines as a build-time guard.
//
// If any of these assertions fail, the visual stripe artifact will likely
// return under DPR>1. Do not "fix" the test by deleting assertions — fix the
// rendering code.

const HERE = dirname(fileURLToPath(import.meta.url))
const GAME_CANVAS_PATH = resolve(HERE, 'GameCanvas.tsx')
const SOURCE = readFileSync(GAME_CANVAS_PATH, 'utf8')

describe('GameCanvas pixel-art rendering configuration', () => {
  it('sets global TextureSource scaleMode to nearest before asset load', () => {
    // The atlas must be sampled with NEAREST to prevent edge texel bleed
    // into transparent gutter pixels (root cause of the RGB vertical stripes).
    expect(SOURCE).toMatch(
      /TextureSource\.defaultOptions\.scaleMode\s*=\s*['"]nearest['"]/,
    )
  })

  it('imports TextureSource from pixi.js', () => {
    expect(SOURCE).toMatch(/TextureSource/)
    expect(SOURCE).toMatch(/from ['"]pixi\.js['"]/)
  })

  it('disables antialiasing on Application init', () => {
    // antialias:true under DPR>1 produces sub-pixel texel sampling which
    // re-introduces the stripe artifact even with NEAREST filtering.
    expect(SOURCE).toMatch(/antialias:\s*false/)
    expect(SOURCE).not.toMatch(/antialias:\s*true/)
  })

  it('enables roundPixels on Application init', () => {
    // Snap sprite positions to integer pixels so tiled sprites line up
    // exactly on device pixels regardless of DPR.
    expect(SOURCE).toMatch(/roundPixels:\s*true/)
  })
})
