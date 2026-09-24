import type {
  DocumentTypeCreateRequest,
  DocumentTypeUpdateRequest,
  ToolManifestResponse,
  ToolPresetsResponse,
} from '../../types';
import { request } from './client';
import { mapFileType } from './internal';

export const documentTypes = {
  list: (params?: { active_only?: boolean }) => {
    const searchParams = new URLSearchParams();
    if (params?.active_only !== undefined) {
      searchParams.set('active_only', params.active_only.toString());
    }
    const query = searchParams.toString();
    return request<{ count: number; items: Record<string, unknown>[] }>(
      `/config/file-types${query ? `?${query}` : ''}`
    ).then((response) => ({
      items: response.items.map(mapFileType),
      total: response.count,
    }));
  },

  get: (typeId: string) =>
    request<Record<string, unknown>>(`/config/file-types/${typeId}`).then(mapFileType),

  create: (data: DocumentTypeCreateRequest) =>
    request<Record<string, unknown>>('/config/file-types', {
      method: 'POST',
      body: JSON.stringify(data),
    }).then(mapFileType),

  update: (typeId: string, data: DocumentTypeUpdateRequest) =>
    request<Record<string, unknown>>(`/config/file-types/${typeId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }).then(mapFileType),

  delete: (typeId: string) =>
    request<void>(`/config/file-types/${typeId}`, {
      method: 'DELETE',
    }),

  getTools: () =>
    request<ToolManifestResponse>('/config/document-types/tools'),

  getToolPresets: () =>
    request<ToolPresetsResponse>('/config/document-types/tools/presets'),
};
