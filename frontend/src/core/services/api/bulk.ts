import type { EntityState } from '../../types';
import { request } from './client';

export interface BulkTransitionResult {
  entity_id: string;
  success: boolean;
  from_state: string | null;
  to_state: string | null;
  error: string | null;
}

export interface BulkTransitionResponse {
  results: BulkTransitionResult[];
  total: number;
  succeeded: number;
  failed: number;
}

export interface BulkStatesResponse {
  states: Record<string, EntityState | null>;
}

export const bulk = {
  transition: (data: {
    entity_ids: string[];
    trigger: string;
    actor_type?: string;
    actor_id?: string;
  }) =>
    request<BulkTransitionResponse>('/bulk/transitions', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  getStates: (entityIds: string[]) =>
    request<BulkStatesResponse>('/bulk/states', {
      method: 'POST',
      body: JSON.stringify({ entity_ids: entityIds }),
    }),
};
