import { expect, test } from '@playwright/test';

/**
 * Closes two evidence gaps:
 *  1. A pre-existing pinned Method Block on a *different* entity type than the
 *     earlier perkin_request check still resolves after the backfill.
 *  2. `entity_type` threading is exercised independently at BOTH call sites —
 *     StagesStep (Wizard) and StateInspector (Canvas) — with each view's own
 *     captured requests, so neither is inferred from the other.
 */

// final_entity draft with two states, each carrying a method pinned before the
// migration: INITIAL → "Final Method" (M-158), MIDDLE STATE → "Middle Method".
const WORKFLOW_ID = '29095d59-90f1-4ea2-9800-a3630dc95592';
const ENTITY_TYPE = 'final_entity';
const SHOT = 'test-results/callsites';

test.setTimeout(240_000);

test('entity_type threading at both call sites, and a pre-existing final_entity pin still resolves', async ({
  page,
}) => {
  let calls: string[] = [];
  page.on('request', (r) => {
    const url = r.url();
    if (url.includes('/method-library/methods?')) calls.push(url);
  });

  const methodPickerOptions = async () => {
    const picker = page.locator('select').filter({ hasText: 'Select method' }).first();
    await expect(picker).toBeVisible({ timeout: 20000 });
    return picker.locator('option').allInnerTexts();
  };

  // ─── Call site A: Wizard → StagesStep.tsx:291 ────────────────────────────
  calls = [];
  await page.goto(`/funnel/${WORKFLOW_ID}/edit?view=wizard`);
  await page.waitForLoadState('networkidle');
  await page.getByRole('button', { name: 'States', exact: true }).click();
  await expect(page.getByText('Method Library').first()).toBeVisible({ timeout: 20000 });
  await page.waitForTimeout(2500);

  const wizardCalls = [...calls];
  const wizardOptions = await methodPickerOptions();
  // The pre-existing pin renders by name, which is only possible if the
  // backfill tagged it for this entity type.
  const wizardPinned = page.getByText('Final Method', { exact: true }).first();
  await expect(wizardPinned).toBeVisible({ timeout: 15000 });
  await wizardPinned.scrollIntoViewIfNeeded();
  await page.screenshot({ path: `${SHOT}/A-wizard-stagesstep.png` });

  // ─── Call site B: Canvas → StateInspector.tsx:272 ────────────────────────
  calls = [];
  await page.goto(`/funnel/${WORKFLOW_ID}/edit?view=canvas`);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(2000);

  // Open the same INITIAL state the Wizard leg looked at, so the two views are
  // compared like for like. The canvas draws custom nodes, not react-flow ones,
  // so the node is addressed by its label inside the canvas surface.
  const node = page.locator('.canvas-grid').getByText('INITIAL', { exact: true }).first();
  await expect(node).toBeVisible({ timeout: 20000 });
  // Hovering reveals the node's own controls; "Edit state" is what opens the
  // Inspector — clicking the node body only selects it.
  await node.hover();
  await page.getByTitle('Edit state').first().click();
  await expect(page.getByText('Method Library').first()).toBeVisible({ timeout: 20000 });
  await page.waitForTimeout(2500);

  const canvasCalls = [...calls];
  const canvasOptions = await methodPickerOptions();
  // The Inspector scrolls independently; bring the Method Library into frame so
  // the screenshot shows the pinned block rather than the panel header.
  const canvasPinned = page.getByText('Final Method', { exact: true }).first();
  await expect(canvasPinned).toBeVisible({ timeout: 15000 });
  await canvasPinned.scrollIntoViewIfNeeded();
  await page.waitForTimeout(500);
  await page.screenshot({ path: `${SHOT}/B-canvas-stateinspector.png` });

  /* eslint-disable no-console */
  console.log('\n=== A) WIZARD (StagesStep.tsx:291) ===');
  console.log('requests:', JSON.stringify(wizardCalls, null, 2));
  console.log('picker options:', JSON.stringify(wizardOptions));
  console.log('\n=== B) CANVAS (StateInspector.tsx:272) ===');
  console.log('requests:', JSON.stringify(canvasCalls, null, 2));
  console.log('picker options:', JSON.stringify(canvasOptions));
  /* eslint-enable no-console */

  // Each call site is asserted on its OWN captured requests.
  expect(
    wizardCalls.filter((u) => u.includes(`entity_type=${ENTITY_TYPE}`)).length,
    `Wizard/StagesStep must send entity_type=${ENTITY_TYPE}; saw ${JSON.stringify(wizardCalls)}`,
  ).toBeGreaterThan(0);
  expect(
    canvasCalls.filter((u) => u.includes(`entity_type=${ENTITY_TYPE}`)).length,
    `Canvas/StateInspector must send entity_type=${ENTITY_TYPE}; saw ${JSON.stringify(canvasCalls)}`,
  ).toBeGreaterThan(0);

  // 2 tagged methods + the placeholder option, not the full 79-method library.
  expect(wizardOptions.length, 'wizard option count').toBe(3);
  expect(canvasOptions.length, 'canvas option count').toBe(3);
});
