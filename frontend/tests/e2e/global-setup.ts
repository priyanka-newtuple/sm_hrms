import { test as setup, expect } from '@playwright/test';

import { getCredentials, loginViaUI } from './helpers/auth';
import { seedBaseline } from './helpers/baseline-seed';

/**
 * Global setup:
 * 1. Authenticates each role and saves storageState.
 * 2. Seeds stable baseline data (entity type, workflow, form) — idempotent.
 */

setup('authenticate as admin', async ({ page }) => {
  const credentials = getCredentials('admin');
  await loginViaUI(page, credentials);
  await expect(page.locator('body')).toBeVisible();
  await page.context().storageState({ path: 'tests/e2e/.auth/admin.json' });
});

setup('authenticate as superadmin', async ({ page }) => {
  const credentials = getCredentials('superadmin');
  await loginViaUI(page, credentials);
  await expect(page.locator('body')).toBeVisible();
  await page.context().storageState({ path: 'tests/e2e/.auth/superadmin.json' });
});

setup('seed baseline data', async () => {
  const baseline = await seedBaseline();
  console.log(`Baseline: entityType=${baseline.entityTypeName}, workflow=${baseline.machineName}`);
});
