import { useEffect, useMemo, useState } from 'react';
import { CheckCircle2, Loader2, Send } from 'lucide-react';
import { useParams } from 'react-router-dom';

import { getApiErrorMessage } from '../../core/services/api';
import { formSchemas, mapEntityFieldToFormField } from '../../core/services/api/formSchemas';
import type { FormField, PublicFormSchemaResponse } from '../../core/types';
import { isMissingRequiredFieldValue, validateFieldValue } from '../../shared/utils/entityForm';
import { resolveEntityTypeLabel } from '../../shared/utils/labels';
import { applyCalculations } from '../../shared/utils/calc';
import { ErrorBanner } from './components/ErrorBanner';
import { FieldInput } from './components/FieldInput';
import { Shell } from './components/Shell';

function initialValue(field: FormField): unknown {
  if (field.current_value !== undefined && field.current_value !== null) return field.current_value;
  if (field.type === 'boolean') return false;
  if (field.type === 'multi_select') return [];
  if (field.type === 'table') {
    if (field.table_config?.row_mode !== 'fixed') return [];
    return (field.table_config.rows ?? []).map((row) => ({
      _row_id: row.id,
      ...(row.line ? { line: row.line, _line: row.line } : {}),
      ...(row.label ? { description: row.label, _label: row.label } : {}),
      ...(row.cells ?? {}),
    }));
  }
  return '';
}

function buildInitialValues(fields: FormField[]): Record<string, unknown> {
  return Object.fromEntries(fields.map((f) => [f.id, initialValue(f)]));
}

function normalizeValue(field: FormField, value: unknown): unknown {
  if (field.type === 'integer') {
    const raw = String(value ?? '').trim();
    return raw && /^-?\d+$/.test(raw) ? Number(raw) : raw;
  }
  if (field.type === 'multi_select') return Array.isArray(value) ? value : [];
  if (field.type === 'table') return Array.isArray(value) ? value : [];
  if (field.type === 'auto_number') return undefined;
  return value;
}

function isVisible(field: FormField): boolean {
  // Documents are excluded because uploading requires an authenticated actor
  // (POST /filehandler/upload), which a public respondent is not — so the field
  // could never be filled. Timers are operated by an authenticated workflow user,
  // not entered by a public-form respondent. Neither may fall through to text.
  return (
    field.type !== 'section' &&
    field.type !== 'reference' &&
    field.type !== 'auto_number' &&
    field.type !== 'document' &&
    field.type !== 'timer_duration'
  );
}

function validateFields(
  fields: FormField[],
  values: Record<string, unknown>,
): Record<string, string> {
  const errors: Record<string, string> = {};
  for (const field of fields) {
    if (field.type === 'boolean') continue;
    const val = values[field.id];
    if (isMissingRequiredFieldValue(field, val)) {
      errors[field.id] = `${field.label} is required`;
      continue;
    }
    const msg = validateFieldValue(field, val);
    if (msg) errors[field.id] = msg;
  }
  return errors;
}

/** Publicly accessible form page — loads a form schema by token or entity ID from the URL, renders fields, and submits responses without requiring authentication. */
export default function PublicFormPage() {
  const { token = '', entityId = '' } = useParams();
  const [payload, setPayload] = useState<PublicFormSchemaResponse | null>(null);
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  useEffect(() => {
    if (!entityId && !token) {
      setSubmitError('Missing form link.');
      setLoading(false);
      return;
    }
    void (async () => {
      try {
        const data = entityId
          ? await formSchemas.getPublicByEntity(entityId)
          : await formSchemas.getPublic(token);
        const parsed = (data.form.fields ?? []).map(mapEntityFieldToFormField).filter(isVisible);
        setPayload(data);
        setValues(buildInitialValues(parsed));
      } catch (err) {
        setSubmitError(getApiErrorMessage(err, 'Failed to load form.'));
      } finally {
        setLoading(false);
      }
    })();
  }, [token, entityId]);

  const fields = useMemo(
    () => (payload?.form.fields ?? []).map(mapEntityFieldToFormField).filter(isVisible),
    [payload],
  );

  // Calc fields/columns update live from the raw entered values; kept separate
  // from `values` so the raw, editable state is untouched (backend recomputes
  // authoritatively on submit regardless).
  const computedValues = useMemo(() => applyCalculations(fields, values), [fields, values]);

  const handleChange = (id: string, val: unknown) => {
    setValues((prev) => ({ ...prev, [id]: val }));
    if (fieldErrors[id]) {
      setFieldErrors((prev) => {
        const next = { ...prev };
        delete next[id];
        return next;
      });
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const errors = validateFields(fields, values);
    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      setSubmitError('Please fix the errors below before submitting.');
      return;
    }
    try {
      setSubmitting(true);
      setSubmitError(null);
      setFieldErrors({});
      // TODO(calc, P1): these values include client-computed calc fields/columns/cells.
      // The public-form submit path (backend FormsServiceManager._submit_with_raw_payload ->
      // FormsModelService.patch_entity_data) writes them directly WITHOUT server-side
      // apply_calculations — unlike entities/manager.py create/update — so a stale/crafted
      // client can persist arbitrary calc values. Recompute server-side via
      // calc.apply.apply_calculations (or route through the entities create/update choke
      // point) before persisting. Same gap for the create-new-entity form action.
      // [issue](https://dev.flowtuple.com/pipeline/00240677-cdac-4d68-8e57-b2ce1cddc9b9/entity/546bc86c-6191-41f6-83f6-e3c85d566b85)
      const normalized = Object.fromEntries(
        fields.filter((f) => !f.read_only).map((f) => [f.id, normalizeValue(f, computedValues[f.id])]),
      );
      if (entityId) {
        await formSchemas.submitPublicByEntity(entityId, normalized);
      } else {
        await formSchemas.submitPublic({ token, fields: normalized });
      }
      setSubmitted(true);
    } catch (err) {
      setSubmitError(getApiErrorMessage(err, 'Failed to submit. Please try again.'));
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <Shell>
        <div className="flex h-48 items-center justify-center">
          <Loader2 className="h-6 w-6 animate-spin text-info" />
        </div>
      </Shell>
    );
  }

  if (!payload && submitError) {
    return (
      <Shell>
        <div className="px-6 py-10 sm:px-8">
          <ErrorBanner message={submitError} />
        </div>
      </Shell>
    );
  }

  if (submitted) {
    return (
      <Shell>
        <div className="flex flex-col items-center px-6 py-12 text-center sm:px-8">
          <div className="mb-5 flex h-14 w-14 items-center justify-center rounded-2xl bg-success-subtle text-success">
            <CheckCircle2 className="h-7 w-7" />
          </div>
          <h2 className="text-xl font-semibold text-foreground">Submission received</h2>
          <p className="mt-2 max-w-xs text-sm text-muted-foreground">
            Thanks for completing this form. You can close this page.
          </p>
        </div>
      </Shell>
    );
  }

  return (
    <Shell>
      <div className="border-b border-border px-6 pb-5 pt-6 sm:px-8 sm:pt-8">
        {payload?.form.entity_type && (
          <p className="mb-1 text-[11px] font-semibold uppercase tracking-widest text-info">
            {resolveEntityTypeLabel(payload.form.entity_type)}
          </p>
        )}
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">
          {payload?.form.name ?? 'Form Submission'}
        </h1>
        {payload?.form.description && (
          <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{payload.form.description}</p>
        )}
      </div>

      <form
        noValidate
        onSubmit={(e) => void handleSubmit(e)}
        className="space-y-5 px-6 py-6 sm:px-8 sm:py-8"
      >
        {submitError && <ErrorBanner message={submitError} />}

        {fields.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border bg-muted/50 py-8 text-center text-sm text-muted-foreground">
            No fields configured.
          </div>
        ) : (
          fields.map((field) => (
            <div key={field.id}>
              <div className="mb-1.5 flex items-baseline gap-1">
                <label className="text-sm font-medium text-foreground">{field.label}</label>
                {field.required && (
                  <span className="text-xs font-semibold text-destructive" aria-label="required">*</span>
                )}
              </div>
              <FieldInput
                field={field}
                value={computedValues[field.id]}
                hasError={Boolean(fieldErrors[field.id])}
                onChange={handleChange}
              />
              {fieldErrors[field.id] && (
                <p className="mt-1.5 text-xs text-destructive" role="alert">
                  {fieldErrors[field.id]}
                </p>
              )}
            </div>
          ))
        )}

        <div className="border-t border-border pt-2">
          <button
            type="submit"
            disabled={submitting || fields.length === 0}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-info px-5 py-3 text-sm font-semibold text-info-foreground shadow-sm transition hover:bg-info/90 focus:outline-none focus:ring-2 focus:ring-info/30 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            {submitting ? 'Submitting…' : 'Submit'}
          </button>
        </div>
      </form>
    </Shell>
  );
}
