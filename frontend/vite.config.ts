/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws': { target: 'ws://localhost:8000', ws: true },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test-setup.ts',
    // Playwright specs live under ./e2e and must not be picked up by
    // Vitest — they import from `@playwright/test` which doesn't work
    // under jsdom. Keep Vitest's default include pattern and just add
    // e2e to the exclude list.
    exclude: ['**/node_modules/**', '**/dist/**', 'e2e/**'],
  },
})
