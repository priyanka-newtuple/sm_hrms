import type { WorkflowEntityState } from '@/core/services/api';

interface WorkflowEntityIdentitySource {
  entity_id?: string | null;
  state_id?: string | null;
  workflow_id?: string | null;
}

/** Primitive identifiers that uniquely select one entity enrollment. */
export interface FullWorkflowEntityIdentity {
  entityId: string | null;
  stateId: string | null;
  workflowId: string | null;
}

/** Primitive enrollment identity used to decide when full hydration is required. */
export function fullWorkflowEntityIdentity(
  summary: WorkflowEntityIdentitySource | null,
): FullWorkflowEntityIdentity {
  return {
    entityId: summary?.entity_id ?? null,
    stateId: summary?.state_id ?? null,
    workflowId: summary?.workflow_id ?? null,
  };
}

/** Display selection and loading state while a summary hydrates to a full entity. */
export interface FullWorkflowEntityDisplay {
  displayedEntity: WorkflowEntityState | null;
  displayLoading: boolean;
  entityIsCurrent: boolean;
}

/**
 * Keeps a selected summary visible while its full record hydrates, without
 * briefly showing a fully hydrated record from the previously selected row.
 */
export function resolveFullWorkflowEntityDisplay(
  summary: WorkflowEntityState | null,
  entity: WorkflowEntityState | null,
  loading: boolean,
  error: string | null,
): FullWorkflowEntityDisplay {
  const summaryIdentity = fullWorkflowEntityIdentity(summary);
  const entityIdentity = fullWorkflowEntityIdentity(entity);
  // Match on entityId only (entity-identity, not same-enrollment).
  // stateId changes after a transition and workflowId may differ between
  // the list summary and the detail entity during the refetch window —
  // comparing them here caused a permanent mismatch that locked
  // displayLoading to true. Multi-enrollment correctness is handled
  // in useFullWorkflowEntity's merge/refetch logic instead.
  const entityIsCurrent = Boolean(
    summary
      && entity
      && summaryIdentity.entityId === entityIdentity.entityId,
  );

  return {
    displayedEntity: entityIsCurrent ? entity : summary,
    displayLoading: Boolean(summary && !error && (loading || !entityIsCurrent)),
    entityIsCurrent,
  };
}
