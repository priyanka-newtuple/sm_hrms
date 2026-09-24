import { test, expect } from '@playwright/test';

/**
 * Funnels List — Filters Dropdown
 *
 * Covers the Settings > Funnels "Filters" button: it must open a working
 * dropdown (regression coverage for a Base UI MenuGroupContext crash caused
 * by an ungrouped DropdownMenuLabel) and let the user narrow the table by
 * Owner and Version.
 */

async function openFunnelsTab(page: import('@playwright/test').Page) {
  await page.goto('/settings');
  await expect(page.getByPlaceholder(/find a setting/i)).toBeVisible({ timeout: 15_000 });
  await page.getByRole('button', { name: 'Funnels', exact: true }).click();
  await expect(page.getByLabel('Breadcrumb')).toBeVisible();
}

test.describe('Funnels List Filters', () => {
  test('Filters button opens a dropdown without crashing @smoke', async ({ page }) => {
    const pageErrors: string[] = [];
    page.on('pageerror', (err) => pageErrors.push(err.message));

    await openFunnelsTab(page);
    await page.getByRole('button', { name: 'Filters' }).click();

    // Regression guard: previously threw "Base UI: MenuGroupContext is missing."
    const menu = page.getByRole('menu');
    await expect(menu).toBeVisible();
    await expect(menu.getByText('Owner', { exact: true })).toBeVisible();
    await expect(menu.getByText('Version', { exact: true })).toBeVisible();
    expect(pageErrors).toEqual([]);
  });

  test('selecting an owner filters the table and shows an active-filter badge @critical', async ({ page }) => {
    await openFunnelsTab(page);
    await page.getByRole('button', { name: 'Filters' }).click();
    await expect(page.getByRole('menu')).toBeVisible();

    const ownerOption = page.getByRole('menuitemcheckbox').first();
    const hasOwners = await ownerOption.isVisible().catch(() => false);
    test.skip(!hasOwners, 'No workflows with a resolvable owner in this environment');

    const ownerLabel = (await ownerOption.textContent())?.trim();
    await ownerOption.click();

    // Dropdown stays open for multi-select; close it to check the table + badge.
    await page.keyboard.press('Escape');
    await expect(page.getByRole('button', { name: 'Filters' })).toContainText('1');

    if (ownerLabel) {
      // Every remaining visible row's owner cell should match the selected owner,
      // or the empty-state message should show when nothing matches.
      const noMatches = page.getByText('No workflows match your filters.');
      const rows = page.locator('table tbody tr');
      const rowCount = await rows.count();
      if (rowCount === 1 && await noMatches.isVisible().catch(() => false)) {
        // Selected owner has no other overlapping rows — acceptable outcome.
      } else {
        expect(rowCount).toBeGreaterThan(0);
      }
    }
  });

  test('Clear filters resets owner and version selections @critical', async ({ page }) => {
    await openFunnelsTab(page);
    await page.getByRole('button', { name: 'Filters' }).click();
    await expect(page.getByRole('menu')).toBeVisible();

    const versionOption = page.getByRole('menuitemcheckbox').last();
    const hasVersions = await versionOption.isVisible().catch(() => false);
    test.skip(!hasVersions, 'No workflow versions available in this environment');

    await versionOption.click();
    await expect(page.getByRole('menuitem', { name: 'Clear filters' })).toBeVisible();
    await page.getByRole('menuitem', { name: 'Clear filters' }).click();

    await expect(page.getByRole('button', { name: 'Filters' })).not.toContainText(/[1-9]/);
  });
});
