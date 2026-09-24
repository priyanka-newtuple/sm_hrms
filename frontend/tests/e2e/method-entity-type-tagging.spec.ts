import { expect, test } from '@playwright/test';

const SHOT = 'test-results/tagging';

// Real UI verification of Method Block ↔ entity type tagging: the Settings
// control writes tags, and the workflow state picker asks the server for only
// the tagged ones.
test.setTimeout(180_000);

test('Method entity-type tags: Settings control writes them, state picker filters on them', async ({
  page,
}) => {
  const listCalls: string[] = [];
  page.on('request', (r) => {
    const url = r.url();
    if (url.includes('/method-library/methods?')) listCalls.push(url);
  });

  // ---- 1. Settings → Methods: the Entity types control exists -------------
  await page.goto('/settings?tab=methods');
  await page.waitForLoadState('networkidle');

  // Pick the first method in the list so an editor panel is on screen.
  const firstMethod = page.locator('button, [role="button"]').filter({ hasText: /^M-\d+/ }).first();
  if (await firstMethod.count()) {
    await firstMethod.click();
    await page.waitForTimeout(1200);
  }

  const tagControl = page.getByTestId('method-entity-types');
  await expect(tagControl).toBeVisible({ timeout: 20000 });
  await page.screenshot({ path: `${SHOT}/1-settings-entity-types-control.png`, fullPage: true });

  // The control must list real entity types, not be an empty shell.
  const boxes = tagControl.locator('input[type="checkbox"]');
  const boxCount = await boxes.count();
  expect(boxCount, 'entity-type checkboxes rendered').toBeGreaterThan(0);

  // ---- 2. Tagging writes through (PATCH + re-read) ------------------------
  const label = tagControl.locator('label').first();
  const labelText = (await label.innerText()).trim();
  const box = label.locator('input[type="checkbox"]');
  const before = await box.isChecked();

  const patch = page.waitForResponse(
    (r) => r.url().includes('/method-library/methods/') && r.request().method() === 'PATCH',
    { timeout: 20000 },
  );
  await box.click();
  const patchResponse = await patch;
  expect(patchResponse.ok(), 'PATCH succeeded').toBeTruthy();
  const patchBody = (await patchResponse.json()) as { entity_types?: string[] };
  // The checkbox state must actually flip, which only happens if the response
  // carried the new tag list back.
  await expect(box).toBeChecked({ checked: !before, timeout: 10000 });
  await page.screenshot({ path: `${SHOT}/2-tag-toggled.png`, fullPage: true });

  // Put it back so the run leaves no trace.
  const restore = page.waitForResponse(
    (r) => r.url().includes('/method-library/methods/') && r.request().method() === 'PATCH',
  );
  await box.click();
  await restore;
  await expect(box).toBeChecked({ checked: before, timeout: 10000 });

  // ---- 3. The state picker asks the server for one entity type -----------
  // A real perkin_request draft. Navigating straight to it keeps the check on
  // the picker's query rather than on the workflow list's markup.
  const DRAFT_ID = '4d778e70-b766-4d18-a201-ab48d9598824';
  listCalls.length = 0;
  await page.goto(`/funnel/${DRAFT_ID}/edit`);
  await page.waitForLoadState('networkidle');

  // The editor opens on Wizard → Basics; the Method Library picker lives on
  // the States step, which is the StagesStep call site.
  await page.getByRole('button', { name: 'States', exact: true }).click();
  await expect(page.getByText('Method Library').first()).toBeVisible({ timeout: 20000 });
  await page.waitForTimeout(2500);

  const filtered = listCalls.filter((u) => u.includes('entity_type='));
  await page.screenshot({ path: `${SHOT}/3-workflow-editor.png`, fullPage: true });

  // The picker must offer only the tagged methods, not the whole library.
  const picker = page.locator('select').filter({ hasText: 'Select method' }).first();
  if (await picker.count()) {
    const optionCount = await picker.locator('option').count();
    // eslint-disable-next-line no-console
    console.log('PICKER OPTIONS (incl. placeholder):', optionCount);
    expect(optionCount, 'picker must not list the entire 79-method library').toBeLessThan(40);
  }

  // eslint-disable-next-line no-console
  console.log('METHOD LIST CALLS:', JSON.stringify(listCalls, null, 2));
  // eslint-disable-next-line no-console
  console.log('PATCH echoed entity_types:', JSON.stringify(patchBody.entity_types));
  // eslint-disable-next-line no-console
  console.log('First tag label:', labelText, '| checkboxes:', boxCount);

  expect(
    filtered.length,
    `state picker must request methods scoped to an entity type; saw: ${JSON.stringify(listCalls)}`,
  ).toBeGreaterThan(0);
});
