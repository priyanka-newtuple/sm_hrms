import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Ban, Pencil, Plus } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { allocationsApi } from "@/skins/hrms/api/allocations";
import type { Allocation } from "@/skins/hrms/api/types";
import { usePermission } from "@/skins/hrms/auth/usePermission";
import { OverallocationBadge } from "@/skins/hrms/components/OverallocationBadge";
import { Badge } from "@/skins/hrms/components/Badge";
import { Button } from "@/skins/hrms/components/Button";
import { Card, CardHeader, CardTitle } from "@/skins/hrms/components/Card";
import { ConfirmDialog } from "@/skins/hrms/components/ConfirmDialog";
import { Select } from "@/skins/hrms/components/Form";
import { Table, type Column } from "@/skins/hrms/components/Table";
import { FEATURES } from "@/skins/hrms/lib/features";

import { AllocationForm } from "./AllocationForm";

export default function AllocationsPage() {
  const queryClient = useQueryClient();
  const canCreate = usePermission(FEATURES.ALLOCATIONS, "create");
  const canEdit = usePermission(FEATURES.ALLOCATIONS, "edit");

  const [includeCancelled, setIncludeCancelled] = useState(false);
  const [overallocatedOnly, setOverallocatedOnly] = useState(false);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Allocation | null>(null);
  const [cancelling, setCancelling] = useState<Allocation | null>(null);
  const [searchParams, setSearchParams] = useSearchParams();
  const prefillEmployee = searchParams.get("employee");

  useEffect(() => {
    if (prefillEmployee && canCreate) setCreating(true);
  }, [prefillEmployee, canCreate]);

  const { data, isLoading } = useQuery({
    queryKey: ["allocations", includeCancelled, overallocatedOnly],
    queryFn: () => allocationsApi.list({ include_cancelled: includeCancelled, overallocated_only: overallocatedOnly }),
  });

  const columns: Column<Allocation>[] = [
    {
      key: "employee",
      header: "Employee",
      // Nested from the API — no client-side id→name resolution needed.
      render: (a) => (
        <Link
          to={`/employees/${a.employee_id}`}
          className="font-medium text-gray-900 hover:text-cobalt"
        >
          {a.employee?.full_name ?? "—"}
        </Link>
      ),
    },
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
    { key: "customer", header: "Customer", render: (a) => a.project?.customer?.name ?? "—" },
    { key: "role", header: "Role", render: (a) => a.role_on_project },
    { key: "pct", header: "Allocation", render: (a) => <div>{a.allocation_percent}%<OverallocationBadge allocation={a} /></div> },
    { key: "window", header: "Window", render: (a) => `${a.start_date} → ${a.end_date ?? "ongoing"}` },
    { key: "status", header: "Status", render: (a) => <Badge>{a.status}</Badge> },
    {
      key: "actions",
      header: "",
      render: (a) =>
        canEdit && a.status !== "cancelled" ? (
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setEditing(a)} aria-label="Edit">
              <Pencil size={14} />
            </Button>
            <Button variant="ghost" onClick={() => setCancelling(a)} aria-label="Cancel">
              <Ban size={14} />
            </Button>
          </div>
        ) : null,
    },
  ];

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-light tracking-tight text-gray-900">Allocations</h1>
        {canCreate && (
          <Button onClick={() => setCreating(true)}>
            <Plus size={16} /> New Allocation
          </Button>
        )}
      </div>

      <div className="mb-4 flex items-center gap-4">
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={overallocatedOnly} onChange={e => setOverallocatedOnly(e.target.checked)} />Overallocated only</label>
        <Select
          value={includeCancelled ? "all" : "active"}
          onChange={(e) => setIncludeCancelled(e.target.value === "all")}
          className="max-w-[14rem]"
        >
          <option value="active">Active only</option>
          <option value="all">Include cancelled</option>
        </Select>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{data?.total ?? 0} allocations</CardTitle>
        </CardHeader>
        {isLoading ? (
          <p className="text-sm text-gray-600">Loading…</p>
        ) : (
          <Table columns={columns} rows={data?.items ?? []} />
        )}
      </Card>

      {creating && (
        <AllocationForm
          defaultEmployeeId={prefillEmployee ?? undefined}
          onClose={() => {
            setCreating(false);
            if (prefillEmployee) setSearchParams({});
          }}
        />
      )}
      {editing && <AllocationForm allocation={editing} onClose={() => setEditing(null)} />}
      <ConfirmDialog
        open={!!cancelling}
        title="Cancel this allocation?"
        message="The allocation is marked cancelled and stops counting toward capacity. The record is kept for history rather than deleted."
        confirmLabel="Cancel allocation"
        variant="danger"
        onConfirm={async () => {
          if (cancelling) {
            await allocationsApi.cancel(cancelling.id);
            await queryClient.invalidateQueries({ queryKey: ["allocations"] });
          }
        }}
        onClose={() => setCancelling(null)}
      />
    </div>
  );
}
