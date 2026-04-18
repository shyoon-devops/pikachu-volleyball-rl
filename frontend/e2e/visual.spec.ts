import { test, expect, type Page } from '@playwright/test'

/**
 * Visual regression suite for the 1:1 view.js render layer port.
 *
 * Each test hits the `/visual?scene=<name>` harness — a route that
 * renders `<GameCanvas>` with a hand-authored, deterministic game
 * state. No backend, no WebSocket, no clock dependency. The only
 * non-determinism is cloud/wave RNG, which stabilizes within a few
 * frames — we wait long enough for at least one full layout before
 * snapping.
 *
 * Baselines are created on the first successful run (`--update-snapshots`)
 * and committed alongside the spec. Regressions show up as a pixel-
 * diff failure; to accept a legitimate change re-run with
 * `--update-snapshots` locally and commit the new baseline.
 *
 * Scenes:
 *   serve     — idle spawn positions, score 0-0
 *   rally     — both pikachus airborne, ball mid-court
 *   powerhit  — trail + hyper + punch-ring simultaneously visible
 *   gameend   — 15-14 endgame with the overlay still expanding,
 *               winning/losing poses (state 5 / 6)
 *   ready     — beforeStartOfNextRound: half-faded overlay + READY blink
 */

async function gotoScene(page: Page, scene: string): Promise<void> {
  await page.goto(`/visual?scene=${scene}`)
  // The harness is mounted as soon as the router resolves. Wait for
  // the data-scene attribute so we know React has rendered *this*
  // scene (not a stale cache) before snapping.
  await page.waitForSelector(`[data-scene="${scene}"]`)
  // Allow a few frames for Pixi to finish the initial draw + for the
  // cloud/wave RNG to settle — measured ≤ 200ms on local dev.
  await page.waitForTimeout(300)
}

test.describe('GameCanvas visual regression (view.js port)', () => {
  test('serve scene matches baseline', async ({ page }) => {
    await gotoScene(page, 'serve')
    await expect(page.locator('[data-testid="visual-harness"]')).toHaveScreenshot('serve.png')
  })

  test('rally scene matches baseline', async ({ page }) => {
    await gotoScene(page, 'rally')
    await expect(page.locator('[data-testid="visual-harness"]')).toHaveScreenshot('rally.png')
  })

  test('powerhit scene matches baseline (trail + hyper + punch ring)', async ({ page }) => {
    await gotoScene(page, 'powerhit')
    await expect(page.locator('[data-testid="visual-harness"]')).toHaveScreenshot('powerhit.png')
  })

  test('gameend scene matches baseline (expanding overlay, winning/losing poses)', async ({ page }) => {
    await gotoScene(page, 'gameend')
    await expect(page.locator('[data-testid="visual-harness"]')).toHaveScreenshot('gameend.png')
  })

  test('ready scene matches baseline (mid-fade overlay + READY blink)', async ({ page }) => {
    await gotoScene(page, 'ready')
    await expect(page.locator('[data-testid="visual-harness"]')).toHaveScreenshot('ready.png')
  })
})
