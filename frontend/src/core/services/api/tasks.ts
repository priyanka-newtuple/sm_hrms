import { request } from './client';

export interface TaskRecord {
  id: string;
  organization_id: string;
  entity_id: string;
  entity_type: string;
  title: string;
  description: string | null;
  assigned_to: string | null;
  created_by: string;
  status: string;
  priority: string;
  due_date: string | null;
  stage: string | null;
  source: string;
  completed_at: string | null;
  archived_at: string | null;
  created_at: string;
  updated_at: string | null;
  assigned_to_name: string | null;
  created_by_name: string | null;
}

export interface TaskListResponse {
  tasks: TaskRecord[];
  total: number;
}

export const tasks = {
  list: (entityId: string, status?: string): Promise<TaskRecord[]> => {
    const params = new URLSearchParams();
    if (status) params.set('status', status);
    const qs = params.size ? `?${params.toString()}` : '';
    return request<TaskListResponse>(`/entities/${entityId}/tasks${qs}`).then((r) => r.tasks ?? []);
  },

  create: (entityId: string, payload: { title: string; description?: string; priority?: string }): Promise<TaskRecord> =>
    request<TaskRecord>(`/entities/${entityId}/tasks`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  update: (taskId: string, payload: { title?: string; status?: string; priority?: string; description?: string }): Promise<TaskRecord> =>
    request<TaskRecord>(`/tasks/${taskId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),

  archive: (taskId: string): Promise<TaskRecord> =>
    request<TaskRecord>(`/tasks/${taskId}`, { method: 'DELETE' }),
};
