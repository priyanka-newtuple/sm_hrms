import { expect, test } from '@playwright/test';

import type { WorkflowEntityState } from '../../src/core/services/api';
import type { EntityType, FormSchema } from '../../src/core/types';
import {
  entityTypeCardKey,
  latestEntityTypesByName,
} from '../../src/pages/records/components/utils';
import { deriveEntityDisplayName } from '../../src/pages/records/detail/helpers';

const entity = (overrides: Partial<WorkflowEntityState>): WorkflowEntityState => ({
  entity_id: 'entity-12345678',
  entity_type: 'Candidate',
  organization_id: 'org-1',
  machine_name: '',
  machine_version: 0,
  current_state: 'CREATED',
  state_version: 0,
  data: {},
  ...overrides,
});

test('uses the canonical API display name before form field values', () => {
  const schema = {
    schema: {
      fields: [{ id: 'email', label: 'Email', type: 'text' }],
    },
  } as FormSchema;

  expect(
    deriveEntityDisplayName(
      entity({
        display_name: 'CAND-0042',
        data: { email: 'candidate@example.com' },
      }),
      schema,
    ),
  ).toBe('CAND-0042');
});

test('uses the canonical API display name without a form schema', () => {
  expect(
    deriveEntityDisplayName(
      entity({
        display_name: 'Formless record',
        data: {},
      }),
      null,
    ),
  ).toBe('Formless record');
});

test('keeps only the latest definition for each logical entity type', () => {
  const definitions = [
    { entity_type_id: 'candidate-v1', name: 'ATS.Candidate', version: 1 },
    { entity_type_id: 'job-v1', name: 'Job', version: 1 },
    { entity_type_id: 'candidate-v2', name: 'candidate', version: 2 },
  ] as EntityType[];

  expect(latestEntityTypesByName(definitions)).toEqual([
    definitions[2],
    definitions[1],
  ]);
});

test('uses the canonical API entity type identifier as the card key', () => {
  const definition = {
    id: undefined,
    entity_type_id: 'candidate-v2',
    name: 'Candidate',
  } as unknown as EntityType;

  expect(entityTypeCardKey(definition)).toBe('candidate-v2');
});
