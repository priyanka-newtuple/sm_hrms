import type {
  RemoteMcpAuthorizeResponse,
  RemoteMcpDiscoverResponse,
  RemoteMcpOAuthCallbackResponse,
  RemoteMcpServer,
  RemoteMcpServerCreateRequest,
  RemoteMcpServerListResponse,
  RemoteMcpServerUpdateRequest,
} from '../../types';
import { request } from './client';

/** API client for remote MCP server connections — pre-built app catalog (Settings → Connectors). */
export const remoteMcp = {
  list: () => request<RemoteMcpServerListResponse>('/remote-mcp/servers'),

  get: (id: string) => request<RemoteMcpServer>(`/remote-mcp/servers/${id}`),

  create: (data: RemoteMcpServerCreateRequest) =>
    request<RemoteMcpServer>('/remote-mcp/servers', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  update: (id: string, data: RemoteMcpServerUpdateRequest) =>
    request<RemoteMcpServer>(`/remote-mcp/servers/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  delete: (id: string) =>
    request<void>(`/remote-mcp/servers/${id}`, {
      method: 'DELETE',
    }),

  discover: (id: string) =>
    request<RemoteMcpDiscoverResponse>(`/remote-mcp/servers/${id}/discover`, {
      method: 'POST',
    }),

  authorize: (id: string) =>
    request<RemoteMcpAuthorizeResponse>(`/remote-mcp/servers/${id}/oauth/authorize`, {
      method: 'POST',
      // The body's only field (redirect_uri) is optional, but FastAPI still
      // requires a JSON body to be present since the param itself has no default.
      body: JSON.stringify({}),
    }),

  // No auth header required — the signed `state` carries the organization and server id.
  oauthCallback: (code: string, state: string) =>
    request<RemoteMcpOAuthCallbackResponse>('/remote-mcp/oauth/callback', {
      method: 'POST',
      body: JSON.stringify({ code, state }),
    }),
};
