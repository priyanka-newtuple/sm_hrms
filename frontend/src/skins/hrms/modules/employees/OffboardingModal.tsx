import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { useState } from "react";

import { employeesApi } from "@/skins/hrms/api/employees";
import type { Employee } from "@/skins/hrms/api/types";
import { Button } from "@/skins/hrms/components/Button";
import { Field, FormActions, FormError, Select, TextArea, TextInput } from "@/skins/hrms/components/Form";
import { Modal } from "@/skins/hrms/components/Modal";
import { apiErrorMessage } from "@/skins/hrms/lib/apiError";

/**
 * Offboarding is gated by a readiness check: anything requiring a human decision
 * (who inherits their projects / reports, where their laptop went) must be
 * resolved first. The confirm button stays disabled until the API says ready.
 */
export function OffboardingModal({
  employee,
  onClose,
}: {
  employee: Employee;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({
    last_working_day: new Date().toISOString().slice(0, 10),
    exit_type: "resignation",
    exit_reason: "",
    rehire_eligible: true,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: readiness, isLoading } = useQuery({
    queryKey: ["offboarding-readiness", employee.id],
    queryFn: () => employeesApi.offboardingReadiness(employee.id),
  });

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await employeesApi.offboard(employee.id, form);
      await queryClient.invalidateQueries({ queryKey: ["employee", employee.id] });
      await queryClient.invalidateQueries({ queryKey: ["employees"] });
      await queryClient.invalidateQueries({ queryKey: ["allocations"] });
      onClose();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open onClose={onClose} title={`Offboard ${employee.full_name}`}>
      <div className="max-h-[70vh] space-y-4 overflow-y-auto pr-1">
        {isLoading ? (
          <p className="text-sm text-gray-600">Checking readiness…</p>
        ) : readiness?.ready ? (
          <div className="flex items-start gap-2 rounded-xl border border-success/30 bg-success/5 px-3 py-2 text-sm">
            <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-success" />
            <span className="text-gray-900">
              Ready to offboard. Open allocations will be end-dated and their login revoked.
            </span>
          </div>
        ) : (
          <div className="space-y-2">
            <div className="flex items-start gap-2 rounded-xl border border-warning/40 bg-warning/5 px-3 py-2 text-sm">
              <AlertTriangle size={16} className="mt-0.5 shrink-0 text-warning" />
              <span className="text-gray-900">
                Resolve these before offboarding — each needs someone to take over.
              </span>
            </div>
            {readiness?.blockers.map((blocker) => (
              <div key={blocker.kind} className="rounded-xl border border-gray-200 p-3">
                <div className="text-sm font-medium text-gray-900">{blocker.message}</div>
                <ul className="mt-2 space-y-1 text-xs text-gray-600">
                  {blocker.items.map((item, i) => (
                    <li key={i}>
                      {item.name ?? item.code ?? item.week_start_date ?? item.assigned_date}
                      {item.code && item.name ? ` (${item.code})` : ""}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <Field label="Last working day">
              <TextInput
                required
                type="date"
                value={form.last_working_day}
                onChange={(e) => setForm({ ...form, last_working_day: e.target.value })}
              />
            </Field>
            <Field label="Exit type">
              <Select
                value={form.exit_type}
                onChange={(e) => setForm({ ...form, exit_type: e.target.value })}
              >
                <option value="resignation">Resignation</option>
                <option value="termination">Termination</option>
                <option value="end_of_contract">End of contract</option>
                <option value="retirement">Retirement</option>
              </Select>
            </Field>
          </div>

          <Field label="Reason">
            <TextArea
              value={form.exit_reason}
              onChange={(e) => setForm({ ...form, exit_reason: e.target.value })}
            />
          </Field>

          <label className="flex items-center gap-2 text-sm text-gray-900">
            <input
              type="checkbox"
              checked={form.rehire_eligible}
              onChange={(e) => setForm({ ...form, rehire_eligible: e.target.checked })}
              className="rounded border-gray-200 text-cobalt focus:ring-cobalt"
            />
            Eligible for rehire
          </label>

          <FormError message={error} />
          <FormActions>
            <Button type="button" variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" variant="danger" disabled={busy || !readiness?.ready}>
              {busy ? "Offboarding…" : "Confirm offboarding"}
            </Button>
          </FormActions>
        </form>
      </div>
    </Modal>
  );
}
