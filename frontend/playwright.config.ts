import { defineConfig, devices } from '@playwright/test'

/**
 * Playwright visual regression config.
 *
 * Runs against the Vite dev server (`npm run dev`, port 5173). The
 * WebServer block lets CI boot the dev server automatically — on a
 * local machine you can skip it by exporting `PLAYWRIGHT_BASE_URL`
 * to point at an already-running instance.
 *
 * Snapshots land next to each spec under `__snapshots__/<spec>/`
 * with a per-browser suffix. The visual diff threshold is tight
 * (0.02) because the canvas is integer-pixel aligned — anything
 * larger than a few hundred pixels signals an actual rendering
 * regression, not a font or anti-alias drift.
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: 'html',
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? 'http://localhost:5173',
    trace: 'on-first-retry',
  },
  expect: {
    toHaveScreenshot: {
      // Allow ≤0.2% pixel delta — tight enough to catch sprite
      // reshuffles but loose enough to survive GPU driver noise.
      maxDiffPixelRatio: 0.002,
    },
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        // Force a fixed viewport so the canvas CSS scale is stable
        // across platforms. The harness renders at its native 432×304.
        viewport: { width: 640, height: 420 },
        deviceScaleFactor: 1,
      },
    },
  ],
  webServer: process.env.PLAYWRIGHT_BASE_URL
    ? undefined
    : {
        command: 'npm run dev',
        url: 'http://localhost:5173',
        reuseExistingServer: !process.env.CI,
        timeout: 60_000,
      },
})
