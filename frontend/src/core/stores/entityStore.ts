import { create } from 'zustand';
import {
  entityTypes as entityTypesApi,
  formSchemas as formSchemasApi,
  workflowEntities,
} from '../services/api';
import type { WorkflowEntityState } from '../services/api';
import type { EntityType, FormSchema } from '../types';
import { IDENTIFIER_FIELD_KEY } from '@/shared/utils/entityForm';

interface EntityStore {
  entities: WorkflowEntityState[];
  entityTypes: EntityType[];
  schemas: FormSchema[];
  loading: boolean;
  error: string | null;
  entityTypesError: string | null;
  schemasError: string | null;

  fetchAll: (anchorEntityId?: string | null) => Promise<void>;
  fetchSchemas: () => Promise<void>;
  addEntity: (entity: WorkflowEntityState) => void;
  patchEntity: (entityId: string, data: Record<string, unknown>) => void;
  deleteEntity: (entityId: string) => Promise<void>;
  clearError: () => void;
}

type AsyncResult<T> =
  | { status: 'fulfilled'; value: T }
  | { status: 'rejected'; reason: unknown };

const settle = <T>(promise: Promise<T>): Promise<AsyncResult<T>> =>
  promise.then(
    (value) => ({ status: 'fulfilled', value }),
    (reason) => ({ status: 'rejected', reason }),
  );

function activeSchemasFor(
  result: AsyncResult<Awaited<ReturnType<typeof formSchemasApi.list>>>,
): FormSchema[] {
  return result.status === 'fulfilled'
    ? result.value.items.filter((schema) => schema.is_active)
    : [];
}

function schemaResultState(
  result: AsyncResult<Awaited<ReturnType<typeof formSchemasApi.list>>>,
  schemas: FormSchema[],
): Pick<EntityStore, 'schemas' | 'schemasError'> {
  if (result.status === 'fulfilled') return { schemas, schemasError: null };
  console.warn('Failed to load form schemas (field labels unavailable):', result.reason);
  return {
    schemas: [],
    schemasError: result.reason instanceof Error ? result.reason.message : 'Failed to load forms',
  };
}

function entityTypeResultState(
  result: AsyncResult<Awaited<ReturnType<typeof entityTypesApi.list>>>,
): Partial<Pick<EntityStore, 'entityTypes' | 'entityTypesError'>> {
  if (result.status === 'fulfilled') {
    return {
      entityTypes: result.value.items.filter((entityType) => entityType.is_active),
      entityTypesError: null,
    };
  }
  console.warn('Failed to load entity types:', result.reason);
  return {
    entityTypesError: result.reason instanceof Error ? result.reason.message : 'Failed to load entity types',
  };
}

function entityResultState(
  entitiesResult: AsyncResult<WorkflowEntityState[]>,
  enrollmentsResult: AsyncResult<WorkflowEntityState[]>,
): Partial<Pick<EntityStore, 'entities' | 'error'>> {
  if (entitiesResult.status === 'rejected') {
    return { error: entitiesResult.reason instanceof Error ? entitiesResult.reason.message : 'Failed to load records' };
  }
  const enrollments = enrollmentsResult.status === 'fulfilled'
    ? new Map(enrollmentsResult.value.map((entity) => [entity.entity_id, entity]))
    : new Map<string, WorkflowEntityState>();
  const entities = Array.from(
    new Map(
      entitiesResult.value.map((entity) => {
        const enrollment = enrollments.get(entity.entity_id);
        return [
          entity.entity_id,
          enrollment
            ? { ...entity, ...enrollment, data: { ...entity.data, ...enrollment.data } }
            : entity,
        ];
      }),
    ).values(),
  );
  return { entities, error: null };
}

export const useEntityStore = create<EntityStore>((set) => ({
  entities: [],
  entityTypes: [],
  schemas: [],
  loading: false,
  error: null,
  entityTypesError: null,
  schemasError: null,

  fetchAll: async (anchorEntityId?: string | null) => {
    set({ loading: true, error: null, entityTypesError: null, schemasError: null });
    // Schemas determine the bounded summary projection. If the actor cannot
    // read them, the records endpoint still returns its safe title fields.
    const schemasResult = await settle(formSchemasApi.list());
    const entityTypesResult = await settle(entityTypesApi.list());

    const activeSchemas = activeSchemasFor(schemasResult);
    const summaryFields = Array.from(
      new Set(
        [
          IDENTIFIER_FIELD_KEY,
          ...activeSchemas.flatMap((schema) =>
            schema.schema.fields
              .filter((field) => field.type !== 'section' && field.type !== 'reference' && !field.system)
              .slice(0, 3)
              .map((field) => field.id),
          ),
        ],
      ),
    );
    const [entitiesResult, enrollmentsResult] = await Promise.all([
      settle(
        workflowEntities.list(undefined, undefined, {
          anchorEntityId,
          summaryFields,
        }),
      ),
      settle(
        workflowEntities.listAll({
          anchorEntityId,
          summaryFields,
        }),
      ),
    ]);

    set(schemaResultState(schemasResult, activeSchemas));
    set(entityTypeResultState(entityTypesResult));
    set(entityResultState(entitiesResult, enrollmentsResult));

    set({ loading: false });
  },

  fetchSchemas: async () => {
    try {
      const resp = await formSchemasApi.list();
      set({ schemas: resp.items.filter((s) => s.is_active), schemasError: null });
    } catch (e) {
      set({ schemasError: e instanceof Error ? e.message : 'Failed to load schemas' });
    }
  },

  addEntity: (entity) =>
    set((state) => ({
      entities: [...state.entities.filter((e) => e.entity_id !== entity.entity_id), entity],
    })),

  patchEntity: (entityId, data) => {
    set((state) => ({
      entities: state.entities.map((e) =>
        e.entity_id === entityId ? { ...e, data: { ...e.data, ...data } } : e
      ),
    }));
  },

  deleteEntity: async (entityId) => {
    await workflowEntities.delete(entityId);
    set((state) => ({
      entities: state.entities.filter((e) => e.entity_id !== entityId),
    }));
  },

  clearError: () => set({ error: null }),
}));

export function schemaForEntityType(
  schemas: FormSchema[],
  entityType: string
): FormSchema | null {
  const normalize = (value: string) =>
    value
      .replace(/^ATS\./i, '')
      .trim()
      .toLowerCase();

  const normalized = normalize(entityType);
  const exact = schemas.find((s) => normalize(s.entity_type) === normalized);
  if (exact) return exact;

  return (
    schemas.find((s) => {
      const normalizedSchemaType = normalize(s.entity_type);
      const schemaToken = normalizedSchemaType.replace(/\./g, '_');
      return normalized.includes(schemaToken);
    }) ?? null
  );
}
