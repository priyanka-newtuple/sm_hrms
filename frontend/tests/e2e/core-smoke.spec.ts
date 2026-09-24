import { test, expect } from '@playwright/test';

/**
 * Core Smoke Suite — ~25 tests that run safely on any organization/fork.
 *
 * No dependency on seeded data, specific entity types, or workflows.
 * Tests: login, navigation, all settings tabs, display feature toggles.
 */

// ─── Auth ───────────────────────────────────────────────────────────────────

test.describe('Auth', () => {
  test('login page loads with email and password @smoke', async ({ browser }) => {
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    await page.goto('/login');
    await expect(page.getByLabel(/email/i)).toBeVisible();
    await expect(page.locator('#password')).toBeVisible();
    await ctx.close();
  });

  test('login page has Google and Microsoft OAuth @smoke', async ({ browser }) => {
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    await page.goto('/login');
    await expect(page.getByRole('button', { name: /sign in with google/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /sign in with microsoft/i })).toBeVisible();
    await ctx.close();
  });

  test('authenticated user lands on app @smoke', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('navigation')).toBeVisible();
  });
});

// ─── Navigation ─────────────────────────────────────────────────────────────

test.describe('Navigation', () => {
  test('sidebar shows Dashboard, Workflows, Records @smoke', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('button', { name: 'Dashboard', exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Workflows', exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Records', exact: true })).toBeVisible();
  });

  test('dashboard page loads @smoke', async ({ page }) => {
    await page.goto('/dashboard');
    await expect(page.locator('body')).toBeVisible();
  });

  test('workflows page loads @smoke', async ({ page }) => {
    await page.goto('/workflows');
    await expect(page.locator('body')).toBeVisible();
  });

  test('records page loads @smoke', async ({ page }) => {
    await page.goto('/records');
    await expect(page.locator('body')).toBeVisible();
  });

  test('settings page loads @smoke', async ({ page }) => {
    await page.goto('/settings');
    await expect(page.getByPlaceholder(/find a setting/i)).toBeVisible({ timeout: 15_000 });
  });
});

// ─── Settings Tabs ──────────────────────────────────────────────────────────

async function openTab(page: import('@playwright/test').Page, name: string) {
  await page.goto('/settings');
  await expect(page.getByPlaceholder(/find a setting/i)).toBeVisible({ timeout: 15_000 });
  await page.getByRole('button', { name, exact: true }).click();
  await expect(page.getByLabel('Breadcrumb')).toBeVisible();
}

test.describe('Settings Tabs', () => {
  test('Funnels tab loads @smoke', async ({ page }) => { await openTab(page, 'Funnels'); });
  test('Forms tab loads @smoke', async ({ page }) => { await openTab(page, 'Forms'); });
  test('Entities tab loads @smoke', async ({ page }) => { await openTab(page, 'Entities'); });
  test('Agents tab loads @smoke', async ({ page }) => { await openTab(page, 'Agents'); });
  test('Documents tab loads @smoke', async ({ page }) => { await openTab(page, 'Documents'); });
  test('Connectors tab loads @smoke', async ({ page }) => { await openTab(page, 'Connectors'); });
  test('Connectors tab shows the GitHub app with a Connect button @smoke', async ({ page }) => {
    await openTab(page, 'Connectors');
    await expect(page.getByText('GitHub', { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Connect' }).first()).toBeVisible();
  });
  test('Users tab loads @smoke', async ({ page }) => { await openTab(page, 'Users'); });
  test('Roles tab loads @smoke', async ({ page }) => { await openTab(page, 'Roles'); });
  test('Display tab loads @smoke', async ({ page }) => { await openTab(page, 'Display'); });
  test('MCP Tools tab loads @smoke', async ({ page }) => {
    await openTab(page, 'MCP Tools');
    await expect(page.getByRole('heading', { name: 'MCP Servers & Tools' })).toBeVisible();
  });
});

// ─── Remote MCP connect — error paths ──────────────────────────────────────

test.describe('Remote MCP connect — error paths', () => {
  const GITHUB_SERVER: Record<string, unknown> = {
    id: 'srv_test_github',
    name: 'GitHub',
    server_url: 'https://api.githubcopilot.com/mcp',
    auth_type: 'oauth2',
    status: 'connected',
    is_enabled: true,
    requires_authorization: false,
    tool_count: 12,
    secret_hints: {},
    token_expires_at: null,
    last_error: null,
    last_discovered_at: null,
    auth_config: { preset: 'github' },
  };

  test('OAuth callback with ?error= shows the Connection failed screen @smoke', async ({ page }) => {
    await page.goto('/auth/remote-mcp/callback?error=access_denied');
    await expect(page.getByRole('heading', { name: 'Connection failed' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Back to Connectors' })).toBeVisible();
  });

  test('OAuth callback with no code/state redirects back to Connectors @smoke', async ({ page }) => {
    await page.goto('/auth/remote-mcp/callback');
    await page.waitForURL(/\/settings\?tab=connectors/);
    await expect(page.getByPlaceholder(/find a setting/i)).toBeVisible({ timeout: 15_000 });
  });

  test('Disconnect shows an error toast when it fails @smoke', async ({ page }) => {
    await page.route('**/api/remote-mcp/servers', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ items: [GITHUB_SERVER], total: 1 }),
        });
      } else {
        await route.continue();
      }
    });
    await page.route('**/api/remote-mcp/servers/srv_test_github', async (route) => {
      if (route.request().method() === 'DELETE') {
        await route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'Could not disconnect GitHub.' }),
        });
      } else {
        await route.continue();
      }
    });

    await openTab(page, 'Connectors');
    await page.getByRole('button', { name: 'Disconnect' }).click();
    await expect(page.getByText('Could not disconnect GitHub.')).toBeVisible();
  });
});

// ─── Display Feature Toggles ────────────────────────────────────────────────

test.describe('Display Feature Toggles', () => {
  test.use({ storageState: 'tests/e2e/.auth/superadmin.json' });

  async function goToDisplay(page: import('@playwright/test').Page) {
    await page.goto('/settings');
    await expect(page.getByPlaceholder(/find a setting/i)).toBeVisible({ timeout: 15_000 });
    await page.getByRole('button', { name: 'Display', exact: true }).click();
    await expect(page.getByLabel('Breadcrumb')).toBeVisible();
  }

  test('Display page shows feature flag toggles @critical', async ({ page }) => {
    await goToDisplay(page);
    await expect(page.getByRole('switch', { name: /show kanban board/i })).toBeVisible();
    await expect(page.getByRole('switch', { name: /show dashboard/i })).toBeVisible();
    await expect(page.getByRole('switch', { name: /show due date/i })).toBeVisible();
  });

  test('Display page has Save button @critical', async ({ page }) => {
    await goToDisplay(page);
    await expect(page.getByRole('button', { name: /save/i }).first()).toBeVisible({ timeout: 5000 });
  });

  test('toggling Kanban board OFF hides Board tab on pipeline @critical', async ({ page }) => {
    await goToDisplay(page);
    const toggle = page.getByRole('switch', { name: /show kanban board/i });

    // Turn OFF if currently ON
    if ((await toggle.getAttribute('aria-checked')) === 'true') {
      await toggle.click();
      await page.getByRole('button', { name: /save/i }).first().click();
      await page.waitForTimeout(1000);
    }

    // Verify on pipeline — Board tab should be hidden
    await page.goto('/workflows');
    await expect(page.getByRole('button', { name: /E2E Baseline Workflow/i }).first()).toBeVisible({ timeout: 10_000 });
    await page.getByRole('button', { name: /E2E Baseline Workflow/i }).first().click();
    await page.waitForTimeout(1000);
    // Only Table/List visible, no Board tab
    await expect(page.getByRole('tab', { name: 'Table' })).toBeVisible({ timeout: 5000 });
    await expect(page.getByRole('tab', { name: 'Board' })).toBeHidden();

    // REVERT — turn back ON
    await goToDisplay(page);
    const revert = page.getByRole('switch', { name: /show kanban board/i });
    if ((await revert.getAttribute('aria-checked')) === 'false') {
      await revert.click();
      await page.getByRole('button', { name: /save/i }).first().click();
    }
  });

  test('toggling Kanban board ON shows Board tab on pipeline @critical', async ({ page }) => {
    await goToDisplay(page);
    const toggle = page.getByRole('switch', { name: /show kanban board/i });

    // Turn ON if currently OFF
    if ((await toggle.getAttribute('aria-checked')) === 'false') {
      await toggle.click();
      await page.getByRole('button', { name: /save/i }).first().click();
      await page.waitForTimeout(1000);
    }

    // Verify on pipeline — Board tab should be visible
    await page.goto('/workflows');
    await expect(page.getByRole('button', { name: /E2E Baseline Workflow/i }).first()).toBeVisible({ timeout: 10_000 });
    await page.getByRole('button', { name: /E2E Baseline Workflow/i }).first().click();
    await page.waitForTimeout(1000);
    await expect(page.getByRole('tab', { name: 'Table' })).toBeVisible({ timeout: 5000 });
    await expect(page.getByRole('tab', { name: 'Board' })).toBeVisible();
  });

  test('toggling Dashboard OFF hides it from sidebar @critical', async ({ page }) => {
    await goToDisplay(page);
    const toggle = page.getByRole('switch', { name: /show dashboard/i });

    // Turn OFF
    if ((await toggle.getAttribute('aria-checked')) === 'true') {
      await toggle.click();
      await page.getByRole('button', { name: /save/i }).first().click();
      await page.waitForTimeout(1000);
    }

    // Verify sidebar — Dashboard hidden
    await page.goto('/');
    await expect(page.getByRole('button', { name: 'Dashboard', exact: true })).toBeHidden({ timeout: 5000 });

    // REVERT
    await goToDisplay(page);
    const revert = page.getByRole('switch', { name: /show dashboard/i });
    if ((await revert.getAttribute('aria-checked')) === 'false') {
      await revert.click();
      await page.getByRole('button', { name: /save/i }).first().click();
    }
  });

  test('toggling Due date OFF hides it in entity creation @critical', async ({ page }) => {
    await goToDisplay(page);
    const toggle = page.getByRole('switch', { name: /show due date/i });

    // Turn OFF
    if ((await toggle.getAttribute('aria-checked')) === 'true') {
      await toggle.click();
      await page.getByRole('button', { name: /save/i }).first().click();
      await page.waitForTimeout(1000);
    }

    // Verify in add entity dialog — "Due date" hidden
    await page.goto('/workflows');
    await expect(page.getByRole('button', { name: /E2E Baseline Workflow/i }).first()).toBeVisible({ timeout: 10_000 });
    await page.getByRole('button', { name: /E2E Baseline Workflow/i }).first().click();
    await expect(page.getByRole('button', { name: /add e2ebaseline/i })).toBeVisible({ timeout: 10_000 });
    await page.getByRole('button', { name: /add e2ebaseline/i }).click();
    await expect(page.getByText('Due date')).toBeHidden({ timeout: 3000 });
    await page.getByRole('button', { name: 'Cancel', exact: true }).click();

    // REVERT
    await goToDisplay(page);
    const revert = page.getByRole('switch', { name: /show due date/i });
    if ((await revert.getAttribute('aria-checked')) === 'false') {
      await revert.click();
      await page.getByRole('button', { name: /save/i }).first().click();
    }
  });
});
