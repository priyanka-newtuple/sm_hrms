import type {
  DashboardDataRequest,
  DashboardDataResponse,
  DashboardDefinitionRead,
  DashboardDefinitionUpdate,
  DashboardFilterOptionsResponse,
  DashboardMetricsResponse,
  DashboardQueryDefinitionRequest,
  DashboardQueryPreviewResponse,
  DashboardQuerySourcesResponse,
} from '../../types';
import { request } from './client';

export const dashboards = {
  get: (key = 'primary') =>
    request<DashboardDefinitionRead>(`/dashboards/${key}`),

  update: (key: string, data: DashboardDefinitionUpdate) =>
    request<DashboardDefinitionRead>(`/dashboards/${key}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  // Pass workflowId to scope the "fields"/"states" catalogs to that one
  // workflow's entity type instead of the org-wide union across every
  // workflow — used by the widget builder once a specific workflow (not
  // "All") is picked.
  metrics: (workflowId?: string) =>
    request<DashboardMetricsResponse>(
      `/dashboards/metrics${workflowId ? `?workflow_id=${encodeURIComponent(workflowId)}` : ''}`,
    ),

  filterOptions: (workflowId?: string) =>
    request<DashboardFilterOptionsResponse>(
      `/dashboards/filter-options${workflowId ? `?workflow_id=${encodeURIComponent(workflowId)}` : ''}`,
    ),

  data: (body: DashboardDataRequest) =>
    request<DashboardDataResponse>('/dashboards/data', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  querySources: () =>
    request<DashboardQuerySourcesResponse>('/dashboards/query-sources'),

  queryPreview: (query: DashboardQueryDefinitionRequest) =>
    request<DashboardQueryPreviewResponse>('/dashboards/query-preview', {
      method: 'POST',
      body: JSON.stringify({ query }),
    }),
};
