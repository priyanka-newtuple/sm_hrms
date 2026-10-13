import { type Field } from './ConfiguredForm';
import { useQuery } from '@tanstack/react-query';
import { request } from '@/core/services/api/client';

/** A field the organization added in Settings → Fields/Forms, beyond the ones this screen has. */
export type CustomValues = Record<string, unknown>;

const title = (field: Field) => field.description?.trim() || field.field.replaceAll('_', ' ').replace(/^./, c => c.toUpperCase());

function useCustomFields(entityType: string) {
  // Same query as ConfiguredForm, so the form configuration is fetched once.
  const schema = useQuery({ queryKey: ['hrms', 'form-config', entityType], queryFn: () => request<{ fields: Field[] }>(`/hrms/forms/${entityType}`), staleTime: 0 });
  return (schema.data?.fields ?? []).filter(field => field.custom);
}

/** The organization's own fields as read-only "Label: value" lines. */
export function CustomFieldValues({ entityType, values }: { entityType: string; values?: CustomValues }) {
  const fields = useCustomFields(entityType).filter(field => values?.[field.field] != null && values[field.field] !== '');
  if (!fields.length) return null;
  const shown = (value: unknown) => value === true ? 'Yes' : value === false ? 'No' : typeof value === 'object' ? JSON.stringify(value) : String(value);
  return <dl className="mt-2 grid gap-x-4 gap-y-1 text-sm sm:grid-cols-2">{fields.map(field => <div key={field.field}><dt className="inline text-slate-500">{title(field)}: </dt><dd className="inline">{shown(values?.[field.field])}</dd></div>)}</dl>;
}
