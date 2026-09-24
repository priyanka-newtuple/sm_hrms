import type { CustomFormSchema } from '../../types/customForms';
import { request } from './client';
import { queryClient } from '../../queryClient';
import { workflowEntityKeys } from './queryKeys';
import type { AvailableTransition } from '../../types';

export interface WorkflowEntityState {
  state_id?: string;
  entity_id: string;
  entity_type_id?: string;
  entity_type: string;
  organization_id: string;
  machine_name: string;
  machine_version: number;
  workflow_id?: string;
  current_state: string;
  /** Prose description of the current state, when the workflow defines one. */
  current_state_description?: string;
  state_version: number;
  owner_id?: string;
  owner_name?: string;
  assignee_id?: string;
  assignee_name?: string;
  due_date?: string;
  data: Record<string, unknown>;
  custom_form_schema?: Record<string, CustomFormSchema>;
  custom_form_data?: Record<string, unknown>;
  state_entered_at?: string;
  last_transition_at?: string;
  sla_due_at?: string;
  created_at?: string;
  updated_at?: string;
  archived_at?: string;
  preview_thumbnail_url?: string | null;
  display_name?: string;
  machine_display_name?: string;
  transition_options?: AvailableTransition[];
}

interface WorkflowEnrollmentSummaryPage {
  items: Array<{
    state_id: string;
    entity_id: string;
    entity_type_id: string;
    entity_type: string;
    organization_id: string;
    workflow_id: string;
    machine_name: string;
    machine_display_name: string;
    machine_version: number;
    current_state: string;
    state_version: number;
    display_name: string;
    summary_fields: Record<string, unknown>;
    transition_options?: AvailableTransition[];
    owner_id?: string;
    assignee_id?: string;
    due_date?: string;
    state_entered_at?: string;
    last_transition_at?: string;
    sla_due_at?: string;
    entity_created_at?: string;
    entity_updated_at?: string;
    archived_at?: string;
    preview_thumbnail_url?: string | null;
  }>;
  has_more: boolean;
  state_counts?: Record<string, number> | null;
  total_count?: number | null;
  identifier_options?: string[] | null;
  field_totals?: Record<string, FieldTotalValue | FieldTotalError> | null;
  /** Server hit a bounded row-scan cap: counts understate and `has_more` can
   *  be a false negative. Only reachable for roles whose read permission
   *  carries a condition that must be evaluated on a loaded record. */
  scan_truncated?: boolean;
}

interface EntityRecordSummaryPage {
  items: Array<{
    entity_id: string;
    organization_id: string;
    entity_type_id: string;
    entity_type: string;
    display_name: string;
    summary_fields: Record<string, unknown>;
    owner_id?: string;
    assignee_id?: string;
    due_date?: string;
    created_at?: string;
    updated_at?: string;
    archived_at?: string;
  }>;
  next_cursor?: string | null;
  has_more: boolean;
}

interface EntityRecordResponse {
  entity_id: string;
  organization_id: string;
  entity_type_id: string;
  data: Record<string, unknown>;
  custom_form_schema?: Record<string, CustomFormSchema>;
  custom_form_data?: Record<string, unknown>;
  owner_id?: string;
  assignee_id?: string;
  due_date?: string;
  created_at?: string;
  updated_at?: string;
  archived_at?: string;
}

interface EntityStateRow {
  state_id: string;
  organization_id: string;
  entity_id: string;
  workflow_id: string;
  current_state: string;
  state_version: number;
  state_entered_at?: string;
  last_transition_at?: string;
  sla_due_at?: string;
  created_at?: string;
  updated_at?: string;
}

interface EntityWithStatesResponse {
  entity: EntityRecordResponse;
  states: EntityStateRow[];
}

export interface StateActionRerunResponse {
  run_id: string;
  entity_id: string;
  state: string;
  action_kinds: string[];
  status: string;
}

interface EntityTypeMaps {
  byId: Map<string, string>;
  byName: Map<string, string>;
}

let userNameCache: Promise<Map<string, string>> | null = null;

const loadUserNames = (): Promise<Map<string, string>> => {
  if (userNameCache) return userNameCache;
  userNameCache = request<Array<{ id: string; full_name?: string; email?: string }>>('/users')
    .then((resp) => {
      const byId = new Map<string, string>();
      for (const user of resp ?? []) {
        byId.set(user.id, user.full_name || user.email || user.id);
      }
      return byId;
    })
    .catch((err) => {
      userNameCache = null;
      throw err;
    });
  return userNameCache;
};

// Deliberately uncached — entity types are created/renamed/deleted during a
// session (e.g. from Settings) and this map is what resolves entity_type_id to
// a name for every record's route-matching filter. A stale, never-invalidated
// cache here previously meant a *newly created* entity type would resolve to
// its raw UUID for the rest of the browser tab's lifetime, silently failing
// every route-based filter and making all of that type's records disappear
// from the list — a real, hard-to-diagnose bug, not just a perf concern.
// `/entity-types` is a small, indexed, per-org lookup — cheap enough to fetch
// fresh every time rather than risk staleness.
const loadEntityTypeMaps = (): Promise<EntityTypeMaps> =>
  request<{ items: Array<{ entity_type_id: string; name: string }> }>('/entity-types').then(
    (resp) => {
      const byId = new Map<string, string>();
      const byName = new Map<string, string>();
      for (const item of resp.items ?? []) {
        byId.set(item.entity_type_id, item.name);
        byName.set(item.name, item.entity_type_id);
      }
      return { byId, byName };
    }
  );

const workflowVersionCache = new Map<string, number>();

export const mapEnrollmentSummary = (
  item: WorkflowEnrollmentSummaryPage['items'][number],
): WorkflowEntityState => ({
  state_id: item.state_id,
  entity_id: item.entity_id,
  entity_type_id: item.entity_type_id,
  entity_type: item.entity_type,
  organization_id: item.organization_id,
  machine_name: item.machine_name,
  machine_display_name: item.machine_display_name,
  machine_version: item.machine_version,
  workflow_id: item.workflow_id,
  current_state: item.current_state,
  state_version: item.state_version,
  display_name: item.display_name,
  data: item.summary_fields ?? {},
  transition_options: item.transition_options ?? [],
  owner_id: item.owner_id,
  assignee_id: item.assignee_id,
  due_date: item.due_date,
  state_entered_at: item.state_entered_at,
  last_transition_at: item.last_transition_at,
  sla_due_at: item.sla_due_at,
  created_at: item.entity_created_at,
  updated_at: item.entity_updated_at,
  archived_at: item.archived_at,
  preview_thumbnail_url: item.preview_thumbnail_url,
});

/** A column's total, with the currency the server confirmed it is in. */
export interface FieldTotalValue {
  total: number;
  /** Set only for a currency column whose rows all shared one code. */
  currency_code?: string | null;
}

/** Why one requested column has no single total, in place of a number. */
export interface FieldTotalError {
  error: 'mixed_currency';
  currency_codes: string[];
  message: string;
}

export const isFieldTotalError = (
  value: FieldTotalValue | FieldTotalError,
): value is FieldTotalError => 'error' in value;

export interface EnrollmentSummaryPageResult {
  items: WorkflowEntityState[];
  hasMore: boolean;
  stateCounts: Record<string, number> | null;
  totalCount: number | null;
  identifierOptions: string[] | null;
  /** Per-field totals across the whole filtered set, not just this page.
   *  Only present for fields requested via `sumFields` that the actor may
   *  actually read. */
  fieldTotals: Record<string, FieldTotalValue | FieldTotalError> | null;
  scanTruncated: boolean;
}

export const fetchEnrollmentSummaryPage = async (
  params: URLSearchParams,
): Promise<EnrollmentSummaryPageResult> => {
  // Owner/assignee names are not a server field — they're joined here from the
  // cached `/users` map. The paginated table and the Kanban columns fetch
  // through this function rather than the old full-drain `list`/`listAll`, so
  // the join has to live here or every Owner cell renders "Unassigned".
  const [page, userNames] = await Promise.all([
    request<WorkflowEnrollmentSummaryPage>(`/workflow-enrollments?${params.toString()}`),
    loadUserNames().catch(() => new Map<string, string>()),
  ]);
  return {
    items: (page.items ?? []).map((item) => {
      const entity = mapEnrollmentSummary(item);
      return {
        ...entity,
        owner_name: entity.owner_id ? userNames.get(entity.owner_id) ?? undefined : undefined,
        assignee_name: entity.assignee_id
          ? userNames.get(entity.assignee_id) ?? undefined
          : undefined,
      };
    }),
    hasMore: page.has_more,
    stateCounts: page.state_counts ?? null,
    totalCount: page.total_count ?? null,
    identifierOptions: page.identifier_options ?? null,
    fieldTotals: page.field_totals ?? null,
    scanTruncated: page.scan_truncated ?? false,
  };
};

/** Sentinel matching `UNASSIGNED_FILTER` in `useAssigneeFilter` and the
 *  backend's `UNASSIGNED_FILTER_SENTINEL` — kept as a plain string here (not
 *  re-exported from useAssigneeFilter) to avoid a core→pages import. */
const UNASSIGNED_SENTINEL = '__unassigned__';

export interface WorkflowEnrollmentFilterParams {
  thumbnailField?: string;
  anchorEntityId?: string | null;
  summaryFields?: string[];
  search?: string;
  assigneeIds?: string[];
  excludeStates?: string[];
  identifier?: string;
  /** Exact matches against entity data fields. A field mapped to an array is
   *  an OR across those values (e.g. a multi-select "labels" filter with
   *  several picks selected) — a row matches if it has ANY of them. */
  fieldFilters?: Record<string, string | string[]>;
  /** Numeric/currency columns to total across the whole filtered set. */
  sumFields?: string[];
}

/** Shared query-string builder for the column and table hooks — every filter
 *  they both understand, minus the pagination-mode-specific params
 *  (current_state/limit/cursor for columns; offset/sort for the table). */
export const buildEnrollmentQueryParams = (
  machineName: string,
  filters: WorkflowEnrollmentFilterParams,
): URLSearchParams => {
  const qs = new URLSearchParams();
  qs.set('machine_name', machineName);
  if (filters.thumbnailField) qs.set('thumbnail_field', filters.thumbnailField);
  if (filters.anchorEntityId) qs.set('anchor_entity_id', filters.anchorEntityId);
  if (filters.summaryFields?.length) qs.set('fields', filters.summaryFields.join(','));
  if (filters.search?.trim()) qs.set('search', filters.search.trim());
  if (filters.assigneeIds?.length) qs.set('assignee_ids', filters.assigneeIds.join(','));
  if (filters.excludeStates?.length) qs.set('exclude_states', filters.excludeStates.join(','));
  if (filters.identifier) qs.set('identifier', filters.identifier);
  if (filters.fieldFilters && Object.keys(filters.fieldFilters).length) {
    qs.set('field_filters', JSON.stringify(filters.fieldFilters));
  }
  if (filters.sumFields?.length) qs.set('sum_fields', filters.sumFields.join(','));
  return qs;
};

export { UNASSIGNED_SENTINEL as ENROLLMENT_UNASSIGNED_SENTINEL };

/** Org users for the assignee-filter dropdown — reuses the same cached
 *  `/users` fetch `mapEnrollmentSummary`'s owner/assignee name-joining
 *  already relies on, so this adds no new request in the common case where
 *  something has already resolved a name. Deliberately org-wide rather than
 *  "assignees seen so far in loaded rows": since the board/table no longer
 *  load everything up front, "seen so far" would make the dropdown grow
 *  arbitrarily incomplete depending on scroll/page position. */
export const listOrgUsers = async (): Promise<Array<{ id: string; name: string }>> => {
  const byId = await loadUserNames();
  return Array.from(byId, ([id, name]) => ({ id, name }));
};

const DRAIN_PAGE_SIZE = 200;
/** Hard stop on the drain loop. A `has_more` that never clears (server bug, a
 *  filter mutating under us) would otherwise spin forever; 500 pages at 200
 *  rows is far past any real workflow. */
const DRAIN_MAX_PAGES = 500;

const fetchAllEnrollmentSummaryPages = async (
  params: URLSearchParams,
): Promise<WorkflowEntityState[]> => {
  const items: WorkflowEntityState[] = [];
  for (let pageIndex = 0; pageIndex < DRAIN_MAX_PAGES; pageIndex += 1) {
    const pageParams = new URLSearchParams(params);
    pageParams.set('limit', String(DRAIN_PAGE_SIZE));
    pageParams.set('offset', String(pageIndex * DRAIN_PAGE_SIZE));
    const page = await request<WorkflowEnrollmentSummaryPage>(
      `/workflow-enrollments?${pageParams.toString()}`,
    );
    items.push(...(page.items ?? []).map(mapEnrollmentSummary));
    if (!page.has_more) break;
  }
  return items;
};

const resolveMachineVersion = async (machineName: string): Promise<number> => {
  const cached = workflowVersionCache.get(machineName);
  if (cached !== undefined) return cached;
  try {
    const machine = await request<{ version?: number }>(
      `/workflow-state-machines/${encodeURIComponent(machineName)}/active`
    );
    const version = machine.version ?? 0;
    workflowVersionCache.set(machineName, version);
    return version;
  } catch {
    return 0;
  }
};

const stubWorkflowEntity = (
  record: EntityRecordResponse,
  entityTypeName: string
): WorkflowEntityState => ({
  entity_id: record.entity_id,
  entity_type: entityTypeName,
  organization_id: record.organization_id,
  machine_name: '',
  machine_version: 0,
  current_state: 'CREATED',
  state_version: 0,
  owner_id: record.owner_id,
  assignee_id: record.assignee_id,
  due_date: record.due_date,
  data: { ...(record.data ?? {}) },
  created_at: record.created_at,
  updated_at: record.updated_at,
  archived_at: record.archived_at,
});

const mergeRecordWithState = async (
  record: EntityRecordResponse,
  state: EntityStateRow,
  entityTypeName: string
): Promise<WorkflowEntityState> => {
  return {
    entity_id: record.entity_id,
    entity_type: entityTypeName,
    organization_id: record.organization_id,
    machine_name: '',
    machine_version: 0,
    // The list path maps this; the single-entity path forgot it, so any
    // consumer resolving the workflow FROM the entity (rather than a
    // /pipeline/:id URL) saw workflow_id undefined and no board data.
    workflow_id: state.workflow_id,
    current_state: state.current_state,
    state_version: state.state_version,
    owner_id: record.owner_id,
    assignee_id: record.assignee_id,
    due_date: record.due_date,
    data: { ...(record.data ?? {}) },
    custom_form_schema: record.custom_form_schema,
    custom_form_data: record.custom_form_data,
    state_entered_at: state.state_entered_at,
    last_transition_at: state.last_transition_at,
    sla_due_at: state.sla_due_at,
    created_at: record.created_at,
    updated_at: record.updated_at,
    archived_at: record.archived_at,
  };
};

/**
 * Fetch a fresh SAS thumbnail URL for an entity's blob field.
 * Returns null when the request fails or the field path is invalid.
 */
export async function getEntityThumbnailUrl(
  entityId: string,
  field: string,
): Promise<string | null> {
  try {
    const result = await request<{ url: string | null }>(
      `/entity-records/${encodeURIComponent(entityId)}/thumbnail-url?field=${encodeURIComponent(field)}`,
    );
    return result.url ?? null;
  } catch (err) {
    console.warn('Failed to refresh thumbnail URL for entity', entityId, err);
    return null;
  }
}

export const workflowEntities = {
  list: async (
    machineName?: string,
    currentState?: string,
    params?: {
      thumbnailField?: string;
      anchorEntityId?: string | null;
      summaryFields?: string[];
    }
  ): Promise<WorkflowEntityState[]> => {
    if (machineName) {
      const qsParams = new URLSearchParams();
      qsParams.set('machine_name', machineName);
      if (currentState) qsParams.set('current_state', currentState);
      if (params?.thumbnailField) qsParams.set('thumbnail_field', params.thumbnailField);
      if (params?.anchorEntityId) qsParams.set('anchor_entity_id', params.anchorEntityId);
      if (params?.summaryFields?.length) qsParams.set('fields', params.summaryFields.join(','));
      const [items, userNames] = await Promise.all([
        fetchAllEnrollmentSummaryPages(qsParams),
        loadUserNames().catch(() => new Map<string, string>()),
      ]);
      return items.map((item) => ({
        ...item,
        owner_name: item.owner_id ? userNames.get(item.owner_id) ?? undefined : undefined,
        assignee_name: item.assignee_id ? userNames.get(item.assignee_id) ?? undefined : undefined,
      }));
    }
    const items: WorkflowEntityState[] = [];
    let cursor: string | null = null;
    do {
      const qs = new URLSearchParams({ limit: '200' });
      if (params?.anchorEntityId) qs.set('anchor_entity_id', params.anchorEntityId);
      if (params?.summaryFields?.length) qs.set('fields', params.summaryFields.join(','));
      if (cursor) qs.set('cursor', cursor);
      const page = await request<EntityRecordSummaryPage>(`/entity-records/summary?${qs}`);
      items.push(
        ...(page.items ?? []).map((item) => ({
          entity_id: item.entity_id,
          entity_type_id: item.entity_type_id,
          entity_type: item.entity_type,
          organization_id: item.organization_id,
          machine_name: '',
          machine_version: 0,
          current_state: 'CREATED',
          state_version: 0,
          display_name: item.display_name,
          data: item.summary_fields ?? {},
          owner_id: item.owner_id,
          assignee_id: item.assignee_id,
          due_date: item.due_date,
          created_at: item.created_at,
          updated_at: item.updated_at,
          archived_at: item.archived_at,
        })),
      );
      cursor = page.has_more ? page.next_cursor ?? null : null;
    } while (cursor);
    return items;
  },

  // Org-wide aggregate: every entity enrolled across all workflows.
  listAll: async (params?: {
    entityType?: string;
    includeArchived?: boolean;
    anchorEntityId?: string | null;
    summaryFields?: string[];
  }): Promise<WorkflowEntityState[]> => {
    const qs = new URLSearchParams();
    if (params?.entityType) qs.set('entity_type_name', params.entityType);
    if (params?.includeArchived) qs.set('include_archived', 'true');
    if (params?.anchorEntityId) qs.set('anchor_entity_id', params.anchorEntityId);
    if (params?.summaryFields?.length) qs.set('fields', params.summaryFields.join(','));
    const [items, userNames] = await Promise.all([
      fetchAllEnrollmentSummaryPages(qs),
      loadUserNames().catch(() => new Map<string, string>()),
    ]);
    return items.map((item) => ({
      ...item,
      owner_name: item.owner_id ? userNames.get(item.owner_id) ?? undefined : undefined,
      assignee_name: item.assignee_id ? userNames.get(item.assignee_id) ?? undefined : undefined,
    }));
  },

  create: async (payload: {
    entity_type: string;
    machine_name?: string;
    data: Record<string, unknown>;
    due_date?: string | null;
    schema_fields?: Array<Record<string, unknown>>;
    source_entity_ids?: string[];
  }): Promise<WorkflowEntityState> => {
    const maps = await loadEntityTypeMaps();
    const entityTypeId = maps.byName.get(payload.entity_type);
    if (!entityTypeId) {
      throw new Error(`unknown entity_type '${payload.entity_type}'`);
    }
    const created = await request<EntityRecordResponse>('/entity-records', {
      method: 'POST',
      body: JSON.stringify({
        entity_type_id: entityTypeId,
        data: payload.data,
        due_date: payload.due_date,
        ...(payload.source_entity_ids?.length
          ? { source_entity_ids: payload.source_entity_ids }
          : {}),
      }),
    });
    const entityId = created.entity_id;
    if (payload.machine_name) {
      return workflowEntities.enroll(payload.machine_name, entityId);
    }
    return workflowEntities.get(entityId);
  },

  // Enroll an existing (already-created) entity into a workflow's active version, so
  // it gets a current_state and shows up on that workflow's board. Entities created
  // via an agent tool call (e.g. document-upload-driven creation) aren't enrolled by
  // that path, so callers with workflow context enroll them explicitly afterward.
  enroll: async (machineName: string, entityId: string): Promise<WorkflowEntityState> => {
    const enrolled = await request<WorkflowEntityState>(
      `/workflow-state-machines/${encodeURIComponent(machineName)}/enrollments`,
      {
        method: 'POST',
        body: JSON.stringify({ entity_id: entityId }),
      }
    );
    void queryClient.invalidateQueries({ queryKey: workflowEntityKeys.all() });
    return enrolled;
  },

  update: async (
    entityId: string,
    payload: {
      data?: Record<string, unknown>;
      due_date?: string | null;
      schema_fields?: Array<Record<string, unknown>>;
      /** Link additional provider records after the fact — e.g. an entity created via an
       * agent tool call has no source links yet. Matched to active relation declarations
       * the same way create() does; a declaration already linked is left untouched. */
      source_entity_ids?: string[];
      custom_form_data?: Record<string, unknown>;
    }
  ): Promise<WorkflowEntityState> => {
    await request<EntityRecordResponse>(`/entity-records/${entityId}`, {
      method: 'PUT',
      body: JSON.stringify({
        ...(payload.data ? { data: payload.data } : {}),
        ...(Object.hasOwn(payload, 'due_date') ? { due_date: payload.due_date } : {}),
        ...(payload.source_entity_ids?.length
          ? { source_entity_ids: payload.source_entity_ids }
          : {}),
        ...(payload.custom_form_data && Object.keys(payload.custom_form_data).length > 0
          ? { custom_form_data: payload.custom_form_data }
          : {}),
      }),
    });
    void queryClient.invalidateQueries({ queryKey: workflowEntityKeys.all() });
    return workflowEntities.get(entityId);
  },

  // Assign the entity to a user, or clear it (pass null to unassign).
  setAssignee: async (
    entityId: string,
    assigneeId: string | null
  ): Promise<WorkflowEntityState> => {
    await request<EntityRecordResponse>(`/entity-records/${entityId}/assignee`, {
      method: 'PUT',
      body: JSON.stringify({ assignee_id: assigneeId }),
    });
    void queryClient.invalidateQueries({ queryKey: workflowEntityKeys.all() });
    return workflowEntities.get(entityId);
  },

  // Assign the entity to whoever originally created it. The originator is
  // resolved server-side from the record's creation history — the client never
  // sends a user id for this mode.
  assignToOriginator: async (entityId: string): Promise<WorkflowEntityState> => {
    await request<EntityRecordResponse>(`/entity-records/${entityId}/assignee`, {
      method: 'PUT',
      body: JSON.stringify({ assign_to_originator: true }),
    });
    void queryClient.invalidateQueries({ queryKey: workflowEntityKeys.all() });
    return workflowEntities.get(entityId);
  },

  delete: async (entityId: string): Promise<void> => {
    await request<EntityRecordResponse>(`/entity-records/${entityId}`, {
      method: 'DELETE',
    });
    void queryClient.invalidateQueries({ queryKey: workflowEntityKeys.all() });
  },

  // actionIndex re-runs just that one action, isolated; omit for the whole chain.
  rerunStateAction: (
    entityId: string,
    actionIndex?: number,
    workflowId?: string
  ): Promise<StateActionRerunResponse> =>
    request<StateActionRerunResponse>(
      `/entities/${encodeURIComponent(entityId)}/actions/rerun${workflowId ? `?workflow_id=${encodeURIComponent(workflowId)}` : ''}`,
      {
        method: 'POST',
        body: JSON.stringify(actionIndex != null ? { action_index: actionIndex } : {}),
      }
    ),

  get: async (entityId: string): Promise<WorkflowEntityState> => {
    const [resp, maps] = await Promise.all([
      request<EntityWithStatesResponse>(`/entity-records/${entityId}/with-states`),
      loadEntityTypeMaps(),
    ]);
    const entityTypeName =
      maps.byId.get(resp.entity.entity_type_id) ?? resp.entity.entity_type_id;
    if (resp.states.length === 0) {
      return stubWorkflowEntity(resp.entity, entityTypeName);
    }
    const primary = resp.states[0];
    const merged = await mergeRecordWithState(resp.entity, primary, entityTypeName);
    try {
      const machine = await request<{ machine_name?: string; version?: number }>(
        `/workflow-state-machines/${primary.workflow_id}`
      );
      if (machine.machine_name) {
        merged.machine_name = machine.machine_name;
        merged.machine_version = machine.version ?? (
          await resolveMachineVersion(machine.machine_name)
        );
      }
    } catch {
      // ignore: leave machine_name empty
    }
    return merged;
  },
};
