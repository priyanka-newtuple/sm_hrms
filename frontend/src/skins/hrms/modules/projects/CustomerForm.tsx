import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { employeesApi } from "@/skins/hrms/api/employees";
import { customersApi } from "@/skins/hrms/api/projects";
import type { Customer } from "@/skins/hrms/api/types";
import { Button } from "@/skins/hrms/components/Button";
import { Field, FormActions, FormError, Select, TextArea, TextInput } from "@/skins/hrms/components/Form";
import { Modal } from "@/skins/hrms/components/Modal";
import { useHasPermissionKey } from "@/skins/hrms/auth/usePermission";
import { apiErrorMessage } from "@/skins/hrms/lib/apiError";

type FormState = {
  name: string;
  industry: string;
  contact_name: string;
  contact_email: string;
  account_owner_id: string;
  status: string;
  contract_start_date: string;
  contract_end_date: string;
  currency: string;
  country: string;
  billing_address: string;
  notes: string;
  contract_value: string;
  payment_terms_days: string;
};

function initialState(customer?: Customer): FormState {
  return {
    name: customer?.name ?? "",
    industry: customer?.industry ?? "",
    contact_name: customer?.contact_name ?? "",
    contact_email: customer?.contact_email ?? "",
    account_owner_id: customer?.account_owner_id ?? "",
    status: customer?.status ?? "active",
    contract_start_date: customer?.contract_start_date ?? "",
    contract_end_date: customer?.contract_end_date ?? "",
    currency: customer?.currency ?? "INR",
    country: customer?.country ?? "",
    billing_address: customer?.billing_address ?? "",
    notes: customer?.notes ?? "",
    contract_value: customer?.contract_value != null ? String(customer.contract_value) : "",
    payment_terms_days:
      customer?.payment_terms_days != null ? String(customer.payment_terms_days) : "",
  };
}

export function CustomerForm({
  customer,
  onClose,
}: {
  customer?: Customer;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const isEdit = !!customer;
  // Commercial fields are only editable by roles that can actually see them.
  const canSeeCommercials = useHasPermissionKey("view_customer_contract_value");
  const { data: employees } = useQuery({
    queryKey: ["employees"],
    queryFn: () => employeesApi.list(),
  });

  const [form, setForm] = useState<FormState>(initialState(customer));
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
      industry: form.industry || null,
      contact_name: form.contact_name || null,
      contact_email: form.contact_email || null,
      account_owner_id: form.account_owner_id || null,
      status: form.status,
      contract_start_date: form.contract_start_date || null,
      contract_end_date: form.contract_end_date || null,
      currency: form.currency,
      country: form.country || null,
      billing_address: form.billing_address || null,
      notes: form.notes || null,
    };
    if (canSeeCommercials) {
      payload.contract_value = form.contract_value ? Number(form.contract_value) : null;
      payload.payment_terms_days = form.payment_terms_days
        ? Number(form.payment_terms_days)
        : null;
    }

    try {
      if (isEdit) {
        await customersApi.update(customer.id, payload);
      } else {
        await customersApi.create(payload);
      }
      await queryClient.invalidateQueries({ queryKey: ["customers"] });
      await queryClient.invalidateQueries({ queryKey: ["customer", customer?.id] });
      onClose();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open onClose={onClose} title={isEdit ? `Edit ${customer.name}` : "Add Customer"}>
      <form onSubmit={handleSubmit} className="max-h-[70vh] space-y-3 overflow-y-auto pr-1">
        <Field label="Customer name">
          <TextInput
            required
            value={form.name}
            onChange={(e) => set("name", e.target.value)}
            placeholder="Acme Industries"
          />
        </Field>

        <div className="grid grid-cols-2 gap-3">
          <Field label="Industry">
            <TextInput value={form.industry} onChange={(e) => set("industry", e.target.value)} />
          </Field>
          <Field label="Status">
            <Select value={form.status} onChange={(e) => set("status", e.target.value)}>
              <option value="prospect">Prospect</option>
              <option value="active">Active</option>
              <option value="on_hold">On hold</option>
            </Select>
          </Field>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <Field label="Contact name">
            <TextInput
              value={form.contact_name}
              onChange={(e) => set("contact_name", e.target.value)}
            />
          </Field>
          <Field label="Contact email">
            <TextInput
              type="email"
              value={form.contact_email}
              onChange={(e) => set("contact_email", e.target.value)}
            />
          </Field>
        </div>

        <Field label="Account owner" hint="Usually the Delivery Manager for this account.">
          <Select
            value={form.account_owner_id}
            onChange={(e) => set("account_owner_id", e.target.value)}
          >
            <option value="">Unassigned</option>
            {employees?.items.map((emp) => (
              <option key={emp.id} value={emp.id}>
                {emp.full_name} — {emp.designation}
              </option>
            ))}
          </Select>
        </Field>

        <div className="grid grid-cols-2 gap-3">
          <Field label="Contract start">
            <TextInput
              type="date"
              value={form.contract_start_date}
              onChange={(e) => set("contract_start_date", e.target.value)}
            />
          </Field>
          <Field label="Contract end">
            <TextInput
              type="date"
              value={form.contract_end_date}
              onChange={(e) => set("contract_end_date", e.target.value)}
            />
          </Field>
        </div>

        {canSeeCommercials && (
          <div className="grid grid-cols-3 gap-3">
            <Field label="Contract value">
              <TextInput
                type="number"
                min={0}
                value={form.contract_value}
                onChange={(e) => set("contract_value", e.target.value)}
              />
            </Field>
            <Field label="Currency">
              <TextInput
                maxLength={3}
                value={form.currency}
                onChange={(e) => set("currency", e.target.value.toUpperCase())}
              />
            </Field>
            <Field label="Payment terms">
              <TextInput
                type="number"
                min={0}
                placeholder="days"
                value={form.payment_terms_days}
                onChange={(e) => set("payment_terms_days", e.target.value)}
              />
            </Field>
          </div>
        )}

        <div className="grid grid-cols-2 gap-3">
          <Field label="Country">
            <TextInput value={form.country} onChange={(e) => set("country", e.target.value)} />
          </Field>
          <Field label="Billing address">
            <TextInput
              value={form.billing_address}
              onChange={(e) => set("billing_address", e.target.value)}
            />
          </Field>
        </div>

        <Field label="Notes">
          <TextArea value={form.notes} onChange={(e) => set("notes", e.target.value)} />
        </Field>

        <FormError message={error} />
        <FormActions>
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={busy}>
            {busy ? "Saving…" : isEdit ? "Save changes" : "Create customer"}
          </Button>
        </FormActions>
      </form>
    </Modal>
  );
}
