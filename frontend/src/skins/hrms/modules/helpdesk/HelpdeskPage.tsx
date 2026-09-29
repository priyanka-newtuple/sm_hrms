import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useState } from "react";

import { helpdeskApi } from "@/skins/hrms/api/helpdesk";
import type { Ticket } from "@/skins/hrms/api/types";
import { usePermission } from "@/skins/hrms/auth/usePermission";
import { Badge } from "@/skins/hrms/components/Badge";
import { Button } from "@/skins/hrms/components/Button";
import { Card, CardHeader, CardTitle } from "@/skins/hrms/components/Card";
import { Modal } from "@/skins/hrms/components/Modal";
import { Table, type Column } from "@/skins/hrms/components/Table";
import { FEATURES } from "@/skins/hrms/lib/features";

const STATUSES = ["open", "assigned", "in_progress", "resolved", "closed"] as const;

export default function HelpdeskPage() {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["tickets"], queryFn: () => helpdeskApi.list() });
  const { data: categories } = useQuery({ queryKey: ["helpdesk-categories"], queryFn: helpdeskApi.categories });
  const canCreate = usePermission(FEATURES.HELP_DESK, "create");
  const canManage = usePermission(FEATURES.HELP_DESK, "manage");
  const [showCreate, setShowCreate] = useState(false);

  const categoryName = (id: string) => categories?.find((c) => c.id === id)?.name ?? "—";

  async function advanceStatus(ticket: Ticket) {
    const idx = STATUSES.indexOf(ticket.status);
    const next = STATUSES[Math.min(idx + 1, STATUSES.length - 1)];
    await helpdeskApi.update(ticket.id, { status: next });
    await queryClient.invalidateQueries({ queryKey: ["tickets"] });
  }

  const columns: Column<Ticket>[] = [
    { key: "number", header: "Ticket", render: (t) => t.ticket_number },
    { key: "subject", header: "Subject", render: (t) => t.subject },
    { key: "category", header: "Category", render: (t) => categoryName(t.category_id) },
    { key: "priority", header: "Priority", render: (t) => <Badge>{t.priority}</Badge> },
    { key: "status", header: "Status", render: (t) => <Badge>{t.status}</Badge> },
    {
      key: "actions",
      header: "",
      render: (t) =>
        canManage && t.status !== "closed" ? (
          <Button variant="secondary" onClick={() => advanceStatus(t)}>
            Advance
          </Button>
        ) : null,
    },
  ];

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-light tracking-tight text-gray-900">Help Desk</h1>
        {canCreate && (
          <Button onClick={() => setShowCreate(true)}>
            <Plus size={16} /> Raise Ticket
          </Button>
        )}
      </div>
      <Card>
        <CardHeader>
          <CardTitle>{data?.total ?? 0} tickets</CardTitle>
        </CardHeader>
        {isLoading ? <p className="text-sm text-gray-600">Loading…</p> : <Table columns={columns} rows={data?.items ?? []} />}
      </Card>
      {showCreate && categories && (
        <CreateTicketModal categories={categories} onClose={() => setShowCreate(false)} />
      )}
    </div>
  );
}

function CreateTicketModal({
  categories,
  onClose,
}: {
  categories: { id: string; name: string }[];
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({ category_id: "", subject: "", description: "", priority: "medium" });
  const [submitting, setSubmitting] = useState(false);
  const inputClass = "w-full rounded-xl border border-gray-200 px-3 py-2 text-sm focus:border-cobalt focus:outline-none";

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      await helpdeskApi.create(form);
      await queryClient.invalidateQueries({ queryKey: ["tickets"] });
      onClose();
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal open onClose={onClose} title="Raise Ticket">
      <form onSubmit={handleSubmit} className="space-y-3">
        <select required className={inputClass} value={form.category_id} onChange={(e) => setForm({ ...form, category_id: e.target.value })}>
          <option value="">Select category…</option>
          {categories.map((c) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </select>
        <input required placeholder="Subject" className={inputClass} value={form.subject} onChange={(e) => setForm({ ...form, subject: e.target.value })} />
        <textarea required placeholder="Description" className={inputClass} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
        <select className={inputClass} value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}>
          <option value="low">Low</option>
          <option value="medium">Medium</option>
          <option value="high">High</option>
          <option value="urgent">Urgent</option>
        </select>
        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={submitting}>{submitting ? "Submitting…" : "Raise Ticket"}</Button>
        </div>
      </form>
    </Modal>
  );
}
