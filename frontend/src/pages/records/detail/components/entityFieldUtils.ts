import type { WorkflowEntityState } from '../../../../core/services/api';
import type { FormField, FormSchema } from '../../../../core/types';
import { picklistLabel } from '../../../../core/utils';
import { formatDocumentFieldValue, formatEntityFieldDisplayValue } from '../../../../shared/utils/entityDisplay';

const HIDDEN_DETAIL_KEYS = new Set(['id', 'entity_id', 'organization_id']);

export type DetailField = {
  id: string;
  label: string;
  value: unknown;
  field?: FormField;
};

function isLegacySchemaMetadataKey(key: string): boolean {
  const normalized = key.replace(/[^a-z0-9]/gi, '').toLowerCase();
  return normalized === 'predefinedreviewrows' || normalized === 'fixedrows' || normalized === 'presetrows';
}

export function detailFieldFromFormField(
  entity: WorkflowEntityState,
  field: FormField,
): DetailField {
  return {
    id: field.id,
    label: field.label,
    value: entity.data[field.id],
    field,
  };
}

export function detailFieldsFor(
  entity: WorkflowEntityState,
  schema: FormSchema | null,
): DetailField[] {
  if (schema) {
    return (schema.schema.fields ?? [])
      .filter((field) => field.type !== 'section' && !field.system)
      .map((field) => detailFieldFromFormField(entity, field));
  }

  return Object.entries(entity.data)
    .filter(([key]) => !HIDDEN_DETAIL_KEYS.has(key) && !isLegacySchemaMetadataKey(key))
    .map(([key, value]) => ({
      id: key,
      label: key,
      value,
    }));
}

export function formatDetailValue(field: FormField | undefined, value: unknown): string {
  if (field?.type === 'document') return formatDocumentFieldValue(value, '—');
  if (Array.isArray(value) && field?.enum_values?.length) {
    const labels = value
      .map((item) => picklistLabel(field, item) ?? (item == null ? '' : String(item)))
      .filter(Boolean);
    return labels.length > 0 ? labels.join(', ') : '—';
  }
  return picklistLabel(field, value) ?? formatEntityFieldDisplayValue(value, '—');
}
