import type { StateMachineRecord, StateMachineCanvasMetadata, WorkflowService, WorkflowServiceListResponse } from '../../types';
import { request } from './client';

export const stateMachines = {
  list: async (machineName?: string): Promise<StateMachineRecord[]> => {
    const params = new URLSearchParams({ scope: 'all' });
    if (machineName) params.set('machine_name', machineName);
    const resp = await request<{
      scope: string;
      published_items: StateMachineRecord[];
      draft_items: StateMachineRecord[];
    }>(`/workflow-state-machines?${params.toString()}`);
    return [...resp.published_items, ...resp.draft_items];
  },

  /**
   * Fetch all published (version >= 1) state machines, optionally filtered by machine name.
   *
   * @param machineName - Optional machine name filter.
   * @returns Array of published StateMachineRecord items.
   */
  listPublished: async (machineName?: string): Promise<StateMachineRecord[]> => {
    const params = new URLSearchParams({ scope: 'published' });
    if (machineName) params.set('machine_name', machineName);
    const resp = await request<{
      scope: string;
      published_items: StateMachineRecord[];
      draft_items: StateMachineRecord[];
    }>(`/workflow-state-machines?${params.toString()}`);
    return resp.published_items;
  },

  getById: (id: string) =>
    request<StateMachineRecord>(`/workflow-state-machines/${encodeURIComponent(id)}`),

  getDraft: async (machineName: string): Promise<StateMachineRecord | null> => {
    const resp = await request<{
      scope: string;
      published_items: StateMachineRecord[];
      draft_items: StateMachineRecord[];
    }>(`/workflow-state-machines?scope=draft&machine_name=${encodeURIComponent(machineName)}`);
    return resp.draft_items.find(r => r.version === 0) ?? null;
  },

  get: (machineName: string, version: number) =>
    request<StateMachineRecord>(`/workflow-state-machines/${encodeURIComponent(machineName)}/${version}`),

  getActive: (machineName: string) =>
    request<StateMachineRecord>(`/workflow-state-machines/${encodeURIComponent(machineName)}/active`),

  validate: (doc: unknown) =>
    request<{
      machine_name: string;
      can_publish: boolean;
      validation_report: { issues?: { code: string; message: string; severity: string; bucket?: string | null }[] };
      dry_run_report: { issues?: { code: string; message: string; severity: string; bucket?: string | null }[] } | null;
    }>('/workflow-state-machines/validate', {
      method: 'POST',
      body: JSON.stringify(doc),
    }),

  publish: (
    stateMachineId: string,
    definition: unknown,
    canvasMetadata?: StateMachineCanvasMetadata | null,
  ) =>
    request<{
      state_machine: StateMachineRecord;
      validation_report_id: string;
      validation_report: { issues?: unknown[] };
      dry_run_report: { issues?: unknown[] };
    }>(`/workflow-state-machines/${encodeURIComponent(stateMachineId)}/publish`, {
      method: 'POST',
      body: JSON.stringify({
        definition,
        ...(canvasMetadata !== undefined ? { canvas_metadata: canvasMetadata } : {}),
      }),
    }),

  createDraft: (payload?: { name?: string; description?: string }) =>
    request<StateMachineRecord>('/workflow-state-machines/draft', {
      method: 'POST',
      body: JSON.stringify(payload ?? {}),
    }),

  seedDraft: (machineName: string) =>
    request<StateMachineRecord>(`/workflow-state-machines/${encodeURIComponent(machineName)}/draft`, {
      method: 'POST',
    }),

  saveDraft: (
    stateMachineId: string,
    definition: unknown,
    canvasMetadata?: StateMachineCanvasMetadata | null,
  ) =>
    request<{
      record: StateMachineRecord;
      validation_issues: { code: string; message: string; severity: string; bucket?: string | null; action?: string | null }[];
      is_valid: boolean;
      deactivated: boolean;
    }>(
      `/workflow-state-machines/${encodeURIComponent(stateMachineId)}/draft`,
      {
        method: 'PUT',
        body: JSON.stringify({
          definition,
          ...(canvasMetadata !== undefined ? { canvas_metadata: canvasMetadata } : {}),
        }),
      },
    ),

  activate: (machineName: string, version: number) =>
    request<StateMachineRecord>(`/workflow-state-machines/${encodeURIComponent(machineName)}/${version}/activate`, {
      method: 'POST',
    }),

  delete: (id: string) =>
    request<StateMachineRecord>(`/workflow-state-machines/${encodeURIComponent(id)}`, {
      method: 'DELETE',
    }),

  services: {
    list: async (): Promise<WorkflowServiceListResponse> => {
      return request<WorkflowServiceListResponse>('/workflow-state-machines/services');
    },

    create: async (name: string): Promise<WorkflowService> => {
      return request<WorkflowService>('/workflow-state-machines/services', {
        method: 'POST',
        body: JSON.stringify({ name }),
      });
    },

    rename: async (serviceId: string, name: string): Promise<WorkflowService> => {
      return request<WorkflowService>(`/workflow-state-machines/services/${encodeURIComponent(serviceId)}`, {
        method: 'PATCH',
        body: JSON.stringify({ name }),
      });
    },

    remove: async (serviceId: string): Promise<void> => {
      await request<void>(`/workflow-state-machines/services/${encodeURIComponent(serviceId)}`, {
        method: 'DELETE',
      });
    },
  },
};
