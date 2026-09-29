import { apiClient } from "./client";
import type { Allocation, AllocationWriteResult, Capacity, CapacityPeriod, Page } from "./types";

export interface AllocationListParams {
  page?: number;
  page_size?: number;
  employee_id?: string;
  project_id?: string;
  active_on?: string;
  include_cancelled?: boolean;
  overallocated_only?: boolean;
}

export interface AllocationPayload {
  employee_id: string;
  project_id: string;
  allocation_percent: number;
  role_on_project: string;
  start_date: string;
  end_date?: string | null;
  billable?: boolean;
  notes?: string | null;
  confirm_overallocation?: boolean;
  overallocation_reason?: string | null;
}

export interface AllocationPreview {
  over_allocated: boolean;
  total_allocation_percent: number;
  overallocated_periods: CapacityPeriod[];
  allocations: { allocation_id: string; project_name: string; manager_name: string; allocation_percent: number;
    start_date: string; end_date: string | null; status: string; over_allocated: boolean; total_allocation_percent: number }[];
}

export const allocationsApi = {
  options: () => apiClient.get<{
    employees: {id: string; label: string}[];
    projects: {id: string; label: string}[];
    project_roles: {id: string; value: string; label: string}[];
  }>("/allocations/options").then(r => r.data),
  preview: (payload: {employee_id: string; project_id: string; start_date: string; end_date: string | null;
    allocation_percent: number; exclude_allocation_id?: string}) =>
    apiClient.post<AllocationPreview>("/allocations/preview", payload).then(r => r.data),
  list: (params: AllocationListParams = {}) =>
    apiClient
      .get<Page<Allocation>>("/allocations", {
        params: { page: 1, page_size: 100, ...params },
      })
      .then((r) => r.data),
  get: (id: string) => apiClient.get<Allocation>(`/allocations/${id}`).then((r) => r.data),
  create: (payload: AllocationPayload) =>
    apiClient.post<AllocationWriteResult>("/allocations", payload).then((r) => r.data),
  update: (id: string, payload: Partial<AllocationPayload>) =>
    apiClient.patch<AllocationWriteResult>(`/allocations/${id}`, payload).then((r) => r.data),
  /** Allocations are cancelled, never deleted — history is preserved. */
  cancel: (id: string) =>
    apiClient.post<Allocation>(`/allocations/${id}/cancel`).then((r) => r.data),
  projectAllocations: (projectId: string) =>
    apiClient
      .get<Page<Allocation>>(`/projects/${projectId}/allocations`)
      .then((r) => r.data),
  employeeAllocations: (employeeId: string) =>
    apiClient
      .get<Page<Allocation>>(`/employees/${employeeId}/allocations`)
      .then((r) => r.data),
  capacity: (employeeId: string, on?: string) =>
    apiClient
      .get<Capacity>(`/employees/${employeeId}/capacity`, { params: on ? { on } : {} })
      .then((r) => r.data),
};
