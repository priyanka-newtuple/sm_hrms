import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, Pencil, Plus } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { customersApi } from "@/skins/hrms/api/projects";
import type { Customer } from "@/skins/hrms/api/types";
import { usePermission } from "@/skins/hrms/auth/usePermission";
import { Badge } from "@/skins/hrms/components/Badge";
import { Button } from "@/skins/hrms/components/Button";
import { Card, CardHeader, CardTitle } from "@/skins/hrms/components/Card";
import { ConfirmDialog } from "@/skins/hrms/components/ConfirmDialog";
import { Select, TextInput } from "@/skins/hrms/components/Form";
import { Table, type Column } from "@/skins/hrms/components/Table";
import { FEATURES } from "@/skins/hrms/lib/features";

import { CustomerForm } from "./CustomerForm";

export default function CustomersPage() {
  const queryClient = useQueryClient();
  const canCreate = usePermission(FEATURES.CUSTOMERS, "create");
  const canEdit = usePermission(FEATURES.CUSTOMERS, "edit");

  const [search, setSearch] = useState("");
  const [includeArchived, setIncludeArchived] = useState(false);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Customer | null>(null);
  const [archiving, setArchiving] = useState<Customer | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["customers", search, includeArchived],
    queryFn: () =>
      customersApi.list({ search: search || undefined, include_archived: includeArchived }),
  });

  const columns: Column<Customer>[] = [
    {
      key: "name",
      header: "Customer",
      render: (c) => (
        <Link to={`/customers/${c.id}`} className="font-medium text-gray-900 hover:text-cobalt">
          {c.name}
        </Link>
      ),
    },
    { key: "code", header: "Code", render: (c) => c.code },
    { key: "status", header: "Status", render: (c) => <Badge>{c.status}</Badge> },
    { key: "industry", header: "Industry", render: (c) => c.industry ?? "—" },
    { key: "owner", header: "Account Owner", render: (c) => c.account_owner?.full_name ?? "—" },
    {
      key: "contract",
      header: "Contract Value",
      // Absent entirely (not null) when the role lacks VIEW_CUSTOMER_CONTRACT_VALUE.
      render: (c) =>
        c.contract_value != null
          ? `${c.currency} ${c.contract_value.toLocaleString()}`
          : "—",
    },
    {
      key: "actions",
      header: "",
      render: (c) =>
        canEdit ? (
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setEditing(c)} aria-label="Edit">
              <Pencil size={14} />
            </Button>
            {c.status !== "archived" && (
              <Button variant="ghost" onClick={() => setArchiving(c)} aria-label="Archive">
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
        <h1 className="text-2xl font-light tracking-tight text-gray-900">Customers</h1>
        {canCreate && (
          <Button onClick={() => setCreating(true)}>
            <Plus size={16} /> Add Customer
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
          value={includeArchived ? "all" : "active"}
          onChange={(e) => setIncludeArchived(e.target.value === "all")}
          className="max-w-[12rem]"
        >
          <option value="active">Active only</option>
          <option value="all">Include archived</option>
        </Select>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{data?.total ?? 0} customers</CardTitle>
        </CardHeader>
        {isLoading ? (
          <p className="text-sm text-gray-600">Loading…</p>
        ) : (
          <Table columns={columns} rows={data?.items ?? []} />
        )}
      </Card>

      {creating && <CustomerForm onClose={() => setCreating(false)} />}
      {editing && <CustomerForm customer={editing} onClose={() => setEditing(null)} />}
      <ConfirmDialog
        open={!!archiving}
        title={`Archive ${archiving?.name ?? ""}?`}
        message="Archiving hides the customer from the default list. Nothing is deleted, and it will be refused if any projects are still open."
        confirmLabel="Archive"
        onConfirm={async () => {
          if (archiving) {
            await customersApi.archive(archiving.id);
            await queryClient.invalidateQueries({ queryKey: ["customers"] });
          }
        }}
        onClose={() => setArchiving(null)}
      />
    </div>
  );
}
