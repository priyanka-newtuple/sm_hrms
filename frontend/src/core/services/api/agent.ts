import type {
  AgentDefinition,
  AgentDefinitionListItem,
  AgentDefinitionCreateRequest,
  AgentDefinitionUpdateRequest,
  AgentSession,
  AgentSessionWithMessages,
  AgentRun,
  AgentRunCreateRequest,
  AgentRunListResponse,
} from '../../types';
import { request } from './client';

export const agent = {
  listDefinitions: (activeOnly = true, includeAgentMode = false) =>
    request<AgentDefinitionListItem[]>(
      `/agent/definitions?active_only=${activeOnly}&include_agent_mode=${includeAgentMode}`
    ),

  getDefinition: (definitionId: string) =>
    request<AgentDefinition>(`/agent/definitions/${definitionId}`),

  /** The hidden, locked, all-tools agent that powers Agent Mode. */
  getAgentModeDefinition: () =>
    request<AgentDefinition>(`/agent/definitions/agent-mode`),

  createDefinition: (data: AgentDefinitionCreateRequest) =>
    request<AgentDefinition>('/agent/definitions', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateDefinition: (definitionId: string, data: AgentDefinitionUpdateRequest) =>
    request<AgentDefinition>(`/agent/definitions/${definitionId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  deleteDefinition: (definitionId: string) =>
    request<{ success: boolean; deleted_id: string }>(
      `/agent/definitions/${definitionId}`,
      { method: 'DELETE' }
    ),

  listSessions: (limit = 20, offset = 0) =>
    request<AgentSession[]>(`/agent/sessions?limit=${limit}&offset=${offset}`),

  getSession: (sessionId: string) =>
    request<AgentSessionWithMessages>(`/agent/sessions/${sessionId}`),

  deleteSession: (sessionId: string) =>
    request<{ success: boolean; deleted_id: string }>(
      `/agent/sessions/${sessionId}`,
      { method: 'DELETE' }
    ),

  renameSession: (sessionId: string, title: string) =>
    request<AgentSession>(`/agent/sessions/${sessionId}`, {
      method: 'PATCH',
      body: JSON.stringify({ title }),
    }),

  createRun: (data: AgentRunCreateRequest) =>
    request<AgentRun>('/agent/runs', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  listRuns: (params: { limit?: number; offset?: number; definition_id?: string } = {}) => {
    const query = new URLSearchParams();
    query.set('limit', String(params.limit ?? 20));
    query.set('offset', String(params.offset ?? 0));
    if (params.definition_id) query.set('definition_id', params.definition_id);
    return request<AgentRunListResponse>(`/agent/runs?${query.toString()}`);
  },

  getRun: (runId: string) => request<AgentRun>(`/agent/runs/${runId}`),
};
