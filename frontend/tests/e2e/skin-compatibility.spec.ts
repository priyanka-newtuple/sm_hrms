import { expect, test } from '@playwright/test';

import { resolveSkinHomePath } from '../../src/shared/skin/homePath';
import { formatLibraryCount } from '../../src/pages/settings/components/fields/fieldLibraryCopy';
import { getMethodLibraryLabels } from '../../src/pages/settings/components/methods/libraryLabels';

test('keeps the standalone State Machine default library wording', () => {
  const labels = getMethodLibraryLabels('method');

  expect(labels).toMatchObject({
    entityTitle: 'Method',
    entityTitlePlural: 'Methods',
    libraryLabel: 'Field Library',
    libraryItemTitle: 'Field',
    libraryItemTitlePlural: 'Fields',
    libraryItemLower: 'field',
    libraryItemLowerPlural: 'fields',
  });
});

test('preserves singular and plural default library counts', () => {
  expect(formatLibraryCount(1, false, 'field', 'fields')).toBe('1 field');
  expect(formatLibraryCount(2, false, 'field', 'fields')).toBe('2 fields');
  expect(formatLibraryCount(1, true, 'field', 'fields')).toBe('1 match');
  expect(formatLibraryCount(2, true, 'field', 'fields')).toBe('2 matches');
});

test('keeps the PE Composite Block wording explicit and isolated', () => {
  const labels = getMethodLibraryLabels('composite-block');

  expect(labels).toMatchObject({
    entityTitle: 'Composite Block',
    entityTitlePlural: 'Composite Blocks',
    libraryLabel: 'Step Objects',
    libraryItemTitle: 'Step Object',
    libraryItemTitlePlural: 'Step Objects',
    libraryItemLower: 'step object',
    libraryItemLowerPlural: 'step objects',
  });
});

test('preserves all landing-path defaults and skin-owned paths', () => {
  expect(resolveSkinHomePath(undefined)).toBe('/workflows');
  expect(resolveSkinHomePath('workflows')).toBe('/workflows');
  expect(resolveSkinHomePath('pipeline')).toBe('pipeline');
  expect(resolveSkinHomePath('/pe/home')).toBe('/pe/home');
});
