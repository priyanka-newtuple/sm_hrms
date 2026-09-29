import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import { assetsApi } from "@/skins/hrms/api/assets";
import { employeesApi } from "@/skins/hrms/api/employees";
import type { Asset } from "@/skins/hrms/api/types";
import { usePermission } from "@/skins/hrms/auth/usePermission";
import { Badge } from "@/skins/hrms/components/Badge";
import { Button } from "@/skins/hrms/components/Button";
import { Card, CardHeader, CardTitle } from "@/skins/hrms/components/Card";
import { Modal } from "@/skins/hrms/components/Modal";
import { Table, type Column } from "@/skins/hrms/components/Table";
import { FEATURES } from "@/skins/hrms/lib/features";

export default function AssetsPage() {
  const { data, isLoading } = useQuery({ queryKey: ["assets"], queryFn: () => assetsApi.list() });
  const { data: employees } = useQuery({ queryKey: ["employees"], queryFn: () => employeesApi.list() });
  const canManage = usePermission(FEATURES.ASSET_MANAGEMENT, "edit");
  const canCreate = usePermission(FEATURES.ASSET_MANAGEMENT, "create");
  const [showCreate, setShowCreate] = useState(false);
  const [assigning, setAssigning] = useState<Asset | null>(null);
  const [searchParams] = useSearchParams();
  const assignTo = searchParams.get("assignTo");
  const assignToName = employees?.items.find((e) => e.id === assignTo)?.full_name;

  const columns: Column<Asset>[] = [
    { key: "tag", header: "Tag", render: (a) => a.asset_tag },
    { key: "name", header: "Asset", render: (a) => a.name },
    { key: "type", header: "Type", render: (a) => a.asset_type },
    { key: "status", header: "Status", render: (a) => <Badge>{a.status}</Badge> },
    {
      key: "actions",
      header: "",
      render: (a) =>
        canManage && a.status === "in_stock" ? (
          <Button variant="secondary" onClick={() => setAssigning(a)}>
            Assign
          </Button>
        ) : null,
    },
  ];

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-light tracking-tight text-gray-900">Asset Management</h1>
        {canCreate && (
          <Button onClick={() => setShowCreate(true)}>
            <Plus size={16} /> Add Asset
          </Button>
        )}
      </div>
      {assignTo && (
        <p className="mb-4 rounded-xl bg-cobalt/5 px-4 py-3 text-sm text-gray-700">
          Assigning a laptop or badge to{" "}
          <span className="font-medium text-gray-900">{assignToName ?? "the new hire"}</span>{" "}
          will complete their onboarding asset step automatically.
        </p>
      )}
      <Card>
        <CardHeader>
          <CardTitle>{data?.total ?? 0} assets</CardTitle>
        </CardHeader>
        {isLoading ? <p className="text-sm text-gray-600">Loading…</p> : <Table columns={columns} rows={data?.items ?? []} />}
      </Card>
      {showCreate && <CreateAssetModal onClose={() => setShowCreate(false)} />}
      {assigning && employees && (
        <AssignAssetModal
          asset={assigning}
          employees={employees.items}
          defaultEmployeeId={assignTo ?? ""}
          onClose={() => setAssigning(null)}
        />
      )}
    </div>
  );
}

function CreateAssetModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({ asset_tag: "", name: "", asset_type: "", serial_number: "" });
  const [submitting, setSubmitting] = useState(false);
  const inputClass = "w-full rounded-xl border border-gray-200 px-3 py-2 text-sm focus:border-cobalt focus:outline-none";

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      await assetsApi.create(form);
      await queryClient.invalidateQueries({ queryKey: ["assets"] });
      await queryClient.invalidateQueries({ queryKey: ["onboarding"] });
      onClose();
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal open onClose={onClose} title="Add Asset">
      <form onSubmit={handleSubmit} className="space-y-3">
        <input required placeholder="Asset tag" className={inputClass} value={form.asset_tag} onChange={(e) => setForm({ ...form, asset_tag: e.target.value })} />
        <input required placeholder="Name (e.g. MacBook Pro 14)" className={inputClass} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <input required placeholder="Type (Laptop, Monitor, Phone…)" className={inputClass} value={form.asset_type} onChange={(e) => setForm({ ...form, asset_type: e.target.value })} />
        <input placeholder="Serial number" className={inputClass} value={form.serial_number} onChange={(e) => setForm({ ...form, serial_number: e.target.value })} />
        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={submitting}>{submitting ? "Creating…" : "Create"}</Button>
        </div>
      </form>
    </Modal>
  );
}

function AssignAssetModal({
  asset,
  employees,
  defaultEmployeeId,
  onClose,
}: {
  asset: Asset;
  employees: { id: string; full_name: string }[];
  defaultEmployeeId?: string;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [employeeId, setEmployeeId] = useState(defaultEmployeeId ?? "");
  const [submitting, setSubmitting] = useState(false);
  const inputClass = "w-full rounded-xl border border-gray-200 px-3 py-2 text-sm focus:border-cobalt focus:outline-none";

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      await assetsApi.assign(asset.id, {
        employee_id: employeeId,
        assigned_date: new Date().toISOString().slice(0, 10),
      });
      await queryClient.invalidateQueries({ queryKey: ["assets"] });
      await queryClient.invalidateQueries({ queryKey: ["onboarding"] });
      onClose();
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal open onClose={onClose} title={`Assign ${asset.name}`}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <select required className={inputClass} value={employeeId} onChange={(e) => setEmployeeId(e.target.value)}>
          <option value="">Select employee…</option>
          {employees.map((e) => (
            <option key={e.id} value={e.id}>{e.full_name}</option>
          ))}
        </select>
        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={submitting}>{submitting ? "Assigning…" : "Assign"}</Button>
        </div>
      </form>
    </Modal>
  );
}
