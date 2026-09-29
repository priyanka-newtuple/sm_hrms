import { useQuery } from "@tanstack/react-query";
import { Pencil } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { customersApi } from "@/skins/hrms/api/projects";
import type { Project } from "@/skins/hrms/api/types";
import { usePermission } from "@/skins/hrms/auth/usePermission";
import { Badge } from "@/skins/hrms/components/Badge";
import { Button } from "@/skins/hrms/components/Button";
import { Card, CardHeader, CardTitle } from "@/skins/hrms/components/Card";
import { Table, type Column } from "@/skins/hrms/components/Table";
import { FEATURES } from "@/skins/hrms/lib/features";

import { CustomerForm } from "./CustomerForm";

function Field({ label, value }: { label: string; value?: string | number | null }) {
  if (value === null || value === undefined || value === "") return null;
  return (
    <div>
      <div className="text-xs uppercase tracking-wider text-gray-600">{label}</div>
      <div className="mt-0.5 text-sm text-gray-900">{value}</div>
    </div>
  );
}

export default function CustomerDetailPage() {
  const { id } = useParams<{ id: string }>();
  const canEdit = usePermission(FEATURES.CUSTOMERS, "edit");
  const [editing, setEditing] = useState(false);

  const {
    data: customer,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ["customer", id],
    queryFn: () => customersApi.get(id!),
    enabled: !!id,
  });

  const { data: projects } = useQuery({
    queryKey: ["customer-projects", id],
    queryFn: () => customersApi.projects(id!),
    enabled: !!id,
  });

  if (isLoading) return <p className="text-sm text-gray-600">Loading…</p>;
  if (isError || !customer) {
    return (
      <p className="text-sm text-gray-600">
        This customer doesn&apos;t exist, or you don&apos;t have permission to view it.
      </p>
    );
  }

  const projectColumns: Column<Project>[] = [
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
    { key: "status", header: "Status", render: (p) => <Badge>{p.status}</Badge> },
    { key: "pm", header: "Project Manager", render: (p) => p.project_manager?.full_name ?? "—" },
    { key: "start", header: "Start", render: (p) => p.start_date },
  ];

  return (
    <div className="max-w-4xl space-y-6">
      <div className="flex items-start gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-light tracking-tight text-gray-900">{customer.name}</h1>
            <Badge>{customer.status}</Badge>
          </div>
          <p className="text-sm text-gray-600">
            {customer.code}
            {customer.industry && ` · ${customer.industry}`}
          </p>
        </div>
        {canEdit && (
          <div className="ml-auto">
            <Button variant="secondary" onClick={() => setEditing(true)}>
              <Pencil size={14} /> Edit
            </Button>
          </div>
        )}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Account</CardTitle>
        </CardHeader>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          <Field label="Account Owner" value={customer.account_owner?.full_name} />
          <Field label="Contact" value={customer.contact_name} />
          <Field label="Contact Email" value={customer.contact_email} />
          <Field label="Country" value={customer.country} />
          <Field label="Contract Start" value={customer.contract_start_date} />
          <Field label="Contract End" value={customer.contract_end_date} />
          <Field label="Billing Address" value={customer.billing_address} />
        </div>
      </Card>

      {/* Rendered only when the API actually returned commercial fields. */}
      {(customer.contract_value != null || customer.payment_terms_days != null) && (
        <Card>
          <CardHeader>
            <CardTitle>Commercials</CardTitle>
          </CardHeader>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
            <Field
              label="Contract Value"
              value={
                customer.contract_value != null
                  ? `${customer.currency} ${customer.contract_value.toLocaleString()}`
                  : null
              }
            />
            <Field
              label="Payment Terms"
              value={
                customer.payment_terms_days != null
                  ? `${customer.payment_terms_days} days`
                  : null
              }
            />
          </div>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Projects ({projects?.total ?? 0})</CardTitle>
        </CardHeader>
        <Table
          columns={projectColumns}
          rows={projects?.items ?? []}
          emptyMessage="No projects for this customer yet."
        />
      </Card>

      {customer.notes && (
        <Card>
          <CardHeader>
            <CardTitle>Notes</CardTitle>
          </CardHeader>
          <p className="whitespace-pre-wrap text-sm text-gray-600">{customer.notes}</p>
        </Card>
      )}

      {editing && <CustomerForm customer={customer} onClose={() => setEditing(false)} />}
    </div>
  );
}
