import { useEffect, useState } from 'react';
import { fieldLibrary, methodLibrary, METHOD_LIBRARY_MAX_LIMIT } from '@/core/services/api';
import type { FormSchema, MethodWithFields, StateMachineRecord } from '@/core/types';
import { buildFallbackFormSchemaFromEntitySchema } from '@/lib/state-machine/entitySchema';
import { buildFieldTypeCatalogue, fieldsForMethod } from '@/lib/state-machine/methodFields';
import type { ResolvedMethodSchema, StateMachineDefinition } from '@/lib/state-machine/types';
import { normalizeEntityType } from './helpers';

type WorkflowMethodDefinition = Pick<StateMachineDefinition, 'initial_state' | 'method_schemas'>;

function definitionFor(workflow: StateMachineRecord): WorkflowMethodDefinition | null {
  const candidate = workflow.definition as Partial<WorkflowMethodDefinition> | undefined;
  if (typeof candidate?.initial_state !== 'string') return null;
  return {
    initial_state: candidate.initial_state,
    method_schemas: candidate.method_schemas,
  };
}

/**
 * Resolves all Method Library schemas for an entity type. `loading` remains
 * true until the stored result was produced for the current entity type.
 */
export function useEntityTypeMethodSchemas(entityType: string): {
  schemas: FormSchema[];
  loading: boolean;
  error: string | null;
} {
  const [result, setResult] = useState<{ entityType: string; schemas: FormSchema[]; error: string | null }>({
    entityType: '',
    schemas: [],
    error: null,
  });

  useEffect(() => {
    if (!entityType) {
      return;
    }
    let cancelled = false;
    Promise.all([
      methodLibrary.list({ entityType, limit: METHOD_LIBRARY_MAX_LIMIT }),
      fieldLibrary.listFieldTypes(),
    ])
      .then(async ([methods, fieldTypes]) => {
        const details: MethodWithFields[] = [];
        const batchSize = 8;
        for (let index = 0; index < methods.items.length; index += batchSize) {
          const batch = methods.items.slice(index, index + batchSize);
          details.push(...await Promise.all(batch.map((method) => methodLibrary.get(method.method_id))));
        }
        if (cancelled) return;
        const catalogue = buildFieldTypeCatalogue(fieldTypes.items);
        setResult({
          entityType,
          schemas: details
            .map((method, index) => methodSchemaFromLibrary(entityType, method, catalogue, index))
            .filter((schema): schema is FormSchema => schema !== null),
          error: null,
        });
      })
      .catch((error: unknown) => {
        console.warn('Failed to load method schemas:', error);
        if (!cancelled) {
          setResult({ entityType, schemas: [], error: 'Could not load forms. Please try again.' });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [entityType]);

  if (!entityType) return { schemas: [], loading: false, error: null };
  return {
    schemas: result.entityType === entityType ? result.schemas : [],
    loading: result.entityType !== entityType,
    error: result.entityType === entityType ? result.error : null,
  };
}

export function methodSchemasForWorkflowInitialState(
  workflows: StateMachineRecord[],
  entityType: string,
  selectedMachineName: string,
): FormSchema[] {
  const workflow = workflows.find((candidate) => candidate.machine_name === selectedMachineName);
  const definition = workflow ? definitionFor(workflow) : null;
  return methodSchemasForWorkflowState(workflow, entityType, definition?.initial_state ?? '');
}

export function methodSchemasForWorkflowState(
  workflow: StateMachineRecord | undefined,
  entityType: string,
  stateName: string,
): FormSchema[] {
  const target = normalizeEntityType(entityType);
  const definition = workflow ? definitionFor(workflow) : null;
  if (!workflow || !definition || normalizeEntityType(workflow.entity_type) !== target) return [];
  return (definition.method_schemas ?? [])
    .filter((method) => method.state_name === stateName)
    .map((method, index) => methodSchemaFromSnapshot(workflow.entity_type, method, index))
    .filter((schema): schema is FormSchema => schema !== null);
}

function methodSchemaFromLibrary(
  entityType: string,
  method: MethodWithFields,
  catalogue: ReturnType<typeof buildFieldTypeCatalogue>,
  displayOrder: number,
): FormSchema | null {
  return buildFallbackFormSchemaFromEntitySchema(entityType, fieldsForMethod(method.fields, catalogue), {
    schemaKey: `method:${method.identity.method_id}:${method.version.version_id}`,
    name: method.identity.name,
    version: method.version.version,
    displayOrder,
    allowEmpty: true,
  });
}

function methodSchemaFromSnapshot(
  entityType: string,
  method: ResolvedMethodSchema,
  displayOrder: number,
): FormSchema | null {
  return buildFallbackFormSchemaFromEntitySchema(entityType, method.fields, {
    schemaKey: `method:${method.method_id}:${method.version_id}`,
    name: method.method_name,
    version: method.version,
    displayOrder,
    allowEmpty: true,
  });
}
