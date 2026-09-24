import { expect, test } from '@playwright/test';

import { getPageToken } from './helpers/api-fixtures';

const BACKEND_URL = process.env.VITE_DEV_PROXY_TARGET ?? 'http://localhost:8001';

/**
 * Role → Forms tab must offer Method-Block entity_schema fields for a
 * Form-less type (request → request_flow_name via a "Workflow fields" card)
 * while a Forms-based type (perkin_client) keeps its exact Form card.
 */
const SHOT = 'test-results/role-forms-tab';

test.setTimeout(180_000);

test('role Forms tab lists Method-Block fields and keeps Form fields unchanged', async ({ page, request }) => {
  await page.goto('/settings?tab=roles');
  const token = await getPageToken(page);
  const suffix = `${Date.now()}`;
  const created = await request.fetch(`${BACKEND_URL}/v1/api/roles`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    data: {
      name: `mb_forms_tab_probe_${suffix}`,
      display_name: `MB FormsTab Probe ${suffix}`,
      entity_permissions: [{ entity_type: 'request', action: 'view', allowed: true }],
    },
  });
  expect(created.ok()).toBeTruthy();
  const roleId = ((await created.json()) as { id: string }).id;

  try {
  await page.reload();
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1500);

  await page.getByText(`MB FormsTab Probe ${suffix}`, { exact: true }).first().click();
  await page.waitForTimeout(1000);
  // Two "Forms" buttons exist (settings sidebar + role tab bar) — take the tab bar's.
  await page.getByRole('button', { name: 'Forms', exact: true }).last().click();
  await page.waitForTimeout(2000);

  // MB-only entity type: request
  await page.getByRole('button', { name: /^request\b/ }).first().click();
  await page.waitForTimeout(1500);
  const bodyText = await page.locator('body').innerText();
  await page.screenshot({ path: `${SHOT}/1-request-mb-fields.png`, fullPage: true });
  /* eslint-disable no-console */
  console.log('REQUEST tab shows request_flow_name:', bodyText.includes('request_flow_name'));
  console.log('REQUEST tab shows Workflow fields card:', bodyText.includes('Workflow fields'));
  console.log('REQUEST tab shows old empty message:', bodyText.includes('No forms configured'));
  /* eslint-enable no-console */
  expect(bodyText).toContain('request_flow_name');
  expect(bodyText).toContain('Workflow fields');

  // Forms-based regression: perkin_client
  await page.getByRole('button', { name: /^perkin_client\b/ }).first().click();
  await page.waitForTimeout(1500);
  const clientText = await page.locator('body').innerText();
  await page.screenshot({ path: `${SHOT}/2-perkin-client-form.png`, fullPage: true });
  /* eslint-disable no-console */
  console.log('PERKIN_CLIENT shows Client form:', clientText.includes('Client'));
  console.log('PERKIN_CLIENT shows synthetic card:', clientText.includes('Workflow fields'));
  /* eslint-enable no-console */
  expect(clientText).not.toContain('Workflow fields');
  } finally {
    await request.fetch(`${BACKEND_URL}/v1/api/roles/${roleId}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${token}` },
    }).catch(() => {});
  }
});
