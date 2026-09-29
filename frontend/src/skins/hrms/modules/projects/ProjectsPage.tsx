import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, Pencil, Plus } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { projectsApi } from "@/skins/hrms/api/projects";
import type { Project } from "@/skins/hrms/api/types";
import { usePermission } from "@/skins/hrms/auth/usePermission";
import { Badge } from "@/skins/hrms/components/Badge";
import { Button } from "@/skins/hrms/components/Button";
import { Card, CardHeader, CardTitle } from "@/skins/hrms/components/Card";
import { ConfirmDialog } from "@/skins/hrms/components/ConfirmDialog";
import { Select, TextInput } from "@/skins/hrms/components/Form";
import { Table, type Column } from "@/skins/hrms/components/Table";
import { FEATURES } from "@/skins/hrms/lib/features";

import { ProjectForm } from "./ProjectForm";

const HEALTH_TONE = { green: "success", amber: "warning", red: "danger" } as const;

export default function ProjectsPage() {
  const queryClient = useQueryClient();
  const canCreate = usePermission(FEATURES.PROJECTS, "create");
  const canEdit = usePermission(FEATURES.PROJECTS, "edit");

  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Project | null>(null);
  const [archiving, setArchiving] = useState<Project | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["projects", search, status],
    queryFn: () =>
      projectsApi.list({ search: search || undefined, status: status || undefined }),
  });

  const columns: Column<Project>[] = [
    {
      key: "name",
      header: "Project",
      render: (p) => (
        <Link to={`/projects/${p.id}`} className="font-medium text-gray-900 hover:text-cobalt">
          {p.name}
        </Link>
      ),
    },
    { key: "code", header: "Code", render: (p) => p.code },
    // Nested customer comes straight from the API — no client-side id lookup.
    { key: "customer", header: "Customer", render: (p) => p.customer?.name ?? "—" },
    { key: "approval", header: "Approval", render: (p) => <Badge>{p.approval_request?.kind === "amendment" && ["draft", "pending", "changes_requested"].includes(p.approval_request.status) ? `Amendment: ${p.approval_request.status}` : p.approval_status}</Badge> },
    { key: "status", header: "Status", render: (p) => <Badge>{p.status}</Badge> },
    {
      key: "health",
      header: "Health",
      render: (p) => <Badge tone={HEALTH_TONE[p.health]}>{p.health}</Badge>,
    },
    { key: "pm", header: "Manager", render: (p) => p.project_manager?.full_name ?? "—" },
    {
      key: "rate",
      header: "Billing Rate",
      render: (p) =>
        p.billing_rate != null ? `${p.currency} ${p.billing_rate.toLocaleString()}` : "—",
    },
    {
      key: "actions",
      header: "",
      render: (p) =>
        canEdit && p.can_edit ? (
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setEditing(p)} aria-label="Edit">
              <Pencil size={14} />
            </Button>
            {p.status !== "archived" && p.approval_status === "approved" && (!p.approval_request || !["draft", "pending", "changes_requested"].includes(p.approval_request.status)) && (
              <Button variant="ghost" onClick={() => setArchiving(p)} aria-label="Archive">
                <Archive size={14} />
              </Button>
            )}
          </div>
        ) : null,
    },
  ];

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-light tracking-tight text-gray-900">Projects</h1>
        {canCreate && (
          <Button onClick={() => setCreating(true)}>
            <Plus size={16} /> New Project
          </Button>
        )}
      </div>

      <div className="mb-4 flex gap-3">
        <TextInput
          placeholder="Search by name or code…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-xs"
        />
        <Select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="max-w-[12rem]"
        >
          <option value="">All statuses</option>
          <option value="planned">Planned</option>
          <option value="active">Active</option>
          <option value="on_hold">On hold</option>
          <option value="completed">Completed</option>
        </Select>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{data?.total ?? 0} projects</CardTitle>
        </CardHeader>
        {isLoading ? (
          <p className="text-sm text-gray-600">Loading…</p>
        ) : (
          <Table columns={columns} rows={data?.items ?? []} />
        )}
      </Card>

      {creating && <ProjectForm onClose={() => setCreating(false)} />}
      {editing && <ProjectForm project={editing} onClose={() => setEditing(null)} />}
      <ConfirmDialog
        open={!!archiving}
        title={`Archive ${archiving?.name ?? ""}?`}
        message="Archiving hides the project from the default list. Nothing is deleted, and it will be refused while active allocations remain."
        confirmLabel="Archive"
        onConfirm={async () => {
          if (archiving) {
            await projectsApi.archive(archiving.id);
            await queryClient.invalidateQueries({ queryKey: ["projects"] });
          }
        }}
        onClose={() => setArchiving(null)}
      />
    </div>
  );
}
