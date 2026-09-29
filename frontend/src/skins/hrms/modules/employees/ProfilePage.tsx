import { OverallocationBadge } from "@/skins/hrms/components/OverallocationBadge";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, UserMinus, UserPlus } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { allocationsApi } from "@/skins/hrms/api/allocations";
import { assetsApi } from "@/skins/hrms/api/assets";
import { employeesApi } from "@/skins/hrms/api/employees";
import { onboardingApi } from "@/skins/hrms/api/onboarding";
import type { Allocation, EmployeeDocument } from "@/skins/hrms/api/types";
import { useAuth } from "@/skins/hrms/auth/AuthContext";
import { useFeatureScope, usePermission } from "@/skins/hrms/auth/usePermission";
import { Badge } from "@/skins/hrms/components/Badge";
import { Button } from "@/skins/hrms/components/Button";
import { CapacityBar } from "@/skins/hrms/components/CapacityBar";
import { Card, CardHeader, CardTitle } from "@/skins/hrms/components/Card";
import { ConfirmDialog } from "@/skins/hrms/components/ConfirmDialog";
import { Table, type Column } from "@/skins/hrms/components/Table";
import { FEATURES } from "@/skins/hrms/lib/features";

import { EmployeeForm } from "./EmployeeForm";
import { OffboardingModal } from "./OffboardingModal";
import {
  DOC_STATUS_STYLES,
  DOC_TYPE_LABELS,
  formatDate,
} from "../onboarding/shared";

function Field({ label, value }: { label: string; value?: string | number | null }) {
  if (value === null || value === undefined || value === "") return null;
  return (
    <div>
      <div className="text-xs uppercase tracking-wider text-gray-600">{label}</div>
      <div className="mt-0.5 text-sm text-gray-900">{value}</div>
    </div>
  );
}

const EMPLOYMENT_TYPE_LABEL: Record<string, string> = {
  full_time: "Full time",
  contract: "Contract",
  intern: "Intern",
};

export default function ProfilePage() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const { user } = useAuth();

  const canEditDirectory = usePermission(FEATURES.EMPLOYEE_DIRECTORY, "edit");
  const canOffboard = usePermission(FEATURES.EMPLOYEE_OFFBOARDING, "edit");
  const canViewAllocations = usePermission(FEATURES.ALLOCATIONS, "view");
  const canViewOnboarding = usePermission(FEATURES.EMPLOYEE_ONBOARDING, "view");
  const scope = useFeatureScope(FEATURES.EMPLOYEE_DIRECTORY);
  const isSelf = id === user?.employee_id;

  const [editing, setEditing] = useState(false);
  const [offboarding, setOffboarding] = useState(false);
  const [reactivating, setReactivating] = useState(false);

  const {
    data: employee,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ["employee", id],
    queryFn: () => employeesApi.get(id!),
    enabled: !!id,
  });
  const { data: allocations } = useQuery({
    queryKey: ["employee-allocations", id],
    queryFn: () => allocationsApi.employeeAllocations(id!),
    enabled: !!id && canViewAllocations,
  });
  const { data: capacity } = useQuery({
    queryKey: ["capacity", id],
    queryFn: () => allocationsApi.capacity(id!),
    enabled: !!id && canViewAllocations,
  });
  const { data: assetHistory } = useQuery({
    queryKey: ["employee-assets", id],
    queryFn: () => assetsApi.employeeHistory(id!),
    enabled: !!id,
  });
  const canSeeDocuments = isSelf || canViewOnboarding;
  const { data: documents } = useQuery({
    queryKey: ["employee-documents", id],
    queryFn: () => onboardingApi.listDocuments(id!),
    enabled: !!id && canSeeDocuments,
  });

  if (isLoading) return <p className="text-sm text-gray-600">Loading…</p>;
  if (isError || !employee) {
    return (
      <p className="text-sm text-gray-600">
        This employee doesn&apos;t exist, or you don&apos;t have permission to view their profile.
      </p>
    );
  }

  const isOffboarded = employee.employment_status === "offboarded";
  // A self-scoped grant can still edit contact details, just not role/department.
  const canEdit = canEditDirectory && (!isSelf || scope === "self" || scope === "all");

  const allocationColumns: Column<Allocation>[] = [
    {
      key: "project",
      header: "Project",
      render: (a) =>
        a.project ? (
          <Link to={`/projects/${a.project.id}`} className="text-gray-900 hover:text-cobalt">
            {a.project.name}
          </Link>
        ) : (
          "—"
        ),
    },
    { key: "role", header: "Role", render: (a) => a.role_on_project },
    { key: "pct", header: "Allocation", render: (a) => <div>{a.allocation_percent}%<OverallocationBadge allocation={a} /></div> },
    { key: "window", header: "Window", render: (a) => `${a.start_date} → ${a.end_date ?? "ongoing"}` },
    { key: "status", header: "Status", render: (a) => <Badge>{a.status}</Badge> },
  ];

  return (
    <div className="max-w-4xl space-y-6">
      <div className="flex items-center gap-4">
        <div className="flex h-16 w-16 items-center justify-center rounded-full bg-cobalt/10 text-xl font-semibold text-cobalt">
          {employee.first_name[0]}
          {employee.last_name[0]}
        </div>
        <div>
          <h1 className="text-2xl font-light tracking-tight text-gray-900">
            {employee.full_name}
          </h1>
          <p className="text-sm text-gray-600">
            {employee.designation} · {employee.department} · {employee.employee_code}
          </p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <Badge>{employee.employment_status}</Badge>
          {canEdit && !isOffboarded && (
            <Button variant="secondary" onClick={() => setEditing(true)}>
              <Pencil size={14} /> Edit
            </Button>
          )}
          {canOffboard && !isOffboarded && !isSelf && (
            <Button variant="danger" onClick={() => setOffboarding(true)}>
              <UserMinus size={14} /> Offboard
            </Button>
          )}
          {canEditDirectory && isOffboarded && (
            <Button variant="secondary" onClick={() => setReactivating(true)}>
              <UserPlus size={14} /> Reactivate
            </Button>
          )}
        </div>
      </div>

      {isOffboarded && (
        <Card className="border-danger/30 bg-danger/5">
          <CardHeader>
            <CardTitle>Offboarded</CardTitle>
          </CardHeader>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <Field label="Last Working Day" value={employee.last_working_day} />
            <Field label="Exit Type" value={employee.exit_type?.replace(/_/g, " ")} />
            <Field
              label="Rehire Eligible"
              value={employee.rehire_eligible == null ? null : employee.rehire_eligible ? "Yes" : "No"}
            />
            <Field label="Reason" value={employee.exit_reason} />
          </div>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Profile</CardTitle>
        </CardHeader>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          <Field label="Work Email" value={employee.work_email} />
          <Field label="Phone" value={employee.phone} />
          <Field label="Reports To" value={employee.reports_to?.full_name} />
          <Field label="Date Joined" value={employee.date_joined} />
          <Field
            label="Employment Type"
            value={EMPLOYMENT_TYPE_LABEL[employee.employment_type]}
          />
          <Field label="Work Location" value={employee.work_location} />
          <Field label="Confirmation Date" value={employee.confirmation_date} />
          <Field
            label="Notice Period"
            value={employee.notice_period_days ? `${employee.notice_period_days} days` : null}
          />
          <Field label="Skills" value={employee.skills} />
          <Field label="Personal Email" value={employee.personal_email} />
          <Field label="Address" value={employee.address} />
          <Field label="Date of Birth" value={employee.date_of_birth} />
        </div>
      </Card>

      {/* Present only when the caller's data profile + permission keys allowed it. */}
      {(employee.salary_ctc != null ||
        employee.bank_account_number != null ||
        employee.employee_cost_rate != null ||
        employee.payroll_reference != null) && (
        <Card>
          <CardHeader>
            <CardTitle>Compensation &amp; Payroll</CardTitle>
          </CardHeader>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <Field
              label="Salary (CTC)"
              value={employee.salary_ctc ? `₹${employee.salary_ctc.toLocaleString()}` : null}
            />
            <Field label="Bank Account" value={employee.bank_account_number} />
            <Field label="IFSC" value={employee.bank_ifsc} />
            <Field label="Razorpay ID" value={employee.payroll_reference} />
            <Field
              label="Cost Rate"
              value={
                employee.employee_cost_rate
                  ? `₹${employee.employee_cost_rate.toLocaleString()}/mo`
                  : null
              }
            />
          </div>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Role</CardTitle>
        </CardHeader>
        <Badge tone="info">{employee.role.name}</Badge>
      </Card>

      {canViewAllocations && (
        <Card>
          <CardHeader>
            <CardTitle>Allocations ({allocations?.total ?? 0})</CardTitle>
          </CardHeader>
          {capacity && (
            <div className="mb-4">
              <CapacityBar
                percent={capacity.total_allocation_percent}
                label="Committed today"
              />
            </div>
          )}
          <Table
            columns={allocationColumns}
            rows={allocations?.items ?? []}
            emptyMessage="Not allocated to any project."
          />
        </Card>
      )}

      {canSeeDocuments && (
        <Card>
          <CardHeader>
            <CardTitle>Documents ({documents?.length ?? 0})</CardTitle>
          </CardHeader>
          {!documents || documents.length === 0 ? (
            <p className="text-sm text-gray-600">No documents uploaded yet.</p>
          ) : (
            <ul className="divide-y divide-gray-100">
              {documents.map((doc: EmployeeDocument) => (
                <li key={doc.id} className="flex items-center justify-between gap-3 py-2">
                  <div className="min-w-0">
                    <div className="text-sm text-gray-900">{DOC_TYPE_LABELS[doc.doc_type]}</div>
                    <div className="text-xs text-gray-600">
                      {doc.file_name} · {formatDate(doc.created_at)}
                    </div>
                  </div>
                  <span
                    className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${DOC_STATUS_STYLES[doc.status]}`}
                  >
                    {doc.status}
                  </span>
                  <a
                    href={onboardingApi.documentDownloadUrl(doc.id)}
                    target="_blank"
                    rel="noreferrer"
                    className="text-sm text-cobalt hover:underline"
                  >
                    Download
                  </a>
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}
      {assetHistory && assetHistory.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Asset History</CardTitle>
          </CardHeader>
          <ul className="space-y-2 text-sm">
            {assetHistory.map((a) => (
              <li key={a.id} className="flex items-center justify-between">
                <span className="text-gray-900">
                  Assigned {a.assigned_date}
                  {a.returned_date && ` — Returned ${a.returned_date}`}
                </span>
                <Badge tone={a.returned_date ? "neutral" : "success"}>
                  {a.returned_date ? "Returned" : "Active"}
                </Badge>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {editing && <EmployeeForm employee={employee} onClose={() => setEditing(false)} />}
      {offboarding && (
        <OffboardingModal employee={employee} onClose={() => setOffboarding(false)} />
      )}
      <ConfirmDialog
        open={reactivating}
        title={`Reactivate ${employee.full_name}?`}
        message="This restores their active status and re-enables their login."
        confirmLabel="Reactivate"
        onConfirm={async () => {
          await employeesApi.reactivate(employee.id);
          await queryClient.invalidateQueries({ queryKey: ["employee", id] });
        }}
        onClose={() => setReactivating(false)}
      />
    </div>
  );
}
