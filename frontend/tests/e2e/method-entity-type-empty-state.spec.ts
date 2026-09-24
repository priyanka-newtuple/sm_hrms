import { expect, test } from '@playwright/test';

// perkin_site is a registered entity type with no methods tagged for it, so its
// state picker must say so and point at Settings rather than silently showing
// an empty dropdown.
const EMPTY_WORKFLOW_ID = '98e634b5-7cd4-46f9-b22d-144289c19e66';

test.setTimeout(120_000);

test('a state picker for an entity type with no tagged methods explains why it is empty', async ({
  page,
}) => {
  const listCalls: string[] = [];
  page.on('request', (r) => {
    if (r.url().includes('/method-library/methods?')) listCalls.push(r.url());
  });

  await page.goto(`/funnel/${EMPTY_WORKFLOW_ID}/edit`);
  await page.waitForLoadState('networkidle');
  await page.getByRole('button', { name: 'States', exact: true }).click();
  await expect(page.getByText('Method Library').first()).toBeVisible({ timeout: 20000 });
  await page.waitForTimeout(2000);

  const emptyNote = page.getByText(/No methods are tagged for/i).first();
  await expect(emptyNote).toBeVisible({ timeout: 15000 });
  await expect(page.getByRole('link', { name: /Settings → Methods/ }).first()).toBeVisible();
  // It sits below the States panel's inner scroll fold, so bring it on screen
  // before capturing — otherwise the screenshot shows everything but the point.
  await emptyNote.scrollIntoViewIfNeeded();
  await page.waitForTimeout(500);
  await page.screenshot({ path: 'test-results/tagging/4-empty-state.png' });

  // eslint-disable-next-line no-console
  console.log('EMPTY-STATE LIST CALLS:', JSON.stringify(listCalls, null, 2));
  expect(listCalls.some((u) => u.includes('entity_type=perkin_site'))).toBeTruthy();
});
