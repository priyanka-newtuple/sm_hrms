import type { PipelineViewRead, HeatmapRead } from '../../types';
import { request } from './client';

export const projections = {
  pipeline: (params?: { current_state?: string; job_id?: string; sla_risk?: string }) => {
    const searchParams = new URLSearchParams();
    if (params?.current_state) searchParams.set('current_state', params.current_state);
    if (params?.job_id) searchParams.set('job_id', params.job_id);
    if (params?.sla_risk) searchParams.set('sla_risk', params.sla_risk);
    const query = searchParams.toString();
    return request<PipelineViewRead[]>(`/projections/pipeline${query ? `?${query}` : ''}`);
  },

  heatmap: (params?: { job_id?: string }) => {
    const searchParams = new URLSearchParams();
    if (params?.job_id) searchParams.set('job_id', params.job_id);
    const query = searchParams.toString();
    return request<HeatmapRead[]>(`/projections/heatmap${query ? `?${query}` : ''}`);
  },

  refreshHeatmap: (jobId?: string) =>
    request<{ message: string; updated_count: number }>('/projections/heatmap/refresh', {
      method: 'POST',
      body: JSON.stringify(jobId ? { job_id: jobId } : {}),
    }),
};
