import { request } from './client';

export type ScheduleFrequency = 'once' | 'monthly' | 'quarterly' | 'annual';
export type ScheduleConditionOperator = 'equals' | 'not_equals' | 'in' | 'not_in' | 'exists' | 'not_exists';

export interface ScheduleCondition {
  field: string;
  operator: ScheduleConditionOperator;
  value?: unknown;
}

export interface EntitySchedule {
  schedule_id: string;
  organization_id: string;
  machine_name: string;
  name: string;
  description?: string | null;
  anchor_entity_type_id: string;
  target_entity_type_id: string;
  relation_def_id: string;
  target_scope: 'all' | 'selected';
  recurrence: {
    frequency: ScheduleFrequency;
    day_of_month?: number | null;
    months: number[];
    occurs_on?: string | null;
  };
  occurrences_per_batch: number;
  lead_days: number;
  timezone: string;
  entity_data: Record<string, unknown>;
  identifier_template: string;
  conditions: ScheduleCondition[];
  condition_mode: 'all' | 'any';
  is_enabled: boolean;
  completed_at?: string | null;
}

export interface ScheduleTarget {
  target_id: string;
  anchor_entity_id: string;
  next_due_date: string;
  next_materialization_date: string;
  is_enabled: boolean;
  last_result?: string | null;
}

export interface ScheduleCreatePayload {
  machine_name: string;
  name: string;
  anchor_entity_type_id: string;
  relation_def_id: string;
  target_scope?: 'all' | 'selected';
  recurrence: EntitySchedule['recurrence'];
  occurrences_per_batch?: number;
  lead_days: number;
  timezone: string;
  entity_data?: Record<string, unknown>;
  identifier_template?: string;
  conditions?: ScheduleCondition[];
  condition_mode?: 'all' | 'any';
  anchor_entity_ids?: string[];
}

export interface ScheduleRunPreview {
  schedule_id: string;
  schedule_name: string;
  invocation_id: string;
  eligible: number;
  skipped: number;
  items: Array<{
    target_id: string;
    anchor_entity_id: string;
    anchor_identifier: string;
    due_date: string;
    due_dates: string[];
    status: 'eligible' | 'skipped';
    reason?: string | null;
  }>;
}

export interface ScheduleRunNowResult {
  schedule_id: string;
  invocation_id: string;
  queued: number;
  skipped: number;
  run_ids: string[];
}

export const schedules = {
  list: (machineName?: string) =>
    request<{ items: EntitySchedule[]; total: number }>(
      `/schedules${machineName ? `?machine_name=${encodeURIComponent(machineName)}` : ''}`,
    ),
  create: (payload: ScheduleCreatePayload) =>
    request<EntitySchedule>('/schedules', { method: 'POST', body: JSON.stringify(payload) }),
  update: (scheduleId: string, payload: Partial<ScheduleCreatePayload> & { is_enabled?: boolean }) =>
    request<EntitySchedule>(`/schedules/${encodeURIComponent(scheduleId)}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  delete: (scheduleId: string) =>
    request<void>(`/schedules/${encodeURIComponent(scheduleId)}`, { method: 'DELETE' }),
  targets: (scheduleId: string) =>
    request<{ items: ScheduleTarget[]; total: number }>(
      `/schedules/${encodeURIComponent(scheduleId)}/targets`,
    ),
  addTarget: (scheduleId: string, anchorEntityId: string) =>
    request<ScheduleTarget>(`/schedules/${encodeURIComponent(scheduleId)}/targets`, {
      method: 'POST',
      body: JSON.stringify({ anchor_entity_id: anchorEntityId }),
    }),
  preview: (scheduleId: string) =>
    request<{ items: Array<{ due_date: string; materialization_date: string }> }>(
      `/schedules/${encodeURIComponent(scheduleId)}/preview`,
    ),
  previewRunNow: (scheduleId: string) =>
    request<ScheduleRunPreview>(
      `/schedules/${encodeURIComponent(scheduleId)}/run-preview`,
    ),
  runNow: (scheduleId: string, invocationId: string) =>
    request<ScheduleRunNowResult>(
      `/schedules/${encodeURIComponent(scheduleId)}/run-now`,
      { method: 'POST', body: JSON.stringify({ invocation_id: invocationId }) },
    ),
};
