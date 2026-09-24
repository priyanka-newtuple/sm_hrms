import { test, expect } from '@playwright/test';

/**
 * Agent editor — save feedback and the Agent Mode assistant's locked fields.
 *
 * Covers FT-0185: the editor used to swallow save failures entirely (no catch
 * on the save handler, no global unhandledrejection handler), so a rejected
 * save looked identical to a broken button.
 */

const AGENT_MODE_NAME = 'Flowtuple AI Agent';

async function openAgentsTab(page: import('@playwright/test').Page) {
  await page.goto('/settings');
  await expect(page.getByPlaceholder(/find a setting/i)).toBeVisible({ timeout: 15_000 });
  await page.getByRole('button', { name: 'Agents', exact: true }).click();
  await expect(page.getByLabel('Breadcrumb')).toBeVisible();
}

async function openAgentModeEditor(page: import('@playwright/test').Page) {
  // Targets the row's icon-only Edit button by its aria-label, which is unique
  // per agent — avoids a positional/`hasText` row locator that would silently
  // drift as the list changes.
  await page.getByRole('button', { name: `Edit ${AGENT_MODE_NAME}` }).click();
  await expect(page.getByRole('heading', { name: `Edit: ${AGENT_MODE_NAME}` })).toBeVisible();
}

test.describe('Agent editor save feedback', () => {
  test('a rejected save shows the error and keeps the modal open @smoke', async ({ page }) => {
    await page.route('**/api/agent/definitions/*', async (route) => {
      if (route.request().method() === 'PATCH') {
        await route.fulfill({
          status: 400,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'Agent could not be saved.' }),
        });
      } else {
        await route.continue();
      }
    });

    await openAgentsTab(page);
    await openAgentModeEditor(page);
    await page.getByRole('button', { name: 'Save Changes' }).click();

    // The message must be rendered...
    await expect(page.getByText('Agent could not be saved.')).toBeVisible();
    // ...inside the still-open modal. If the error were routed to the page-level
    // error state it would replace the whole page and discard the admin's edits,
    // so asserting the Save button survives is the real regression guard.
    await expect(page.getByRole('button', { name: 'Save Changes' })).toBeVisible();
  });

  test('a successful save closes the modal @smoke', async ({ page }) => {
    await page.route('**/api/agent/definitions/*', async (route) => {
      if (route.request().method() === 'PATCH') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            definition_id: 'def-agent-mode',
            name: 'agent_mode',
            display_name: AGENT_MODE_NAME,
            description: null,
            system_prompt: 'You are the built-in assistant.',
            allowed_tools: null,
            constraints: { max_iterations: 12, require_approval: [] },
            suggestions: [],
            model_override: null,
            is_active: true,
            is_system: true,
          }),
        });
      } else {
        await route.continue();
      }
    });

    await openAgentsTab(page);
    await openAgentModeEditor(page);
    await page.getByRole('button', { name: 'Save Changes' }).click();

    await expect(page.getByRole('button', { name: 'Save Changes' })).toBeHidden();
  });
});

test.describe('Agent Mode assistant locked fields', () => {
  test('is editable but its tools and active state are locked @smoke', async ({ page }) => {
    await openAgentsTab(page);
    await openAgentModeEditor(page);

    // The prompt is editable — this is the whole point of FT-0185.
    await expect(page.getByLabel('System Prompt')).toBeEnabled();

    // Tools are granted wholesale by the backend, so the list is read-only
    // rather than a field whose saved value would be silently ignored.
    await expect(page.getByText('All Tools', { exact: true })).toBeVisible();
    await expect(page.getByLabel(/active \(locked for this assistant\)/i)).toBeDisabled();
  });
});
