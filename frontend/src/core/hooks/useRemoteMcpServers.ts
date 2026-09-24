/**
 * Remote MCP server hooks
 *
 * Data-fetching + mutation access for the pre-built app catalog (Settings →
 * Connectors → Apps), keeping components free of direct service imports.
 */

import { useCallback } from 'react';

import { remoteMcp } from '../services/api';
import type { RemoteMcpServerCreateRequest, RemoteMcpServerUpdateRequest } from '../types';
import { useApi } from './useApi';

/** List every remote MCP server connection in the org. */
export function useRemoteMcpServerList() {
  const fetcher = useCallback(() => remoteMcp.list(), []);
  return useApi(fetcher, { immediate: true });
}

/** Mutation helpers for remote MCP servers. */
export function useRemoteMcpServerActions() {
  const create = useCallback((data: RemoteMcpServerCreateRequest) => remoteMcp.create(data), []);
  const update = useCallback(
    (id: string, data: RemoteMcpServerUpdateRequest) => remoteMcp.update(id, data),
    [],
  );
  const remove = useCallback((id: string) => remoteMcp.delete(id), []);
  const discover = useCallback((id: string) => remoteMcp.discover(id), []);
  const authorize = useCallback((id: string) => remoteMcp.authorize(id), []);
  return { create, update, remove, discover, authorize };
}
