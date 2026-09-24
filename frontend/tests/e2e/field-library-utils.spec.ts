import { expect, test } from '@playwright/test';

import type {
  FieldListResponse,
  FieldWithVersion,
  FormField,
  Picklist,
} from '../../src/core/types';
import {
  coerceImportedDraft,
  fetchAllLibraryFieldPages,
  duplicateNameAndTypeError,
  matchesHistorySearch,
  prepareLibraryCreateRequest,
  prepareLibraryVersionRequest,
  settingsAreEqual,
  toFormField,
  versionsNewestFirst,
} from '../../src/pages/settings/components/fields/fieldLibraryUtils';

const statusPicklist: Picklist = {
  id: 'status-picklist',
  name: 'Status',
  options: [
    { value: 'in_progress', label: 'In progress' },
    { value: 'done', label: 'Done' },
  ],
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

function fieldEntry(index: number): FieldWithVersion {
  const libraryFieldId = `library-field-${index}`;
  return {
    identity: {
      library_field_id: libraryFieldId,
      field_count_id: index,
      organization_id: 'org-1',
      name: `Field ${index}`,
      field_key: `field_${index}`,
      field_type: 'text',
      is_archived: false,
    },
    version: {
      version_id: `version-${index}`,
      library_field_id: libraryFieldId,
      organization_id: 'org-1',
      version: 1,
      name: `Field ${index}`,
      field_type: 'text',
      settings: { required: false },
      is_latest: true,
    },
  };
}

test('loads every backend field page without the old 200-field cap', async () => {
  const allFields = Array.from({ length: 425 }, (_, index) => fieldEntry(index + 1));
  const offsets: number[] = [];

  const result = await fetchAllLibraryFieldPages(async ({ limit = 25, offset = 0 }) => {
    offsets.push(offset);
    const response: FieldListResponse = {
      organization_id: 'org-1',
      items: allFields.slice(offset, offset + limit),
      total: allFields.length,
      limit,
      offset,
    };
    return response;
  });

  expect(offsets).toEqual([0, 200, 400]);
  expect(result).toHaveLength(425);
  expect(result.at(-1)?.identity.field_key).toBe('field_425');
});

test('creates the same picklist value and label snapshot as Forms', () => {
  const field: FormField = {
    id: '',
    label: ' Status ',
    type: 'select',
    required: true,
    system: false,
    picklist_id: statusPicklist.id,
  };

  const prepared = prepareLibraryCreateRequest(field, ' Current status ', [], [statusPicklist]);

  expect(prepared.error).toBeNull();
  expect(prepared.request).toMatchObject({
    name: 'Status',
    field_key: 'status',
    field_type: 'select',
    description: 'Current status',
    settings: {
      required: true,
      picklist_id: statusPicklist.id,
      enum_values: ['in_progress', 'done'],
      enum_labels: ['In progress', 'Done'],
    },
  });
});

test('applies Forms validation to new fields, versions, and imports', () => {
  const tableField: FormField = {
    id: 'measurements',
    label: 'Measurements',
    type: 'table',
    required: false,
    system: false,
    table_config: { row_mode: 'dynamic', display_mode: 'grid', columns: [] },
  };
  const selectWithoutPicklist: FormField = {
    id: '',
    label: 'Status',
    type: 'select',
    required: false,
    system: false,
  };

  expect(prepareLibraryVersionRequest(tableField, '', []).error).toBe(
    'Table fields must include at least one column',
  );
  expect(prepareLibraryCreateRequest(selectWithoutPicklist, '', [], []).error).toBe(
    'Please select a picklist for this field',
  );
});

test('plain JSON imports keep identity metadata out of version settings', () => {
  const imported = coerceImportedDraft({
    name: 'Status',
    field_key: 'ignored_key',
    field_type: 'text',
    description: 'Current status',
    required: true,
    placeholder: 'Enter status',
  });

  expect(imported).not.toBeNull();
  expect(imported?.description).toBe('Current status');
  expect(imported?.field).toMatchObject({
    id: '',
    label: 'Status',
    type: 'text',
    required: true,
    placeholder: 'Enter status',
  });
  expect(imported?.field).not.toHaveProperty('field_key');
  expect(imported?.field).not.toHaveProperty('field_type');
  expect(imported?.field).not.toHaveProperty('description');
});

test('version requests carry the selected field type snapshot', () => {
  const field: FormField = {
    id: 'count',
    label: 'Count',
    type: 'integer',
    required: true,
    system: false,
  };

  const prepared = prepareLibraryVersionRequest(field, '', []);

  expect(prepared.error).toBeNull();
  expect(prepared.request).toMatchObject({
    field_type: 'integer',
    settings: { required: true },
  });
});

test('reconstructs a pinned field from its version type snapshot', () => {
  const entry = fieldEntry(1);
  entry.identity.field_type = 'text';
  entry.version.field_type = 'integer';

  expect(toFormField(entry).type).toBe('integer');
});

test('version history search includes required and optional state', () => {
  const entry = fieldEntry(1);

  expect(matchesHistorySearch(entry.identity, entry.version, 'optional')).toBe(true);
  expect(matchesHistorySearch(
    entry.identity,
    { ...entry.version, settings: { required: true } },
    'required',
  )).toBe(true);
});

test('duplicate validation uses the live name and type combination', () => {
  const textField = fieldEntry(1);

  expect(duplicateNameAndTypeError([textField], ' FIELD 1 ', 'text')).toContain(
    'name "FIELD 1" and type "Text" already exists',
  );
  expect(duplicateNameAndTypeError([textField], 'Field 1', 'integer')).toBeNull();
  expect(duplicateNameAndTypeError(
    [textField],
    'Field 1',
    'text',
    textField.identity.library_field_id,
  )).toBeNull();
  expect(duplicateNameAndTypeError([
    { ...textField, identity: { ...textField.identity, is_archived: true } },
  ], 'Field 1', 'text')).toBeNull();
});

test('versions are newest first and retain searchable snapshot metadata', () => {
  const entry = fieldEntry(1);
  const older = {
    ...entry.version,
    version_id: 'version-old',
    version: 1,
    name: 'Original field name',
    field_type: 'integer',
    created_by_name: 'Ada Lovelace',
    is_latest: false,
  };
  const latest = { ...entry.version, version_id: 'version-new', version: 2 };

  expect(versionsNewestFirst([older, latest]).map((version) => version.version)).toEqual([2, 1]);
  expect(matchesHistorySearch(entry.identity, older, 'Original field')).toBe(true);
  expect(matchesHistorySearch(entry.identity, older, 'Integer')).toBe(true);
  expect(matchesHistorySearch(entry.identity, older, 'Ada Lovelace')).toBe(true);
});

test('settings comparison ignores object key order but detects content changes', () => {
  expect(settingsAreEqual(
    { required: true, config: { unit: 'mL', precision: 2 } },
    { config: { precision: 2, unit: 'mL' }, required: true },
  )).toBe(true);
  expect(settingsAreEqual({ required: true }, { required: false })).toBe(false);
});
