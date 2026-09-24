import { readFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

import { defineConfig, devices } from '@playwright/test';

// Load .env.test into process.env (no extra dependency needed).
try {
  const envPath = resolve(dirname(fileURLToPath(import.meta.url)), '.env.test');
  for (const line of readFileSync(envPath, 'utf-8').split('\n')) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const eqIndex = trimmed.indexOf('=');
    if (eqIndex > 0) {
      const key = trimmed.slice(0, eqIndex).trim();
      const val = trimmed.slice(eqIndex + 1).trim();
      if (!process.env[key]) process.env[key] = val;
    }
  }
} catch (err: unknown) {
  if ((err as NodeJS.ErrnoException)?.code !== 'ENOENT') {
    console.warn('Failed to parse .env.test:', err);
  }
}

/**
 * Playwright configuration for Flowtuple E2E tests.
 *
 * Env vars (set in .env.test or CI):
 *   BASE_URL          – app URL to test against (default: http://localhost:5173)
 *   TEST_ADMIN_EMAIL  – admin login
 *   TEST_ADMIN_PASSWORD
 */
export default defineConfig({
  testDir: './tests/e2e',

  /* Fail the build on CI if test.only is left in source code. */
  forbidOnly: !!process.env.CI,

  /* Retry once on CI, never locally — flaky tests should be fixed, not masked. */
  retries: process.env.CI ? 1 : 0,

  /* Parallel by default; CI can limit with PLAYWRIGHT_WORKERS env. */
  workers: process.env.CI ? 2 : 3,

  /* Reporter: HTML report always generated; GitHub annotations on CI. */
  reporter: process.env.CI
    ? [['github'], ['html', { open: 'never' }]]
    : 'html',

  use: {
    baseURL: process.env.BASE_URL ?? 'http://localhost:5173',

    /* Capture evidence for every test — screenshots always, trace + video on retry. */
    trace: 'on-first-retry',
    screenshot: 'on',
    video: 'on-first-retry',

    /* Reasonable timeouts. */
    actionTimeout: 10_000,
    navigationTimeout: 15_000,
  },

  /* Browser targets. Start with Chromium only — expand later. */
  projects: [
    /* Shared setup: authenticate and save storage state for each role. */
    {
      name: 'setup',
      testMatch: /global-setup\.ts/,
    },

    /* Default project — runs as admin. RBAC tests override storageState per-describe. */
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        storageState: 'tests/e2e/.auth/admin.json',
      },
      dependencies: ['setup'],
    },
  ],

  /* Start the dev server automatically when running locally. */
  webServer: process.env.CI
    ? undefined
    : {
        command: 'npm run dev',
        url: 'http://localhost:5173',
        reuseExistingServer: true,
        timeout: 30_000,
      },
});
