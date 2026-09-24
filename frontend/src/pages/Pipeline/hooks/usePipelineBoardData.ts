import { useEffect, useMemo, useState } from 'react';
import { useEntitySchemasForState, useWorkflow } from '@/shared/hooks';
import { usePermissions } from '@/core/hooks/usePermissions';
import { useSkin, type EntityViewConfig } from '@/skins';
import { deriveViewModelFromRecord } from '@/shared/utils/pipelineViewModel';
import { getEntityPrimaryValue } from '@/shared/utils/entityDisplay';
import { resolveEntityTypeLabel } from '@/shared/utils/labels';
import type { DemoEntityCard, PipelineListEntity } from '@/shared/types/pipeline';
import type { WorkflowEntityState } from '@/core/services/api';
import type { FormSchema } from '@/core/types';
import { PLACEHOLDER_ENTITY_TYPE } from '@/lib/state-machine/types';
import {
  buildFallbackFormSchemasFromEntitySchema,
  inheritedMappingsForEntityType,
  withInheritedReferenceFields,
} from '@/lib/state-machine/entitySchema';
import { entityRelations, entityTypes as entityTypesApi } from '@/core/services/api';
import type { RelationDeclaration } from '@/core/types';
import type { StateMachineDefinition } from '@/lib/state-machine/types';

export function toDemoCard(entity: WorkflowEntityState): DemoEntityCard {
  return {
    id: entity.entity_id,
    enrollmentId: entity.state_id,
    workflowId: entity.workflow_id,
    title: getEntityPrimaryValue(entity.data, entity.entity_id),
    subtitle: resolveEntityTypeLabel(entity.entity_type),
    stateId: entity.current_state,
    stateEnteredAt: entity.state_entered_at,
    slaDueAt: entity.sla_due_at,
    dueDate: entity.due_date,
    thumbnailUrl: entity.preview_thumbnail_url ?? undefined,
    assigneeName: entity.assignee_name,
    data: entity.data,
  };
}

export function toListEntity(entity: WorkflowEntityState): PipelineListEntity {
  const createdAt =
    entity.created_at ??
    entity.state_entered_at ??
    entity.last_transition_at ??
    entity.updated_at ??
    new Date().toISOString();
  const updatedAt =
    entity.updated_at ?? entity.last_transition_at ?? entity.state_entered_at ?? createdAt;

  return {
    entity_id: entity.entity_id,
    state_id: entity.state_id,
    workflow_id: entity.workflow_id,
    current_state: entity.current_state,
    created_at: createdAt,
    updated_at: updatedAt,
    data: entity.data,
    due_date: entity.due_date,
    assignee_id: entity.assignee_id,
    assignee_name: entity.assignee_name,
    transition_options: entity.transition_options,
  };
}

interface BoardFields {
  /** Fields to request in the enrollment `fields` query param — whatever a
   *  skin's view config needs for title/subtitle/list display, plus identifier
   *  and the thumbnail's own data field. */
  summaryFields: string[];
  /** Fields the default Kanban card already shows unconditionally (the card
   *  header's title/subtitle), when a skin configures them for this entity
   *  type. Surfaced so `useCardFieldsConfig` can exclude them from the "extra
   *  fields" picker — selecting one would just repeat what's already visible. */
  builtInCardFields: string[];
}

/** Pure — the skin/entity-type lookup behind both `summaryFields` and
 *  `builtInCardFields`, split out of the hook so it's unit-testable and the
 *  hook itself stays under the file's function-size limit. */
function deriveBoardFields(
  entityViews: EntityViewConfig[],
  thumbnailDataField: string | undefined,
  entityType: string | undefined,
): BoardFields {
  const entityView = entityViews.find((item) => item.entityType === entityType);
  const summaryFields = Array.from(
    new Set(
      [
        'identifier',
        ...(entityView
          ? [entityView.titleField, entityView.subtitleField, ...entityView.listFields.map((f) => f.source)]
          : []),
        ...(thumbnailDataField ? [thumbnailDataField.split('.', 1)[0]] : []),
      ].filter((field): field is string => Boolean(field)),
    ),
  );
  const builtInCardFields = [entityView?.titleField, entityView?.subtitleField].filter(
    (field): field is string => Boolean(field),
  );
  return { summaryFields, builtInCardFields };
}

/** Shared workflow + entity-schema loading for a single pipeline, used by
 *  both the /pipeline/:id page and the dashboard's embedded board widget.
 *  Entity *data* fetching is owned by the caller now: Kanban uses
 *  `useWorkflowColumnEntities` per column, the Table uses
 *  `usePaginatedPipelineList`, and Calendar (still full-drain, out of scope
 *  for this pass) fetches its own flat list directly via `useWorkflowEntities`
 *  gated on its tab being active. */
export function usePipelineBoardData(workflowId: string | undefined) {
  const { skin } = useSkin();
  const { workflow, loading, error } = useWorkflow(workflowId);
  const model = useMemo(
    () => (workflow ? deriveViewModelFromRecord(workflow) : null),
    [workflow],
  );

  const {
    schemas: formSchemas,
    loading: entitySchemasLoading,
    error: entitySchemasError,
  } = useEntitySchemasForState(workflow?.entity_type);

  // An entity type whose fields come from Method Blocks pinned to a workflow
  // state has no Forms config — publish merges those fields into the
  // workflow's own entity_schema and nothing propagates them to Forms. Without
  // a fallback every form-driven surface here reports "No form is configured"
  // even though the workflow knows the fields. A real form always wins; this
  // only fills a genuine absence.
  //
  // `schemasForState` narrows the fallback to one workflow state. Creation
  // passes the initial state (a new record starts there); a detail view passes
  // the record's current state. Omitting the state yields every field, which is
  // what surfaces with no state in hand (e.g. board-wide filters) still want.
  // Relation-inherited fields are declared on the relation, not on any Form or
  // entity_schema, so they have to be fetched separately and folded in.
  const [declarations, setDeclarations] = useState<RelationDeclaration[]>([]);
  const [typeNameById, setTypeNameById] = useState<Map<string, string>>(new Map());
  const boardEntityType = workflow?.entity_type;
  useEffect(() => {
    let cancelled = false;
    // No reset here: mappings are matched against the *current* entity type, so
    // declarations left over from a previous one can never resolve.
    if (!boardEntityType || boardEntityType === PLACEHOLDER_ENTITY_TYPE) return;
    void entityTypesApi
      .list()
      .then(async (types) => {
        if (cancelled) return;
        const byId = new Map<string, string>();
        let selfId: string | null = null;
        for (const item of types.items ?? []) {
          const id = item.entity_type_id ?? item.id;
          if (!id) continue;
          byId.set(id, item.name);
          if (item.name?.toLowerCase() === boardEntityType.toLowerCase()) selfId = id;
        }
        setTypeNameById(byId);
        if (!selfId) {
          setDeclarations([]);
          return;
        }
        const res = await entityRelations.listDeclarations(selfId, 'to');
        if (!cancelled) setDeclarations(res.items ?? []);
      })
      .catch(() => {
        // Inherited fields simply do not render; the rest of the board is fine.
        if (!cancelled) setDeclarations([]);
      });
    return () => {
      cancelled = true;
    };
  }, [boardEntityType]);

  const inheritedMappings = useMemo(
    () => inheritedMappingsForEntityType(boardEntityType, declarations, typeNameById),
    [boardEntityType, declarations, typeNameById],
  );

  const buildSchemas = useMemo(() => {
    const definition = workflow?.definition as StateMachineDefinition | undefined;
    const fields = definition?.entity_schema?.fields;
    return (stateName?: string, requireState = false): FormSchema[] => {
      const withInherited = (schemas: FormSchema[]) =>
        withInheritedReferenceFields(schemas, {
          entityType: workflow?.entity_type,
          mappings: inheritedMappings,
        });
      if (formSchemas.length > 0 || entitySchemasLoading) return withInherited(formSchemas);
      if (
        !workflow?.entity_type ||
        (!fields?.length && !definition?.method_schemas?.length)
      ) {
        return withInherited(formSchemas);
      }
      const fallback = buildFallbackFormSchemasFromEntitySchema(
        workflow.entity_type,
        fields ?? [],
        definition?.method_schemas,
        { stateName, requireState },
      );
      return withInherited(fallback.length > 0 ? fallback : formSchemas);
    };
  }, [formSchemas, entitySchemasLoading, workflow, inheritedMappings]);

  // Board-wide consumers (column picker, filter builders) want every field.
  const entitySchemas = useMemo(() => buildSchemas(), [buildSchemas]);
  const initialStateName = (workflow?.definition as StateMachineDefinition | undefined)
    ?.initial_state;
  /** Fields a brand-new record can fill: the initial state's own. */
  const creationSchemas = useMemo(
    () => buildSchemas(initialStateName),
    [buildSchemas, initialStateName],
  );

  // main's pure helper owns the skin/entity-type lookup; the inherited targets
  // are added on top of it. The summary resolver only overlays inherited fields
  // it was asked for, so an unrequested one comes back missing rather than empty.
  const { summaryFields: baseSummaryFields, builtInCardFields } = useMemo(
    () => deriveBoardFields(skin.entityViews, skin.board.thumbnailDataField, workflow?.entity_type),
    [skin.entityViews, skin.board.thumbnailDataField, workflow?.entity_type],
  );
  const summaryFields = useMemo(
    () =>
      Array.from(
        new Set([...baseSummaryFields, ...inheritedMappings.map((mapping) => mapping.targetField)]),
      ),
    [baseSummaryFields, inheritedMappings],
  );

  const { can } = usePermissions();
  const isPlaceholderEntityType = workflow?.entity_type === PLACEHOLDER_ENTITY_TYPE;
  const canView = !workflow || isPlaceholderEntityType || can('view', workflow.entity_type);
  const canCreate = !workflow || isPlaceholderEntityType || can('create', workflow.entity_type);

  return {
    workflow,
    loading,
    error,
    model,
    entitySchemas,
    creationSchemas,
    // Detail views render one record: an unknown state hides state-scoped
    // fields rather than falling back to showing all of them.
    schemasForState: (stateName?: string) => buildSchemas(stateName, true),
    entitySchemasLoading,
    entitySchemasError,
    summaryFields,
    builtInCardFields,
    canView,
    canCreate,
    isPlaceholderEntityType,
  };
}
