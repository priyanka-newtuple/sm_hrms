import { expect, test } from '@playwright/test';

import {
  entityIteratorDirectionForKey,
  entityIteratorViewState,
} from '../../src/core/hooks/useEntityIterator';
import type { WorkflowEntityState } from '../../src/core/services/api';
import { filterPipelineEntities } from '../../src/pages/Pipeline/utils/entityFilters';
import { isEntityEditDirty } from '../../src/pages/records/detail/helpers';
import {
  fullWorkflowEntityIdentity,
  resolveFullWorkflowEntityDisplay,
} from '../../src/shared/hooks/fullWorkflowEntityIdentity';

const summary = {
  entity_id: 'entity-1',
  state_id: 'state-1',
  workflow_id: 'workflow-1',
  data: { name: 'Summary' },
} as WorkflowEntityState;

test('equivalent summary objects have the same hydration identity', () => {
  const first = fullWorkflowEntityIdentity({
    entity_id: 'entity-1',
    state_id: 'state-1',
    workflow_id: 'workflow-1',
  });
  const reconstructed = fullWorkflowEntityIdentity({
    entity_id: 'entity-1',
    state_id: 'state-1',
    workflow_id: 'workflow-1',
  });

  expect(reconstructed).toEqual(first);
});

test('a different enrollment changes the hydration identity', () => {
  const first = fullWorkflowEntityIdentity({
    entity_id: 'entity-1',
    state_id: 'state-1',
    workflow_id: 'workflow-1',
  });
  const otherEnrollment = fullWorkflowEntityIdentity({
    entity_id: 'entity-1',
    state_id: 'state-2',
    workflow_id: 'workflow-2',
  });

  expect(otherEnrollment).not.toEqual(first);
});

test('keeps the summary visible while full hydration is pending', () => {
  expect(resolveFullWorkflowEntityDisplay(summary, null, true, null)).toEqual({
    displayedEntity: summary,
    displayLoading: true,
    entityIsCurrent: false,
  });
});

test('ignores a hydrated entity from the previously selected enrollment', () => {
  const staleEntity = {
    ...summary,
    entity_id: 'entity-previous',
    data: { name: 'Previous' },
  };

  expect(resolveFullWorkflowEntityDisplay(summary, staleEntity, false, null)).toEqual({
    displayedEntity: summary,
    displayLoading: true,
    entityIsCurrent: false,
  });
});

test('shows the current fully hydrated entity without a loading veil', () => {
  const fullEntity = { ...summary, data: { name: 'Full record', extra: true } };

  expect(resolveFullWorkflowEntityDisplay(summary, fullEntity, false, null)).toEqual({
    displayedEntity: fullEntity,
    displayLoading: false,
    entityIsCurrent: true,
  });
});

test('hides invalid iterator positions', () => {
  expect(entityIteratorViewState(0, 0, false).hidden).toBe(true);
});

test('renders a 1-based position and explicit boundary state', () => {
  expect(entityIteratorViewState(1, 3, false)).toEqual({
    hidden: false,
    label: '1 of 3',
    previousDisabled: true,
    nextDisabled: false,
  });
  expect(entityIteratorViewState(2, 3, true)).toEqual({
    hidden: false,
    label: '2 of 3',
    previousDisabled: true,
    nextDisabled: true,
  });
});

test('maps Alt+Arrow shortcuts only when navigation is allowed', () => {
  expect(entityIteratorDirectionForKey('ArrowLeft', true, 2, 3, false)).toBe(-1);
  expect(entityIteratorDirectionForKey('ArrowRight', true, 2, 3, false)).toBe(1);
  expect(entityIteratorDirectionForKey('ArrowLeft', true, 1, 3, false)).toBeNull();
  expect(entityIteratorDirectionForKey('ArrowRight', true, 3, 3, false)).toBeNull();
  expect(entityIteratorDirectionForKey('ArrowRight', false, 2, 3, false)).toBeNull();
  expect(entityIteratorDirectionForKey('ArrowRight', true, 2, 3, true)).toBeNull();
});

test('uses shared board filters for the full-page iterator sequence', () => {
  const entities = [
    { entity_id: 'visible', current_state: 'ACTIVE', assignee_id: 'user-1' },
    { entity_id: 'other-assignee', current_state: 'ACTIVE', assignee_id: 'user-2' },
    { entity_id: 'terminal', current_state: 'DONE', assignee_id: 'user-1' },
  ] as WorkflowEntityState[];

  const filtered = filterPipelineEntities(entities, {
    applyBoardFilters: (rows) => rows,
    matchesAssignee: (entity) => entity.assignee_id === 'user-1',
    user: null,
    hideTerminal: true,
    terminalStateNames: new Set(['DONE']),
  });

  expect(filtered.map((entity) => entity.entity_id)).toEqual(['visible']);
});

test('detects whether a Records edit draft has unsaved changes', () => {
  const original = { name: 'Ada', status: 'Applied' };

  expect(isEntityEditDirty({ ...original }, original)).toBe(false);
  expect(isEntityEditDirty({ ...original, status: 'Screening' }, original)).toBe(true);
});
