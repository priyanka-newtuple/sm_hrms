/**
 * Entity Type admin hook — data + mutations for the Settings › Entity Types tab.
 *
 * Owns the type + form-schema lists and the create/update/delete operations so
 * the tab's components depend on this abstraction instead of the API service.
 * Mutations throw on failure; callers own their own saving/error UI state.
 */

import { useCallback, useEffect, useState } from 'react';
import {
  entityTypes as entityTypesApi,
  formSchemas as formSchemasApi,
} from '../services/api';
import { invalidateIdentifierConfigCache } from '@/shared/hooks/useIdentifierConfig';
import type {
  EntityType,
  EntityTypeCreateRequest,
  EntityTypeUpdateRequest,
  FormSchema,
} from '../types';

function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message.trim()) return error.message;
  return fallback;
}

interface UseEntityTypeAdminResult {
  types: EntityType[];
  schemas: FormSchema[];
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  createType: (payload: EntityTypeCreateRequest) => Promise<void>;
  updateType: (name: string, payload: EntityTypeUpdateRequest) => Promise<void>;
  deleteType: (name: string) => Promise<void>;
}

export function useEntityTypeAdmin(): UseEntityTypeAdminResult {
  const [types, setTypes] = useState<EntityType[]>([]);
  const [schemas, setSchemas] = useState<FormSchema[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const [typeResponse, schemaResponse] = await Promise.all([
        entityTypesApi.list(),
        formSchemasApi.list(),
      ]);
      setTypes(typeResponse.items ?? []);
      setSchemas(schemaResponse.items ?? []);
    } catch (e) {
      setError(getErrorMessage(e, 'Failed to load entity types'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const createType = useCallback(async (payload: EntityTypeCreateRequest) => {
    await entityTypesApi.create(payload);
    invalidateIdentifierConfigCache();
    await refresh();
  }, [refresh]);

  const updateType = useCallback(async (name: string, payload: EntityTypeUpdateRequest) => {
    await entityTypesApi.update(name, payload);
    invalidateIdentifierConfigCache();
    await refresh();
  }, [refresh]);

  const deleteType = useCallback(async (name: string) => {
    await entityTypesApi.delete(name);
    invalidateIdentifierConfigCache(name);
    await refresh();
  }, [refresh]);

  return { types, schemas, loading, error, refresh, createType, updateType, deleteType };
}
