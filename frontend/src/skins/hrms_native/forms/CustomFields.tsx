import { useQuery } from '@tanstack/react-query';
import { request } from '@/core/services/api/client';

/** A field the organization added in Settings → Fields/Forms, beyond the ones this screen has. */
type Field = { field: string; description?: string; placeholder?: string; required?: boolean; read_only?: boolean; type?: string; enum_values?: string[]; enum_labels?: Record<string, string>; custom?: boolean };
export type CustomValues = Record<string, unknown>;

const WHOLE = new Set(['integer', 'int', 'number', 'timer_duration']);
const DECIMAL = new Set(['float', 'decimal']);
const INPUT_TYPES: Record<string, string> = { date: 'date', datetime: 'datetime-local', email: 'email', url: 'url', phone: 'tel' };
// Types a plain form can edit; others (JSON, documents) are shown read-only.
const EDITABLE = new Set(['string', 'str', 'text', 'enum', 'boolean', 'bool', ...WHOLE, ...DECIMAL, ...Object.keys(INPUT_TYPES)]);
const title = (field: Field) => field.description?.trim() || field.field.replaceAll('_', ' ').replace(/^./, c => c.toUpperCase());

function useCustomFields(entityType: string) {
  // Same query as ConfiguredForm, so the form configuration is fetched once.
  const schema = useQuery({ queryKey: ['hrms', 'form-config', entityType], queryFn: () => request<{ fields: Field[] }>(`/hrms/forms/${entityType}`), staleTime: 0 });
  return (schema.data?.fields ?? []).filter(field => field.custom);
}

/** Inputs for the organization's own fields; values go to the server as they are typed. `saved` shows what an
 * edited record already holds; the server keeps a saved value that is not sent again. */
export function CustomFields({ entityType, values, onChange, saved }: { entityType: string; values: CustomValues; onChange: (values: CustomValues) => void; saved?: CustomValues }) {
  const fields = useCustomFields(entityType);
  if (!fields.length) return null;
  const set = (key: string, value: unknown) => onChange({ ...values, [key]: value });
  return <div className="grid gap-3 sm:grid-cols-2">{fields.map(field => {
    const type = String(field.type ?? 'string').toLowerCase();
    const value = field.field in values ? values[field.field] : saved?.[field.field];
    const common = { required: Boolean(field.required && !field.read_only), disabled: Boolean(field.read_only) || !EDITABLE.has(type), placeholder: field.placeholder, className: 'hrms-field-input' };
    let control;
    if (type === 'boolean' || type === 'bool') {
      return <label key={field.field} className="flex items-center gap-2 text-sm font-medium"><input type="checkbox" disabled={common.disabled} checked={value === true} onChange={e => set(field.field, e.target.checked)} />{title(field)}</label>;
    } else if (field.enum_values?.length) {
      control = <select {...common} value={String(value ?? '')} onChange={e => set(field.field, e.target.value || null)}><option value="">Select…</option>{field.enum_values.map(option => <option key={option} value={option}>{field.enum_labels?.[option] ?? option}</option>)}</select>;
    } else if (type === 'text') {
      control = <textarea {...common} rows={2} value={String(value ?? '')} onChange={e => set(field.field, e.target.value)} />;
    } else if (WHOLE.has(type) || DECIMAL.has(type)) {
      control = <input {...common} type="number" step={WHOLE.has(type) ? 1 : 'any'} value={value == null ? '' : String(value)} onChange={e => set(field.field, e.target.value === '' ? null : Number(e.target.value))} />;
    } else if (EDITABLE.has(type)) {
      control = <input {...common} type={INPUT_TYPES[type] ?? 'text'} value={String(value ?? '').slice(0, type === 'datetime' ? 16 : undefined)} onChange={e => set(field.field, e.target.value)} />;
    } else {
      control = <input {...common} value={value == null ? '' : JSON.stringify(value)} readOnly />;
    }
    return <label key={field.field} className={`block space-y-1 text-sm font-medium ${type === 'text' ? 'sm:col-span-2' : ''}`}><span>{title(field)}</span>{control}</label>;
  })}</div>;
}

/** The organization's own fields as read-only "Label: value" lines. */
export function CustomFieldValues({ entityType, values }: { entityType: string; values?: CustomValues }) {
  const fields = useCustomFields(entityType).filter(field => values?.[field.field] != null && values[field.field] !== '');
  if (!fields.length) return null;
  const shown = (value: unknown) => value === true ? 'Yes' : value === false ? 'No' : typeof value === 'object' ? JSON.stringify(value) : String(value);
  return <dl className="mt-2 grid gap-x-4 gap-y-1 text-sm sm:grid-cols-2">{fields.map(field => <div key={field.field}><dt className="inline text-slate-500">{title(field)}: </dt><dd className="inline">{shown(values?.[field.field])}</dd></div>)}</dl>;
}
