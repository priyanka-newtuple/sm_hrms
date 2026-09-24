import type { FormField, FormSchema } from '../../../../core/types';
import { templateTokens } from '@/shared/utils/entityForm';

/** Field types that can be referenced as `{{token}}`s in an identifier template. */
export const ALLOWED_IDENTIFIER_FIELD_TYPES = [
  'text',
  'textarea',
  'email',
  'phone',
  'url',
  'select',
  'integer',
  'number',
  'date',
  'datetime',
  'auto_number',
  'reference',
] as const;

export interface TokenOption {
  id: string;
  label: string;
}

const normalizeTypeName = (name: string) => name.replace(/^ATS\./, '').trim().toLowerCase();

/** De-duplicated form fields declared for an entity type across all its form schemas. */
export function fieldsForEntityType(schemas: FormSchema[], entityTypeName: string): FormField[] {
  const normalized = normalizeTypeName(entityTypeName);
  const seen = new Set<string>();
  return schemas
    .filter((schema) => normalizeTypeName(schema.entity_type) === normalized)
    .flatMap((schema) => schema.schema.fields)
    .filter((field) => {
      if (seen.has(field.id)) return false;
      seen.add(field.id);
      return true;
    });
}

export function allowedIdentifierFields(fields: FormField[]): FormField[] {
  return fields.filter((field) =>
    (ALLOWED_IDENTIFIER_FIELD_TYPES as readonly string[]).includes(field.type),
  );
}

/** Combobox options: allowed field tokens, related `<type>_identifier` tokens, then Sequence. */
export function buildTokenOptions(
  allowedFields: FormField[],
  relatedIdentifierTokens: string[],
): TokenOption[] {
  const fieldChipIds = new Set(allowedFields.map((field) => field.id.toLowerCase()));
  const relatedChips = relatedIdentifierTokens
    .filter((token) => !fieldChipIds.has(token))
    .map((token) => ({ id: token, label: `${token.replace(/_identifier$/, '')} identifier` }));
  return [
    ...allowedFields.map((field) => ({ id: field.id, label: field.label })),
    ...relatedChips,
    { id: 'seq', label: 'Sequence' },
  ];
}

/** Append `{{id}}` to a template, inserting a `-` separator unless one is already trailing. */
export function appendToken(template: string, id: string): string {
  const separator = !template || /[-_.]$/.test(template) ? '' : '-';
  return `${template}${separator}{{${id}}}`;
}

/** True when the template contains a brace outside a well-formed `{{token}}`. */
export function hasStrayBraces(template: string): boolean {
  return /[{}]/.test(template.replace(/\{\{\s*[A-Za-z0-9_]+\s*\}\}/g, ''));
}

/** Placeholder values for `renderIdentifierPreview`, keyed by lowercase field id / token. */
export function buildPreviewValueMap(
  allowedFields: FormField[],
  relatedIdentifierTokens: string[],
): Record<string, string> {
  return Object.fromEntries([
    ...allowedFields.map((field) => [field.id.toLowerCase(), field.label]),
    ...relatedIdentifierTokens.map((token) => [token, token.replace(/_identifier$/, '')]),
  ]);
}

/**
 * Template tokens that resolve to neither a known field, a `<type>_identifier`
 * relation, nor the `seq` counter — surfaced as a warning badge in the table.
 */
export function missingIdentifierTokens(
  template: string,
  knownFieldIds: Set<string>,
  typeNames: Set<string>,
): string[] {
  return templateTokens(template).filter(
    (token) =>
      token !== 'seq' &&
      !knownFieldIds.has(token) &&
      !(token.endsWith('_identifier') && typeNames.has(token.replace(/_identifier$/, ''))),
  );
}
