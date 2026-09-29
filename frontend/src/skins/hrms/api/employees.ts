import { apiClient } from "./client";
import type { Employee, OffboardingReadiness, Page, Role } from "./types";

export interface EmployeeCreatePayload {
  email: string;
  first_name: string;
  last_name: string;
  department: string;
  designation: string;
  role_id: string;
  reports_to_id?: string | null;
  date_joined: string;
  employment_type?: string;
  work_location?: string | null;
  notice_period_days?: number | null;
  phone?: string | null;
}

export interface OffboardPayload {
  last_working_day: string;
  exit_type: string;
  exit_reason?: string | null;
  rehire_eligible?: boolean;
}

export interface EmployeeListParams {
  page?: number;
  page_size?: number;
  search?: string;
  department?: string;
  status?: string;
}

export interface ReferenceOption {
  id: string;
  value: string;
  label: string;
}

export const employeesApi = {
  formOptions: () =>
    apiClient
      .get<{ departments: ReferenceOption[]; designations: ReferenceOption[] }>(
        "/employees/form-options",
      )
      .then((r) => r.data),
  list: (params: EmployeeListParams = {}) =>
    apiClient
      .get<Page<Employee>>("/employees", { params: { page: 1, page_size: 100, ...params } })
      .then((r) => r.data),
  get: (id: string) => apiClient.get<Employee>(`/employees/${id}`).then((r) => r.data),
  create: (payload: EmployeeCreatePayload) =>
    apiClient.post<Employee>("/employees", payload).then((r) => r.data),
  update: (id: string, payload: Partial<Employee> & { role_id?: string }) =>
    apiClient.patch<Employee>(`/employees/${id}`, payload).then((r) => r.data),
  offboardingReadiness: (id: string) =>
    apiClient
      .get<OffboardingReadiness>(`/employees/${id}/offboarding-readiness`)
      .then((r) => r.data),
  offboard: (id: string, payload: OffboardPayload) =>
    apiClient.post<Employee>(`/employees/${id}/offboard`, payload).then((r) => r.data),
  reactivate: (id: string) =>
    apiClient.post<Employee>(`/employees/${id}/reactivate`).then((r) => r.data),
};

export const rolesApi = {
  list: () => apiClient.get<Role[]>("/roles").then((r) => r.data),
};
