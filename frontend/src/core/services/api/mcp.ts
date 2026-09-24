import type {
  McpCapability,
  McpServerPackage,
  McpToolingOverview,
} from '../../types';
import { request } from './client';

export const mcp = {
  getTooling: () => request<McpToolingOverview>('/mcp/tooling'),

  updateServerConfiguration: (packageId: string, data: { is_enabled: boolean; config?: Record<string, unknown> }) =>
    request<McpServerPackage>(`/mcp/server-packages/${packageId}/configuration`, {
      method: 'PATCH',
      body: JSON.stringify({ is_enabled: data.is_enabled, config: data.config ?? {} }),
    }),

  updateCapabilityConfiguration: (
    capabilityId: string,
    data: { is_enabled: boolean; requires_approval?: boolean; config?: Record<string, unknown>; integration_ref?: string | null },
  ) =>
    request<McpCapability>(`/mcp/capabilities/${capabilityId}/configuration`, {
      method: 'PATCH',
      body: JSON.stringify({
        is_enabled: data.is_enabled,
        requires_approval: data.requires_approval,
        config: data.config ?? {},
        integration_ref: data.integration_ref ?? null,
      }),
    }),
};
