import { expect, test } from '@playwright/test';

/**
 * The Entity Types field is a chip row + type-ahead, not a checkbox list, and
 * (on the Forms surface, libraryEntity 'field') single-select: the picker
 * unmounts its search input entirely once one type is tagged, and a tag must
 * be removed before another can be picked. Verifies the type-ahead narrows
 * while untagged, that picking replaces rather than appends (the input
 * disappears so a second pick isn't even reachable), and that removing a tag
 * brings the input back so a different one can be chosen.
 */

const SHOT = 'test-results/picker';
// Tagged final_entity going in; the test removes and restores it so the
// record's tag set is unchanged at the end (other specs pin this method by
// name, not by its tags).
const METHOD_NAME = 'Final Method';
const EXISTING_TAG = 'final_entity';
const REPLACEMENT_TAG = 'perkin_site';

test.setTimeout(180_000);

test('entity-type picker: chips + type-ahead, single-select replaces (not appends)', async ({
  page,
}) => {
  await page.goto('/settings?tab=methods');
  await page.waitForLoadState('networkidle');

  // UI copy presents Methods as "Forms" (see libraryLabels.ts); the search
  // placeholder follows that noun even though the API/testids stay "method".
  await page.getByPlaceholder(/Search forms by name or category/i).fill(METHOD_NAME);
  await page.waitForTimeout(1500);
  await page.getByText(METHOD_NAME, { exact: true }).first().click();

  const picker = page.getByTestId('method-entity-types');
  await expect(picker).toBeVisible({ timeout: 20000 });

  // 1. No checkbox wall.
  expect(await picker.locator('input[type="checkbox"]').count(), 'checkboxes').toBe(0);

  const chips = picker.getByTestId('entity-type-chip');
  const input = picker.getByLabel('Search entity types');

  // 2. The pre-existing tag renders as a chip, and single-select hides the
  // search input entirely while a tag is present.
  await expect(chips.filter({ hasText: EXISTING_TAG })).toHaveCount(1);
  const chipsBefore = await chips.allInnerTexts();
  expect(await input.count(), 'input hidden while a chip exists').toBe(0);
  await page.screenshot({ path: `${SHOT}/1-tagged-input-hidden.png` });

  // 3. Removing the tag brings the input back — now untagged.
  const removeInitialPatch = page.waitForResponse(
    (r) => r.url().includes('/method-library/methods/') && r.request().method() === 'PATCH',
    { timeout: 20000 },
  );
  await picker.getByRole('button', { name: `Remove ${EXISTING_TAG}` }).click();
  expect((await removeInitialPatch).ok()).toBeTruthy();
  await expect(chips).toHaveCount(0, { timeout: 10000 });
  await expect(input, 'input reappears once untagged').toBeVisible({ timeout: 10000 });

  // 4. Focusing shows suggestions; typing narrows them.
  await input.click();
  const suggestions = picker.getByTestId('entity-type-suggestion');
  await expect(suggestions.first()).toBeVisible({ timeout: 10000 });
  const unfiltered = await suggestions.allInnerTexts();
  await page.screenshot({ path: `${SHOT}/2-untagged-typeahead.png` });

  await input.fill('perkin');
  await page.waitForTimeout(400);
  const narrowed = await suggestions.allInnerTexts();
  await page.screenshot({ path: `${SHOT}/3-narrowed-by-typing.png` });

  // 5. Case-insensitive substring match, and it genuinely narrows.
  await input.fill('PERKIN');
  await page.waitForTimeout(400);
  const narrowedUpper = await suggestions.allInnerTexts();

  // 6. Zero-match state.
  await input.fill('zzzz-no-such-type');
  await page.waitForTimeout(400);
  const noneCount = await suggestions.count();
  await expect(picker.getByText('No matching entity types')).toBeVisible();

  // 7. Picking a type persists it as the sole tag, and single-select hides
  // the input again — there is no way through the UI to append a second one.
  await input.fill(REPLACEMENT_TAG);
  await page.waitForTimeout(400);
  const addPatch = page.waitForResponse(
    (r) => r.url().includes('/method-library/methods/') && r.request().method() === 'PATCH',
    { timeout: 20000 },
  );
  await suggestions.filter({ hasText: REPLACEMENT_TAG }).first().click();
  const addBody = (await addPatch).ok();
  await expect(chips).toHaveCount(1, { timeout: 10000 });
  await expect(chips.filter({ hasText: REPLACEMENT_TAG })).toHaveCount(1);
  expect(await input.count(), 'input hides again once a chip exists').toBe(0);
  await page.screenshot({ path: `${SHOT}/4-replaced-input-hidden.png` });

  // 8. Removing it and re-tagging the original restores the record's
  // original tag set (input reappears a second time, proving the toggle is
  // not one-shot).
  const removeReplacementPatch = page.waitForResponse(
    (r) => r.url().includes('/method-library/methods/') && r.request().method() === 'PATCH',
    { timeout: 20000 },
  );
  await picker.getByRole('button', { name: `Remove ${REPLACEMENT_TAG}` }).click();
  const removeOk = (await removeReplacementPatch).ok();
  await expect(chips).toHaveCount(0, { timeout: 10000 });
  await expect(input, 'input reappears again after the second removal').toBeVisible({
    timeout: 10000,
  });

  const restorePatch = page.waitForResponse(
    (r) => r.url().includes('/method-library/methods/') && r.request().method() === 'PATCH',
    { timeout: 20000 },
  );
  await input.click();
  await input.fill(EXISTING_TAG);
  await page.waitForTimeout(400);
  await suggestions.filter({ hasText: EXISTING_TAG }).first().click();
  const restoreOk = (await restorePatch).ok();
  await expect(chips.filter({ hasText: EXISTING_TAG })).toHaveCount(1, { timeout: 10000 });
  const chipsAfter = await chips.allInnerTexts();

  console.log('\n=== PICKER (single-select) ===');
  console.log('checkboxes rendered      :', 0);
  console.log('chips before             :', JSON.stringify(chipsBefore));
  console.log('suggestions (no query)   :', JSON.stringify(unfiltered));
  console.log('suggestions "perkin"     :', JSON.stringify(narrowed));
  console.log('suggestions "PERKIN"     :', JSON.stringify(narrowedUpper));
  console.log('suggestions no-match     :', noneCount);
  console.log('remove/add/remove/restore ok:', removeOk, '/', addBody, '/', removeOk, '/', restoreOk);
  console.log('chips after full cycle   :', JSON.stringify(chipsAfter));

  expect(narrowed.length, 'typing narrows the list').toBeLessThan(unfiltered.length);
  expect(narrowed.every((n) => n.toLowerCase().includes('perkin'))).toBeTruthy();
  expect(narrowedUpper, 'match is case-insensitive').toEqual(narrowed);
  expect(noneCount, 'no-match shows nothing').toBe(0);
  expect(chipsAfter, 'tag set restored exactly, one type at a time').toEqual(chipsBefore);
});
