import {
  entityRelations,
  entityTypes,
} from '../../../../core/services/api';
import {
  prepareReferenceMappingChangeWithDependencies,
  type PreparedReferenceMappingChange,
  type ReferenceMappingChangeParams,
  type ReferenceMappingDependencies,
} from './referenceMappingPlan';

export {
  referenceFromStoredField,
  referenceKeyFromFormField,
} from './referenceMappingPlan';

const defaultDependencies: ReferenceMappingDependencies = {
  listEntityTypes: () => entityTypes.list(),
  getDeclarationForPair: (sourceId, targetId) => (
    entityRelations.getDeclarationForPair(sourceId, targetId)
  ),
  updateMapping: (relationDefId, metadata) => (
    entityRelations.updateMapping(relationDefId, metadata)
  ),
};

/** Insert or replace one field mapping on an existing relation declaration. */
export async function upsertReferenceMapping(params: {
  sourceEntityTypeId: string;
  targetEntityTypeId: string;
  sourceEntity: string;
  sourceField: string;
  targetEntity: string;
  targetField: string;
}): Promise<void> {
  const declaration = await entityRelations.getDeclarationForPair(
    params.sourceEntityTypeId,
    params.targetEntityTypeId,
  );
  await entityRelations.updateMapping(declaration.relation_def_id, {
    ...(declaration.relation_metadata ?? {}),
    [`${params.sourceEntity}.${params.sourceField}`]: `${params.targetEntity}.${params.targetField}`,
  });
}

/** Remove one field mapping from an existing relation declaration. */
export async function removeReferenceMapping(params: {
  sourceEntityTypeId: string;
  targetEntityTypeId: string;
  sourceEntity: string;
  sourceField: string;
}): Promise<void> {
  const declaration = await entityRelations.getDeclarationForPair(
    params.sourceEntityTypeId,
    params.targetEntityTypeId,
  );
  const metadata = { ...(declaration.relation_metadata ?? {}) };
  delete metadata[`${params.sourceEntity}.${params.sourceField}`];
  await entityRelations.updateMapping(declaration.relation_def_id, metadata);
}

/** Prepare safe reference mapping changes for a form JSON create or update. */
export async function prepareReferenceMappingChange(
  params: ReferenceMappingChangeParams,
): Promise<PreparedReferenceMappingChange> {
  return prepareReferenceMappingChangeWithDependencies(params, defaultDependencies);
}
