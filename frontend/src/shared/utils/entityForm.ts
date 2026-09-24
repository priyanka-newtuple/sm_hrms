import type { ExtensionField, FormField, FormSchema, IdentifierConfig, TableColumn } from '../../core/types';
import { cellConfigFor } from './calc';

// Key for the per-entity-type unique identifier stored in entity `data`.
export const IDENTIFIER_FIELD_KEY = 'identifier';

// Required field shown at the top of the first add-entity tab.
export const IDENTIFIER_FIELD: FormField = {
  id: IDENTIFIER_FIELD_KEY,
  label: 'Unique Name',
  type: 'text',
  required: true,
  system: false,
  placeholder: '',
};

/**
 * "ATS.Candidate" → "Candidate Unique Name"
 * "jsi_client"    → "Client Unique Name"  (strips org prefix before first _)
 * "jsi_my_entity" → "My Entity Unique Name"
 */
export function getIdentifierLabel(entityType?: string | null): string {
  if (!entityType) return 'Unique Name';
  let raw: string;
  if (entityType.includes('.')) {
    raw = entityType.split('.').pop()!;
  } else if (entityType.includes('_')) {
    raw = entityType.substring(entityType.indexOf('_') + 1).replace(/_/g, ' ');
  } else {
    raw = entityType;
  }
  const name = raw.replace(/\b\w/g, (c) => c.toUpperCase());
  return `${name} Unique Name`;
}

export function getFormFields(schema: FormSchema | null): FormField[] {
  const fields = schema?.schema.fields || [];
  return fields.filter((f) => f.type !== 'section');
}

/** Fields a user can fill in an entry/edit form (excludes auto-generated + inherited). */
export function getEnterableFields(schema: FormSchema | null): FormField[] {
  return getFormFields(schema).filter(
    (f) => f.type !== 'auto_number' && f.type !== 'reference' && f.type !== 'timer_duration' && !f.calc
  );
}

/** Read-only fields inherited from a related record via a relation declaration. */
export function getReferenceFields(schema: FormSchema | null): FormField[] {
  return getFormFields(schema).filter(
    (f) => f.type === 'reference' && !f.id.includes('.') // dotted ids are legacy, never resolve
  );
}

/**
 * Calculated fields — excluded from `getEnterableFields` (never submitted; the
 * backend recomputes authoritatively), but must still be included wherever a
 * schema's fields are rendered so their live-computed value shows up in the form.
 */
export function getCalculatedFields(schema: FormSchema | null): FormField[] {
  return getFormFields(schema).filter((f) => f.calc);
}

/**
 * Restrict an update payload to enterable field values (plus the identifier).
 *
 * Form data seeded from `entity.data` carries backend-overlaid inherited
 * (reference) values; sending those keys back trips the backend's 403
 * "inherited field" guard once a REFERENCE declaration exists.
 */
export function pickEnterableData(
  schemas: FormSchema[],
  formData: Record<string, unknown>,
): Record<string, unknown> {
  const enterableIds = new Set(
    schemas.flatMap((s) => getEnterableFields(s)).filter((field) => !field.read_only).map((field) => field.id),
  );
  const result: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(formData)) {
    if (enterableIds.has(key) || key === IDENTIFIER_FIELD_KEY) result[key] = value;
  }
  return result;
}

function defaultValueFor(field: FormField): unknown {
  if (field.type === 'boolean') return false;
  if (field.type === 'multi_select') return [];
  if (field.type === 'picklist_multi') return [];
  if (field.type === 'table') return defaultTableValue(field);
  // Always a list: the backend rejects a document field that isn't one.
  if (field.type === 'document') return [];
  return '';
}

function defaultTableValue(field: FormField): Array<Record<string, unknown>> {
  const config = field.table_config;
  if (config?.row_mode !== 'fixed') return [];
  return (config.rows ?? []).map((row) => ({
    _row_id: row.id,
    ...(row.line ? { line: row.line, _line: row.line } : {}),
    ...(row.label ? { description: row.label, _label: row.label } : {}),
    ...(row.cells ?? {}),
  }));
}

export function buildDefaultFormData(schema: FormSchema | null): Record<string, unknown> {
  const defaults: Record<string, unknown> = {};
  getEnterableFields(schema).forEach((field) => {
    defaults[field.id] = defaultValueFor(field);
  });
  return defaults;
}

/**
 * Default form data merged across every attached form. Shared field ids resolve
 * to a single entry (first occurrence wins), so a value typed under one tab is
 * preserved when switching to another.
 */
export function buildDefaultFormDataForSchemas(
  schemas: FormSchema[]
): Record<string, unknown> {
  const defaults: Record<string, unknown> = {};
  // Seed the first-tab identifier so its input stays controlled.
  if (schemas.length > 0) defaults[IDENTIFIER_FIELD_KEY] = '';
  schemas.forEach((schema) => {
    getEnterableFields(schema).forEach((field) => {
      if (!(field.id in defaults)) defaults[field.id] = defaultValueFor(field);
    });
  });
  return defaults;
}

/**
 * timer_duration fields across every attached form, in order.
 *
 * A timer measures the work of filling a record in, which spans all of its
 * forms — but a field can only belong to one form. So the surfaces render a
 * timer once at record level, above the form tabs/steps, rather than inside
 * whichever form happens to declare it. These helpers are what let them do
 * that: collect the timer fields from every form, and drop them from the
 * per-form field list so the same control isn't drawn twice.
 *
 * More than one form may declare a timer. They all describe the same run, so
 * the first is the one that is operated and the rest mirror its value.
 */
export function collectTimerFields(fields: FormField[]): FormField[] {
  return fields.filter((field) => field.type === 'timer_duration');
}

export function withoutTimerFields(fields: FormField[]): FormField[] {
  return fields.filter((field) => field.type !== 'timer_duration');
}

/** All fillable fields across every attached form, deduped by field id. */
export function getFormFieldsForSchemas(schemas: FormSchema[]): FormField[] {
  const seen = new Set<string>();
  const fields: FormField[] = [];
  schemas.forEach((schema) => {
    getFormFields(schema).forEach((field) => {
      if (seen.has(field.id)) return;
      seen.add(field.id);
      fields.push(field);
    });
  });
  return fields;
}

export function parseCurrencyValue(value: unknown): { amount: unknown; currency_code: unknown } | null {
  let v: unknown = value;
  if (typeof value === 'string' && value.trimStart().startsWith('{')) {
    try { v = JSON.parse(value); } catch { /* not valid JSON — treat as plain string */ }
  }
  if (v !== null && typeof v === 'object' && !Array.isArray(v)) {
    const cv = v as Record<string, unknown>;
    if (cv.__type === 'currency' || 'amount' in cv || 'currency_code' in cv) {
      return cv as { amount: unknown; currency_code: unknown };
    }
  }
  return null;
}

/**
 * Walk the "Extend Field" values a picklist_multi holds, visiting only the
 * fields that are actually shown: those configured for an option that is
 * selected in that row. `label` prefixes the row and option so a message can
 * name where in the wizard the problem is.
 */
function forEachExtensionValue(
  field: FormField,
  value: unknown,
  visit: (extensionField: ExtensionField, entered: unknown, label: string) => void,
): void {
  const extensions = field.extensions;
  if (!extensions || !Array.isArray(value)) return;
  for (const raw of value) {
    if (!raw || typeof raw !== 'object') continue;
    const row = raw as { dropdown?: unknown; toggles?: unknown; extensions?: unknown };
    const toggles = Array.isArray(row.toggles) ? row.toggles.map(String) : [];
    const entered = (row.extensions ?? {}) as Record<string, Record<string, unknown>>;
    for (const option of toggles) {
      for (const extensionField of extensions[option]?.fields ?? []) {
        visit(
          extensionField,
          entered[option]?.[extensionField.id],
          `"${field.label}" — ${String(row.dropdown ?? '')} / ${option}`,
        );
      }
    }
  }
}

/**
 * The first type-level problem among the extension values a picklist_multi
 * holds, named by the row and option it sits under. One level deep by
 * construction: an extension field can never itself be a picklist_multi.
 */
function validateExtensionValues(field: FormField, value: unknown): string | null {
  let message: string | null = null;
  forEachExtensionValue(field, value, (extensionField, entered, label) => {
    if (message) return;
    const problem = validateFieldValue(extensionField, entered);
    if (problem) message = `${label}: ${problem}`;
  });
  return message;
}

/** Whether a required extension field of a selected option was left empty. */
function hasMissingRequiredExtensionValue(field: FormField, value: unknown): boolean {
  let missing = false;
  forEachExtensionValue(field, value, (extensionField, entered) => {
    missing = missing || isMissingRequiredFieldValue(extensionField, entered);
  });
  return missing;
}

function validateCurrencyValue(field: FormField, value: unknown): string | null {
  const raw = parseCurrencyValue(value)?.amount;
  if (raw === null || raw === undefined || raw === '') return null; // empty — caught by required check
  const num = parseFloat(String(raw));
  if (isNaN(num) || num < 0) return `"${field.label}" must be a valid positive amount`;
  return null;
}

function validateEmailValue(field: FormField, value: unknown): string | null {
  const email = String(value ?? '').trim();
  if (!email) return null;
  // The browser's own parser, rather than a regex of our own to keep correct.
  const input = document.createElement('input');
  input.type = 'email';
  input.value = email;
  return input.checkValidity() ? null : `"${field.label}" must be a valid email address`;
}

function validateUrlValue(field: FormField, value: unknown): string | null {
  const url = String(value ?? '').trim();
  if (!url) return null;
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return `"${field.label}" must be a valid URL starting with http:// or https://`;
  }
  if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') {
    return `"${field.label}" must start with http:// or https://`;
  }
  return null;
}

function validateIntegerValue(field: FormField, value: unknown): string | null {
  const raw = String(value ?? '').trim();
  if (!raw) return null;
  if (!/^-?\d+$/.test(raw)) {
    return `"${field.label}" must be a whole number — no letters, decimals, or special characters`;
  }
  return null;
}

export function validateFieldValue(field: FormField, value: unknown): string | null {
  if (field.calc) return null;
  if (field.type === 'picklist_multi' && field.extensions) {
    const problem = validateExtensionValues(field, value);
    if (problem) return problem;
  }
  if (field.type === 'auto_number') return null;
  if (field.type === 'document') return validateDocumentValue(field, value);
  // Required-ness is enforced by the workflow transition guard once
  // completed, not by this record-level check — a required timer that is
  // still running (or not yet started) must not block saving anything else
  // on the record.
  if (field.type === 'timer_duration') return null;
  if (field.type === 'table') return validateTableValue(field, value);
  if (field.type === 'currency') return validateCurrencyValue(field, value);
  if (field.type === 'email') return validateEmailValue(field, value);
  if (field.type === 'url') return validateUrlValue(field, value);
  if (field.type === 'integer') return validateIntegerValue(field, value);
  return null;
}

export function isMissingRequiredFieldValue(field: FormField, value: unknown): boolean {
  if (field.calc) return false;
  // Same reason as a calc field: the user has no way to fill this one, so a
  // required marker on it must never make Save unreachable.
  if (field.read_only) return false;
  // The field itself may still be required and empty, so this only short-circuits.
  if (field.type === 'picklist_multi' && field.extensions) {
    if (hasMissingRequiredExtensionValue(field, value)) return true;
  }
  // A timer writes its own value directly when stopped. A required marker must
  // never make the ordinary form Save wait for a separate Stop action.
  if (field.type === 'timer_duration') return false;
  if (!field.required) return false;
  if (field.type === 'table') {
    return !Array.isArray(value) || countMeaningfulTableRows(field, value) === 0;
  }
  if (field.type === 'currency') {
    const cv = parseCurrencyValue(value);
    const raw = cv?.amount;
    if (raw === null || raw === undefined || raw === '' || raw === '.') return true;
    return isNaN(parseFloat(String(raw)));
  }
  if (value === null || value === undefined) return true;
  if (typeof value === 'string') return value.trim() === '';
  if (Array.isArray(value)) return value.length === 0;
  return false;
}

function countMeaningfulTableRows(field: FormField, value: unknown): number {
  if (!Array.isArray(value)) return 0;
  const columns = field.table_config?.columns ?? [];
  if (field.table_config?.row_mode === 'fixed') return value.length;
  return value.filter((row) => isMeaningfulTableRow(row, columns)).length;
}

function isMeaningfulTableRow(row: unknown, columns: TableColumn[]): boolean {
  if (!row || typeof row !== 'object' || Array.isArray(row)) return false;
  const record = row as Record<string, unknown>;
  return columns.some((column) => {
    const value = record[column.id];
    if (Array.isArray(value)) return value.length > 0;
    return value !== null && value !== undefined && String(value).trim() !== '';
  });
}

function validateTableValue(field: FormField, value: unknown): string | null {
  const config = field.table_config;
  const columns = config?.columns ?? [];
  if (columns.length === 0) return `"${field.label}" must define at least one column`;
  if (!Array.isArray(value)) {
    if (field.required || (config?.min_rows ?? 0) > 0) return `"${field.label}" must be a table`;
    return null;
  }
  const meaningfulRows = countMeaningfulTableRows(field, value);
  const minRows = config?.min_rows ?? 0;
  if (minRows > 0 && meaningfulRows < minRows) {
    return `"${field.label}" must include at least ${minRows} ${minRows === 1 ? 'row' : 'rows'}`;
  }
  if (config?.max_rows && meaningfulRows > config.max_rows) {
    return `"${field.label}" cannot include more than ${config.max_rows} rows`;
  }

  for (let rowIndex = 0; rowIndex < value.length; rowIndex += 1) {
    const rawRow = value[rowIndex];
    if (!rawRow || typeof rawRow !== 'object' || Array.isArray(rawRow)) {
      return `"${field.label}" row ${rowIndex + 1} must be an object`;
    }
    const row = rawRow as Record<string, unknown>;
    const rowLabel = tableRowLabel(row, rowIndex);
    const hasAnyValue = isMeaningfulTableRow(row, columns);
    for (const column of columns) {
      const cell = row[column.id];
      const cc = cellConfigFor(field, row)?.[column.id];
      if (cc?.calc) continue; // computed cell — backend authoritative, never blocks save
      const cellRequired = cc?.readonly ? false : column.required;
      if ((field.table_config?.row_mode === 'fixed' || hasAnyValue) && cellRequired && isEmptyCell(cell)) {
        return `"${field.label}" ${rowLabel}: "${column.label}" is required`;
      }
      const effectiveType = cc?.type ?? column.type;
      const message = validateTableCell({ ...column, type: effectiveType }, cell);
      if (message) return `"${field.label}" ${rowLabel}: ${message}`;
    }
  }
  return null;
}

function tableRowLabel(row: Record<string, unknown>, rowIndex: number): string {
  const line = row.line ?? row._line ?? row._row_id;
  return line ? `line ${String(line)}` : `row ${rowIndex + 1}`;
}

function isEmptyCell(value: unknown): boolean {
  if (value === null || value === undefined) return true;
  if (typeof value === 'string') return value.trim() === '';
  if (Array.isArray(value)) return value.length === 0;
  return false;
}

function validateTableCell(column: TableColumn, value: unknown): string | null {
  if (isEmptyCell(value)) return null;
  if (column.type === 'integer') {
    if (typeof value === 'number') {
      return Number.isInteger(value) ? null : `"${column.label}" must be a whole number`;
    }
    if (!/^-?\d+$/.test(String(value).trim())) return `"${column.label}" must be a whole number`;
  }
  if (column.type === 'number' || column.type === 'currency' || column.type === 'percent') {
    const n = typeof value === 'number' ? value : Number(String(value).trim());
    if (!Number.isFinite(n)) return `"${column.label}" must be a number`;
  }
  if (column.type === 'email') {
    const input = document.createElement('input');
    input.type = 'email';
    input.value = String(value).trim();
    if (!input.checkValidity()) return `"${column.label}" must be a valid email address`;
  }
  if (column.type === 'url') {
    let parsed: URL;
    try {
      parsed = new URL(String(value).trim());
    } catch {
      return `"${column.label}" must be a valid URL starting with http:// or https://`;
    }
    if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') {
      return `"${column.label}" must start with http:// or https://`;
    }
  }
  if (column.type === 'select' && column.enum_values?.length) {
    return typeof value === 'string' && column.enum_values.includes(value)
      ? null
      : `"${column.label}" must be one of the configured options`;
  }
  if (column.type === 'multi_select' && column.enum_values?.length) {
    return Array.isArray(value) && value.every((item) => column.enum_values?.includes(String(item)))
      ? null
      : `"${column.label}" must only use configured options`;
  }
  return null;
}

/**
 * Mirrors the backend's own document checks (entities/manager.py
 * `_validate_document_field_values`) so a bad list is caught before a round
 * trip: a list of non-empty file ids, no duplicates. Whether each id exists is
 * only knowable server-side, so that stays the backend's call.
 */
function validateDocumentValue(field: FormField, value: unknown): string | null {
  if (value === null || value === undefined || value === '') return null;
  if (!Array.isArray(value)) return `"${field.label}" must hold a list of files`;
  const ids = value.map((entry) => (typeof entry === 'string' ? entry.trim() : ''));
  if (ids.some((id) => !id)) return `"${field.label}" has a file entry that isn't valid`;
  const duplicated = ids.find((id, index) => ids.indexOf(id) !== index);
  if (duplicated) return `"${field.label}" lists the same file twice`;
  return null;
}

function mapFormFieldTypeToEntityType(field: FormField): string {
  if (field.type === 'select' && field.enum_values?.length) {
    return 'enum';
  }
  // A multi-value field stores a list, and `matches_workflow_value` only accepts
  // a list for 'multi_select' and 'json' — calling it 'enum' (or, for
  // picklist_multi, falling through to 'string') made the workflow reject the
  // field's own value. Empty options leave it as json, which EntityField allows
  // and 'multi_select' does not.
  if (field.type === 'multi_select' || field.type === 'picklist_multi') {
    return field.enum_values?.length ? 'multi_select' : 'json';
  }
  switch (field.type) {
    case 'text':
    case 'textarea':
      return 'string';
    case 'phone':
      return 'phone';
    case 'url':
      return 'url';
    case 'date':
    case 'datetime':
      return 'datetime';
    case 'email':
      return 'email';
    case 'integer':
    case 'number':
      return 'int';
    case 'boolean':
      return 'boolean';
    case 'table':
      return 'json';
    case 'auto_number':
      return 'auto_number';
    case 'document':
      return 'document';
    case 'timer_duration':
      return 'timer_duration';
    default:
      return 'string';
  }
}

function fieldToSchemaField(field: FormField): Record<string, unknown> {
  // Reference fields persist their source through the `__ref__:` description
  // marker (see formSchemas.ts) — writing the plain label here would destroy
  // the encoding on the next schema_fields upsert.
  const description =
    field.type === 'reference'
      ? `__ref__:${field.source_entity ?? ''}:${field.source_field ?? ''}:${field.label}`
      : field.label || null;
  return {
    field: field.id,
    type: mapFormFieldTypeToEntityType(field),
    required: field.required,
    nullable: !field.required,
    description,
    ...((field.type === 'select' ||
      field.type === 'multi_select' ||
      field.type === 'picklist_multi') && field.enum_values?.length
      ? { enum_values: field.enum_values }
      : {}),
    ...(field.type === 'table' && field.table_config ? { table_config: field.table_config } : {}),
    ...(field.calc ? { calc: field.calc } : {}),
    ...(field.style_config ? { style_config: field.style_config } : {}),
    ...(field.read_only ? { read_only: true } : {}),
  };
}

export function buildCompleteSchemaFields(schema: FormSchema | null): Array<Record<string, unknown>> {
  return getFormFields(schema).map(fieldToSchemaField);
}

/** Union of entity schema fields across every attached form, deduped by field id. */
export function buildCompleteSchemaFieldsForSchemas(
  schemas: FormSchema[]
): Array<Record<string, unknown>> {
  return getFormFieldsForSchemas(schemas).map(fieldToSchemaField);
}

const IDENTIFIER_TOKEN_RE = /\{\{\s*([A-Za-z0-9_]+)\s*\}\}/g;

/** FE mirror of backend token rendering — preview only, backend is authoritative. */
export function rawIdentifierValue(value: unknown): string {
  if (value === null || value === undefined || typeof value === 'object') return '';
  return String(value);
}

export function templateTokens(template: string): string[] {
  return [...(template ?? '').matchAll(IDENTIFIER_TOKEN_RE)].map((match) =>
    match[1].toLowerCase(),
  );
}

/** Preview render — `{{seq}}` shows as a sample `0001`. */
export function renderIdentifierPreview(
  template: string,
  values: Record<string, unknown>,
): string {
  const substituted = (template ?? '').replace(IDENTIFIER_TOKEN_RE, (_, raw: string) => {
    const token = raw.toLowerCase();
    if (token === 'seq') return '0001';
    return rawIdentifierValue(values[token]);
  });
  return substituted
    .replace(/[-_]{2,}/g, (match) => match[0])
    .replace(/^[-_]+|[-_]+$/g, '')
    .slice(0, 120);
}

export function hasIdentifierTemplate(config?: IdentifierConfig | null): boolean {
  return Boolean(String(config?.identifier_template ?? '').trim());
}

export function resolveIdentifierLabel(
  config: IdentifierConfig | null | undefined,
  entityTypeName?: string | null,
): string {
  const label = String(config?.identifier_label ?? '').trim();
  return label || getIdentifierLabel(entityTypeName);
}

/** Configured blank-identifier message, or the default `<label> is required`. */
export function resolveIdentifierRequiredMessage(
  config: IdentifierConfig | null | undefined,
  label: string,
): string {
  return String(config?.identifier_error_message ?? '').trim() || `${label} is required`;
}
