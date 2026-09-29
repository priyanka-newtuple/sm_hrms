import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { employeesApi, rolesApi } from "@/skins/hrms/api/employees";
import type { Employee, EmploymentType } from "@/skins/hrms/api/types";
import { useAuth } from "@/skins/hrms/auth/AuthContext";
import { useFeatureScope } from "@/skins/hrms/auth/usePermission";
import { Button } from "@/skins/hrms/components/Button";
import { Field, FormActions, FormError, Select, TextInput } from "@/skins/hrms/components/Form";
import { Modal } from "@/skins/hrms/components/Modal";
import { apiErrorMessage } from "@/skins/hrms/lib/apiError";
import { FEATURES } from "@/skins/hrms/lib/features";

export function EmployeeForm({
  employee,
  onClose,
}: {
  employee?: Employee;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const isEdit = !!employee;
  const scope = useFeatureScope(FEATURES.EMPLOYEE_DIRECTORY);
  // Mirrors employee_service._PRIVILEGED_FIELDS: a SELF-scoped grant can edit
  // contact details but never role, manager, department or compensation.
  const selfServiceOnly =
    scope === "self" || (isEdit && employee.id === user?.employee_id && scope === "self");

  const { data: roles } = useQuery({
    queryKey: ["roles"],
    queryFn: rolesApi.list,
    enabled: !selfServiceOnly,
  });
  const { data: employees } = useQuery({
    queryKey: ["employees"],
    queryFn: () => employeesApi.list(),
    enabled: !selfServiceOnly,
  });
  const { data: formOptions } = useQuery({
    queryKey: ["employee-form-options"],
    queryFn: employeesApi.formOptions,
    enabled: !selfServiceOnly,
  });

  const [form, setForm] = useState({
    email: "",
    first_name: employee?.first_name ?? "",
    last_name: employee?.last_name ?? "",
    department: employee?.department ?? "",
    designation: employee?.designation ?? "",
    role_id: employee?.role_id ?? "",
    reports_to_id: employee?.reports_to_id ?? "",
    date_joined: employee?.date_joined ?? new Date().toISOString().slice(0, 10),
    employment_type: (employee?.employment_type ?? "full_time") as EmploymentType,
    work_location: employee?.work_location ?? "",
    notice_period_days:
      employee?.notice_period_days != null ? String(employee.notice_period_days) : "",
    phone: employee?.phone ?? "",
    skills: employee?.skills ?? "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function set<K extends keyof typeof form>(key: K, value: (typeof form)[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);

    try {
      if (isEdit) {
        const payload: Record<string, unknown> = {
          first_name: form.first_name,
          last_name: form.last_name,
          phone: form.phone || null,
          skills: form.skills || null,
          work_location: form.work_location || null,
        };
        if (!selfServiceOnly) {
          payload.department = form.department;
          payload.designation = form.designation;
          payload.role_id = form.role_id;
          payload.reports_to_id = form.reports_to_id || null;
          payload.employment_type = form.employment_type;
          payload.notice_period_days = form.notice_period_days
            ? Number(form.notice_period_days)
            : null;
        }
        await employeesApi.update(employee.id, payload);
      } else {
        await employeesApi.create({
          email: form.email,
          first_name: form.first_name,
          last_name: form.last_name,
          department: form.department,
          designation: form.designation,
          role_id: form.role_id,
          reports_to_id: form.reports_to_id || null,
          date_joined: form.date_joined,
          employment_type: form.employment_type,
          work_location: form.work_location || null,
          notice_period_days: form.notice_period_days
            ? Number(form.notice_period_days)
            : null,
          phone: form.phone || null,
        });
      }
      await queryClient.invalidateQueries({ queryKey: ["employees"] });
      await queryClient.invalidateQueries({ queryKey: ["employee", employee?.id] });
      await queryClient.invalidateQueries({ queryKey: ["onboarding"] });
      onClose();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open onClose={onClose} title={isEdit ? `Edit ${employee.full_name}` : "Add Employee"}>
      <form onSubmit={handleSubmit} className="max-h-[70vh] space-y-3 overflow-y-auto pr-1">
        <div className="grid grid-cols-2 gap-3">
          <Field label="First name">
            <TextInput
              required
              value={form.first_name}
              onChange={(e) => set("first_name", e.target.value)}
            />
          </Field>
          <Field label="Last name">
            <TextInput
              required
              value={form.last_name}
              onChange={(e) => set("last_name", e.target.value)}
            />
          </Field>
        </div>

        {!isEdit && (
          <Field label="Work email" hint="Must be @newtuple.com to match Google SSO.">
            <TextInput
              required
              type="email"
              placeholder="first.last@newtuple.com"
              value={form.email}
              onChange={(e) => set("email", e.target.value)}
            />
          </Field>
        )}

        {!selfServiceOnly && (
          <>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Department">
                <Select
                  required
                  value={form.department}
                  onChange={(e) => set("department", e.target.value)}
                >
                  <option value="">Select department…</option>
                  {formOptions?.departments.map((option) => (
                    <option key={option.id} value={option.value}>{option.label}</option>
                  ))}
                </Select>
              </Field>
              <Field label="Designation">
                <Select
                  required
                  value={form.designation}
                  onChange={(e) => set("designation", e.target.value)}
                >
                  <option value="">Select designation…</option>
                  {formOptions?.designations.map((option) => (
                    <option key={option.id} value={option.value}>{option.label}</option>
                  ))}
                </Select>
              </Field>
            </div>

            <Field label="Role">
              <Select
                required
                value={form.role_id}
                onChange={(e) => set("role_id", e.target.value)}
              >
                <option value="">Select role…</option>
                {roles?.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name}
                  </option>
                ))}
              </Select>
            </Field>

            <Field label="Reporting manager">
              <Select
                value={form.reports_to_id}
                onChange={(e) => set("reports_to_id", e.target.value)}
              >
                <option value="">None</option>
                {employees?.items
                  .filter((e) => e.id !== employee?.id)
                  .map((e) => (
                    <option key={e.id} value={e.id}>
                      {e.full_name} — {e.designation}
                    </option>
                  ))}
              </Select>
            </Field>

            <div className="grid grid-cols-3 gap-3">
              <Field label="Employment type">
                <Select
                  value={form.employment_type}
                  onChange={(e) => set("employment_type", e.target.value as EmploymentType)}
                >
                  <option value="full_time">Full time</option>
                  <option value="contract">Contract</option>
                  <option value="intern">Intern</option>
                </Select>
              </Field>
              {!isEdit && (
                <Field label="Date joined">
                  <TextInput
                    required
                    type="date"
                    value={form.date_joined}
                    onChange={(e) => set("date_joined", e.target.value)}
                  />
                </Field>
              )}
              <Field label="Notice period">
                <TextInput
                  type="number"
                  min={0}
                  placeholder="days"
                  value={form.notice_period_days}
                  onChange={(e) => set("notice_period_days", e.target.value)}
                />
              </Field>
            </div>
          </>
        )}

        <div className="grid grid-cols-2 gap-3">
          <Field label="Phone">
            <TextInput value={form.phone} onChange={(e) => set("phone", e.target.value)} />
          </Field>
          <Field label="Work location">
            <TextInput
              value={form.work_location}
              onChange={(e) => set("work_location", e.target.value)}
            />
          </Field>
        </div>

        {isEdit && (
          <Field label="Skills">
            <TextInput value={form.skills} onChange={(e) => set("skills", e.target.value)} />
          </Field>
        )}

        <FormError message={error} />
        <FormActions>
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={busy}>
            {busy ? "Saving…" : isEdit ? "Save changes" : "Create employee"}
          </Button>
        </FormActions>
      </form>
    </Modal>
  );
}
