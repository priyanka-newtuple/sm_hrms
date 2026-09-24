/**
 * fieldLibraryUtils
 *
 * Pure helpers shared between FieldsTab (the list) and FieldDetailSheet (the
 * per-field detail panel), factored out so neither file has to duplicate the
 * identity/version <-> FormField mapping or the settings formatting logic.
 */

import type {
  FieldCreateRequest,
  FieldIdentity,
  FieldListResponse,
  FieldType,
  FieldVersion,
  FieldVersionCreateRequest,
  FieldWithVersion,
  FormField,
  Picklist,
} from '../../../../core/types';
import { FIELD_TYPE_LABELS, generateFieldId } from '../form-config/constants';
import { resolveFieldForSave } from '../form-config/fieldSaveValidation';

// FIELD_TYPES is only the subset the "Add field" dropdown offers; library
// fields can carry any type in the full FieldType union (e.g. `number`,
// `date`), so validity has to be checked against every key of
// FIELD_TYPE_LABELS (a Record<FieldType, string>, exhaustive by
// construction) rather than that create-time subset.
export const FIELD_TYPE_VALUES = new Set<FieldType>(Object.keys(FIELD_TYPE_LABELS) as FieldType[]);
export const NEW_FIELD_DRAFT: FormField = { id: '', label: '', type: 'text', required: false, system: false };
export const DUPLICATE_MESSAGE_FRAGMENT = 'already exists in this organization';
export const FIELD_LIBRARY_FETCH_LIMIT = 200;
const IMPORT_METADATA_KEYS = new Set([
  'description',
  'field_id',
  'field_key',
  'field_type',
  'id',
  'label',
  'name',
  'settings',
  'system',
  'type',
]);

interface FieldPageParams {
  includeArchived?: boolean;
  search?: string;
  fieldType?: string;
}
type FieldPageLoader = (
  params: FieldPageParams & { limit: number; offset: number },
) => Promise<FieldListResponse>;

/** Fetch every page for client-side full-text search and formula operands. */
export async function fetchAllLibraryFieldPages(
  loadPage: FieldPageLoader,
  params: FieldPageParams = {},
  pageSize = FIELD_LIBRARY_FETCH_LIMIT,
): Promise<FieldWithVersion[]> {
  const byId = new Map<string, FieldWithVersion>();
  let offset = 0;
  let total = Number.POSITIVE_INFINITY;

  while (offset < total) {
    const response = await loadPage({ ...params, limit: pageSize, offset });
    total = response.total;
    for (const item of response.items) {
      byId.set(item.identity.library_field_id, item);
    }
    if (response.items.length === 0) break;
    offset += response.items.length;
  }

  return [...byId.values()];
}

/** Client-side mirror of the backend's live name + type uniqueness rule. */
export function duplicateNameAndTypeError(
  entries: FieldWithVersion[],
  name: string,
  fieldType: FieldType,
  excludeLibraryFieldId?: string,
): string | null {
  const normalizedName = name.trim().toLowerCase();
  if (!normalizedName) return null;
  const duplicate = entries.some(({ identity }) => (
    !identity.is_archived &&
    identity.library_field_id !== excludeLibraryFieldId &&
    identity.field_type === fieldType &&
    identity.name.trim().toLowerCase() === normalizedName
  ));
  if (!duplicate) return null;
  const typeLabel = FIELD_TYPE_LABELS[fieldType] ?? fieldType;
  return `A field with the name "${name.trim()}" and type "${typeLabel}" already exists.`;
}

/** Defensive ordering in case a cached or older API response is unsorted. */
export function versionsNewestFirst(versions: FieldVersion[]): FieldVersion[] {
  return [...versions].sort((left, right) => right.version - left.version);
}

function canonicalize(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonicalize);
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .filter(([, child]) => child !== undefined)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, child]) => [key, canonicalize(child)]),
    );
  }
  return value;
}

/** Compare version settings by content rather than object insertion order. */
export function settingsAreEqual(
  left: Record<string, unknown> | undefined,
  right: Record<string, unknown> | undefined,
): boolean {
  return JSON.stringify(canonicalize(left ?? {})) === JSON.stringify(canonicalize(right ?? {}));
}

/** A library field as `LibraryFieldEditor` (and its calc builder / table
 *  field references) needs to see it, reconstructed from the backend's
 *  identity + version shape back into the Forms tab's own FormField shape. */
export function toFormField(entry: FieldWithVersion): FormField {
  const settings = (entry.version.settings ?? {}) as Partial<FormField>;
  const type = FIELD_TYPE_VALUES.has(entry.version.field_type as FieldType)
    ? (entry.version.field_type as FieldType)
    : 'text';
  return {
    ...settings,
    id: entry.identity.field_key,
    label: entry.identity.name,
    type,
    required: settings.required === true,
    system: false,
  };
}

/** Strips the identity-only keys off a `LibraryFieldEditor` draft, leaving
 *  what belongs in a version's `settings` blob (including `required`, which
 *  the backend keeps on the version, not the identity). */
export function extractSettings(field: FormField): Record<string, unknown> {
  const settings: Record<string, unknown> = { ...field };
  delete settings.id;
  delete settings.label;
  delete settings.type;
  delete settings.system;
  return settings;
}

export function buildCreateRequest(field: FormField, description: string, existingKeys: string[]): FieldCreateRequest {
  const field_key = generateFieldId(
    field.label,
    existingKeys.map((key) => ({ id: key }) as FormField),
    -1,
  );
  return {
    name: field.label.trim(),
    field_key,
    field_type: field.type,
    description: description.trim() || undefined,
    settings: extractSettings(field),
  };
}

export function buildVersionRequest(field: FormField, description: string): FieldVersionCreateRequest {
  return {
    description: description.trim() || undefined,
    settings: extractSettings(field),
    field_type: field.type,
  };
}

type PreparedRequest<T> =
  | { request: T; error: null }
  | { request: null; error: string };

/** Apply the exact Forms-tab validation and picklist snapshot logic to v1. */
export function prepareLibraryCreateRequest(
  field: FormField,
  description: string,
  existingKeys: string[],
  picklists: Picklist[],
): PreparedRequest<FieldCreateRequest> {
  const initial = buildCreateRequest(field, description, existingKeys);
  const { resolved, error } = resolveFieldForSave(
    { ...field, id: initial.field_key },
    picklists,
  );
  if (error) return { request: null, error };
  return {
    request: {
      ...initial,
      name: resolved.label.trim(),
      field_type: resolved.type,
      settings: extractSettings(resolved),
    },
    error: null,
  };
}

/** Apply the same validation and picklist snapshot logic to a new version. */
export function prepareLibraryVersionRequest(
  field: FormField,
  description: string,
  picklists: Picklist[],
): PreparedRequest<FieldVersionCreateRequest> {
  const { resolved, error } = resolveFieldForSave(field, picklists);
  if (error) return { request: null, error };
  return { request: buildVersionRequest(resolved, description), error: null };
}

export type FieldSavePlan =
  | { kind: 'create'; request: FieldCreateRequest }
  | { kind: 'noop' }
  | {
      kind: 'metadata';
      libraryFieldId: string;
      originalName: string;
      name: string;
      nameChanged: boolean;
      description: string | null;
      descriptionChanged: boolean;
    }
  | {
      kind: 'version';
      libraryFieldId: string;
      originalName: string;
      name: string;
      nameChanged: boolean;
      request: FieldVersionCreateRequest;
    };

type SavePlanResult = { plan: FieldSavePlan; error: null } | { plan: null; error: string };

interface EditingDraft {
  isNew: boolean;
  field: FormField;
  description: string;
  target?: FieldWithVersion;
}

/** Decide what a save actually needs to do: create a new field, add a
 *  version (type or settings changed), or a metadata-only rename/description
 *  update (nothing to version). Kept pure so `FieldsTab` only has to act on
 *  the result, not re-derive it. */
export function buildFieldSavePlan(
  editing: EditingDraft,
  existingKeys: string[],
  picklists: Picklist[],
): SavePlanResult {
  if (editing.isNew) {
    const prepared = prepareLibraryCreateRequest(editing.field, editing.description, existingKeys, picklists);
    if (prepared.error !== null) return { plan: null, error: prepared.error };
    return { plan: { kind: 'create', request: prepared.request }, error: null };
  }

  const target = editing.target!;
  const name = editing.field.label.trim();
  const description = editing.description.trim() || null;
  const currentDescription = target.version.description?.trim() || null;
  const nameChanged = name !== target.identity.name;
  const descriptionChanged = description !== currentDescription;

  const draftSettings = extractSettings(editing.field);
  const typeChanged = editing.field.type !== target.identity.field_type;
  if (typeChanged || !settingsAreEqual(draftSettings, target.version.settings)) {
    const prepared = prepareLibraryVersionRequest(editing.field, editing.description, picklists);
    if (prepared.error !== null) return { plan: null, error: prepared.error };
    if (typeChanged || !settingsAreEqual(prepared.request.settings, target.version.settings)) {
      return {
        plan: {
          kind: 'version',
          libraryFieldId: target.identity.library_field_id,
          originalName: target.identity.name,
          name,
          nameChanged,
          request: prepared.request,
        },
        error: null,
      };
    }
  }

  if (nameChanged || descriptionChanged) {
    return {
      plan: {
        kind: 'metadata',
        libraryFieldId: target.identity.library_field_id,
        originalName: target.identity.name,
        name,
        nameChanged,
        description,
        descriptionChanged,
      },
      error: null,
    };
  }

  return { plan: { kind: 'noop' }, error: null };
}

interface FieldSaveClient {
  create: (request: FieldCreateRequest) => Promise<FieldWithVersion>;
  rename: (libraryFieldId: string, request: { name: string }) => Promise<unknown>;
  createVersion: (libraryFieldId: string, request: FieldVersionCreateRequest) => Promise<unknown>;
  updateDescription: (libraryFieldId: string, request: { description: string | null }) => Promise<unknown>;
}

/** Executes a plan from `buildFieldSavePlan` against the field library API.
 *  A rename that's immediately followed by a failed version/description
 *  write is rolled back, so a field never ends up renamed without the
 *  change it was renamed alongside. */
export async function applyFieldSavePlan(
  plan: FieldSavePlan,
  client: FieldSaveClient,
): Promise<{ createdName?: string; toastMessage: string }> {
  if (plan.kind === 'create') {
    const created = await client.create(plan.request);
    return { createdName: created.identity.name, toastMessage: `Created "${created.identity.name}"` };
  }
  if (plan.kind === 'noop') {
    return { toastMessage: 'No changes to save.' };
  }

  let renamed = false;
  if (plan.nameChanged) {
    await client.rename(plan.libraryFieldId, { name: plan.name });
    renamed = true;
  }
  try {
    if (plan.kind === 'version') {
      await client.createVersion(plan.libraryFieldId, plan.request);
    } else if (plan.descriptionChanged) {
      await client.updateDescription(plan.libraryFieldId, { description: plan.description });
    }
  } catch (saveError) {
    if (renamed) {
      try {
        await client.rename(plan.libraryFieldId, { name: plan.originalName });
      } catch (rollbackError) {
        const saveMessage = saveError instanceof Error ? saveError.message : 'Failed to update the field';
        const rollbackMessage = rollbackError instanceof Error ? rollbackError.message : 'rename rollback failed';
        throw new Error(`${saveMessage}. The rename also could not be rolled back: ${rollbackMessage}`);
      }
    }
    throw saveError;
  }

  if (plan.kind === 'version') return { toastMessage: 'New field version created.' };
  return { toastMessage: 'Field details updated without creating a version.' };
}

export interface ImportSummary {
  created: number;
  skipped: number;
  failed: number;
  firstFailureMessage: string | null;
  knownEntries: FieldWithVersion[];
}

/** Sequential import loop: skips exact name+type duplicates, validates each
 *  draft the same way a manual save would, and keeps a running tally so the
 *  final toast can report created/skipped/failed counts. Runs one create at
 *  a time (rather than in parallel) so each draft's duplicate check sees
 *  every field created earlier in the same import. */
export async function importFieldDrafts(
  drafts: { field: FormField; description: string }[],
  initialEntries: FieldWithVersion[],
  picklists: Picklist[],
  createField: (request: FieldCreateRequest) => Promise<FieldWithVersion>,
): Promise<ImportSummary> {
  let knownEntries = initialEntries;
  let knownKeys = initialEntries.map((entry) => entry.identity.field_key);
  const summary: ImportSummary = { created: 0, skipped: 0, failed: 0, firstFailureMessage: null, knownEntries };

  for (const draft of drafts) {
    if (duplicateNameAndTypeError(knownEntries, draft.field.label, draft.field.type)) {
      summary.skipped += 1;
      continue;
    }
    const prepared = prepareLibraryCreateRequest(draft.field, draft.description, knownKeys, picklists);
    if (prepared.error !== null) {
      summary.failed += 1;
      summary.firstFailureMessage ??= `"${draft.field.label}": ${prepared.error}`;
      continue;
    }
    try {
      const result = await createField(prepared.request);
      knownKeys = [...knownKeys, result.identity.field_key];
      knownEntries = [...knownEntries, result];
      summary.created += 1;
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Failed to create field';
      if (message.includes(DUPLICATE_MESSAGE_FRAGMENT)) {
        summary.skipped += 1;
      } else {
        summary.failed += 1;
        summary.firstFailureMessage ??= message;
      }
    }
  }

  summary.knownEntries = knownEntries;
  return summary;
}

export function importSummaryToast(summary: ImportSummary): { level: 'success' | 'error'; message: string } {
  const { created, skipped, failed, firstFailureMessage } = summary;
  if (failed > 0) {
    return {
      level: 'error',
      message:
        `Imported ${created}, skipped ${skipped} duplicate${skipped === 1 ? '' : 's'}, ` +
        `${failed} failed: ${firstFailureMessage}`,
    };
  }
  return {
    level: 'success',
    message:
      skipped > 0
        ? `Imported ${created} field${created === 1 ? '' : 's'}, skipped ${skipped} duplicate${skipped === 1 ? '' : 's'}.`
        : `Imported ${created} field${created === 1 ? '' : 's'}.`,
  };
}

/** Parses one imported field's raw JSON into a draft, accepting either the
 *  backend's own shape (name/field_type/settings, what "Copy JSON"
 *  produces) or a plain FormField-ish shape, defaulting/coercing whatever it
 *  can rather than rejecting outright. Any `id`/`field_key`/`field_id`
 *  present is ignored, the key is always assigned fresh on create. */
export function coerceImportedDraft(raw: unknown): { field: FormField; description: string } | null {
  if (!raw || typeof raw !== 'object') return null;
  const r = raw as Record<string, unknown>;
  const label = typeof r.name === 'string' ? r.name.trim() : typeof r.label === 'string' ? r.label.trim() : '';
  if (!label) return null;
  const typeRaw = typeof r.field_type === 'string' ? r.field_type : typeof r.type === 'string' ? r.type : 'text';
  const type = FIELD_TYPE_VALUES.has(typeRaw as FieldType) ? (typeRaw as FieldType) : 'text';
  const nestedSettings = r.settings;
  const settings = nestedSettings && typeof nestedSettings === 'object' && !Array.isArray(nestedSettings)
    ? (nestedSettings as Record<string, unknown>)
    : Object.fromEntries(
        Object.entries(r).filter(([key]) => !IMPORT_METADATA_KEYS.has(key)),
      );
  const description = typeof r.description === 'string' ? r.description : '';
  return {
    field: { ...(settings as Partial<FormField>), id: '', label, type, required: settings.required === true, system: false },
    description,
  };
}

/** Does this field match `query` across everything the list shows, not
 *  just name/key like the backend's own `search` param, but type label,
 *  description and settings too. Used when a search is active, over a
 *  larger batch fetched without the backend's own search filter. */
export function matchesSearch(field: FieldWithVersion, query: string): boolean {
  const normalizedQuery = query.trim().toLowerCase();
  if (!normalizedQuery) return true;
  const typeLabel = FIELD_TYPE_LABELS[field.identity.field_type as FieldType] ?? field.identity.field_type;
  const haystacks = [
    field.identity.name,
    field.identity.field_key,
    typeLabel,
    field.version.description ?? '',
    JSON.stringify(field.version.settings ?? {}),
  ];
  return haystacks.some((h) => h.toLowerCase().includes(normalizedQuery));
}

/** `field_count_id` (a plain sequential integer) shown as a short code:
 *  "F-04" reads as a field reference; "#4" reads as a comment count. */
export function formatFieldCode(fieldCountId: number, prefix = 'F'): string {
  return `${prefix}-${String(fieldCountId).padStart(2, '0')}`;
}

const SETTINGS_LABEL_OVERRIDES: Record<string, string> = {
  enum_values: 'Options',
  enum_labels: 'Option labels',
  enum_values_2: 'Second options',
  enum_labels_2: 'Second option labels',
  picklist_id: 'Picklist',
  picklist_id_2: 'Second picklist',
  extensions: 'Extended fields',
  table_config: 'Table columns',
  auto_number_config: 'Auto-number format',
  currency_config: 'Currency',
  col_span: 'Width',
  min_value: 'Minimum',
  max_value: 'Maximum',
  max_length: 'Max length',
  source_entity: 'Source entity',
  source_field: 'Source field',
  calc: 'Formula',
  document_config: 'Document settings',
};

export function humanizeSettingsKey(key: string): string {
  return SETTINGS_LABEL_OVERRIDES[key] ?? key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

const CALC_OPERATORS: Record<string, string> = { add: '+', sub: '−', mul: '×', div: '÷' };

/** A calc field's config is a small expression tree (shared/utils/calc.ts
 *  `CalcNode`), rendered as an actual expression, not a dumped object, so
 *  it reads as "reagent_count x 2" instead of "[object Object]". */
export function formatCalcNode(node: unknown): string {
  if (!node || typeof node !== 'object') return 'None';
  const n = node as Record<string, unknown>;
  switch (n.t) {
    case 'const':
      return String(n.value);
    case 'field':
      return String(n.field);
    case 'col':
      return String(n.col);
    case 'cell':
      return `${n.row}.${n.col}`;
    case 'agg':
      return `${n.fn}(${n.table}.${n.column})`;
    case 'binary':
      return `${formatCalcNode(n.left)} ${CALC_OPERATORS[n.op as string] ?? n.op} ${formatCalcNode(n.right)}`;
    default:
      return 'None';
  }
}

function isCalcNode(value: Record<string, unknown>): boolean {
  return typeof value.t === 'string' && ['const', 'field', 'col', 'cell', 'agg', 'binary'].includes(value.t);
}

export function humanizeSettingsValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return 'None';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (Array.isArray(value)) return value.length ? value.map(String).join(', ') : 'None';
  if (typeof value === 'object') {
    const record = value as Record<string, unknown>;
    if (isCalcNode(record)) return formatCalcNode(record);
    if (Array.isArray(record.columns)) {
      const columns = record.columns as { id: string; label?: string }[];
      return `${columns.length} column${columns.length === 1 ? '' : 's'}: ${columns.map((c) => c.label || c.id).join(', ')}`;
    }
    const entries = Object.entries(record).filter(([, v]) => v !== undefined && v !== null && v !== '');
    return entries.length
      ? entries.map(([k, v]) => `${humanizeSettingsKey(k)}: ${typeof v === 'object' ? humanizeSettingsValue(v) : v}`).join(' · ')
      : 'None';
  }
  return String(value);
}

/** Turns a version's raw settings blob into readable label/value rows for
 *  the version history panel, `required` is already shown as a badge, so
 *  it's left out here to avoid saying the same thing twice. */
export function settingsToRows(settings: Record<string, unknown>): { label: string; value: string }[] {
  return Object.entries(settings)
    .filter(([key, value]) => key !== 'required' && value !== undefined && value !== null && value !== '')
    .map(([key, value]) => ({ label: humanizeSettingsKey(key), value: humanizeSettingsValue(value) }));
}

/** Filters one field's version history by version number, snapshot name/type, description, or
 *  any setting's label/value, so a field with a long history is still
 *  findable without scrolling through every version by hand. */
export function matchesHistorySearch(identity: FieldIdentity, version: FieldVersion, query: string, codePrefix = 'F'): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  const rows = settingsToRows((version.settings ?? {}) as Record<string, unknown>);
  const haystacks = [
    identity.name,
    version.name,
    FIELD_TYPE_LABELS[version.field_type as FieldType] ?? version.field_type,
    identity.field_key,
    formatFieldCode(identity.field_count_id, codePrefix),
    `v${version.version}`,
    version.settings?.required === true ? 'required' : 'optional',
    version.description ?? '',
    version.created_by_name ?? '',
    ...rows.map((r) => `${r.label} ${r.value}`),
  ];
  return haystacks.some((h) => h.toLowerCase().includes(q));
}
