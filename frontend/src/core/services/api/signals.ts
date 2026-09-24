import type { Signal } from '../../types';
import { request } from './client';

export const signals = {
  list: (params?: { entity_id?: string }) => {
    const searchParams = new URLSearchParams();
    if (params?.entity_id) searchParams.set('entity_id', params.entity_id);
    const query = searchParams.toString();
    return request<Signal[]>(`/signals${query ? `?${query}` : ''}`);
  },
};
