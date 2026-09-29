import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { projectsApi } from "@/skins/hrms/api/projects";
import type { Project } from "@/skins/hrms/api/types";
import { useAuth } from "@/skins/hrms/auth/AuthContext";
import { useFeatureScope, useHasPermissionKey } from "@/skins/hrms/auth/usePermission";
import { Button } from "@/skins/hrms/components/Button";
import { Field, FormActions, FormError, Select, TextArea, TextInput } from "@/skins/hrms/components/Form";
import { Modal } from "@/skins/hrms/components/Modal";
import { apiErrorMessage } from "@/skins/hrms/lib/apiError";
import { FEATURES } from "@/skins/hrms/lib/features";

type FormState = {
  name: string;
  customer_id: string;
  project_manager_id: string;
  delivery_manager_id: string;
  status: string;
  start_date: string;
  end_date: string;
  description: string;
  engagement_type: string;
  health: string;
  currency: string;
  practice: string;
  budgeted_hours: string;
  budget_amount: string;
  billing_rate: string;
  revenue: string;
  margin_percent: string;
};

function initialState(project: Project | undefined, defaultPmId: string): FormState {
  return {
    name: project?.name ?? "",
    customer_id: project?.customer_id ?? "",
    project_manager_id: project?.project_manager_id ?? defaultPmId,
    delivery_manager_id: project?.delivery_manager_id ?? "",
    status: project?.status ?? "planned",
    start_date: project?.start_date ?? new Date().toISOString().slice(0, 10),
    end_date: project?.end_date ?? "",
    description: project?.description ?? "",
    engagement_type: project?.engagement_type ?? "time_and_materials",
    health: project?.health ?? "green",
    currency: project?.currency ?? "INR",
    practice: project?.practice ?? "",
    budgeted_hours: project?.budgeted_hours != null ? String(project.budgeted_hours) : "",
    budget_amount: project?.budget_amount != null ? String(project.budget_amount) : "",
    billing_rate: project?.billing_rate != null ? String(project.billing_rate) : "",
    revenue: project?.revenue != null ? String(project.revenue) : "",
    margin_percent: project?.margin_percent != null ? String(project.margin_percent) : "",
  };
}

export function ProjectForm({
  project,
  onClose,
}: {
  project?: Project;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { user } = useAuth();
  const isEdit = !!project;
  const scope = useFeatureScope(FEATURES.PROJECTS);
  // A PM (Manage-Assigned) may only create projects they will manage themselves —
  // the backend enforces this too, so the field is locked rather than hidden.
  const pmLocked = scope !== "all";
  const directApproval = user?.permissions.some(p => p.feature_key === FEATURES.PROJECTS && p.actions.includes("full"));
  const operational = isEdit && project.approval_status === "approved";

  const canSeeRate = useHasPermissionKey("view_billing_rate");
  const canSeeRevenue = useHasPermissionKey("view_project_revenue");
  const canSeeMargin = useHasPermissionKey("view_project_margin");
  const showCommercials = canSeeRate || canSeeRevenue || canSeeMargin;

  const { data: options, error: optionsError } = useQuery({
    queryKey: ["project-creation-options", user?.employee_id],
    queryFn: projectsApi.creationOptions,
  });
  const proposedProject = project?.approval_request && ["draft", "changes_requested"].includes(project.approval_request.status)
    ? { ...project, ...project.approval_request.proposed } as Project : project;

  const [form, setForm] = useState<FormState>(
    initialState(proposedProject, user?.employee_id ?? "")
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);

    const payload: Record<string, unknown> = {
      name: form.name,
      customer_id: form.customer_id,
      project_manager_id: form.project_manager_id,
      delivery_manager_id: form.delivery_manager_id || null,
      status: form.status,
      start_date: form.start_date,
      end_date: form.end_date || null,
      description: form.description || null,
      engagement_type: form.engagement_type,
      health: form.health,
      currency: form.currency,
      practice: form.practice || null,
      budgeted_hours: form.budgeted_hours ? Number(form.budgeted_hours) : null,
    };
    if (canSeeRate) payload.billing_rate = form.billing_rate ? Number(form.billing_rate) : null;
    if (canSeeRevenue) {
      payload.revenue = form.revenue ? Number(form.revenue) : null;
      payload.budget_amount = form.budget_amount ? Number(form.budget_amount) : null;
    }
    if (canSeeMargin) {
      payload.margin_percent = form.margin_percent ? Number(form.margin_percent) : null;
    }

    try {
      const saved = isEdit ? await projectsApi.update(project.id, payload) : await projectsApi.create(payload);
      await queryClient.invalidateQueries({ queryKey: ["projects"] });
      await queryClient.invalidateQueries({ queryKey: ["project", project?.id] });
      await queryClient.invalidateQueries({ queryKey: ["work"] });
      await queryClient.invalidateQueries({ queryKey: ["project-review"] });
      onClose();
      navigate(`/projects/${saved.id}`);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open onClose={onClose} title={isEdit ? `Edit ${project.name}` : "New Project"}>
      <form onSubmit={handleSubmit} className="max-h-[70vh] space-y-3 overflow-y-auto pr-1">
        <p className="rounded-xl bg-gray-50 p-3 text-sm text-gray-600">
          {isEdit ? operational ? "Budget, commercial, ownership and date changes are saved as an amendment for approval. Approved values remain in use until it is approved." : "Save your draft, then submit it for Super Admin approval."
            : directApproval ? "This project will be created and approved by Super Admin, with delivery status Planned." : "This creates a draft. Submit it for Super Admin approval before allocating people or logging time."}
        </p>
        {optionsError && <FormError message="Could not load project options. Please reopen this form to retry." />}
        <Field label="Project name">
          <TextInput required value={form.name} onChange={(e) => set("name", e.target.value)} />
        </Field>

        <Field label="Customer">
          <Select
            required
            value={form.customer_id}
            onChange={(e) => set("customer_id", e.target.value)}
          >
            <option value="">Select customer…</option>
            {options?.customers.map((c) => (
              <option key={c.id} value={c.id}>
                {c.label}
              </option>
            ))}
          </Select>
        </Field>

        <div className="grid grid-cols-2 gap-3">
          <Field
            label="Project Manager"
            hint={pmLocked ? "Your role can only create projects you manage." : undefined}
          >
            <Select
              required
              disabled={pmLocked}
              value={form.project_manager_id}
              onChange={(e) => set("project_manager_id", e.target.value)}
            >
              <option value="">Select…</option>
              {options?.employees.map((emp) => (
                <option key={emp.id} value={emp.id}>
                  {emp.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Delivery Manager">
            <Select
              value={form.delivery_manager_id}
              onChange={(e) => set("delivery_manager_id", e.target.value)}
            >
              <option value="">Unassigned</option>
              {options?.employees.map((emp) => (
                <option key={emp.id} value={emp.id}>
                  {emp.label}
                </option>
              ))}
            </Select>
          </Field>
        </div>

        <div className="grid grid-cols-3 gap-3">
          <Field label="Status">
            <Select disabled={!operational} value={form.status} onChange={(e) => set("status", e.target.value)}>
              <option value="planned">Planned</option>
              <option value="active">Active</option>
              <option value="on_hold">On hold</option>
              <option value="completed">Completed</option>
            </Select>
          </Field>
          <Field label="Health">
            <Select value={form.health} onChange={(e) => set("health", e.target.value)}>
              <option value="green">Green</option>
              <option value="amber">Amber</option>
              <option value="red">Red</option>
            </Select>
          </Field>
          <Field label="Engagement">
            <Select
              value={form.engagement_type}
              onChange={(e) => set("engagement_type", e.target.value)}
            >
              <option value="time_and_materials">Time &amp; Materials</option>
              <option value="fixed_bid">Fixed Bid</option>
              <option value="retainer">Retainer</option>
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
          <Field label="End date" hint="Allocations must fit inside this window.">
            <TextInput
              type="date"
              value={form.end_date}
              onChange={(e) => set("end_date", e.target.value)}
            />
          </Field>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <Field label="Practice">
            <TextInput value={form.practice} onChange={(e) => set("practice", e.target.value)} />
          </Field>
          <Field label="Budgeted hours">
            <TextInput
              type="number"
              min={0}
              value={form.budgeted_hours}
              onChange={(e) => set("budgeted_hours", e.target.value)}
            />
          </Field>
        </div>

        {showCommercials && (
          <div className="grid grid-cols-2 gap-3 rounded-xl border border-gray-200 p-3">
            {canSeeRate && (
              <Field label="Billing rate">
                <TextInput
                  type="number"
                  min={0}
                  value={form.billing_rate}
                  onChange={(e) => set("billing_rate", e.target.value)}
                />
              </Field>
            )}
            {canSeeRevenue && (
              <>
                <Field label="Revenue">
                  <TextInput
                    type="number"
                    min={0}
                    value={form.revenue}
                    onChange={(e) => set("revenue", e.target.value)}
                  />
                </Field>
                <Field label="Budget amount">
                  <TextInput
                    type="number"
                    min={0}
                    value={form.budget_amount}
                    onChange={(e) => set("budget_amount", e.target.value)}
                  />
                </Field>
              </>
            )}
            {canSeeMargin && (
              <Field label="Margin %">
                <TextInput
                  type="number"
                  step="0.1"
                  value={form.margin_percent}
                  onChange={(e) => set("margin_percent", e.target.value)}
                />
              </Field>
            )}
          </div>
        )}

        <Field label="Description">
          <TextArea
            value={form.description}
            onChange={(e) => set("description", e.target.value)}
          />
        </Field>

        <FormError message={error} />
        <FormActions>
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={busy}>
            {busy ? "Saving…" : isEdit ? "Save changes" : directApproval ? "Create approved project" : "Save draft"}
          </Button>
        </FormActions>
      </form>
    </Modal>
  );
}
