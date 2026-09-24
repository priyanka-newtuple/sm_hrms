import { type Page, expect } from '@playwright/test';

/**
 * Log in via the UI login form and wait for the dashboard to load.
 *
 * Uses environment variables for credentials — never hardcode secrets.
 *   TEST_ADMIN_EMAIL / TEST_ADMIN_PASSWORD     – admin role
 *   TEST_RECRUITER_EMAIL / TEST_RECRUITER_PASSWORD – recruiter role
 *   TEST_VIEWER_EMAIL / TEST_VIEWER_PASSWORD   – viewer role
 */

export interface TestCredentials {
  email: string;
  password: string;
}

export type TestRole = 'admin' | 'superadmin' | 'recruiter' | 'viewer';

export function getCredentials(role: TestRole): TestCredentials {
  const prefix = `TEST_${role.toUpperCase()}`;
  const email = process.env[`${prefix}_EMAIL`];
  const password = process.env[`${prefix}_PASSWORD`];

  if (!email || !password) {
    throw new Error(
      `Missing env vars: ${prefix}_EMAIL and ${prefix}_PASSWORD must be set. ` +
      `Copy .env.test.example to .env.test and fill in credentials.`,
    );
  }

  return { email, password };
}

/**
 * Perform a UI login. After this, the page should be on the authenticated dashboard.
 */
export async function loginViaUI(page: Page, credentials: TestCredentials): Promise<void> {
  await page.goto('/login');

  await page.getByLabel(/email/i).fill(credentials.email);
  await page.locator('#password').fill(credentials.password);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();

  // Wait for redirect away from login — dashboard or any authenticated page
  await expect(page).not.toHaveURL(/\/login/, { timeout: 15_000 });
}
