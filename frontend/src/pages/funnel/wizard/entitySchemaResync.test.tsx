/**
 * Regression test for the entity-schema re-sync clobbering concurrent edits.
 *
 * This asserts at the *decision* layer — which document the effect picks as
 * its merge base when its fetch resolves late — not only at the outgoing
 * payload. A payload-level check can pass by coincidence of timing while the
 * selection logic underneath is still wrong, which is how this bug survived
 * more than one attempt at fixing it.
 *
 * The fetch is resolved manually rather than after a sleep, so the ordering
 * the bug needs (attach commits first, fetch resolves second) is guaranteed
 * rather than raced for.
 */

import { act, render, waitFor } from '@testing-library/react';
import { useState } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { StateMachineDocument } from '@/lib/state-machine/types';

// Resolved by hand inside each test to pin the ordering.
let resolveFormSchemas: (value: { items: Record<string, unknown>[] }) => void;

vi.mock('@/core/services/api', () => ({
  formSchemas: {
    list: vi.fn(
      () =>
        new Promise<{ items: Record<string, unknown>[] }>((resolve) => {
          resolveFormSchemas = resolve;
        }),
    ),
  },
  fieldLibrary: { listFieldTypes: vi.fn(() => Promise.resolve({ organization_id: '', items: [] })) },
  methodLibrary: { get: vi.fn(() => Promise.resolve({ fields: [] })) },
}));

// The child steps are irrelevant here; the effect under test lives in the
// parent. Stubbing them keeps the test on the merge decision.
vi.mock('./BasicsStep', () => ({ default: () => null }));
vi.mock('./StagesStep', () => ({ default: () => null }));
vi.mock('./TransitionsStep', () => ({ default: () => null }));
vi.mock('./GuardsStep', () => ({ default: () => null }));
vi.mock('./ValidationPanel', () => ({
  default: () => null,
  pathToStep: () => 'basics',
}));

import FunnelBuilder from './index';

const ENTITY_TYPE = 'perkin_client';
const METHOD_ID = 'method-under-test';

function baseDoc(methodRefs: { method_id: string; version_id: string | null }[] = []): StateMachineDocument {
  return {
    machine_name: 'wf_resync',
    base_version: 0,
    definition: {
      machine_key: 'wf_resync',
      name: 'Resync',
      description: '',
      entity_type: ENTITY_TYPE,
      entity_schema: { entity_type: ENTITY_TYPE, fields: [] },
      states: [
        {
          name: 'INITIAL',
          description: '',
          tags: ['initial'],
          order: 1,
          sla_seconds: null,
          method_refs: methodRefs,
        },
      ],
      initial_state: 'INITIAL',
      transitions: [],
    },
  } as unknown as StateMachineDocument;
}

const PINNED_FIELD = 'perkin_client_client_name';

/** What the migration left: an inherited field the pinned method owns. */
const MIGRATED_FIELD = {
  field: PINNED_FIELD,
  type: 'string',
  required: false,
  nullable: true,
  default: '',
  enum_values: [],
  picklist_id: null,
  description: 'Client name',
  ownership: 'inherited',
  source: { context_entity_type: 'perkin_client', context_field: 'client_name' },
  editable: false,
};

/** An already-migrated workflow, as the editor loads it. */
function migratedDoc(): StateMachineDocument {
  const doc = baseDoc([{ method_id: METHOD_ID, version_id: null }]);
  doc.definition.entity_schema.fields = [MIGRATED_FIELD] as never;
  (doc.definition as unknown as { method_schemas: unknown[] }).method_schemas = [
    { method_id: METHOD_ID, method_name: 'Requests', version_id: 'v1', version: 1,
      state_name: 'INITIAL', state_order: 1, method_order: 0, fields: [MIGRATED_FIELD] },
  ];
  return doc;
}

/** The Form still carries the same key, but only a naive version of it. */
const FORM_WITH_PINNED_KEY = {
  items: [
    {
      schema_key: 'perkin_client__default',
      entity_type: ENTITY_TYPE,
      is_active: true,
      schema: { fields: [{ id: PINNED_FIELD, type: 'text', required: false, label: 'Client name' }] },
    },
  ],
};

/**
 * A real form schema, in the shape `formSchemas.list()` returns *after* its
 * own raw->frontend mapping (fields live under `schema.fields`, keyed by
 * `id`) — this mock stands in for the mapped result, not the wire payload.
 */
const FORM_SCHEMA_RESPONSE = {
  items: [
    {
      schema_key: 'perkin_client__default',
      entity_type: ENTITY_TYPE,
      is_active: true,
      schema: {
        fields: [{ id: 'client_name', type: 'string', required: true, label: 'Client' }],
      },
    },
  ],
};

/**
 * Host that owns the document exactly as the real editor page does, so the
 * effect sees a `doc` prop that changes identity when an edit commits.
 */
function Host({
  onCommit,
  initialDoc,
}: {
  onCommit: (doc: StateMachineDocument) => void;
  initialDoc?: StateMachineDocument;
}) {
  const [doc, setDoc] = useState<StateMachineDocument>(() => initialDoc ?? baseDoc());
  hostSetDoc = setDoc;
  return (
    <FunnelBuilder
      doc={doc}
      isCreating
      onChange={(next: StateMachineDocument) => {
        onCommit(next);
        setDoc(next);
      }}
    />
  );
}

let hostSetDoc: (d: StateMachineDocument) => void;

function methodRefsOf(doc: StateMachineDocument): string[] {
  return (doc.definition.states[0].method_refs ?? []).map((r) => r.method_id);
}

describe('entity-schema re-sync merge base', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('merges onto the current document, not the closure captured before an edit', async () => {
    const commits: StateMachineDocument[] = [];
    render(<Host onCommit={(d) => commits.push(d)} />);

    // The effect has fired and is awaiting formSchemas.list().
    await waitFor(() => expect(resolveFormSchemas).toBeDefined());

    // Attach a Method while that request is still in flight. This is the edit
    // the stale closure does not know about. Flushed to completion first, as
    // it is in the real app — the user attaches, React commits, and only some
    // time later does the fetch come back.
    await act(async () => {
      hostSetDoc(baseDoc([{ method_id: METHOD_ID, version_id: null }]));
    });
    expect(commits.length).toBe(0); // nothing has merged yet

    // Only now let the fetch resolve.
    await act(async () => {
      resolveFormSchemas(FORM_SCHEMA_RESPONSE);
    });

    // The re-sync must commit — it has real fields to merge in.
    await waitFor(() => expect(commits.length).toBeGreaterThan(0));
    const resyncCommit = commits[commits.length - 1];

    // Decision-layer assertion: whatever the effect chose as its merge base
    // must have carried the attached method. If it merged onto the stale
    // closure this is [] and the attach was silently discarded.
    expect(methodRefsOf(resyncCommit)).toEqual([METHOD_ID]);

    // And the merge it was actually doing still happened.
    expect(resyncCommit.definition.entity_schema.fields.map((f) => f.field)).toContain('client_name');
  });

  it('does not rewrite a field the pinned method owns', async () => {
    // The reported bug: opening a migrated workflow and changing anything
    // structural rebuilt entity_schema from the Form, dropping ownership and
    // source, and publish then failed with PINNED_METHOD_FIELD_CONFLICT.
    const commits: StateMachineDocument[] = [];
    render(<Host initialDoc={migratedDoc()} onCommit={(d) => commits.push(d)} />);
    await waitFor(() => expect(resolveFormSchemas).toBeDefined());

    await act(async () => {
      resolveFormSchemas(FORM_WITH_PINNED_KEY);
    });

    // The key a pinned method provides must have exactly one source, and it is
    // the method. Whatever is committed must not carry a Form-derived copy of
    // it; the backend adds the real one at publish.
    const fields =
      commits.length === 0
        ? (migratedDoc().definition.entity_schema.fields as unknown as Record<string, unknown>[])
        : (commits[commits.length - 1].definition.entity_schema
            .fields as unknown as Record<string, unknown>[]);
    const pinned = fields.find((f) => f.field === PINNED_FIELD);

    if (pinned) {
      // Only acceptable if it is still the method's own definition, never the
      // naive rebuild that has no ownership and no source.
      expect(pinned.ownership, 'a Form-derived copy was written over the method').toBe(
        'inherited',
      );
    }
    // And no naive copy may have been introduced.
    expect(
      fields.filter((f) => f.field === PINNED_FIELD && f.ownership !== 'inherited'),
    ).toEqual([]);
  });

  it('still applies the schema merge when nothing changed underneath it', async () => {
    const commits: StateMachineDocument[] = [];
    render(<Host onCommit={(d) => commits.push(d)} />);
    await waitFor(() => expect(resolveFormSchemas).toBeDefined());

    await act(async () => {
      resolveFormSchemas(FORM_SCHEMA_RESPONSE);
    });

    await waitFor(() => expect(commits.length).toBeGreaterThan(0));
    expect(commits[commits.length - 1].definition.entity_schema.fields.map((f) => f.field)).toContain(
      'client_name',
    );
  });
});
