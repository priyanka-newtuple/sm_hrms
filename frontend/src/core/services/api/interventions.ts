import type { Intervention, InterventionKind } from '../../types';
import { request } from './client';

export const interventions = {
  list: (params?: { entity_id?: string }) => {
    const searchParams = new URLSearchParams();
    if (params?.entity_id) searchParams.set('entity_id', params.entity_id);
    const query = searchParams.toString();
    return request<Intervention[]>(`/interventions${query ? `?${query}` : ''}`);
  },

  create: (data: {
    entity_id: string;
    entity_type: string;
    kind: InterventionKind;
    requested_by: string;
    assigned_to?: string;
    request_payload?: Record<string, unknown>;
  }) =>
    request<Intervention>('/interventions', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  decide: (
    interventionId: string,
    data: {
      status: 'APPROVED' | 'REJECTED';
      decision_payload?: Record<string, unknown>;
      reason?: string;
    }
  ) =>
    request<Intervention>(`/interventions/${interventionId}/decision`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
};
