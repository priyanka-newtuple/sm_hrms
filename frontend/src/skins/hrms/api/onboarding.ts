import { apiClient } from "./client";
import type {
  EmployeeDocument,
  EmployeeDocumentStatus,
  EmployeeDocumentType,
  MyOnboardingAction,
  OnboardingDetail,
  OnboardingRecord,
  OnboardingTask,
  Page,
} from "./types";

export interface TaskCompletePayload {
  note?: string | null;
  /** Only meaningful on the Razorpay step — stored as employees.payroll_reference. */
  payroll_reference?: string | null;
}

export const onboardingApi = {
  list: (workflowType: "onboarding" | "offboarding", page = 1, pageSize = 50) =>
    apiClient
      .get<Page<OnboardingRecord>>("/onboarding", {
        params: { workflow_type: workflowType, page, page_size: pageSize },
      })
      .then((r) => r.data),
  detail: (recordId: string) =>
    apiClient.get<OnboardingDetail>(`/onboarding/${recordId}`).then((r) => r.data),
  start: (employeeId: string, workflowType: "onboarding" | "offboarding") =>
    apiClient
      .post<OnboardingRecord>("/onboarding/start", {
        employee_id: employeeId,
        workflow_type: workflowType,
      })
      .then((r) => r.data),
  completeTask: (recordId: string, taskId: string, payload?: TaskCompletePayload) =>
    apiClient
      .post<OnboardingTask>(`/onboarding/${recordId}/tasks/${taskId}/complete`, payload ?? {})
      .then((r) => r.data),
  skipTask: (recordId: string, taskId: string, note?: string) =>
    apiClient
      .post<OnboardingRecord>(`/onboarding/${recordId}/tasks/${taskId}/skip`, { note })
      .then((r) => r.data),

  myActions: () =>
    apiClient.get<MyOnboardingAction[]>("/onboarding/my-actions").then((r) => r.data),

  // ---- new-hire self-service (/welcome wizard)
  myOnboarding: () =>
    apiClient.get<OnboardingDetail | null>("/onboarding/me").then((r) => r.data),
  submitProfile: (payload: {
    phone?: string;
    personal_email?: string;
    date_of_birth?: string;
    address?: string;
    bank_account_number?: string;
    bank_ifsc?: string;
  }) =>
    apiClient.post<OnboardingDetail | null>("/onboarding/me/profile", payload).then((r) => r.data),
  acceptInvitation: (token: string) =>
    apiClient
      .post<{ accepted: boolean }>("/onboarding/invitations/accept", { token })
      .then((r) => r.data),

  // ---- documents
  listDocuments: (employeeId: string) =>
    apiClient
      .get<EmployeeDocument[]>(`/onboarding/employees/${employeeId}/documents`)
      .then((r) => r.data),
  uploadDocument: (employeeId: string, docType: EmployeeDocumentType, file: File) => {
    const form = new FormData();
    form.append("doc_type", docType);
    form.append("file", file);
    return apiClient
      .post<EmployeeDocument>(`/onboarding/employees/${employeeId}/documents`, form, {
        headers: { "Content-Type": "multipart/form-data" },
      })
      .then((r) => r.data);
  },
  reviewDocument: (documentId: string, status: EmployeeDocumentStatus, note?: string) =>
    apiClient
      .post<EmployeeDocument>(`/onboarding/documents/${documentId}/review`, { status, note })
      .then((r) => r.data),
  documentDownloadUrl: (documentId: string) =>
    `${apiClient.defaults.baseURL}/onboarding/documents/${documentId}/download`,
};
