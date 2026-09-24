import { useCallback, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { workflowEntities } from '@/core/services/api';
import type { WorkflowEntityState } from '@/core/services/api';
import { workflowEntityKeys } from '@/core/services/api/queryKeys';
import { useGlobalEntityFilter } from '@/core/contexts/GlobalEntityFilterContext';
import { useSkin } from '@/skins';

interface UseAllWorkflowEntitiesResult {
  entities: WorkflowEntityState[];
  loading: boolean;
  refetch: () => Promise<void>;
}

const EMPTY_ENTITIES: WorkflowEntityState[] = [];

/**
 * Fetches every entity enrolled across all workflows for the org (the
 * aggregated cross-workflow list). Owner names are resolved by the API client.
 */
export function useAllWorkflowEntities(): UseAllWorkflowEntitiesResult {
  const { activeAnchorEntityId } = useGlobalEntityFilter();
  const { skin } = useSkin();
  const summaryFields = useMemo(
    () => Array.from(
      new Set(
        skin.entityViews.flatMap((view) => [
          'identifier',
          view.titleField,
          view.subtitleField,
          ...view.listFields.map((field) => field.source),
        ].filter((field): field is string => Boolean(field))),
      ),
    ),
    [skin.entityViews],
  );
  const { data, isLoading, refetch: refetchQuery } = useQuery({
    queryKey: [
      ...workflowEntityKeys.all(),
      'all',
      activeAnchorEntityId ?? null,
      summaryFields.join(','),
    ],
    queryFn: () => workflowEntities.listAll({
        anchorEntityId: activeAnchorEntityId,
        summaryFields,
      }),
  });
  const refetch = useCallback(async () => {
    await refetchQuery();
  }, [refetchQuery]);

  return { entities: data ?? EMPTY_ENTITIES, loading: isLoading, refetch };
}
