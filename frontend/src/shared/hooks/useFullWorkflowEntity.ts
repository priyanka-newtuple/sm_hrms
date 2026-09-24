import { useCallback, useEffect, useRef, useState } from 'react';

import { workflowEntities, type WorkflowEntityState } from '@/core/services/api';
import { fullWorkflowEntityIdentity } from './fullWorkflowEntityIdentity';

/** Load the full record only after a summary row/card has been selected. */
export function useFullWorkflowEntity(summary: WorkflowEntityState | null) {
  const [entity, setEntity] = useState<WorkflowEntityState | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { entityId, stateId, workflowId } = fullWorkflowEntityIdentity(summary);
  const summaryRef = useRef(summary);
  summaryRef.current = summary;

  // Monotonic counter — incremented on each fetch so late-arriving
  // responses from earlier requests are silently discarded.
  const fetchIdRef = useRef(0);

  const fetchEntity = useCallback((eid: string, sid: string | null, wid: string | null, showLoading = true, skipSummaryMerge = false) => {
    const id = ++fetchIdRef.current;
    if (showLoading) {
      setEntity(null);
      setLoading(true);
    }
    setError(null);
    void workflowEntities.get(eid).then(
      (fullEntity) => {
        if (fetchIdRef.current !== id) return; // stale
        if (skipSummaryMerge) {
          // Refetch path — use fresh server data for current_state and fields.
          // Preserve enrollment identity (workflow_id, machine_name) from the
          // previously loaded entity so multi-workflow entities stay on the
          // selected enrollment. workflowEntities.get() returns states[0]
          // which may differ from the user's selected enrollment.
          setEntity((prev) => {
            if (prev && prev.entity_id === eid && prev.workflow_id) {
              return {
                ...fullEntity,
                workflow_id: prev.workflow_id,
                machine_name: prev.machine_name,
                machine_version: prev.machine_version,
              };
            }
            return fullEntity;
          });
          setLoading(false);
          return;
        }
        const latestSummary = summaryRef.current;
        const sameEnrollment =
          latestSummary?.entity_id === eid &&
          latestSummary?.state_id === sid &&
          (latestSummary?.workflow_id ?? null) === wid;
        setEntity(
          sameEnrollment
            ? { ...fullEntity, ...latestSummary, data: fullEntity.data }
            : fullEntity,
        );
        setLoading(false);
      },
      (reason: unknown) => {
        if (fetchIdRef.current !== id) return;
        setError(reason instanceof Error ? reason.message : 'Failed to load entity');
        setLoading(false);
      },
    );
  }, []);

  // Track the last fetched entityId so we can skip the loading flash
  // when only stateId/workflowId change (same entity, state transitioned).
  const prevEntityIdRef = useRef<string | null>(null);

  useEffect(() => {
    if (!entityId) {
      setEntity(null);
      setLoading(false);
      setError(null);
      prevEntityIdRef.current = null;
      return;
    }
    // Different entity → show loading. Same entity (state/workflow changed) → silent refetch.
    const isNewEntity = prevEntityIdRef.current !== entityId;
    prevEntityIdRef.current = entityId;
    fetchEntity(entityId, stateId, workflowId, isNewEntity, !isNewEntity);
  }, [entityId, stateId, workflowId, fetchEntity]);

  /** Re-fetch the current entity from the server without a loading flash.
   *  Skips the stale summary merge — uses server response directly so
   *  current_state, data, and all fields reflect the latest DB state. */
  const refetch = useCallback(() => {
    if (entityId) fetchEntity(entityId, stateId, workflowId, false, true);
  }, [entityId, stateId, workflowId, fetchEntity]);

  return { entity, loading, error, refetch };
}
