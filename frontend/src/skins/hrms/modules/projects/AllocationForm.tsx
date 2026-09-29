import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { allocationsApi } from "@/skins/hrms/api/allocations";
import type { Allocation, CapacityConflict } from "@/skins/hrms/api/types";
import { Button } from "@/skins/hrms/components/Button";
import { CapacityBar } from "@/skins/hrms/components/CapacityBar";
import {
  Field,
  FormActions,
  FormError,
  Select,
  TextArea,
  TextInput,
  WarningBanner,
} from "@/skins/hrms/components/Form";
import { Modal } from "@/skins/hrms/components/Modal";
import { apiErrorMessage } from "@/skins/hrms/lib/apiError";

export function AllocationForm({
  allocation,
  defaultEmployeeId,
  onClose,
}: {
  allocation?: Allocation;
  defaultEmployeeId?: string;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const isEdit = !!allocation;

  const { data: options } = useQuery({queryKey: ["allocation-options"], queryFn: allocationsApi.options});

  const [form, setForm] = useState({
    employee_id: allocation?.employee_id ?? defaultEmployeeId ?? "",
    project_id: allocation?.project_id ?? "",
    allocation_percent: allocation ? String(allocation.allocation_percent) : "100",
    role_on_project: allocation?.role_on_project ?? "",
    start_date: allocation?.start_date ?? new Date().toISOString().slice(0, 10),
    end_date: allocation?.end_date ?? "",
    billable: allocation?.billable ?? true,
    notes: allocation?.notes ?? "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conflicts, setConflicts] = useState<CapacityConflict[] | null>(null);

  const [confirmed, setConfirmed] = useState(false);
  const [reason, setReason] = useState("");
  const previewValid = !!form.employee_id && !!form.project_id && !!form.start_date &&
    (!form.end_date || form.end_date >= form.start_date) && Number(form.allocation_percent) > 0 && Number(form.allocation_percent) <= 100;
  const { data: capacity, isFetching: checkingCapacity, error: capacityError } = useQuery({
    queryKey: ["allocation-preview", form.employee_id, form.project_id, form.start_date, form.end_date, form.allocation_percent, allocation?.id],
    queryFn: () => allocationsApi.preview({employee_id: form.employee_id, project_id: form.project_id,
      start_date: form.start_date, end_date: form.end_date || null, allocation_percent: Number(form.allocation_percent),
      exclude_allocation_id: allocation?.id}),
    enabled: previewValid,
  });

  function set<K extends keyof typeof form>(key: K, value: (typeof form)[K]) {
    setConfirmed(false);
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setConflicts(null);

    const payload = {
      employee_id: form.employee_id,
      project_id: form.project_id,
      allocation_percent: Number(form.allocation_percent),
      role_on_project: form.role_on_project,
      start_date: form.start_date,
      end_date: form.end_date || null,
      billable: form.billable,
      notes: form.notes || null,
      confirm_overallocation: confirmed,
      overallocation_reason: reason.trim() || null,
    };

    try {
      const result = isEdit
        ? await allocationsApi.update(allocation.id, payload)
        : await allocationsApi.create(payload);
      await queryClient.invalidateQueries({ queryKey: ["allocations"] });
      await queryClient.invalidateQueries({ queryKey: ["capacity"] });
      await queryClient.invalidateQueries({ queryKey: ["allocation-preview"] });
      await queryClient.invalidateQueries({ queryKey: ["employee-allocations"] });
      await queryClient.invalidateQueries({ queryKey: ["project-allocations"] });
      await queryClient.invalidateQueries({ queryKey: ["onboarding"] });

      // Over-allocation is saved, not refused — show what it collided with and
      // let the user close when they've read it.
      if (result.over_allocated) {
        setConflicts(result.conflicts);
        return;
      }
      onClose();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  if (conflicts) {
    return (
      <Modal open onClose={onClose} title="Saved — but over-allocated">
        <div className="space-y-3">
          <WarningBanner title={`This person is now booked above 100%.`}>
            The allocation was saved. HR, Super Admin and the allocator are notified when overallocation is created or increased. It overlaps with:
          </WarningBanner>
          <ul className="space-y-1 text-sm text-gray-900">
            {conflicts.map((c) => (
              <li key={c.allocation_id} className="flex justify-between">
                <span>{c.project_name}</span>
                <span className="text-gray-600">
                  {c.allocation_percent}% · from {c.start_date}
                </span>
              </li>
            ))}
          </ul>
          <FormActions>
            <Button onClick={onClose}>Got it</Button>
          </FormActions>
        </div>
      </Modal>
    );
  }

  return (
    <Modal open onClose={onClose} title={isEdit ? "Edit Allocation" : "New Allocation"}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <Field label="Employee">
          <Select
            required
            disabled={isEdit}
            value={form.employee_id}
            onChange={(e) => set("employee_id", e.target.value)}
          >
            <option value="">Select employee…</option>
            {options?.employees
              .map((emp) => (
                <option key={emp.id} value={emp.id}>
                  {emp.label}
                </option>
              ))}
          </Select>
        </Field>

        <Field label="Project">
          <Select
            required
            disabled={isEdit}
            value={form.project_id}
            onChange={(e) => set("project_id", e.target.value)}
          >
            <option value="">Select project…</option>
            {options?.projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
          </Select>
        </Field>

        {capacityError && <FormError message={apiErrorMessage(capacityError)} />}
        {checkingCapacity && <p role="status" className="text-sm text-gray-600">Checking allocation dates…</p>}
        {capacity && <section className="space-y-3 rounded-xl border border-gray-200 p-3" aria-label="Employee allocations across projects">
          <CapacityBar percent={capacity.total_allocation_percent} label="Projected peak commitment" />
          <h3 className="font-medium text-gray-900">All allocations across projects</h3>
          <p className="text-xs text-gray-600">Preview includes the proposed change. Completed and cancelled bookings do not count toward capacity.</p>
          {capacity.allocations.length === 0 ? <p className="text-sm text-gray-600">No existing allocations.</p> :
            <ul className="space-y-2 text-sm">{capacity.allocations.map(a => <li key={a.allocation_id}
              className={`rounded border p-2 ${a.over_allocated ? "border-red-200 bg-red-50" : "border-gray-200"}`}>
              <p className="font-medium">{a.project_name} · {a.allocation_percent}% {a.allocation_id === allocation?.id && "(editing)"}</p>
              <p>{a.manager_name} · {a.start_date} to {a.end_date ?? "ongoing"} · {a.status}</p>
              {a.over_allocated && <p className="font-semibold text-red-800">Overallocated · {a.total_allocation_percent}% peak</p>}
            </li>)}</ul>}
          {capacity.over_allocated && <div className="space-y-3 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-900">
            <p className="font-semibold">Overallocation warning</p>
            {capacity.overallocated_periods.map(p => <p key={p.start_date}>{p.start_date} to {p.end_date ?? "ongoing"}: {p.total_allocation_percent}% · {p.excess_percent}% above capacity</p>)}
            <Field label="Reason for overallocation"><TextArea required maxLength={2000} value={reason} onChange={e => setReason(e.target.value)} /></Field>
            <label className="flex items-start gap-2"><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} />
              Confirm overallocation. HR, Super Admin and you will be emailed when this creates or increases an overbooking.</label>
          </div>}
        </section>}

        <div className="grid grid-cols-2 gap-3">
          <Field label="Allocation %">
            <TextInput
              required
              type="number"
              min={1}
              max={100}
              value={form.allocation_percent}
              onChange={(e) => set("allocation_percent", e.target.value)}
            />
          </Field>
          <Field label="Role on project">
            <Select
              required
              value={form.role_on_project}
              onChange={(e) => set("role_on_project", e.target.value)}
            >
              <option value="">Select project role…</option>
              {options?.project_roles.map((option) => (
                <option key={option.id} value={option.value}>{option.label}</option>
              ))}
            </Select>
          </Field>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <Field label="Start date">
            <TextInput
              required
              type="date"
              value={form.start_date}
              onChange={(e) => set("start_date", e.target.value)}
            />
          </Field>
          <Field label="End date" hint="Blank = ongoing.">
            <TextInput
              type="date"
              value={form.end_date}
              onChange={(e) => set("end_date", e.target.value)}
            />
          </Field>
        </div>

        <label className="flex items-center gap-2 text-sm text-gray-900">
          <input
            type="checkbox"
            checked={form.billable}
            onChange={(e) => set("billable", e.target.checked)}
            className="rounded border-gray-200 text-cobalt focus:ring-cobalt"
          />
          Billable
        </label>

        <Field label="Notes">
          <TextArea value={form.notes} onChange={(e) => set("notes", e.target.value)} />
        </Field>

        <FormError message={error} />
        <FormActions>
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={busy || !previewValid || checkingCapacity || !capacity || !!capacityError || (capacity.over_allocated && (!confirmed || !reason.trim()))}>
            {busy ? "Saving…" : isEdit ? "Save changes" : "Create allocation"}
          </Button>
        </FormActions>
      </form>
    </Modal>
  );
}
