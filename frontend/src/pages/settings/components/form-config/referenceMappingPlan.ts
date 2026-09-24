import type { FormField } from '../../../../core/types';
import type { StoredFormField } from '../../../../core/types/portableForm';

const REFERENCE_DESCRIPTION_PREFIX = '__ref__:';

interface ReferenceMapping {
  sourceEntity: string;
  sourceField: string;
  targetField: string;
}

/** One intended relation metadata mutation before entity IDs are resolved. */
export interface PlannedMappingChange {
  sourceEntity: string;
  key: string;
  target: string | null;
}

/** One relation metadata mutation with rollback state and a relation ID. */
export interface ResolvedMappingChange {
  relationDefId: string;
  original: Record<string, unknown>;
  next: Record<string, unknown>;
}

/** Form fields and existing ownership needed to calculate relation changes. */
export interface ReferenceMappingChangeParams {
  targetEntity: string;
  beforeFields: StoredFormField[];
  afterFields: StoredFormField[];
  referenceMappingsUsedByOtherForms: Map<string, string>;
}

/** Entity-relation operations injected into reference change preparation. */
export interface ReferenceMappingDependencies {
  listEntityTypes: () => Promise<{
    items?: Array<{ name: string; entity_type_id?: string; id: string }>;
  }>;
  getDeclarationForPair: (
    sourceEntityTypeId: string,
    targetEntityTypeId: string,
  ) => Promise<{
    relation_def_id: string;
    relation_metadata?: Record<string, unknown> | null;
  }>;
  updateMapping: (
    relationDefId: string,
    metadata: Record<string, unknown>,
  ) => Promise<unknown>;
}

/** Deferred relation update prepared before the form mutation is persisted. */
export interface PreparedReferenceMappingChange {
  apply: () => Promise<void>;
}

/** Normalize an entity type name for relation matching. */
export function normalizedEntityName(value: string): string {
  return value.replace(/^ATS\./i, '').trim().toLowerCase();
}

function referenceKey(reference: ReferenceMapping): string {
  return `${reference.sourceEntity}.${reference.sourceField}`;
}

function referencesByKey(fields: StoredFormField[]): Map<string, ReferenceMapping> {
  const references = fields
    .map(referenceFromStoredField)
    .filter((reference): reference is ReferenceMapping => reference !== null);
  return new Map(references.map((reference) => [referenceKey(reference), reference]));
}

/** Extract a reference mapping encoded in a stored field description. */
export function referenceFromStoredField(field: StoredFormField): ReferenceMapping | null {
  if (typeof field.description !== 'string' || !field.description.startsWith(REFERENCE_DESCRIPTION_PREFIX)) {
    return null;
  }
  const [sourceEntity, sourceField] = field.description
    .slice(REFERENCE_DESCRIPTION_PREFIX.length)
    .split(':');
  if (!sourceEntity?.trim() || !sourceField?.trim()) return null;
  return {
    sourceEntity: sourceEntity.trim(),
    sourceField: sourceField.trim(),
    targetField: field.field,
  };
}

/** Build the canonical relation-mapping key for a visual reference field. */
export function referenceKeyFromFormField(field: FormField): string | null {
  if (field.type !== 'reference' || !field.source_entity || !field.source_field) return null;
  return `${field.source_entity}.${field.source_field}`;
}

/** Calculate reference mapping mutations without performing API requests. */
export function planReferenceMappingChanges(
  params: ReferenceMappingChangeParams,
): PlannedMappingChange[] {
  const beforeByKey = referencesByKey(params.beforeFields);
  const afterByKey = referencesByKey(params.afterFields);
  const planned: PlannedMappingChange[] = [];
  for (const key of new Set([...beforeByKey.keys(), ...afterByKey.keys()])) {
    const previous = beforeByKey.get(key);
    const desired = afterByKey.get(key);
    const reference = desired ?? previous;
    if (reference && normalizedEntityName(reference.sourceEntity) === normalizedEntityName(params.targetEntity)) {
      continue;
    }
    const desiredTarget = desired ? `${params.targetEntity}.${desired.targetField}` : null;
    const otherFormTarget = params.referenceMappingsUsedByOtherForms.get(key);
    if (otherFormTarget && desiredTarget && otherFormTarget !== desiredTarget) {
      throw new Error(`Reference '${key}' is already mapped to '${otherFormTarget}' by another form.`);
    }
    if (otherFormTarget || previous?.targetField === desired?.targetField || !reference) continue;
    planned.push({ sourceEntity: reference.sourceEntity, key, target: desiredTarget });
  }
  return planned;
}

/** Apply relation metadata changes and roll back earlier updates after a failure. */
export async function applyReferenceMappingChanges(
  changes: ResolvedMappingChange[],
  updateMapping: (
    relationDefId: string,
    metadata: Record<string, unknown>,
  ) => Promise<unknown>,
): Promise<void> {
  const applied: ResolvedMappingChange[] = [];
  try {
    for (const change of changes) {
      await updateMapping(change.relationDefId, change.next);
      applied.push(change);
    }
  } catch (error) {
    await Promise.allSettled(
      applied.map((change) => updateMapping(change.relationDefId, change.original)),
    );
    throw error;
  }
}

function entityTypeIdsByName(
  items: Array<{ name: string; entity_type_id?: string; id: string }>,
): Map<string, string> {
  return new Map(items.map((type) => [
    normalizedEntityName(type.name),
    type.entity_type_id ?? type.id,
  ]));
}

function changesBySourceEntity(
  planned: PlannedMappingChange[],
): Map<string, PlannedMappingChange[]> {
  const grouped = new Map<string, PlannedMappingChange[]>();
  for (const change of planned) {
    const key = normalizedEntityName(change.sourceEntity);
    grouped.set(key, [...(grouped.get(key) ?? []), change]);
  }
  return grouped;
}

async function relationDeclaration(
  sourceEntity: string,
  targetEntity: string,
  sourceTypeId: string,
  targetTypeId: string,
  dependencies: ReferenceMappingDependencies,
) {
  try {
    return await dependencies.getDeclarationForPair(sourceTypeId, targetTypeId);
  } catch {
    throw new Error(
      `Create a relation from '${sourceEntity}' to '${targetEntity}' before copying its reference fields.`,
    );
  }
}

async function resolveMappingChanges(
  targetEntity: string,
  planned: PlannedMappingChange[],
  dependencies: ReferenceMappingDependencies,
): Promise<ResolvedMappingChange[]> {
  const response = await dependencies.listEntityTypes();
  const typeIds = entityTypeIdsByName(response.items ?? []);
  const targetTypeId = typeIds.get(normalizedEntityName(targetEntity));
  if (!targetTypeId) throw new Error(`Entity type '${targetEntity}' was not found.`);

  const resolved: ResolvedMappingChange[] = [];
  for (const [sourceName, sourceChanges] of changesBySourceEntity(planned)) {
    const sourceTypeId = typeIds.get(sourceName);
    const sourceEntity = sourceChanges[0]?.sourceEntity ?? sourceName;
    if (!sourceTypeId) throw new Error(`Referenced entity type '${sourceEntity}' was not found.`);
    const declaration = await relationDeclaration(
      sourceEntity, targetEntity, sourceTypeId, targetTypeId, dependencies,
    );
    const original = { ...(declaration.relation_metadata ?? {}) };
    const next = { ...original };
    for (const change of sourceChanges) {
      if (change.target) next[change.key] = change.target;
      else delete next[change.key];
    }
    if (JSON.stringify(original) !== JSON.stringify(next)) {
      resolved.push({ relationDefId: declaration.relation_def_id, original, next });
    }
  }
  return resolved;
}

/** Prepare reference changes using injected entity-relation dependencies. */
export async function prepareReferenceMappingChangeWithDependencies(
  params: ReferenceMappingChangeParams,
  dependencies: ReferenceMappingDependencies,
): Promise<PreparedReferenceMappingChange> {
  const planned = planReferenceMappingChanges(params);
  if (planned.length === 0) return { apply: async () => undefined };
  const changes = await resolveMappingChanges(params.targetEntity, planned, dependencies);
  return {
    apply: () => applyReferenceMappingChanges(changes, dependencies.updateMapping),
  };
}
