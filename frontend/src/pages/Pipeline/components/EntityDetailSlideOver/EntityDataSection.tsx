import { useCallback, useEffect, useMemo, useRef, useState, type ReactElement } from 'react';
import { AlertCircle } from 'lucide-react';
import { getApiErrorMessage } from '@/core/services/api';
import type { WorkflowEntityState } from '@/core/services/api';
import type {
  CustomFormSchema,
  FormField,
  FormSchema,
  TableColumn,
} from '@/core/types';
import { picklistLabel } from '@/core/utils';
import { RichTextDisplay } from '@/core/components/RichTextEditor';
import { normalizeToHtml } from '@/core/utils/markdownToHtml';
import { usePermissions } from '@/core/hooks/usePermissions';
import EntityFormFields from '@/pages/records/detail/components/EntityFormFields';
import TimerDurationField from '@/core/components/TimerDurationField';
import { useRecordTimer } from '@/shared/hooks/useRecordTimer';
import {
  buildCompleteSchemaFieldsForSchemas,
  collectTimerFields,
  withoutTimerFields,
  getFormFields,
  getFormFieldsForSchemas,
  isMissingRequiredFieldValue,
  pickEnterableData,
  validateFieldValue,
} from '@/shared/utils/entityForm';
import {
  formatEntityFieldDisplayValue,
  getEntityTableDisplayColumns,
  getEntityTableDisplayRows,
} from '@/shared/utils/entityDisplay';
import { humanize } from '@/shared/utils/labels';
import { serializeCellValue } from '@/lib/export/serialize';
import { SchemaTabs } from '@/core/components';
import MaskedValue from '@/core/components/MaskedValue';
import DocumentFieldDisplay from '@/core/components/DocumentFieldDisplay';
import { applyCalculations } from '@/shared/utils/calc';
import EditActionsBar from './EditActionsBar';
import CustomFormPanel from './CustomFormPanel';
import { customFormTabs, parseCustomFormTabKey } from '@/lib/custom-form/fields';

// Matches a pure snake_case key: all-lowercase alphanumeric segments joined by
// single underscores (e.g. `photo_quality_check`, `client_name`, `identifier`).
const RAW_KEY_RE = /^[a-z0-9]+(?:_[a-z0-9]+)*$/;
/** How long the post-save "Saved" confirmation shows before it clears. */
const SAVED_INDICATOR_DURATION_MS = 2000;

/**
 * A field label here may arrive already authored (from a form schema, e.g.
 * "PAN Number" or "PAN_Number") or as a raw snake_case key when no schema is
 * attached. Humanize only raw keys so authored labels keep their exact casing.
 */
function fieldLabel(value: string): string {
  return RAW_KEY_RE.test(value) ? humanize(value) : value;
}

interface EntityDataSectionProps {
  entity: WorkflowEntityState;
  /** All forms attached to the entity type; each renders as a tab. */
  schemas: FormSchema[];
  /**
   * `schemas` is the complete display contract for this record — never fall
   * back to listing raw `entity.data` keys, even when it is empty.
   *
   * Detail views set this. An empty `schemas` there means "this record's state
   * collects no fields", which is a real answer, not the absence of one; the
   * raw-data fallback below would otherwise show every stored key and undo the
   * state scoping entirely. Left off, the historical behaviour is unchanged for
   * entity types that genuinely have no form configured.
   */
  schemasAuthoritative?: boolean;
  onSave: (
    entityId: string,
    payload: {
      data: Record<string, unknown>;
      schema_fields?: Array<Record<string, unknown>>;
      custom_form_data?: Record<string, unknown>;
    },
  ) => Promise<void>;
  onSaved?: (newData: Record<string, unknown>) => void;
  onEditingChange?: (editing: boolean) => void;
}

const HIDDEN_KEYS = new Set(['id', 'entity_id', 'organization_id']);
function isLegacySchemaMetadataKey(key: string): boolean {
  const normalized = key.replace(/[^a-z0-9]/gi, '').toLowerCase();
  return normalized === 'predefinedreviewrows' || normalized === 'fixedrows' || normalized === 'presetrows';
}

function defaultFixedTableRows(field: FormField): Array<Record<string, unknown>> {
  if (field.table_config?.row_mode !== 'fixed') return [];
  return (field.table_config.rows ?? []).map((row) => ({
    _row_id: row.id,
    ...(row.line ? { line: row.line, _line: row.line } : {}),
    ...(row.label ? { description: row.label, _label: row.label } : {}),
    ...(row.cells ?? {}),
  }));
}

function tableReadFormFieldClass(column: TableColumn): string {
  return column.type === 'textarea' || column.readonly ? 'col-span-2' : 'col-span-2 md:col-span-1';
}

function formatValue(value: unknown): string {
  return formatEntityFieldDisplayValue(value);
}

function formatListItem(value: unknown): string {
  return formatEntityFieldDisplayValue(value, '');
}


function formatFallbackDraft(value: unknown): string {
  if (value === null || value === undefined) return '';
  if (typeof value === 'object') return JSON.stringify(value, null, 2);
  return String(value);
}

function parseFallbackValue(key: string, original: unknown, draft: string): { value?: unknown; error?: string } {
  if (typeof original === 'boolean') {
    return { value: draft === 'true' };
  }

  if (typeof original === 'number') {
    const trimmed = draft.trim();
    if (!trimmed) return { error: `"${fieldLabel(key)}" must be a valid number` };
    const parsed = Number(trimmed);
    if (Number.isNaN(parsed)) {
      return { error: `"${fieldLabel(key)}" must be a valid number` };
    }
    return { value: parsed };
  }

  if (Array.isArray(original)) {
    try {
      const parsed = JSON.parse(draft);
      if (!Array.isArray(parsed)) {
        return { error: `"${fieldLabel(key)}" must be a JSON array` };
      }
      return { value: parsed };
    } catch {
      return { error: `"${fieldLabel(key)}" must be valid JSON` };
    }
  }

  if (original && typeof original === 'object') {
    try {
      const parsed = JSON.parse(draft);
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
        return { error: `"${fieldLabel(key)}" must be a JSON object` };
      }
      return { value: parsed };
    } catch {
      return { error: `"${fieldLabel(key)}" must be valid JSON` };
    }
  }

  return { value: draft };
}

interface FieldBoxProps {
  label: string;
  value: unknown;
  field?: FormField;
  /** Preview/record context used by document and timer fields. */
  entityId?: string;
  onTimerComplete?: (elapsedSeconds: number) => void;
  timerDisabled?: boolean;
  /** Same gate as the edit form: a timer cannot stop before the record's
   *  required fields are filled, or the read view would be a way around it. */
  timerCanStop?: boolean;
  timerStopBlockedHint?: string;
}

/**
 * Flatten one picklist_multi row's "Extend Field" values for display.
 *
 * Labels come from the field configuration when it is available — the option's
 * label from `enum_labels_2`, each field's from its snapshot — and fall back to
 * humanized keys, which is what a record saved against a since-changed picklist
 * or an unavailable schema leaves behind.
 */
function extensionEntries(
  field: FormField | undefined,
  rawExtensions: unknown,
): { option: string; label: string; pairs: { key: string; label: string; value: string }[] }[] {
  if (!rawExtensions || typeof rawExtensions !== 'object' || Array.isArray(rawExtensions)) return [];
  const optionValues = field?.enum_values_2 ?? [];
  const entries: { option: string; label: string; pairs: { key: string; label: string; value: string }[] }[] = [];
  for (const [option, values] of Object.entries(rawExtensions as Record<string, unknown>)) {
    if (!values || typeof values !== 'object' || Array.isArray(values)) continue;
    const configured = field?.extensions?.[option]?.fields ?? [];
    const optionIndex = optionValues.indexOf(option);
    const pairs = Object.entries(values as Record<string, unknown>)
      .map(({ 0: key, 1: value }) => ({
        key,
        label: configured.find((entry) => entry.id === key)?.label ?? humanize(key),
        value: serializeCellValue(value),
      }))
      .filter((pair) => pair.value !== '');
    if (pairs.length === 0) continue;
    entries.push({
      option,
      label: (optionIndex >= 0 ? field?.enum_labels_2?.[optionIndex] : undefined) || option,
      pairs,
    });
  }
  return entries;
}

function FieldBox({
  label,
  value,
  field,
  entityId,
  onTimerComplete,
  timerDisabled,
  timerCanStop,
  timerStopBlockedHint,
}: FieldBoxProps) {
  const inferredRows = field?.type === 'reference' ? getEntityTableDisplayRows(value) : [];
  const inferredColumns = inferredRows.length > 0 ? getEntityTableDisplayColumns(inferredRows) : [];
  if (inferredColumns.length > 0) {
    return (
      <div className="col-span-2">
        <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          {fieldLabel(label)}
        </p>
        <div className="overflow-x-auto rounded-lg border border-border bg-card">
          <table className="w-full min-w-[320px] table-fixed border-collapse text-sm">
            <thead>
              <tr className="bg-muted text-left text-xs font-semibold uppercase text-muted-foreground">
                {inferredColumns.map((column) => (
                  <th key={column} className="w-56 border border-border px-3 py-2 whitespace-normal break-words">
                    {fieldLabel(column)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {inferredRows.map((row, index) => (
                <tr key={String(row._row_id ?? index)}>
                  {inferredColumns.map((column) => (
                    <td key={column} className="w-56 border border-border px-3 py-2 align-top text-foreground whitespace-normal break-words">
                      {formatValue(row[column])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  if (field?.type === 'document') {
    return (
      <div>
        <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          {fieldLabel(label)}
        </p>
        <DocumentFieldDisplay value={value} entityId={entityId} showPreview />
      </div>
    );
  }

  if (field?.type === 'table') {
    const storedRows = Array.isArray(value) ? value.filter((row) => row && typeof row === 'object' && !Array.isArray(row)) as Record<string, unknown>[] : [];
    const rows = storedRows.length > 0 ? storedRows : defaultFixedTableRows(field);
    const columns = field.table_config?.columns ?? [];
    const displayMode = field.table_config?.display_mode ?? 'grid';
    const renderTableCellValue = (row: Record<string, unknown>, columnId: string) => {
      const cell = row[columnId];
      return formatValue(cell);
    };

    if (displayMode === 'form') {
      return (
        <div className="col-span-2">
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            {fieldLabel(label)}
          </p>
          <div className="divide-y divide-border rounded-lg border border-border bg-card">
            {rows.length === 0 ? (
              <div className="px-3 py-4 text-center text-sm text-muted-foreground">No rows</div>
            ) : rows.map((row, index) => (
              <div key={String(row._row_id ?? index)} className="p-3">
                {rows.length > 1 && (
                  <div className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Row {index + 1}
                  </div>
                )}
                <div className="grid grid-cols-2 gap-3">
                {columns.map((column) => (
                  <div key={column.id} className={tableReadFormFieldClass(column)}>
                    <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                      {column.label}
                    </p>
                    <div className="min-h-9 rounded-lg border border-border bg-muted px-3 py-2 text-sm text-foreground whitespace-normal break-words">
                      {renderTableCellValue(row, column.id)}
                    </div>
                  </div>
                ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      );
    }

    return (
      <div className="col-span-2">
        <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          {fieldLabel(label)}
        </p>
        <div className="overflow-x-auto rounded-lg border border-border bg-card">
          <table className="w-full min-w-[640px] table-fixed border-collapse text-sm">
            <thead>
              <tr className="bg-muted text-left text-xs font-semibold uppercase text-muted-foreground">
                {columns.map((column) => (
                  <th key={column.id} className="w-56 border border-border px-3 py-2 whitespace-normal break-words">{column.label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr>
                  <td colSpan={columns.length + 2} className="px-3 py-4 text-center text-muted-foreground">No rows</td>
                </tr>
              ) : rows.map((row, index) => (
                <tr key={String(row._row_id ?? index)}>
                  {columns.map((column) => (
                    <td key={column.id} className="w-56 border border-border px-3 py-2 align-top text-foreground whitespace-normal break-words">
                      {renderTableCellValue(row, column.id)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  if (field?.type === 'timer_duration') {
    return (
      <div>
        <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          {fieldLabel(label)}
        </p>
        <TimerDurationField
          fieldKey={field.id}
          value={value}
          onChange={(v) => { if (typeof v === 'number') onTimerComplete?.(v); }}
          entityId={entityId}
          canStop={timerCanStop}
          stopBlockedHint={timerStopBlockedHint}
          disabled={timerDisabled}
        />
      </div>
    );
  }

  const items = Array.isArray(value) ? (value as unknown[]).filter(Boolean) : null;

  // Handle picklist_multi: array of {dropdown, toggles} objects
  const isPicklistMulti = items && items.length > 0 &&
    typeof items[0] === 'object' &&
    items[0] !== null &&
    'dropdown' in (items[0] as Record<string, unknown>);

  if (isPicklistMulti) {
    return (
      <div>
        <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          {fieldLabel(label)}
        </p>
        <div className="space-y-2">
          {(items as unknown[]).map((row, i) => {
            const r = row as Record<string, unknown>;
            const dropdown = String(r.dropdown || '');
            const toggles = Array.isArray(r.toggles) ? (r.toggles as string[]) : [];
            return (
              <div key={i} className="rounded-lg border border-border bg-card px-3 py-2">
                {dropdown && (
                  <div className="text-sm font-medium text-foreground mb-1.5">{dropdown}</div>
                )}
                {toggles.length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {toggles.map((toggle, j) => (
                      <span
                        key={j}
                        className="rounded-full border border-cobalt/20 bg-cobalt/10 px-2.5 py-0.5 text-xs font-medium text-cobalt"
                      >
                        {toggle}
                      </span>
                    ))}
                  </div>
                )}
                {extensionEntries(field, r.extensions).map((entry) => (
                  <div key={entry.option} className="mt-2 border-t border-border pt-2">
                    <p className="text-xs font-medium text-foreground">{entry.label}</p>
                    <dl className="mt-1 space-y-0.5">
                      {entry.pairs.map((pair) => (
                        <div key={pair.key} className="flex gap-2 text-xs">
                          <dt className="shrink-0 text-muted-foreground">{pair.label}</dt>
                          <dd className="min-w-0 break-words text-foreground">{pair.value}</dd>
                        </div>
                      ))}
                    </dl>
                  </div>
                ))}
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  // Rich text — normalizeToHtml handles raw markdown, HTML-wrapped markdown,
  // clean HTML, and plain text so textarea values display consistently.
  // Memoized: the parse is non-trivial and FieldBox re-renders on every parent update.
  const richHtml = useMemo(() => {
    if (field?.type !== 'textarea' || typeof value !== 'string' || !value.trim()) return null;
    return normalizeToHtml(value) || null;
  }, [field?.type, value]);

  return (
    <div>
      <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {fieldLabel(label)}
      </p>
      <div className="min-h-[36px] rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground break-words">
        {richHtml ? (
          <RichTextDisplay html={richHtml} />
        ) : items ? (
          items.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {items.map((item, i) => (
                <span
                  key={i}
                  className="rounded-full border border-cobalt/20 bg-cobalt/10 px-2.5 py-0.5 text-xs font-medium text-cobalt"
                >
                  {picklistLabel(field, item) ?? formatListItem(item)}
                </span>
              ))}
            </div>
          ) : '—'
        ) : (picklistLabel(field, value) ?? formatValue(value))}
      </div>
    </div>
  );
}

function MaskedField({ label }: { label: string }): ReactElement {
  return (
    <div>
      <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {fieldLabel(label)}
      </p>
      <div className="min-h-[36px] rounded-lg border border-border bg-card px-3 py-2 text-sm text-muted-foreground">
        <MaskedValue />
      </div>
    </div>
  );
}

interface FallbackEditorProps {
  fields: Array<[string, unknown]>;
  drafts: Record<string, string>;
  onChange: (key: string, value: unknown) => void;
}

function FallbackEditor({ fields, drafts, onChange }: FallbackEditorProps) {
  return (
    <>
      {fields.map(([key, value]) => (
        <div key={key}>
          <label className="mb-1 block text-xs font-medium capitalize text-muted-foreground">
            {fieldLabel(key)}
          </label>
          {typeof value === 'boolean' ? (
            <label className="inline-flex items-center gap-2 rounded-lg border border-border bg-muted px-3 py-2 text-sm text-muted-foreground">
              <input
                type="checkbox"
                checked={drafts[key] === 'true'}
                onChange={(e) => onChange(key, e.target.checked)}
                className="h-4 w-4 rounded border-border text-cobalt focus:ring-cobalt"
              />
              Enabled
            </label>
          ) : typeof value === 'object' && value !== null ? (
            <textarea
              rows={Array.isArray(value) ? 4 : 6}
              value={drafts[key] ?? ''}
              onChange={(e) => onChange(key, e.target.value)}
              className="w-full rounded-lg border border-border bg-muted px-3 py-2 font-mono text-sm outline-none placeholder:text-muted-foreground focus:border-cobalt/40 focus:bg-card"
            />
          ) : (
            <input
              type={typeof value === 'number' ? 'number' : 'text'}
              value={drafts[key] ?? ''}
              onChange={(e) => onChange(key, e.target.value)}
              className="w-full rounded-lg border border-border bg-muted px-3 py-2 text-sm outline-none placeholder:text-muted-foreground focus:border-cobalt/40 focus:bg-card"
            />
          )}
        </div>
      ))}
    </>
  );
}

/** Edit-mode body: the active form's fields, or a fallback editor when no forms. */
function FormTabEditor({
  error,
  hasForms,
  activeFormFields,
  editData,
  onFieldChange,
  entityType,
  entityId,
  timerCanStop,
  timerStopBlockedHint,
  onTimerStopped,
  fieldsLocked,
  fieldsLockedHint,
  fallbackFields,
  fallbackDrafts,
  onFallbackChange,
}: {
  error: string | null;
  hasForms: boolean;
  activeFormFields: FormField[];
  editData: Record<string, unknown>;
  onFieldChange: (id: string, value: unknown) => void;
  entityType: string;
  entityId: string;
  timerCanStop: boolean;
  timerStopBlockedHint: string;
  onTimerStopped: (fieldId: string, elapsedSeconds: number) => void | Promise<void>;
  fieldsLocked: boolean;
  fieldsLockedHint: string;
  fallbackFields: Array<[string, unknown]>;
  fallbackDrafts: Record<string, string>;
  onFallbackChange: (key: string, value: unknown) => void;
}): ReactElement {
  return (
    <div className="mt-3 rounded-xl border border-border bg-card p-4 space-y-4">
      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-destructive/20 bg-destructive/10 px-3 py-2 text-xs text-destructive">
          <AlertCircle className="h-3.5 w-3.5 flex-shrink-0" />
          {error}
        </div>
      )}
      {hasForms ? (
        activeFormFields.length > 0 ? (
          <EntityFormFields
            fields={activeFormFields}
            values={editData}
            onChange={onFieldChange}
            entityType={entityType}
            entityId={entityId}
            documentPreviewEnabled
            mode="edit"
            timerCanStop={timerCanStop}
            timerStopBlockedHint={timerStopBlockedHint}
            onTimerStopped={onTimerStopped}
            fieldsLocked={fieldsLocked}
            fieldsLockedHint={fieldsLockedHint}
          />
        ) : (
          <p className="text-sm text-muted-foreground">No editable fields on this form.</p>
        )
      ) : (
        <FallbackEditor
          fields={fallbackFields}
          drafts={fallbackDrafts}
          onChange={onFallbackChange}
        />
      )}
    </div>
  );
}

/** View-mode body: the active form's fields plus an "Other" group, or a flat list. */
function FormTabViewer({
  hasForms,
  activeViewFields,
  flatEntries,
  entityData,
  renderReadField,
}: {
  hasForms: boolean;
  activeViewFields: FormField[];
  flatEntries: Array<[string, unknown]>;
  entityData: Record<string, unknown>;
  renderReadField: (key: string, label: string, value: unknown, field?: FormField) => ReactElement;
}): ReactElement {
  if (!hasForms) {
    return (
      <div>
        {flatEntries.length > 0 ? (
          <div className="grid grid-cols-2 gap-x-4 gap-y-3">
            {flatEntries.map(([key, value]) => renderReadField(key, key, value))}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">No details available.</p>
        )}
      </div>
    );
  }
  return (
    <div className="mt-3 space-y-4">
      {activeViewFields.length > 0 ? (
        <div className="grid grid-cols-2 gap-x-4 gap-y-3">
          {activeViewFields.map((f) => renderReadField(f.id, f.label, entityData[f.id], f))}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">No fields to show on this form.</p>
      )}
    </div>
  );
}

export default function EntityDataSection({
  entity,
  schemas: pinnedSchemas,
  schemasAuthoritative = false,
  onSave,
  onSaved,
  onEditingChange,
}: EntityDataSectionProps) {
  // Fetched with the record, so there is nothing to load here.
  const customForms = useMemo<Array<[string, CustomFormSchema]>>(
    () => Object.entries(entity.custom_form_schema ?? {}),
    [entity.custom_form_schema],
  );

  // A custom form's method declares no fields, so publish gives it an empty
  // schema and it would render as a tab reading "no editable fields". Its
  // sections are tabs of their own, so drop the empty one it stands in for.
  const schemas = useMemo(() => {
    if (customForms.length === 0) return pinnedSchemas;
    const customMethodIds = new Set(customForms.map(([methodId]) => methodId));
    return pinnedSchemas.filter((schema) => {
      const [prefix, methodId] = schema.schema_key.split(':');
      return !(prefix === 'method' && customMethodIds.has(methodId));
    });
  }, [pinnedSchemas, customForms]);

  const [activeKey, setActiveKey] = useState<string | undefined>(undefined);
  const [editData, setEditData] = useState<Record<string, unknown>>({});
  const [fallbackDrafts, setFallbackDrafts] = useState<Record<string, string>>({});
  const [isDirty, setIsDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [justSaved, setJustSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saveFailed, setSaveFailed] = useState(false);

  const { can, hasPermission, canViewField, shouldMaskField, canEditField, filterEditablePayload } =
    usePermissions();
  const entityType = entity.entity_type;
  const canEdit = can('edit', entityType);

  const savedTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const seededDataRef = useRef<unknown>(null);

  // Prev/next iteration is locked only while there's an unsaved edit or a save
  // is in flight — never permanently.
  useEffect(() => {
    onEditingChange?.(isDirty || saving);
  }, [isDirty, saving, onEditingChange]);

  // Clear the transient "Saved" timer on unmount. Split from the iteration-lock
  // release below: this timer cleanup must run only on real unmount, not every
  // time `onEditingChange` happens to be a new reference.
  useEffect(() => () => {
    if (savedTimerRef.current) clearTimeout(savedTimerRef.current);
  }, []);

  // Release the iteration lock on unmount. There is no auto-save backstop
  // here by design: a draft only ever persists when the user clicks Save;
  // leaving without saving discards it, same as any form with an explicit
  // Save button.
  useEffect(() => () => onEditingChange?.(false), [onEditingChange]);

  // Reset the draft to the last-saved server data. Used both to seed the
  // initial draft and to reconstruct it after Undo.
  const seedFromEntity = useCallback(() => {
    const editable = filterEditablePayload(entityType, entity.data);
    setEditData(editable);
    setFallbackDrafts(
      Object.fromEntries(Object.entries(editable).map(([key, value]) => [key, formatFallbackDraft(value)])),
    );
  }, [entityType, entity.data, filterEditablePayload]);

  // Re-absorb server updates (post-save refetch, recomputed calc fields)
  // whenever there's no unsaved edit in progress — never clobbering active
  // typing, and never re-seeding from the same `entity.data` twice.
  useEffect(() => {
    if (!canEdit || isDirty || saving) return;
    if (seededDataRef.current === entity.data) return;
    seededDataRef.current = entity.data;
    seedFromEntity();
  }, [canEdit, isDirty, saving, entity.data, seedFromEntity]);

  const activeCustom = useMemo(() => parseCustomFormTabKey(activeKey), [activeKey]);

  // Only the answers actually touched, so a save merges those keys and cannot
  // revert one the results write-back filled after this page loaded.
  const [customDrafts, setCustomDrafts] = useState<Record<string, unknown>>({});
  const handleCustomFormChange = useCallback((values: Record<string, unknown>) => {
    setCustomDrafts((current) => ({ ...current, ...values }));
    setIsDirty(true);
  }, []);
  const customFormValues = useMemo(
    () => ({ ...(entity.custom_form_data ?? {}), ...customDrafts }),
    [entity.custom_form_data, customDrafts],
  );
  const customTabs = useMemo(
    () => customForms.flatMap(([methodId, schema]) => customFormTabs(methodId, schema)),
    [customForms],
  );

  // Active form tab; falls back to the first form so the tabs always have a
  // selection — including while a custom form tab is active, since the draft state
  // below stays bound to a real form.
  const activeSchema = useMemo(
    () => schemas.find((s) => s.schema_key === activeKey) ?? schemas[0] ?? null,
    [schemas, activeKey],
  );
  // Timers render once at record level (above the tabs), never inside a tab.
  const activeFormFields = useMemo(
    () => withoutTimerFields(getFormFields(activeSchema)),
    [activeSchema],
  );
  const allFormFields = useMemo(() => getFormFieldsForSchemas(schemas), [schemas]);
  // Calc fields/columns update live from the raw entered values; kept separate
  // from `editData` so the raw, editable state is untouched (backend recomputes
  // authoritatively on save regardless).
  const computedEditData = useMemo(
    () => applyCalculations(activeFormFields, editData),
    [activeFormFields, editData],
  );

  // A timer measures the work of filling the record in, so it cannot stop
  // until that work is done. Checked across every attached form, not just the
  // active tab, since a timer on one form still waits on the others.
  const timerCanStop = useMemo(() => {
    if (!allFormFields.some((f) => f.type === 'timer_duration')) return true;
    return allFormFields.every(
      (f) => f.type === 'timer_duration' || !isMissingRequiredFieldValue(f, editData[f.id]),
    );
  }, [allFormFields, editData]);

  const timerFields = useMemo(() => collectTimerFields(allFormFields), [allFormFields]);
  const timer = useRecordTimer();
  // The timer that is operated. Any others describe the same run, so they
  // mirror its value rather than each holding a separate one.
  const primaryTimerField = timerFields[0] ?? null;
  const closeTimerRef = useRef<{
    active: boolean;
    finalize: () => Promise<void>;
  } | null>(null);

  /** Persist the frontend-recorded value through the normal entity update. */
  const handleTimerStopped = async (_fieldId: string, elapsedSeconds: number) => {
    const ids = timerFields.map((field) => field.id);
    const applied = Object.fromEntries(ids.map((id) => [id, elapsedSeconds]));
    try {
      await onSave(entity.entity_id, { data: applied });
      setEditData((prev) => ({ ...prev, ...applied }));
      onSaved?.({ ...entity.data, ...applied });
    } catch (e) {
      const message = getApiErrorMessage(e, 'Timer could not be saved');
      setError(message);
      throw new Error(message);
    }
  };

  // The Pipeline X closes the sheet by unmounting this section. Preserve the
  // existing auto-finalize behavior with an ordinary partial entity update.
  closeTimerRef.current = {
    active: timer.isActive && primaryTimerField !== null,
    finalize: async () => {
      if (!primaryTimerField) return;
      const baseSeconds =
        typeof editData[primaryTimerField.id] === 'number'
          ? Number(editData[primaryTimerField.id])
          : 0;
      const recorded = timer.recordedSeconds(baseSeconds);
      const applied = Object.fromEntries(timerFields.map((field) => [field.id, recorded]));
      await onSave(entity.entity_id, { data: applied });
      onSaved?.({ ...entity.data, ...applied });
    },
  };
  useEffect(() => () => {
    const current = closeTimerRef.current;
    if (!current?.active) return;
    void current.finalize().catch(() => {
      // The sheet is already closed; avoid an unhandled rejection.
    });
  }, [entity.entity_id]);

  // When forms exist, they are the display contract for this entity type. Extra
  // stored keys can be stale data from a previous type and should not leak into
  // the detail view.
  // TODO: Add an admin/raw-data view if operators need access to unowned fields.
  const flatEntries = Object.entries(entity.data).filter(
    ([key]) =>
      !HIDDEN_KEYS.has(key) &&
      !isLegacySchemaMetadataKey(key) &&
      canViewField(entityType, key),
  );

  // Typing never calls the API — it only marks the draft dirty, which reveals
  // the Undo/Save controls. Saving happens solely on an explicit Save click.
  // Clears `justSaved` too: without this, a fresh edit made just after a save
  // (before its 2s "Saved" pill has faded) would still show "Saved" as if
  // nothing had changed since.
  const markDirty = () => {
    setIsDirty(true);
    setError(null);
    setSaveFailed(false);
    setJustSaved(false);
  };

  const handleFieldChange = (id: string, value: unknown) => {
    setEditData((prev) => ({ ...prev, [id]: value }));
    markDirty();
  };

  const handleFallbackChange = (key: string, value: unknown) => {
    setFallbackDrafts((prev) => ({ ...prev, [key]: String(value) }));
    if (typeof value === 'boolean') {
      setEditData((prev) => ({ ...prev, [key]: value }));
    }
    markDirty();
  };

  const handleTabSelect = (key: string) => setActiveKey(key);

  // Discard the draft and restore the last-saved server data. Also clears
  // `justSaved`: undoing a post-save edit shouldn't replay the "Saved" pill
  // for a change that was itself just discarded.
  const handleUndo = () => {
    seedFromEntity();
    setIsDirty(false);
    setError(null);
    setSaveFailed(false);
    setJustSaved(false);
  };

  // Switch to the tab whose form owns the given field id.
  const focusFieldTab = (fieldId: string) => {
    const owner = schemas.find((s) => getFormFields(s).some((f) => f.id === fieldId));
    if (owner) setActiveKey(owner.schema_key);
  };

  const validate = (): string | null => {
    if (allFormFields.length === 0) return null;
    // Validate editable, non-masked fields across every attached form.
    const editableFields = allFormFields.filter(
      (f) => canEditField(entityType, f.id) && !shouldMaskField(entityType, f.id),
    );
    const missing = editableFields.find((f) => isMissingRequiredFieldValue(f, editData[f.id]));
    if (missing) {
      focusFieldTab(missing.id);
      return `"${missing.label}" is required`;
    }
    const invalid = editableFields.find((f) => validateFieldValue(f, editData[f.id]));
    if (invalid) {
      focusFieldTab(invalid.id);
      return validateFieldValue(invalid, editData[invalid.id]);
    }
    return null;
  };

  const buildFallbackPayload = (): { data?: Record<string, unknown>; error?: string } => {
    const nextData: Record<string, unknown> = { ...editData };

    for (const [key, originalValue] of flatEntries.filter(
      ([k]) => canEditField(entityType, k) && !shouldMaskField(entityType, k),
    )) {
      const parsed = parseFallbackValue(key, originalValue, fallbackDrafts[key] ?? '');
      if (parsed.error) return { error: parsed.error };
      nextData[key] = parsed.value;
    }

    return { data: nextData };
  };

  // Only reachable via the Save button — never called on typing, blur, or tab
  // switch, and disabled while already saving, so at most one save is in flight.
  const handleSave = async () => {
    const validation = validate();
    if (validation) {
      // Client-side rejection — nothing was sent, so this is not a "save
      // failure" (no Retry treatment in the header, just the inline message).
      setError(validation);
      setSaveFailed(false);
      return; // stays dirty — retried on the next Save click
    }

    setSaving(true);
    setError(null);
    setSaveFailed(false);
    try {
      // editData is seeded from entity.data, which carries backend-overlaid
      // inherited (reference) values — send only enterable field values or the
      // backend 403s with its "inherited field" guard.
      let nextData = pickEnterableData(schemas, editData);
      if (allFormFields.length === 0) {
        const fallbackPayload = buildFallbackPayload();
        if (fallbackPayload.error) {
          // Also a client-side rejection (bad fallback-field value) — same as
          // `validate()` above, nothing was sent.
          setError(fallbackPayload.error);
          return;
        }
        nextData = fallbackPayload.data ?? editData;
      }

      if (primaryTimerField && timer.isActive) {
        const baseSeconds =
          typeof editData[primaryTimerField.id] === 'number'
            ? Number(editData[primaryTimerField.id])
            : 0;
        const recorded = timer.recordedSeconds(baseSeconds);
        nextData = {
          ...nextData,
          ...Object.fromEntries(timerFields.map((field) => [field.id, recorded])),
        };
      }

      await onSave(entity.entity_id, {
        data: nextData,
        schema_fields: buildCompleteSchemaFieldsForSchemas(schemas),
        ...(Object.keys(customDrafts).length > 0 ? { custom_form_data: customDrafts } : {}),
      });
      setCustomDrafts({});
      if (timer.isActive) timer.reset();
      setIsDirty(false);
      onSaved?.({ ...entity.data, ...nextData });
      setJustSaved(true);
      if (savedTimerRef.current) clearTimeout(savedTimerRef.current);
      savedTimerRef.current = setTimeout(() => setJustSaved(false), SAVED_INDICATOR_DURATION_MS);
    } catch (e) {
      // A real save attempt failed server-side — Retry is a genuine action here.
      setError(getApiErrorMessage(e, 'Failed to save'));
      setSaveFailed(true);
    } finally {
      setSaving(false);
    }
  };

  const renderReadField = (key: string, label: string, value: unknown, field?: FormField) =>
    shouldMaskField(entityType, key) ? (
      <MaskedField key={key} label={label} />
    ) : (
      <FieldBox
        key={key}
        label={label}
        value={value}
        field={field}
        entityId={entity.entity_id}
        timerDisabled={!canEditField(entityType, key)}
        timerCanStop={timerCanStop}
        timerStopBlockedHint="Fill in every required field before stopping the timer."
        onTimerComplete={(elapsedSeconds) => onSaved?.({ ...entity.data, [key]: elapsedSeconds })}
      />
    );

  const activeViewFields = activeFormFields.filter((f) => canViewField(entityType, f.id));

  return (
    <section>
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-[13px] font-medium text-muted-foreground">Details</h3>
        {canEdit && !activeCustom && (
          <EditActionsBar
            isDirty={isDirty}
            saving={saving}
            justSaved={justSaved}
            saveFailed={saveFailed}
            onSave={() => void handleSave()}
            onUndo={handleUndo}
          />
        )}
      </div>

      {/* Record-level timer. It measures filling in the whole record, which
          spans every attached form, so it is rendered once here rather than
          inside whichever form declares it — reachable from any tab, and in
          the read view as well as while editing. */}
      {primaryTimerField && (
        <div className="mb-3 border-b border-border pb-3">
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            {primaryTimerField.label}
            {timerFields.length > 1 && (
              <span className="ml-1 font-normal normal-case tracking-normal">
                · recorded on {timerFields.length} forms
              </span>
            )}
          </p>
          <TimerDurationField
            fieldKey={primaryTimerField.id}
            value={computedEditData[primaryTimerField.id] ?? entity.data[primaryTimerField.id]}
            onChange={() => {}}
            entityId={entity.entity_id}
            disabled={!canEdit || !canEditField(entityType, primaryTimerField.id)}
            canStop={timerCanStop}
            stopBlockedHint="Fill in every required field, across all forms, before stopping the timer."
            onStopped={(seconds) => handleTimerStopped(primaryTimerField.id, seconds)}
            localStartedAt={timer.startedAt}
            onLocalStart={timer.start}
            onLocalStop={timer.reset}
            pausedAt={timer.pausedAt}
            pausedMs={timer.pausedMs}
            onPause={timer.pause}
            onResume={timer.resume}
            compact
          />
        </div>
      )}

      {/* One tab per attached form, then one per custom form section. */}
      <SchemaTabs
        schemas={schemas}
        activeKey={activeCustom ? activeKey : activeSchema?.schema_key}
        onSelect={(s) => handleTabSelect(s.schema_key)}
        extraTabs={customTabs}
        onSelectExtra={handleTabSelect}
      />

      {activeCustom
        ? customForms
            .filter(([methodId]) => methodId === activeCustom.methodId)
            .map(([methodId, schema]) => (
              <div key={methodId} className="pt-4">
                <CustomFormPanel
                  schema={schema}
                  values={customFormValues}
                  canEdit={canEdit && hasPermission('entity_record:write')}
                  activeSectionId={activeCustom.sectionId}
                  onChange={handleCustomFormChange}
                />
              </div>
            ))
        : null}

      {activeCustom ? null : canEdit ? (
        <FormTabEditor
          error={error}
          hasForms={allFormFields.length > 0 || schemasAuthoritative}
          activeFormFields={activeFormFields}
          editData={computedEditData}
          onFieldChange={handleFieldChange}
          entityType={entityType}
          entityId={entity.entity_id}
          timerCanStop={timerCanStop}
          timerStopBlockedHint="Fill in every required field before stopping the timer."
          onTimerStopped={handleTimerStopped}
          fieldsLocked={Boolean(primaryTimerField?.required) && (!timer.isActive || timer.isPaused)}
          fieldsLockedHint={timer.isPaused
            ? `${primaryTimerField?.label ?? 'The timer'} is paused. Resume it to carry on editing.`
            : `Start ${primaryTimerField?.label ?? 'the timer'} to edit this record.`}
          fallbackFields={flatEntries.filter(([key]) => canEditField(entityType, key))}
          fallbackDrafts={fallbackDrafts}
          onFallbackChange={handleFallbackChange}
        />
      ) : (
        <FormTabViewer
          hasForms={schemas.length > 0 || schemasAuthoritative}
          activeViewFields={activeViewFields}
          flatEntries={flatEntries}
          entityData={entity.data}
          renderReadField={renderReadField}
        />
      )}
    </section>
  );
}
