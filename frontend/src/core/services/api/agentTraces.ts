import type {
  AgentTraceRunDetail,
  AgentTraceRunListResponse,
  AgentTraceSessionListResponse,
} from '../../types';
import { request } from './client';

export const agentTraces = {
  listRuns: (params?: {
    limit?: number;
    offset?: number;
    status?: string;
    agent_name?: string;
    run_type?: string;
    session_id?: string;
    org_id?: string;
  }) => {
    const query = new URLSearchParams();
    if (params?.limit !== undefined) query.set('limit', String(params.limit));
    if (params?.offset !== undefined) query.set('offset', String(params.offset));
    if (params?.status) query.set('status', params.status);
    if (params?.agent_name) query.set('agent_name', params.agent_name);
    if (params?.run_type) query.set('run_type', params.run_type);
    if (params?.session_id) query.set('session_id', params.session_id);
    if (params?.org_id) query.set('org_id', params.org_id);
    const qs = query.toString();
    return request<AgentTraceRunListResponse>(`/agent-traces/runs${qs ? `?${qs}` : ''}`);
  },

  listSessions: (params?: {
    limit?: number;
    offset?: number;
    status?: string;
    agent_name?: string;
    run_type?: string;
    org_id?: string;
  }) => {
    const query = new URLSearchParams();
    if (params?.limit !== undefined) query.set('limit', String(params.limit));
    if (params?.offset !== undefined) query.set('offset', String(params.offset));
    if (params?.status) query.set('status', params.status);
    if (params?.agent_name) query.set('agent_name', params.agent_name);
    if (params?.run_type) query.set('run_type', params.run_type);
    if (params?.org_id) query.set('org_id', params.org_id);
    const qs = query.toString();
    return request<AgentTraceSessionListResponse>(`/agent-traces/sessions${qs ? `?${qs}` : ''}`);
  },

  getRun: (runId: string, orgId?: string) =>
    request<AgentTraceRunDetail>(
      `/agent-traces/runs/${runId}${orgId ? `?org_id=${encodeURIComponent(orgId)}` : ''}`
    ),
};
