import { OverallocationBadge } from "@/skins/hrms/components/OverallocationBadge";
import { useQuery } from "@tanstack/react-query";
import { Pencil } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { allocationsApi } from "@/skins/hrms/api/allocations";
import { projectsApi } from "@/skins/hrms/api/projects";
import type { Allocation } from "@/skins/hrms/api/types";
import { usePermission } from "@/skins/hrms/auth/usePermission";
import { Badge } from "@/skins/hrms/components/Badge";
import { Button } from "@/skins/hrms/components/Button";
import { Card, CardHeader, CardTitle } from "@/skins/hrms/components/Card";
import { Table, type Column } from "@/skins/hrms/components/Table";
import { FEATURES } from "@/skins/hrms/lib/features";

import { ProjectForm } from "./ProjectForm";

const HEALTH_TONE = { green: "success", amber: "warning", red: "danger" } as const;

const ENGAGEMENT_LABEL: Record<string, string> = {
  time_and_materials: "Time & Materials",
  fixed_bid: "Fixed Bid",
  retainer: "Retainer",
};

function Field({ label, value }: { label: string; value?: string | number | null }) {
  if (value === null || value === undefined || value === "") return null;
  return (
    <div>
      <div className="text-xs uppercase tracking-wider text-gray-600">{label}</div>
      <div className="mt-0.5 text-sm text-gray-900">{value}</div>
    </div>
  );
}

export default function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>();
  const canEdit = usePermission(FEATURES.PROJECTS, "edit");
  const canViewAllocations = usePermission(FEATURES.ALLOCATIONS, "view");
  const [editing, setEditing] = useState(false);

  const {
    data: project,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ["project", id],
    queryFn: () => projectsApi.get(id!),
    enabled: !!id,
  });

  const { data: allocations } = useQuery({
    queryKey: ["project-allocations", id],
    queryFn: () => allocationsApi.projectAllocations(id!),
    enabled: !!id && canViewAllocations,
  });

  if (isLoading) return <p className="text-sm text-gray-600">Loading…</p>;
  if (isError || !project) {
    return (
      <p className="text-sm text-gray-600">
        This project doesn&apos;t exist, or you don&apos;t have permission to view it.
      </p>
    );
  }

  const teamColumns: Column<Allocation>[] = [
    {
      key: "employee",
      header: "Employee",
      render: (a) => (
        <Link
          to={`/employees/${a.employee_id}`}
          className="font-medium text-gray-900 hover:text-cobalt"
        >
          {a.employee?.full_name ?? "—"}
        </Link>
      ),
    },
    { key: "role", header: "Role", render: (a) => a.role_on_project },
    { key: "pct", header: "Allocation", render: (a) => <div>{a.allocation_percent}%<OverallocationBadge allocation={a} /></div> },
    { key: "start", header: "From", render: (a) => a.start_date },
    { key: "end", header: "To", render: (a) => a.end_date ?? "Ongoing" },
    {
      key: "billable",
      header: "Billable",
      render: (a) => (
        <Badge tone={a.billable ? "success" : "neutral"}>{a.billable ? "Yes" : "No"}</Badge>
      ),
    },
  ];

  const totalAllocated = (allocations?.items ?? []).reduce(
    (sum, a) => sum + Number(a.allocation_percent),
    0
  );

  return (
    <div className="max-w-4xl space-y-6">
      <div className="flex items-start gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-light tracking-tight text-gray-900">{project.name}</h1>
            <Badge>{project.status}</Badge>
            <Badge tone={HEALTH_TONE[project.health]}>{project.health}</Badge>
          </div>
          <p className="text-sm text-gray-600">
            {project.code}
            {project.customer && (
              <>
                {" · "}
                <Link
                  to={`/customers/${project.customer.id}`}
                  className="hover:text-cobalt"
                >
                  {project.customer.name}
                </Link>
              </>
            )}
          </p>
        </div>
        {canEdit && project.can_edit && (
          <div className="ml-auto">
            <Button variant="secondary" onClick={() => setEditing(true)}>
              <Pencil size={14} /> Edit
            </Button>
          </div>
        )}
      </div>

      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div><p className="text-sm font-medium text-gray-900">Project approval: {project.approval_status.replace(/_/g, " ")}</p>
            <p className="mt-1 text-sm text-gray-600">{project.approval_status === "approved" ? "Approved for delivery. Material changes go through amendment approval." : "Allocations, timesheets and activation are unavailable until approval."}</p>
            {project.approval_request?.note && <p className="mt-2 text-sm text-gray-700">{project.approval_request.note}</p>}
          </div>
          {project.approval_request && <Link to={`/my-work/projects/${project.approval_request.id}`}><Button variant="secondary">
            {project.approval_request.kind === "amendment" ? `Amendment: ${project.approval_request.status.replace(/_/g, " ")}` : ["draft", "changes_requested"].includes(project.approval_request.status) ? "Review and submit request" : "View approval request"}
          </Button></Link>}
        </div>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Delivery</CardTitle>
        </CardHeader>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          <Field label="Project Manager" value={project.project_manager?.full_name} />
          <Field label="Delivery Manager" value={project.delivery_manager?.full_name} />
          <Field label="Engagement" value={ENGAGEMENT_LABEL[project.engagement_type]} />
          <Field label="Start Date" value={project.start_date} />
          <Field label="End Date" value={project.end_date ?? "Ongoing"} />
          <Field label="Practice" value={project.practice} />
          <Field label="Budgeted Hours" value={project.budgeted_hours} />
          <Field label="Team Size" value={project.allocated_headcount} />
        </div>
        {project.description && (
          <p className="mt-4 whitespace-pre-wrap text-sm text-gray-600">{project.description}</p>
        )}
      </Card>

      {/* Only rendered when the API actually returned commercial fields —
          each is stripped server-side without the matching permission key. */}
      {(project.billing_rate != null ||
        project.revenue != null ||
        project.margin_percent != null ||
        project.budget_amount != null) && (
        <Card>
          <CardHeader>
            <CardTitle>Commercials</CardTitle>
          </CardHeader>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <Field
              label="Billing Rate"
              value={
                project.billing_rate != null
                  ? `${project.currency} ${project.billing_rate.toLocaleString()}`
                  : null
              }
            />
            <Field
              label="Revenue"
              value={
                project.revenue != null
                  ? `${project.currency} ${project.revenue.toLocaleString()}`
                  : null
              }
            />
            <Field
              label="Budget"
              value={
                project.budget_amount != null
                  ? `${project.currency} ${project.budget_amount.toLocaleString()}`
                  : null
              }
            />
            <Field
              label="Margin"
              value={project.margin_percent != null ? `${project.margin_percent}%` : null}
            />
          </div>
        </Card>
      )}

      {canViewAllocations && (
        <Card>
          <CardHeader>
            <CardTitle>
              Team ({allocations?.total ?? 0}) · {totalAllocated}% allocated
            </CardTitle>
          </CardHeader>
          <Table
            columns={teamColumns}
            rows={allocations?.items ?? []}
            emptyMessage="Nobody is allocated to this project yet."
          />
        </Card>
      )}

      {editing && <ProjectForm project={project} onClose={() => setEditing(false)} />}
    </div>
  );
}
