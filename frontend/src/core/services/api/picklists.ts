import type {
  Picklist,
  PicklistListResponse,
  PicklistCreateRequest,
  PicklistUpdateRequest,
} from '../../types';
import { request } from './client';

export const picklists = {
  list: async (): Promise<PicklistListResponse> => {
    return request<PicklistListResponse>('/config/picklists');
  },

  get: async (picklistId: string): Promise<Picklist> => {
    return request<Picklist>(`/config/picklists/${picklistId}`);
  },

  create: async (data: PicklistCreateRequest): Promise<Picklist> => {
    return request<Picklist>('/config/picklists', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  update: async (picklistId: string, data: PicklistUpdateRequest): Promise<Picklist> => {
    return request<Picklist>(`/config/picklists/${picklistId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  delete: async (picklistId: string): Promise<void> => {
    await request<void>(`/config/picklists/${picklistId}`, {
      method: 'DELETE',
    });
  },
};
