import { expect, test } from '@playwright/test';

import {
  parseFormJson,
  parsePicklistJson,
} from '../../src/pages/settings/components/form-config/jsonConfig';

test.describe('form configuration JSON', () => {
  test('normalizes identifiers and types while preserving backend properties', () => {
    const parsed = parseFormJson(JSON.stringify({
      name: ' Candidate Form ',
      fields: [{
        field: ' candidate_name ',
        type: ' STRING ',
        required: true,
        nullable: false,
        description: 'Candidate Name',
      }],
    }));

    expect(parsed).toEqual({
      name: 'Candidate Form',
      fields: [{
        field: 'candidate_name',
        type: 'string',
        required: true,
        nullable: false,
        description: 'Candidate Name',
      }],
    });
  });

  test('rejects duplicate identifiers after trimming', () => {
    expect(() => parseFormJson(JSON.stringify({
      name: 'Candidate Form',
      fields: [
        { field: 'name', type: 'string' },
        { field: ' name ', type: 'string' },
      ],
    }))).toThrow("Field 'name' is duplicated.");
  });

  test('rejects unsupported stored field types', () => {
    expect(() => parseFormJson(JSON.stringify({
      name: 'Candidate Form',
      fields: [{ field: 'name', type: 'dropdown' }],
    }))).toThrow("Field 'name' has an unsupported 'type'.");
  });

  test('rejects malformed form shapes', () => {
    expect(() => parseFormJson('[]')).toThrow('Form JSON must be an object.');
    expect(() => parseFormJson('{"name":"","fields":[]}')).toThrow(
      "'name' must be a non-empty string.",
    );
    expect(() => parseFormJson('{"name":"Form"}')).toThrow("'fields' must be an array.");
  });
});

test.describe('picklist configuration JSON', () => {
  test('normalizes names and options', () => {
    expect(parsePicklistJson(JSON.stringify({
      name: ' Status ',
      options: [{ value: ' open ', label: ' Open ' }],
    }))).toEqual({
      name: 'Status',
      options: [{ value: 'open', label: 'Open' }],
    });
  });

  test('requires at least one complete option', () => {
    expect(() => parsePicklistJson('{"name":"Status","options":[]}')).toThrow(
      "'options' must contain at least one option.",
    );
    expect(() => parsePicklistJson(JSON.stringify({
      name: 'Status',
      options: [{ value: '', label: 'Open' }],
    }))).toThrow("Option 1 needs a non-empty 'value'.");
    expect(() => parsePicklistJson(JSON.stringify({
      name: 'Status',
      options: [{ value: 'open', label: '' }],
    }))).toThrow("Option 'open' needs a non-empty 'label'.");
  });
});
