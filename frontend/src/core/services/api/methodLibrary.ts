import type {
  MethodCategory,
  MethodCategoryListResponse,
  MethodCloneRequest,
  MethodCreateRequest,
  MethodFieldListUpdateRequest,
  MethodFieldRepinRequest,
  MethodIdentity,
  MethodListResponse,
  MethodMetadataUpdateRequest,
  MethodVersionListResponse,
  MethodWithFields,
} from '../../types';
import { request } from './client';

export interface MethodListParams {
  includeArchived?: boolean;
  search?: string;
  /** Keeps only methods tagged for this entity type. Untagged methods are
   *  excluded by the server, so callers never filter the page themselves. */
  entityType?: string;
  limit?: number;
  offset?: number;
}

/** The backend's own MAX_PAGE_LIMIT (method_library/controller.py). */
export const METHOD_LIBRARY_MAX_LIMIT = 200;

export const methodLibrary = {
  list: async (params: MethodListParams = {}): Promise<MethodListResponse> => {
    const query = new URLSearchParams();
    if (params.includeArchived) query.set('include_archived', 'true');
    if (params.search) query.set('search', params.search);
    if (params.entityType) query.set('entity_type', params.entityType);
    if (params.limit != null) query.set('limit', String(params.limit));
    if (params.offset != null) query.set('offset', String(params.offset));
    const qs = query.toString();
    return request<MethodListResponse>(`/method-library/methods${qs ? `?${qs}` : ''}`);
  },

  /** One method resolved into its ordered field list, each field merged with
   *  the shape of the Field Library version it pins. */
  get: async (methodId: string): Promise<MethodWithFields> => {
    return request<MethodWithFields>(`/method-library/methods/${methodId}`);
  },

  listVersions: async (
    methodId: string,
    params: { limit?: number; offset?: number } = {},
  ): Promise<MethodVersionListResponse> => {
    const query = new URLSearchParams();
    if (params.limit != null) query.set('limit', String(params.limit));
    if (params.offset != null) query.set('offset', String(params.offset));
    const qs = query.toString();
    return request<MethodVersionListResponse>(
      `/method-library/methods/${methodId}/versions${qs ? `?${qs}` : ''}`,
    );
  },

  create: async (data: MethodCreateRequest): Promise<MethodWithFields> => {
    return request<MethodWithFields>('/method-library/methods', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  /** Name, description and category edits. Creates no version. */
  updateMetadata: async (
    methodId: string,
    data: MethodMetadataUpdateRequest,
  ): Promise<MethodIdentity> => {
    return request<MethodIdentity>(`/method-library/methods/${methodId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  },

  clone: async (methodId: string, data: MethodCloneRequest): Promise<MethodWithFields> => {
    return request<MethodWithFields>(`/method-library/methods/${methodId}/clone`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  /** Replaces the whole field list, producing a new version. Additions,
   *  removals and reordering all arrive as the list the method should have. */
  replaceFields: async (
    methodId: string,
    data: MethodFieldListUpdateRequest,
  ): Promise<MethodWithFields> => {
    return request<MethodWithFields>(`/method-library/methods/${methodId}/fields`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  /** Repins one already-listed field to a different version of that same field,
   *  without touching the rest of the list. Produces a new method version and
   *  returns the method resolved against it. `linkId` is the field row's `id`. */
  repinField: async (
    methodId: string,
    linkId: string,
    versionId: string,
  ): Promise<MethodWithFields> => {
    const payload: MethodFieldRepinRequest = { version_id: versionId };
    return request<MethodWithFields>(
      `/method-library/methods/${methodId}/fields/${linkId}/version`,
      { method: 'PATCH', body: JSON.stringify(payload) },
    );
  },

  delete: async (methodId: string): Promise<void> => {
    await request<void>(`/method-library/methods/${methodId}`, { method: 'DELETE' });
  },

  /** A visibility change, not a removal: unconditional, idempotent, and allowed
   *  even while the method is in use. Reversed by `unarchive`. */
  archive: async (methodId: string): Promise<MethodIdentity> => {
    return request<MethodIdentity>(`/method-library/methods/${methodId}/archive`, {
      method: 'POST',
    });
  },

  unarchive: async (methodId: string): Promise<MethodIdentity> => {
    return request<MethodIdentity>(`/method-library/methods/${methodId}/unarchive`, {
      method: 'POST',
    });
  },

  categories: {
    list: async (): Promise<MethodCategoryListResponse> => {
      return request<MethodCategoryListResponse>('/method-library/categories');
    },

    create: async (name: string): Promise<MethodCategory> => {
      return request<MethodCategory>('/method-library/categories', {
        method: 'POST',
        body: JSON.stringify({ name }),
      });
    },

    rename: async (categoryId: string, name: string): Promise<MethodCategory> => {
      return request<MethodCategory>(`/method-library/categories/${categoryId}`, {
        method: 'PATCH',
        body: JSON.stringify({ name }),
      });
    },

    remove: async (categoryId: string): Promise<void> => {
      await request<void>(`/method-library/categories/${categoryId}`, { method: 'DELETE' });
    },
  },
};
