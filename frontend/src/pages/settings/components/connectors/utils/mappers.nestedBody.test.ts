/**
 * The connector body editor must accept the nesting the backend already supports.
 *
 * The body column is JSONB, the contract is `dict[str, Any]`, and the placeholder
 * resolver walks dicts and lists. The editor rejected nesting anyway, because the
 * flat row model had nowhere to put it.
 */

import { describe, expect, it } from 'vitest';

import {
  bodyRowsFromTemplate,
  buildBodyTemplate,
  isRowRepresentable,
  parseBodyJson,
} from './mappers';
import { stringsFromJson } from './placeholders';

const NESTED_ARRAY = JSON.stringify({
  fieldValues: [{ fieldTypeId: 'ProductName', value: '$entity.product_name' }],
});
const NESTED_OBJECT = JSON.stringify({ name: { en: '$entity.product_name' } });

describe('parseBodyJson', () => {
  it('accepts an array of objects', () => {
    const { template, error } = parseBodyJson(NESTED_ARRAY);
    expect(error).toBeUndefined();
    expect(template).toEqual({
      fieldValues: [{ fieldTypeId: 'ProductName', value: '$entity.product_name' }],
    });
  });

  it('accepts a nested object', () => {
    const { template, error } = parseBodyJson(NESTED_OBJECT);
    expect(error).toBeUndefined();
    expect(template).toEqual({ name: { en: '$entity.product_name' } });
  });

  it('offers no rows for a nested body, so the nesting is not flattened away', () => {
    expect(parseBodyJson(NESTED_ARRAY).rows).toBeUndefined();
    expect(parseBodyJson(NESTED_OBJECT).rows).toBeUndefined();
  });

  it('still offers rows for a flat body', () => {
    const { rows, error } = parseBodyJson('{"job_id": "$entity.job_id"}');
    expect(error).toBeUndefined();
    expect(rows).toEqual([{ key: 'job_id', field: 'job_id', custom: false }]);
  });

  it('allows booleans and nulls, which the resolver passes through untouched', () => {
    const { template, error } = parseBodyJson('{"active": true, "note": null}');
    expect(error).toBeUndefined();
    expect(template).toEqual({ active: true, note: null });
  });

  it('reports malformed JSON', () => {
    const { error } = parseBodyJson('{"unclosed": ');
    expect(error).toBeTruthy();
  });

  it('accepts a top-level array, which batch endpoints require', () => {
    // inriver's entities:upsert rejects an object outright, and upsert is the
    // idempotent call a re-firing workflow action needs.
    const { template, error } = parseBodyJson('[{"entityTypeId": "Product"}]');
    expect(error).toBeUndefined();
    expect(template).toEqual([{ entityTypeId: 'Product' }]);
  });

  it('offers no rows for an array, so it is edited as JSON', () => {
    expect(parseBodyJson('[{"a": 1}]').rows).toBeUndefined();
  });

  it('still rejects a JSON scalar at the top level', () => {
    expect(parseBodyJson('42').error).toMatch(/object or array/i);
    expect(parseBodyJson('"text"').error).toMatch(/object or array/i);
  });
});

describe('isRowRepresentable', () => {
  it('is true only when every value is a scalar', () => {
    expect(isRowRepresentable({ a: 'x', b: 2, c: null })).toBe(true);
    expect(isRowRepresentable({ a: { b: 'x' } })).toBe(false);
    expect(isRowRepresentable({ a: ['x'] })).toBe(false);
    expect(isRowRepresentable([{ a: 'x' }])).toBe(false);
  });
});

describe('bodyRowsFromTemplate', () => {
  it('yields no rows for a nested template rather than stringifying the nesting', () => {
    // Stringifying it into a row would write it back as a quoted string on save.
    expect(bodyRowsFromTemplate({ name: { en: 'x' } })).toEqual([]);
    expect(bodyRowsFromTemplate({ fieldValues: [{ a: 1 }] })).toEqual([]);
  });

  it('still expands a flat template', () => {
    expect(bodyRowsFromTemplate({ job_id: '$entity.job_id' })).toEqual([
      { key: 'job_id', field: 'job_id', custom: false },
    ]);
  });
});

describe('buildBodyTemplate', () => {
  it('sends the nested body through untouched when one is held', () => {
    const nested = { fieldValues: [{ fieldTypeId: 'X', value: '$entity.f' }] };
    expect(buildBodyTemplate('application/json', '', [], nested)).toEqual(nested);
  });

  it('falls back to the rows when no nested body is held', () => {
    expect(
      buildBodyTemplate('application/json', '', [{ key: 'job_id', field: 'job_id' }], null),
    ).toEqual({ job_id: '$entity.job_id' });
  });

  it('keeps the raw body ahead of both', () => {
    expect(buildBodyTemplate('raw', '<xml/>', [], { a: 1 })).toBe('<xml/>');
  });

  it('sends a top-level array through untouched', () => {
    const batch = [{ entityTypeId: 'Product', fieldValues: [{ value: '$entity.sku' }] }];
    expect(buildBodyTemplate('application/json', '', [], batch)).toEqual(batch);
  });

  it('treats an empty array as no body', () => {
    expect(buildBodyTemplate('application/json', '', [], [])).toBeNull();
  });
});

describe('stringsFromJson', () => {
  it('finds placeholders nested inside objects and arrays', () => {
    const strings = stringsFromJson({
      fieldValues: [{ value: '$entity.product_name' }, { value: '{{weight}}' }],
      name: { en: '$entity.title' },
      count: 3,
    });
    expect(strings).toContain('$entity.product_name');
    expect(strings).toContain('{{weight}}');
    expect(strings).toContain('$entity.title');
  });
});
