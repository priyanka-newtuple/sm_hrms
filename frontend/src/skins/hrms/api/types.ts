export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface FeaturePermission {
  feature_key: string;
  actions: string[];
  record_scope: string;
  data_profile: string;
}

export interface CurrentUser {
  user_id: string;
  email: string;
  employee_id: string;
  full_name: string;
  role_id: string;
  role_name: string;
  department: string;
  designation: string;
  permissions: FeaturePermission[];
  permission_keys: string[];
}

export interface Role {
  id: string;
  name: string;
}

export type EmploymentStatus = "active" | "on_leave" | "offboarding" | "offboarded";

export interface Employee {
  id: string;
  employee_code: string;
  first_name: string;
  last_name: string;
  full_name: string;
  work_email: string;
  department: string;
  designation: string;
  employment_status: EmploymentStatus;
  employment_type: EmploymentType;
  date_joined: string;
  work_location?: string | null;
  probation_end_date?: string | null;
  confirmation_date?: string | null;
  notice_period_days?: number | null;
  reports_to_id: string | null;
  reports_to?: EmployeeSummary | null;
  role_id: string;
  role: Role;
  phone?: string | null;
  skills?: string | null;
  // Offboarding
  last_working_day?: string | null;
  exit_type?: ExitType | null;
  exit_reason?: string | null;
  rehire_eligible?: boolean | null;
  // Sensitive — absent unless the caller's data profile / permission keys allow
  personal_email?: string | null;
  date_of_birth?: string | null;
  address?: string | null;
  salary_ctc?: number | null;
  bank_account_number?: string | null;
  bank_ifsc?: string | null;
  payroll_reference?: string | null;
  employee_cost_rate?: number | null;
}

/** Nested summaries returned by the API so the UI needn't resolve ids itself. */
export interface EmployeeSummary {
  id: string;
  employee_code: string;
  full_name: string;
  designation: string;
  department: string;
}

export interface CustomerSummary {
  id: string;
  code: string;
  name: string;
}

export interface ProjectSummary {
  id: string;
  code: string;
  name: string;
  status: string;
  customer?: CustomerSummary | null;
}

export type CustomerStatus = "prospect" | "active" | "on_hold" | "archived";
export type ProjectStatusValue =
  | "planned"
  | "active"
  | "on_hold"
  | "completed"
  | "archived";
export type EngagementType = "time_and_materials" | "fixed_bid" | "retainer";
export type ProjectHealth = "green" | "amber" | "red";
export type AllocationStatus = "planned" | "active" | "completed" | "cancelled";
export type EmploymentType = "full_time" | "contract" | "intern";
export type ExitType = "resignation" | "termination" | "end_of_contract" | "retirement";

export interface Customer {
  id: string;
  code: string;
  name: string;
  status: CustomerStatus;
  industry?: string | null;
  contact_name?: string | null;
  contact_email?: string | null;
  account_owner_id?: string | null;
  account_owner?: EmployeeSummary | null;
  contract_start_date?: string | null;
  contract_end_date?: string | null;
  currency: string;
  country?: string | null;
  billing_address?: string | null;
  notes?: string | null;
  project_count?: number | null;
  // Stripped without VIEW_CUSTOMER_CONTRACT_VALUE
  contract_value?: number | null;
  payment_terms_days?: number | null;
}

export interface Project {
  approval_status: "draft" | "pending" | "changes_requested" | "rejected" | "approved";
  created_by_id?: string | null;
  can_edit?: boolean;
  approval_request?: import("./projects").ProjectRequest | null;
  approval_history?: import("./projects").ProjectRequest[];
  id: string;
  code: string;
  name: string;
  status: ProjectStatusValue;
  customer_id: string;
  customer?: CustomerSummary | null;
  project_manager_id: string;
  project_manager?: EmployeeSummary | null;
  delivery_manager_id?: string | null;
  delivery_manager?: EmployeeSummary | null;
  start_date: string;
  end_date?: string | null;
  description?: string | null;
  engagement_type: EngagementType;
  health: ProjectHealth;
  currency: string;
  practice?: string | null;
  budgeted_hours?: number | null;
  allocated_headcount?: number | null;
  // Each stripped without its respective VIEW_* permission key
  budget_amount?: number | null;
  billing_rate?: number | null;
  revenue?: number | null;
  margin_percent?: number | null;
}

export interface CapacityPeriod {
  start_date: string; end_date: string | null; total_allocation_percent: number; excess_percent: number;
}

export interface Allocation {
  over_allocated?: boolean;
  total_allocation_percent?: number;
  overallocated_periods?: CapacityPeriod[];
  id: string;
  employee_id: string;
  employee?: EmployeeSummary | null;
  project_id: string;
  project?: ProjectSummary | null;
  allocation_percent: number;
  role_on_project: string;
  start_date: string;
  end_date?: string | null;
  status: AllocationStatus;
  billable: boolean;
  notes?: string | null;
  allocated_by_id?: string | null;
  billing_rate_override?: number | null;
}

export interface CapacityConflict {
  allocation_id: string;
  project_name: string;
  allocation_percent: number;
  start_date: string;
  end_date?: string | null;
}

/** POST/PATCH /allocations returns the row plus a capacity verdict. */
export interface AllocationWriteResult {
  allocation: Allocation;
  over_allocated: boolean;
  total_allocation_percent: number;
  conflicts: CapacityConflict[];
}

export interface Capacity {
  employee_id: string;
  on_date: string;
  total_allocation_percent: number;
  available_percent: number;
  over_allocated: boolean;
  allocations: CapacityConflict[];
}

export interface OffboardingBlocker {
  kind: string;
  message: string;
  items: Record<string, string>[];
}

export interface OffboardingReadiness {
  employee_id: string;
  ready: boolean;
  blockers: OffboardingBlocker[];
}

export interface Timesheet {
  id: string;
  employee_id: string;
  project_id: string;
  week_start_date: string;
  work_date?: string | null;
  hours: number;
  status: "draft" | "submitted" | "approved" | "rejected";
  notes?: string | null;
  task_details?: string | null;
  submitted_at?: string | null;
}

export interface Asset {
  id: string;
  asset_tag: string;
  name: string;
  asset_type: string;
  serial_number?: string | null;
  status: "in_stock" | "assigned" | "under_repair" | "retired";
  purchase_date?: string | null;
  notes?: string | null;
}

export interface AssetAssignment {
  id: string;
  asset_id: string;
  employee_id: string;
  assigned_date: string;
  returned_date?: string | null;
  condition_notes?: string | null;
}

export interface HelpdeskCategory {
  id: string;
  name: string;
  department: string;
}

export interface Ticket {
  id: string;
  ticket_number: string;
  category_id: string;
  raised_by_id: string;
  assigned_to_id?: string | null;
  subject: string;
  description: string;
  priority: "low" | "medium" | "high" | "urgent";
  status: "open" | "assigned" | "in_progress" | "resolved" | "closed";
  resolved_at?: string | null;
}

export type OnboardingTaskStatus = "pending" | "ready" | "done" | "skipped";
export type OnboardingTaskAction =
  | "manual"
  | "invite_employee"
  | "employee_profile"
  | "document_collection"
  | "asset_assignment"
  | "project_allocation";

export interface OnboardingTask {
  id: string;
  seq: number;
  step_key?: string | null;
  title: string;
  description?: string | null;
  status: OnboardingTaskStatus;
  action_type: OnboardingTaskAction;
  is_complete: boolean;
  due_date?: string | null;
  depends_on_seqs?: number[] | null;
  assignee_employee_id?: string | null;
  assignee_role?: string | null;
  assignee_name?: string | null;
  completed_at?: string | null;
  completed_by_name?: string | null;
  completion_note?: string | null;
  linked_entity_type?: string | null;
  linked_entity_id?: string | null;
}

/** Summary of the person being onboarded, embedded in onboarding responses. */
export interface OnboardingEmployee {
  id: string;
  full_name: string;
  department: string;
  designation: string;
  work_email: string;
  date_joined: string;
}

export interface OnboardingRecord {
  id: string;
  employee_id: string;
  workflow_type: "onboarding" | "offboarding";
  status: "not_started" | "in_progress" | "completed";
  flowtuple_workflow_id?: string | null;
  embed_url?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  tasks: OnboardingTask[];
  employee?: OnboardingEmployee | null;
  progress_done: number;
  progress_total: number;
  current_task_title?: string | null;
  current_assignee_name?: string | null;
  current_due_date?: string | null;
}

export type EmployeeDocumentType =
  | "id_proof"
  | "address_proof"
  | "pan"
  | "education_certificate"
  | "experience_certificate"
  | "signed_offer_letter"
  | "other";

export type EmployeeDocumentStatus = "submitted" | "verified" | "rejected";

export interface EmployeeDocument {
  id: string;
  employee_id: string;
  doc_type: EmployeeDocumentType;
  file_name: string;
  content_type?: string | null;
  size_bytes?: number | null;
  status: EmployeeDocumentStatus;
  note?: string | null;
  created_at: string;
  verified_at?: string | null;
  verified_by_name?: string | null;
}

export interface EmployeeInvitation {
  id: string;
  email: string;
  status: "pending" | "accepted" | "expired";
  expires_at: string;
  accepted_at?: string | null;
}

export interface OnboardingDetail extends OnboardingRecord {
  documents: EmployeeDocument[];
  invitation?: EmployeeInvitation | null;
}

/** One actionable onboarding step for the current user. */
export interface MyOnboardingAction {
  record_id: string;
  task: OnboardingTask;
  employee: OnboardingEmployee;
  workflow_type: "onboarding" | "offboarding";
  overdue: boolean;
}
