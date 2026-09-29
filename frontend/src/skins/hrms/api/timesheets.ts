import { apiClient } from "./client";
import type { Timesheet } from "./types";

export interface Holiday {
  id: string;
  holiday_date: string;
  name: string;
  description?: string | null;
  is_optional: boolean;
}

export interface LeaveRequest {
  id: string;
  employee_id: string;
  employee_name?: string | null;
  manager_id?: string | null;
  start_date: string;
  end_date: string;
  leave_type: string;
  reason?: string | null;
  status: string;
  decision_comment?: string | null;
}

export interface TimesheetEntry extends Timesheet {
  work_date: string;
  task_details?: string | null;
  project_name: string;
  employee_name?: string | null;
}

export interface WeekView {
  week_start_date: string;
  days: string[];
  projects: { id: string; name: string }[];
  entries: TimesheetEntry[];
  holidays: Holiday[];
  leaves: LeaveRequest[];
  total_hours: number;
  submission?: TimesheetSubmission | null;
}

export interface TimesheetSubmission {
  week_start_date: string;
  status: "submitted" | "approved" | "rejected" | "partially_reviewed";
  total_hours: number;
  submitted_at?: string | null;
  pending_with_id?: string | null;
  pending_with_name?: string | null;
  decision_comment?: string | null;
  decided_by_name?: string | null;
  decided_at?: string | null;
}

export interface MonthView {
  month: string;
  entries: TimesheetEntry[];
  holidays: Holiday[];
  leaves: LeaveRequest[];
  total_hours: number;
}

export interface ApprovalWeek {
  employee_id: string;
  employee_name: string;
  week_start_date: string;
  total_hours: number;
  entries: TimesheetEntry[];
}

export const timesheetsApi = {
  week: (weekStart: string) =>
    apiClient.get<WeekView>("/timesheets/week", { params: { week_start: weekStart } }).then(r => r.data),
  saveWeek: (week_start_date: string, entries: {project_id: string; work_date: string; hours: number; task_details?: string | null}[]) =>
    apiClient.put<WeekView>("/timesheets/week", { week_start_date, entries }).then(r => r.data),
  submitWeek: (weekStart: string) =>
    apiClient.post<WeekView>("/timesheets/week/submit", null, { params: { week_start: weekStart } }).then(r => r.data),
  month: (month: string) =>
    apiClient.get<MonthView>("/timesheets/month", { params: { month: `${month}-01` } }).then(r => r.data),
  submissions: () => apiClient.get<TimesheetSubmission[]>("/timesheets/submissions").then(r => r.data),
  approvals: () => apiClient.get<ApprovalWeek[]>("/timesheets/approvals").then(r => r.data),
  decideWeek: (employeeId: string, weekStart: string, action: "approve" | "reject", comment?: string) =>
    apiClient.post(`/timesheets/approvals/${employeeId}/${weekStart}/decision`, { action, comment }).then(r => r.data),
  holidays: (year: number) =>
    apiClient.get<Holiday[]>("/timesheets/holidays", { params: { year } }).then(r => r.data),
  createHoliday: (payload: Omit<Holiday, "id">) =>
    apiClient.post<Holiday>("/timesheets/holidays", payload).then(r => r.data),
  updateHoliday: (id: string, payload: Omit<Holiday, "id">) =>
    apiClient.put<Holiday>(`/timesheets/holidays/${id}`, payload).then(r => r.data),
  removeHoliday: (id: string) => apiClient.delete(`/timesheets/holidays/${id}`).then(r => r.data),
  leaves: (approvals = false) =>
    apiClient.get<LeaveRequest[]>("/timesheets/leave-requests", { params: { approvals } }).then(r => r.data),
  applyLeave: (payload: {start_date: string; end_date: string; leave_type: string; reason?: string | null}) =>
    apiClient.post<LeaveRequest>("/timesheets/leave-requests", payload).then(r => r.data),
  decideLeave: (id: string, decision: "approve" | "reject", comment?: string) =>
    apiClient.post<LeaveRequest>(`/timesheets/leave-requests/${id}/decision`, { decision, comment }).then(r => r.data),
  cancelLeave: (id: string) => apiClient.post(`/timesheets/leave-requests/${id}/cancel`).then(r => r.data),
};
