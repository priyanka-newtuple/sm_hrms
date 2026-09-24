/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// Mirrors vite.config.ts: components importing the skin registry need this
// alias too, or vitest fails to resolve it. No private skins in tests.
const customerSkinsPath = process.env.CUSTOMER_SKINS_PATH
  ? path.resolve(process.env.CUSTOMER_SKINS_PATH)
  : path.resolve(__dirname, './src/skins/customer-skins.stub.ts')

/**
 * Unit/component tests only. Playwright owns end-to-end (`npm run test:e2e`);
 * `include` is deliberately narrow so the two never collect each other's
 * specs — Playwright's live under `tests/e2e`, these live beside their source.
 */
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      '@customer-skins': customerSkinsPath,
    },
  },
  test: {
    environment: 'jsdom',
    globals: false,
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    restoreMocks: true,
  },
})
