/**
 * Connectors hooks
 *
 * Data-fetching + mutation access for connectors, keeping components free of
 * direct service imports (Component → Hook → Service).
 */

import { useCallback } from 'react';

import { connectors } from '../services/api';
import type {
  ConnectorCreateRequest,
  ConnectorTestResponse,
  ConnectorUpdateRequest,
} from '../types';
import { useApi } from './useApi';

/** List connectors, optionally filtered by entity type. Stable fetcher avoids refetch loops. */
export function useConnectorList(entityType?: string) {
  const fetcher = useCallback(() => connectors.list(entityType), [entityType]);
  return useApi(fetcher, { immediate: true });
}

/** Mutation helpers for connectors. */
export function useConnectorActions() {
  const create = useCallback((data: ConnectorCreateRequest) => connectors.create(data), []);
  const update = useCallback(
    (id: string, data: ConnectorUpdateRequest) => connectors.update(id, data),
    [],
  );
  const remove = useCallback((id: string) => connectors.delete(id), []);
  const test = useCallback(
    (id: string, sampleFields: Record<string, unknown>) => connectors.test(id, sampleFields),
    [],
  );
  /** Test an unsaved/edited connector payload before persisting it. */
  const testInline = useCallback(
    (
      data: ConnectorCreateRequest,
      sampleFields: Record<string, unknown> = {},
      connectorId?: string,
    ): Promise<ConnectorTestResponse> => connectors.testInline(data, sampleFields, connectorId),
    [],
  );
  return { create, update, remove, test, testInline };
}
