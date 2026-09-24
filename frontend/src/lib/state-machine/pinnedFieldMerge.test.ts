/**
 * The Form-sync must not rewrite a field a pinned Method Block owns.
 *
 * Reported against workflow `perkin_request`: opening the wizard or canvas on
 * an already-migrated workflow and making any structural edit rebuilt
 * `entity_schema.fields` from the entity type's Form. buildEntityFieldsFromForm
 * Schema has no `ownership`, no `source` and only a generic type guess, so the
 * rewritten field stopped matching what the pinned method defines and publish
 * failed with PINNED_METHOD_FIELD_CONFLICT:
 *
 *   state 'Submitted' pins a method that defines field
 *   'select_a_request_for_processing' differently from the workflow's own fields
 *
 * The three fields in that report cover both ways a rewrite diverges: two were
 * inherited (ownership/source lost) and one had its type corrected by the
 * migration (type lost). Both are exercised here.
 */

import { describe, expect, it } from 'vitest';

import {
  buildEntityFieldsFromFormSchema,
  formFieldsExcludingPinned,
  pinnedMethodFieldKeys,
  resyncEntitySchemaFields,
} from './entitySchema';
import type { EntityField, ResolvedMethodSchema } from './types';

const field = (over: Partial<EntityField> & { field: string }): EntityField => ({
  type: 'string',
  required: false,
  nullable: true,
  default: '',
  enum_values: [],
  picklist_id: null,
  description: '',
  ...over,
});

// What the migration left on the workflow.
const MIGRATED_INHERITED = field({
  field: 'perkin_client_client_name',
  ownership: 'inherited',
  source: { context_entity_type: 'perkin_client', context_field: 'client_name' },
  editable: false,
} as Partial<EntityField> & { field: string });

const MIGRATED_TYPED = field({ field: 'select_a_request_for_processing', type: 'enum' });
const FORM_OWNED = field({ field: 'plain_note', description: 'Note' });

// What the Form-derived rebuild would produce for the same keys: no ownership,
// no source, generic type.
const NAIVE_INHERITED = field({ field: 'perkin_client_client_name' });
const NAIVE_TYPED = field({ field: 'select_a_request_for_processing', type: 'string' });

describe('pinnedMethodFieldKeys', () => {
  it('reads the authoritative list published on the definition', () => {
    const definition = {
      method_schemas: [
        { fields: [MIGRATED_INHERITED, MIGRATED_TYPED] } as unknown as ResolvedMethodSchema,
      ],
    };
    expect([...pinnedMethodFieldKeys(definition)].sort()).toEqual([
      'perkin_client_client_name',
      'select_a_request_for_processing',
    ]);
  });

  it('also covers a method pinned since the last publish', () => {
    // method_schemas is written at publish, so a freshly pinned method is only
    // visible through the live method fields.
    const keys = pinnedMethodFieldKeys({ method_schemas: [] }, [[MIGRATED_TYPED]]);
    expect([...keys]).toEqual(['select_a_request_for_processing']);
  });

  it('is empty for a workflow that pins nothing', () => {
    expect(pinnedMethodFieldKeys(undefined).size).toBe(0);
    expect(pinnedMethodFieldKeys({}).size).toBe(0);
  });
});

describe('formFieldsExcludingPinned', () => {
  const protectedKeys = new Set(['perkin_client_client_name', 'select_a_request_for_processing']);

  it('leaves a pinned key out entirely, so there is only one source for it', () => {
    // Writing either copy is what publish refuses. The backend adds the field
    // from the method itself, which is the definition that wins.
    const merged = formFieldsExcludingPinned([NAIVE_INHERITED, FORM_OWNED], protectedKeys);
    expect(merged.map((f) => f.field)).toEqual(['plain_note']);
  });

  it('drops a stale copy a previous publish left behind', () => {
    // This is the repair case: the workflow already holds the method's field
    // and the method has since changed, so the stored copy blocks publish.
    const merged = formFieldsExcludingPinned([NAIVE_TYPED], protectedKeys);
    expect(merged).toEqual([]);
  });

  it('still syncs a Form-owned field', () => {
    const edited = field({ field: 'plain_note', required: true, description: 'Renamed' });
    expect(formFieldsExcludingPinned([edited], protectedKeys)).toEqual([edited]);
  });

  it('still drops a Form-owned field the Form no longer has', () => {
    expect(formFieldsExcludingPinned([], protectedKeys)).toEqual([]);
  });

  it('leaves a Form-only workflow entirely to the Form', () => {
    const edited = field({ field: 'plain_note', required: true });
    expect(formFieldsExcludingPinned([edited], new Set())).toEqual([edited]);
  });
});

describe('why the rewrite broke publish (the real converter)', () => {
  it('a Form-derived field carries no ownership, no source, and a guessed type', () => {
    // Not a fixture: this is buildEntityFieldsFromFormSchema, the function the
    // sync used to rebuild the whole list with. The backend compares a pinned
    // method field against the workflow's own copy with model_dump(exclude=
    // {"source_states"}) and rejects any difference, so each missing key below
    // is one PINNED_METHOD_FIELD_CONFLICT.
    const [rebuilt] = buildEntityFieldsFromFormSchema({
      schema_key: 'perkin_request__default',
      entity_type: 'perkin_request',
      is_active: true,
      schema: {
        fields: [
          { id: 'perkin_client_client_name', type: 'text', label: 'Client name', required: false },
        ],
      },
    } as never);

    expect(rebuilt.field).toBe('perkin_client_client_name');
    expect(rebuilt).not.toHaveProperty('ownership');
    expect(rebuilt).not.toHaveProperty('source');
    // And that is precisely the copy the sync now refuses to write.
    const merged = formFieldsExcludingPinned([rebuilt], new Set(['perkin_client_client_name']));
    expect(merged).toEqual([]);
  });
});

describe('resyncEntitySchemaFields', () => {
  const form = (ids: string[]) =>
    [{
      schema_key: 'k',
      entity_type: 'perkin_request',
      is_active: true,
      schema: {
        fields: ids.map((id) => ({ id, type: 'text', required: false, label: id })),
      },
    }] as never;

  const definition = (fields: EntityField[], transitions: unknown[] = []) =>
    ({ entity_schema: { fields }, transitions, method_schemas: [] }) as never;

  it('reports unchanged when only the order differs', () => {
    // The reviewer's case: JSON.stringify compares element and key order, and
    // both move here. Reporting "changed" for the same set of identical fields
    // commits a reorder and marks an untouched document dirty on open.
    const a = field({ field: 'alpha', description: 'alpha' });
    const b = field({ field: 'beta', description: 'beta' });
    const result = resyncEntitySchemaFields(definition([b, a]), form(['alpha', 'beta']), []);
    expect(result.unchanged, 'a pure reorder was reported as a change').toBe(true);
  });

  it('still reports a real change', () => {
    const result = resyncEntitySchemaFields(
      definition([field({ field: 'alpha', description: 'alpha' })]),
      form(['alpha', 'gamma']),
      [],
    );
    expect(result.unchanged).toBe(false);
    expect(result.fields.map((f) => f.field)).toEqual(['alpha', 'gamma']);
  });

  it('keeps a pinned key out and keeps guards that reference it', () => {
    const guarded = [{
      key: 't', trigger: 't', label: 't', from_state: 'A', to_state: 'B',
      guards: [{ type: 'field_present', field: 'block_only' }],
      required_fields: [], pre_transition_tasks: [], post_transition_tasks: [],
      auto_transition: null, description: null,
    }];
    const result = resyncEntitySchemaFields(
      definition([field({ field: 'block_only' })], guarded),
      form(['block_only', 'plain']),
      [[field({ field: 'block_only' })]],
    );
    expect(result.fields.map((f) => f.field)).toEqual(['plain']);
    expect(result.transitions, 'a guard on a pinned field was pruned').toHaveLength(1);
  });
});
