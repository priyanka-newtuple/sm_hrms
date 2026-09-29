import type { AllocationPreview } from "./allocations";
import axios from "axios";

import { apiClient } from "./client";
import type { Page } from "./types";
import type { TaskCompletePayload } from "./onboarding";

export type WorkView = "todo" | "waiting" | "completed";
export interface WorkItem {
  id: string;
  source: "tasks" | "documents" | "projects" | "performance";
  kind: "action" | "approval";
  title: string;
  description: string | null;
  employee_name: string;
  department: string;
  date_joined: string | null;
  workflow_type: string;
  status: string;
  due_date: string | null;
  overdue: boolean;
  action_type: string;
  assignee_name: string | null;
  note: string | null;
  can_act: boolean;
  payroll_required: boolean;
  file_name: string | null;
  can_reassign: boolean;
  record_id: string | null;
  href?: string | null;
}
export interface WorkOption { id: string; label: string }

export const workApi = {
  list: (view: WorkView, page: number, kind?: string) =>
    apiClient.get<Page<WorkItem>>("/work", { params: { view, page, kind: kind || undefined } }).then(r => r.data),
  summary: () => apiClient.get<{ total: number; actions: number; approvals: number }>("/work/summary").then(r => r.data),
  detail: (source: string, id: string) => apiClient.get<WorkItem>(`/work/${source}/${id}`).then(r => r.data),
  complete: (id: string, payload: TaskCompletePayload) =>
    apiClient.post<WorkItem>(`/work/tasks/${id}/complete`, payload).then(r => r.data),
  options: (id: string, type: "assets" | "projects" | "project-roles" | "assignees") =>
    apiClient.get<WorkOption[]>(`/work/tasks/${id}/${type}`).then(r => r.data),
  assignAsset: (id: string, payload: { asset_id: string; assigned_date: string; condition_notes?: string }) =>
    apiClient.post<WorkItem>(`/work/tasks/${id}/assets`, payload).then(r => r.data),
  allocationPreview: (id: string, payload: {project_id: string; allocation_percent: number; role_on_project: string; start_date: string; end_date?: string}) =>
    apiClient.post<AllocationPreview>(`/work/tasks/${id}/allocation-preview`, payload).then(r => r.data),
  allocate: (id: string, payload: { project_id: string; allocation_percent: number; role_on_project: string; start_date: string; end_date?: string; confirm_overallocation?: boolean; overallocation_reason?: string }) =>
    apiClient.post<{ item: WorkItem; over_allocated: boolean }>(`/work/tasks/${id}/allocation`, payload).then(r => r.data),
  reassign: (id: string, employee_id: string, reason: string) =>
    apiClient.post<WorkItem>(`/work/tasks/${id}/reassign`, { employee_id, reason }).then(r => r.data),
};

export function workError(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (detail?.message) return detail.message;
    if (error.response?.status === 422) return "Check the required fields and dates, then try again.";
  }
  return "Could not load or save this work. Please try again.";
}
