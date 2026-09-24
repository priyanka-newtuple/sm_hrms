import type {
  StateTransition,
  TransitionRequest,
  TransitionResponse,
  AvailableTransitionsResponse,
  PreflightResponse,
} from '../../types';
import { request } from './client';
import { queryClient } from '../../queryClient';
import { workflowEntityKeys } from './queryKeys';

export const transitions = {
  list: (entityId: string) =>
    request<StateTransition[]>(`/entities/${entityId}/transitions`),

  execute: async (entityId: string, data: TransitionRequest) => {
    const result = await request<TransitionResponse>(`/entities/${entityId}/transitions`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
    // A transition changes an entity's current_state, which every
    // useWorkflowEntities consumer (board, sidebar badge, other skin pages)
    // reads from a shared cache — invalidate here, once, instead of relying
    // on each caller to remember to refetch its own hook instance.
    void queryClient.invalidateQueries({ queryKey: workflowEntityKeys.all() });
    return result;
  },

  getAvailable: (entityId: string, workflowId?: string) =>
    request<AvailableTransitionsResponse>(
      `/entities/${entityId}/transitions/available${workflowId ? `?workflow_id=${encodeURIComponent(workflowId)}` : ''}`
    ),

  preflight: (entityId: string, trigger: string) =>
    request<PreflightResponse>(
      `/entities/${entityId}/transitions/${trigger}/preflight`
    ),
};
