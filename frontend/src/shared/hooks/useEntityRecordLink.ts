import { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';

import { useEntityTypes } from '@/core/hooks/useEntityTypes';
import { useStateMachinesList } from '@/core/hooks/useStateMachinesList';

type OpenOptions = {
  tab?: 'activity' | 'comments';
  commentId?: string | null;
};

/**
 * Deep-links an audit row to its record's detail view.
 *
 * Entity detail lives under a pipeline, so a workflow id is needed: the entity
 * type's default state machine, falling back to any active machine for that
 * type. `returnTo` sends the detail page's back arrow to the caller's own page
 * rather than the board it would otherwise default to.
 */
export function useEntityRecordLink(returnTo: string) {
  const navigate = useNavigate();
  const { entityTypes } = useEntityTypes();
  const { data: stateMachines } = useStateMachinesList();

  const resolveMachineId = useCallback(
    (entityType: string | null | undefined): string | undefined => {
      if (!entityType) return undefined;
      const configured = entityTypes.find((type) => type.name === entityType)
        ?.default_state_machine_id;
      if (configured) return configured;
      return (stateMachines ?? []).find(
        (machine) => machine.entity_type === entityType && machine.is_active && machine.id,
      )?.id;
    },
    [entityTypes, stateMachines],
  );

  const isLinkable = useCallback(
    (entityType: string | null | undefined, entityId: string | null | undefined) =>
      Boolean(entityId && resolveMachineId(entityType)),
    [resolveMachineId],
  );

  const openRecord = useCallback(
    (
      entityType: string | null | undefined,
      entityId: string | null | undefined,
      options?: OpenOptions,
    ) => {
      const machineId = resolveMachineId(entityType);
      if (!entityId || !machineId) return;
      const params = new URLSearchParams({ tab: options?.tab ?? 'activity', returnTo });
      if (options?.commentId) params.set('comment', options.commentId);
      navigate(`/pipeline/${machineId}/entity/${entityId}?${params.toString()}`);
    },
    [navigate, resolveMachineId, returnTo],
  );

  return { isLinkable, openRecord };
}
