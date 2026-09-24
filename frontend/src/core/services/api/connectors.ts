import type {
  Connector,
  ConnectorCreateRequest,
  ConnectorListResponse,
  ConnectorTestResponse,
  ConnectorUpdateRequest,
} from '../../types';
import { request } from './client';

/** API client for connectors — reusable approved outbound API calls (Settings → Connectors). */
export const connectors = {
  list: (entityType?: string) => {
    const query = entityType ? `?entity_type=${encodeURIComponent(entityType)}` : '';
    return request<ConnectorListResponse>(`/connectors${query}`);
  },

  get: (id: string) => request<Connector>(`/connectors/${id}`),

  create: (data: ConnectorCreateRequest) =>
    request<Connector>('/connectors', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  update: (id: string, data: ConnectorUpdateRequest) =>
    request<Connector>(`/connectors/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  delete: (id: string) =>
    request<void>(`/connectors/${id}`, {
      method: 'DELETE',
    }),

  test: (id: string, sampleFields: Record<string, unknown> = {}) =>
    request<ConnectorTestResponse>(`/connectors/${id}/test`, {
      method: 'POST',
      body: JSON.stringify({ sample_fields: sampleFields }),
    }),

  // connectorId lets an inline test of a saved connector reuse its stored secrets
  // for any credential left blank in the form.
  testInline: (
    connector: ConnectorCreateRequest,
    sampleFields: Record<string, unknown> = {},
    connectorId?: string,
  ) =>
    request<ConnectorTestResponse>('/connectors/test-inline', {
      method: 'POST',
      body: JSON.stringify({ connector, sample_fields: sampleFields, connector_id: connectorId ?? null }),
    }),
};
