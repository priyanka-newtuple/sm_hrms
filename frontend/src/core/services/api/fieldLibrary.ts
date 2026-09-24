import type {
  FieldCreateRequest,
  FieldDescriptionUpdateRequest,
  FieldIdentity,
  FieldListResponse,
  FieldRenameRequest,
  FieldTypeCatalogueResponse,
  FieldVersion,
  FieldVersionCreateRequest,
  FieldVersionListResponse,
  FieldWithVersion,
} from '../../types';
import { request } from './client';

export interface FieldListParams {
  includeArchived?: boolean;
  search?: string;
  fieldType?: string;
  limit?: number;
  offset?: number;
}

export const fieldLibrary = {
  listFieldTypes: async (): Promise<FieldTypeCatalogueResponse> => {
    return request<FieldTypeCatalogueResponse>('/field-library/field-types');
  },

  list: async (params: FieldListParams = {}): Promise<FieldListResponse> => {
    const query = new URLSearchParams();
    if (params.includeArchived) query.set('include_archived', 'true');
    if (params.search) query.set('search', params.search);
    if (params.fieldType) query.set('field_type', params.fieldType);
    if (params.limit != null) query.set('limit', String(params.limit));
    if (params.offset != null) query.set('offset', String(params.offset));
    const qs = query.toString();
    return request<FieldListResponse>(`/field-library/fields${qs ? `?${qs}` : ''}`);
  },

  get: async (libraryFieldId: string): Promise<FieldWithVersion> => {
    return request<FieldWithVersion>(`/field-library/fields/${libraryFieldId}`);
  },

  create: async (data: FieldCreateRequest): Promise<FieldWithVersion> => {
    return request<FieldWithVersion>('/field-library/fields', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  rename: async (libraryFieldId: string, data: FieldRenameRequest): Promise<FieldIdentity> => {
    return request<FieldIdentity>(`/field-library/fields/${libraryFieldId}/name`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  },

  updateDescription: async (
    libraryFieldId: string,
    data: FieldDescriptionUpdateRequest,
  ): Promise<FieldVersion> => {
    return request<FieldVersion>(`/field-library/fields/${libraryFieldId}/description`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  },

  listVersions: async (libraryFieldId: string): Promise<FieldVersionListResponse> => {
    return request<FieldVersionListResponse>(`/field-library/fields/${libraryFieldId}/versions`);
  },

  createVersion: async (libraryFieldId: string, data: FieldVersionCreateRequest): Promise<FieldVersion> => {
    return request<FieldVersion>(`/field-library/fields/${libraryFieldId}/versions`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  archive: async (libraryFieldId: string): Promise<FieldIdentity> => {
    return request<FieldIdentity>(`/field-library/fields/${libraryFieldId}`, {
      method: 'DELETE',
    });
  },

  hardDelete: async (libraryFieldId: string): Promise<void> => {
    await request<void>(`/field-library/fields/${libraryFieldId}/hard`, {
      method: 'DELETE',
    });
  },
};
