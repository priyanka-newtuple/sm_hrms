import { apiClient } from "./client";
import type { Customer, Page, Project } from "./types";

export interface CustomerListParams {
  page?: number;
  page_size?: number;
  search?: string;
  include_archived?: boolean;
}

export const customersApi = {
  list: (params: CustomerListParams = {}) =>
    apiClient
      .get<Page<Customer>>("/customers", {
        params: { page: 1, page_size: 100, ...params },
      })
      .then((r) => r.data),
  get: (id: string) => apiClient.get<Customer>(`/customers/${id}`).then((r) => r.data),
  create: (payload: Partial<Customer>) =>
    apiClient.post<Customer>("/customers", payload).then((r) => r.data),
  update: (id: string, payload: Partial<Customer>) =>
    apiClient.patch<Customer>(`/customers/${id}`, payload).then((r) => r.data),
  archive: (id: string) =>
    apiClient.post<Customer>(`/customers/${id}/archive`).then((r) => r.data),
  projects: (id: string) =>
    apiClient.get<Page<Project>>(`/customers/${id}/projects`).then((r) => r.data),
};

export interface ProjectListParams {
  page?: number;
  page_size?: number;
  search?: string;
  status?: string;
  customer_id?: string;
  include_archived?: boolean;
}

export const projectsApi = {
  creationOptions: () => apiClient.get<{ customers: {id: string; label: string}[]; employees: {id: string; label: string}[] }>("/project-creation-options").then(r => r.data),
  list: (params: ProjectListParams = {}) =>
    apiClient
      .get<Page<Project>>("/projects", { params: { page: 1, page_size: 100, ...params } })
      .then((r) => r.data),
  get: (id: string) => apiClient.get<Project>(`/projects/${id}`).then((r) => r.data),
  create: (payload: Partial<Project>) =>
    apiClient.post<Project>("/projects", payload).then((r) => r.data),
  update: (id: string, payload: Partial<Project>) =>
    apiClient.patch<Project>(`/projects/${id}`, payload).then((r) => r.data),
  archive: (id: string) =>
    apiClient.post<Project>(`/projects/${id}/archive`).then((r) => r.data),
};

export interface ProjectRequest {
  id: string;
  project_id: string;
  kind: "initial" | "amendment";
  status: "draft" | "pending" | "changes_requested" | "rejected" | "approved";
  version: number;
  requested_by_id: string;
  requester_name: string;
  reviewer_name: string | null;
  note: string | null;
  proposed: Partial<Project>;
  history: { action: string; actor: string; at: string; version: number; note?: string | null; snapshot?: Partial<Project> }[];
}

export interface ProjectReview extends ProjectRequest {
  project_name: string;
  project_code: string;
  current: Partial<Project>;
  current_names: Record<string, string>;
  customer_name: string;
  project_manager_name: string;
  delivery_manager_name: string;
  can_review: boolean;
  can_submit: boolean;
  can_withdraw: boolean;
}

export const projectApprovalsApi = {
  get: (id: string) => apiClient.get<ProjectReview>(`/project-approvals/${id}`).then(r => r.data),
  submit: (id: string, version: number) => apiClient.post<ProjectReview>(`/project-approvals/${id}/submit`, { version }).then(r => r.data),
  withdraw: (id: string, version: number) => apiClient.post<ProjectReview>(`/project-approvals/${id}/withdraw`, { version }).then(r => r.data),
  decide: (id: string, version: number, decision: "approve" | "changes_requested" | "reject", note: string) =>
    apiClient.post<ProjectReview>(`/project-approvals/${id}/decision`, { version, decision, note: note || null }).then(r => r.data),
};
