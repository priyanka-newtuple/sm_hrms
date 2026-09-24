import type {
  EntityType,
  EntityTypeListResponse,
  EntityTypeCreateRequest,
  EntityTypeUpdateRequest,
  EntityTypeFeatures,
  EntityTypeRelationListResponse,
} from '../../types';
import { request } from './client';

export const entityTypes = {
  list: (params?: { limit?: number; offset?: number }) => {
    const searchParams = new URLSearchParams();
    if (params?.limit) searchParams.set('limit', params.limit.toString());
    if (params?.offset) searchParams.set('offset', params.offset.toString());
    const query = searchParams.toString();
    return request<EntityTypeListResponse>(`/entity-types${query ? `?${query}` : ''}`);
  },

  get: (name: string) => request<EntityType>(`/entity-types/${name}`),

  create: (data: EntityTypeCreateRequest) =>
    request<EntityType>('/entity-types', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  update: (name: string, data: EntityTypeUpdateRequest) =>
    request<EntityType>(`/entity-types/${name}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  delete: (name: string) =>
    request<void>(`/entity-types/${name}`, {
      method: 'DELETE',
    }),

  toggle: (entityTypeId: string) =>
    request<EntityType>(`/entity-types/${entityTypeId}/toggle`, {
      method: 'PATCH',
    }),

  getFeatures: (name: string) =>
    request<EntityTypeFeatures>(`/entity-types/${name}/features`),

  getAutoNumberPreviews: (name: string) =>
    request<Record<string, string>>(`/entity-types/${name}/auto-number-preview`),

  relations: (entityTypeId: string) =>
    request<EntityTypeRelationListResponse>(`/entity-types/${entityTypeId}/relations`),
};
