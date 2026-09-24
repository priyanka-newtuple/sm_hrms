import { expect, test } from '@playwright/test';

import type { StoredFormField } from '../../src/core/types/portableForm';
import {
  applyReferenceMappingChanges,
  planReferenceMappingChanges,
  prepareReferenceMappingChangeWithDependencies,
  type ReferenceMappingDependencies,
} from '../../src/pages/settings/components/form-config/referenceMappingPlan';

function referenceField(
  field: string,
  sourceEntity = 'Candidate',
  sourceField = 'name',
): StoredFormField {
  return {
    field,
    type: 'string',
    description: `__ref__:${sourceEntity}:${sourceField}:Reference label`,
  };
}

test.describe('reference mapping planning', () => {
  test('skips same-entity references', () => {
    expect(planReferenceMappingChanges({
      targetEntity: 'Candidate',
      beforeFields: [],
      afterFields: [referenceField('candidate_name')],
      referenceMappingsUsedByOtherForms: new Map(),
    })).toEqual([]);
  });

  test('plans additions and removals for cross-entity references', () => {
    const added = planReferenceMappingChanges({
      targetEntity: 'Application',
      beforeFields: [],
      afterFields: [referenceField('candidate_name')],
      referenceMappingsUsedByOtherForms: new Map(),
    });
    expect(added).toEqual([{
      sourceEntity: 'Candidate',
      key: 'Candidate.name',
      target: 'Application.candidate_name',
    }]);

    const removed = planReferenceMappingChanges({
      targetEntity: 'Application',
      beforeFields: [referenceField('candidate_name')],
      afterFields: [],
      referenceMappingsUsedByOtherForms: new Map(),
    });
    expect(removed).toEqual([{
      sourceEntity: 'Candidate',
      key: 'Candidate.name',
      target: null,
    }]);
  });

  test('preserves shared mappings and rejects conflicts', () => {
    const shared = new Map([['Candidate.name', 'Application.candidate_name']]);
    expect(planReferenceMappingChanges({
      targetEntity: 'Application',
      beforeFields: [],
      afterFields: [referenceField('candidate_name')],
      referenceMappingsUsedByOtherForms: shared,
    })).toEqual([]);

    expect(() => planReferenceMappingChanges({
      targetEntity: 'Application',
      beforeFields: [],
      afterFields: [referenceField('different_name')],
      referenceMappingsUsedByOtherForms: shared,
    })).toThrow(
      "Reference 'Candidate.name' is already mapped to 'Application.candidate_name' by another form.",
    );
  });
});

test.describe('reference mapping application', () => {
  test('rolls back earlier relation updates after a later failure', async () => {
    const calls: Array<[string, Record<string, unknown>]> = [];
    const update = async (relationDefId: string, metadata: Record<string, unknown>) => {
      calls.push([relationDefId, metadata]);
      if (relationDefId === 'relation-2') throw new Error('update failed');
    };

    await expect(applyReferenceMappingChanges([
      { relationDefId: 'relation-1', original: { old: 1 }, next: { next: 1 } },
      { relationDefId: 'relation-2', original: { old: 2 }, next: { next: 2 } },
    ], update)).rejects.toThrow('update failed');

    expect(calls).toEqual([
      ['relation-1', { next: 1 }],
      ['relation-2', { next: 2 }],
      ['relation-1', { old: 1 }],
    ]);
  });

  test('resolves and applies a prepared cross-entity mapping', async () => {
    const updates: Array<[string, Record<string, unknown>]> = [];
    const dependencies: ReferenceMappingDependencies = {
      listEntityTypes: async () => ({ items: [
        { id: 'candidate-id', name: 'Candidate' },
        { id: 'application-id', name: 'Application' },
      ] }),
      getDeclarationForPair: async () => ({
        relation_def_id: 'relation-id',
        relation_metadata: { existing: 'mapping' },
      }),
      updateMapping: async (id, metadata) => { updates.push([id, metadata]); },
    };
    const prepared = await prepareReferenceMappingChangeWithDependencies({
      targetEntity: 'Application',
      beforeFields: [],
      afterFields: [referenceField('candidate_name')],
      referenceMappingsUsedByOtherForms: new Map(),
    }, dependencies);

    await prepared.apply();

    expect(updates).toEqual([['relation-id', {
      existing: 'mapping',
      'Candidate.name': 'Application.candidate_name',
    }]]);
  });

  test('reports missing relation declarations', async () => {
    const dependencies: ReferenceMappingDependencies = {
      listEntityTypes: async () => ({ items: [
        { id: 'candidate-id', name: 'Candidate' },
        { id: 'application-id', name: 'Application' },
      ] }),
      getDeclarationForPair: async () => { throw new Error('not found'); },
      updateMapping: async () => undefined,
    };

    await expect(prepareReferenceMappingChangeWithDependencies({
      targetEntity: 'Application',
      beforeFields: [],
      afterFields: [referenceField('candidate_name')],
      referenceMappingsUsedByOtherForms: new Map(),
    }, dependencies)).rejects.toThrow(
      "Create a relation from 'Candidate' to 'Application' before copying its reference fields.",
    );
  });

  test('reports missing target entity types before resolving relations', async () => {
    const dependencies: ReferenceMappingDependencies = {
      listEntityTypes: async () => ({ items: [
        { id: 'candidate-id', name: 'Candidate' },
      ] }),
      getDeclarationForPair: async () => {
        throw new Error('should not be called');
      },
      updateMapping: async () => undefined,
    };

    await expect(prepareReferenceMappingChangeWithDependencies({
      targetEntity: 'Application',
      beforeFields: [],
      afterFields: [referenceField('candidate_name')],
      referenceMappingsUsedByOtherForms: new Map(),
    }, dependencies)).rejects.toThrow("Entity type 'Application' was not found.");
  });
});
