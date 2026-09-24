import { useEffect, useRef, useState } from 'react';
import type { FormField } from '../../../../core/types';
import { FieldInput } from '@/core/components';
import { usePermissions } from '@/core/hooks/usePermissions';
import MaskedValue from '@/core/components/MaskedValue';
import DocumentFieldDisplay from '@/core/components/DocumentFieldDisplay';
import { cn } from '@/lib/utils';
import {
  formatEntityFieldDisplayValue,
  getEntityTableDisplayColumns,
  getEntityTableDisplayRows,
} from '@/shared/utils/entityDisplay';
import { humanize } from '@/shared/utils/labels';

interface EntityFormFieldsProps {
  fields: FormField[];
  values: Record<string, unknown>;
  onChange: (id: string, value: unknown) => void;
  emptyMessage?: string;
  entityType?: string;
  /** The record being edited, so document uploads can be owned by it and a
   *  timer_duration field can persist its completed value. */
  entityId?: string;
  mode?: 'edit' | 'view';
  compact?: boolean;
  /** Per-field validation messages keyed by field id; renders red border + message. */
  errors?: Record<string, string>;
  /**
   * Bumped once per validation round. Scrolling keys off this, not off `errors`:
   * a round can report *fewer* errors than the last one (a submit guard that
   * reports only the first offender) and must still scroll, while clearing an
   * error by typing must not.
   */
  errorsSeq?: number;
  /** The pipeline slide-over provides the shared file preview panel. */
  documentPreviewEnabled?: boolean;
  /**
   * timer_duration support. Deliberately passed in rather than derived here:
   * this component renders one step's fields, so it cannot see whether the
   * rest of a multi-step form is filled, and cannot hold a start instant that
   * survives leaving the step. Both belong to the container.
   */
  timerCanStop?: boolean;
  timerStopBlockedHint?: string;
  onTimerStopped?: (fieldId: string, elapsedSeconds: number) => void | Promise<void>;
  timerLocalStartedAt?: number | null;
  /** Which field the open local run belongs to, so a form with more than one
   *  timer never records an elapsed time into the wrong one. */
  timerLocalRunFieldId?: string | null;
  /** Disables every field with an explanation — used while a record-level
   *  timer is paused, so the run can't be paused while work continues. */
  fieldsLocked?: boolean;
  fieldsLockedHint?: string;
  onTimerLocalStart?: (fieldId: string) => void;
  onTimerLocalStop?: () => void;
}

export default function EntityFormFields({
  fields,
  values,
  onChange,
  emptyMessage,
  entityType,
  entityId,
  mode = 'edit',
  compact = false,
  errors,
  errorsSeq,
  documentPreviewEnabled = false,
  timerCanStop,
  timerStopBlockedHint,
  onTimerStopped,
  timerLocalStartedAt,
  timerLocalRunFieldId,
  fieldsLocked = false,
  fieldsLockedHint,
  onTimerLocalStart,
  onTimerLocalStop,
}: EntityFormFieldsProps) {
  const { canViewField, canEditField, shouldMaskField } = usePermissions();
  const [focusedFields, setFocusedFields] = useState<Set<string>>(new Set());
  const gridRef = useRef<HTMLDivElement>(null);
  const scrolledSeq = useRef(-1);

  // Long forms can push the offending field off-screen, so a failed Next/Save
  // looks like nothing happened — bring the first error into view once per
  // validation round.
  // Scanned in document order, not this instance's `fields`: one form can
  // render several EntityFormFields (the add-entity dialog splits the
  // identifier from the schema fields), and every instance must agree on the
  // topmost error or whichever effect runs last wins and scrolls past the
  // others. Scoped to the enclosing dialog so an unrelated form elsewhere in
  // the page (pipeline slide-over, bulk-import drafts) can't win the scan with
  // a same-named field.
  useEffect(() => {
    if (errorsSeq === undefined || errorsSeq === scrolledSeq.current) return;
    scrolledSeq.current = errorsSeq;
    if (!errors || Object.keys(errors).length === 0) return;
    const root = gridRef.current?.closest('[role="dialog"]') ?? document;
    const target = [...root.querySelectorAll<HTMLElement>('[data-field-id]')].find(
      (el) => el.dataset.fieldId && errors[el.dataset.fieldId],
    );
    target?.scrollIntoView({
      behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches
        ? 'auto'
        : 'smooth',
      block: 'center',
    });
  }, [errorsSeq, errors]);

  const setFocused = (id: string, on: boolean) =>
    setFocusedFields((prev) => {
      const next = new Set(prev);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });

  const hasValue = (id: string) => {
    const v = values[id];
    return v !== undefined && v !== null && v !== '';
  };

  const visibleFields = entityType
    ? fields.filter((f) => canViewField(entityType, f.id))
    : fields;

  if (visibleFields.length === 0 && emptyMessage) {
    return (
      <div className="py-6 text-center text-muted-foreground">
        <p className="text-sm text-muted-foreground/80">{emptyMessage}</p>
      </div>
    );
  }

  return (
    <div
      ref={gridRef}
      className={cn('grid grid-cols-2 items-start gap-x-4', compact ? 'gap-y-4' : 'gap-y-8')}
    >
      {fieldsLocked && fieldsLockedHint && (
        <p className="col-span-2 text-xs text-muted-foreground">{fieldsLockedHint}</p>
      )}
      {visibleFields.map((field) => {
        const masked = entityType ? shouldMaskField(entityType, field.id) : false;
        const editable = (!entityType || canEditField(entityType, field.id)) && !field.read_only;
        const isReadOnly = mode === 'view' || !editable;
        const fieldDisabled = isReadOnly || fieldsLocked;
        const isHalf = field.col_span === 'half' && field.type !== 'section';
        const fieldError = errors?.[field.id];
        // A field painted with its own background needs its label outside the
        // control, the way the text-area branch already renders one.
        const styledField = Boolean(field.style_config?.background_color);

        // A document field in view mode shows its files read-only; the
        // uploader itself is edit-only.
        if (field.type === 'document' && isReadOnly) {
          return (
            <div key={field.id} data-field-id={field.id} className="col-span-2">
              <div className="mb-2 flex items-center gap-1">
                <label className="text-sm font-medium text-foreground">{field.label}</label>
              </div>
              {masked ? (
                <div className="min-h-[42px] rounded-lg border border-border bg-card px-3 py-2.5 text-sm text-muted-foreground">
                  <MaskedValue />
                </div>
              ) : (
                <DocumentFieldDisplay
                  value={values[field.id]}
                  entityId={entityId}
                  showPreview={documentPreviewEnabled}
                />
              )}
            </div>
          );
        }

        if (field.type === 'reference') {
          const raw = values[field.id];
          const display = formatEntityFieldDisplayValue(raw);
          const inferredRows = getEntityTableDisplayRows(raw);
          const inferredColumns = inferredRows.length > 0 ? getEntityTableDisplayColumns(inferredRows) : [];
          return (
            <div key={field.id} data-field-id={field.id} className={cn(isHalf ? 'col-span-1' : 'col-span-2')}>
              <div className="relative">
                {masked ? (
                  <div className="min-h-[42px] rounded-lg border border-border bg-muted/50 px-3 py-2.5 text-sm text-foreground">
                    <MaskedValue />
                  </div>
                ) : inferredColumns.length > 0 ? (
                  <div className="overflow-x-auto rounded-lg border border-border bg-muted/50">
                    <table className="w-full min-w-[320px] table-fixed border-collapse text-sm">
                      <thead>
                        <tr className="bg-muted text-left text-xs font-semibold uppercase text-muted-foreground">
                          {inferredColumns.map((column) => (
                            <th key={column} className="w-56 border border-border px-3 py-2 whitespace-normal break-words">
                              {humanize(column)}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {inferredRows.map((row, index) => (
                          <tr key={String(row._row_id ?? index)}>
                            {inferredColumns.map((column) => (
                              <td key={column} className="w-56 border border-border px-3 py-2 align-top text-foreground whitespace-normal break-words">
                                {formatEntityFieldDisplayValue(row[column])}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="min-h-[42px] rounded-lg border border-border bg-muted/50 px-3 py-2.5 text-sm text-foreground">
                    {display}
                  </div>
                )}
                <label className="pointer-events-none absolute left-3 z-10 bg-card px-1 top-0 -translate-y-1/2 text-xs font-medium text-primary">
                  {field.label}
                </label>
              </div>
              <p className="mt-1 pl-4 text-xs text-muted-foreground">
                Inherited from {field.source_entity ?? 'related record'}
              </p>
            </div>
          );
        }

        if (field.type === 'boolean') {
          return (
            <div key={field.id} data-field-id={field.id} className={cn(isHalf ? 'col-span-1' : 'col-span-2')}>
              <div className="flex items-center gap-3">
                <FieldInput
                  entityId={entityId}
                  field={field}
                  value={values[field.id]}
                  onChange={(val) => onChange(field.id, val)}
                  disabled={fieldDisabled}
                  invalid={!!fieldError}
                />
                <label className={cn('text-sm font-medium', fieldError ? 'text-destructive' : 'text-foreground')}>
                  {field.label}
                  {field.required && <span className="ml-1 text-destructive">*</span>}
                </label>
              </div>
              {fieldError && <p role="alert" className="mt-1 text-xs text-destructive">{fieldError}</p>}
            </div>
          );
        }

        if (field.type === 'timer_duration') {
          return (
            <div key={field.id} data-field-id={field.id} className="col-span-2">
              <div className="mb-2 flex items-center gap-1">
                <label className={cn('text-sm font-medium', fieldError ? 'text-destructive' : 'text-foreground')}>
                  {field.label}
                  {field.required && <span className="ml-0.5 text-destructive">*</span>}
                </label>
              </div>
              {masked ? (
                <div className="min-h-[42px] rounded-lg border border-border bg-card px-3 py-2.5 text-sm text-muted-foreground">
                  <MaskedValue />
                </div>
              ) : (
                <FieldInput
                  field={field}
                  value={values[field.id]}
                  onChange={(val) => onChange(field.id, val)}
                  disabled={isReadOnly}
                  invalid={!!fieldError}
                  entityId={entityId}
                  timerCanStop={timerCanStop}
                  timerStopBlockedHint={timerStopBlockedHint}
                  onTimerStopped={
                    onTimerStopped ? (seconds) => onTimerStopped(field.id, seconds) : undefined
                  }
                  timerLocalStartedAt={
                    timerLocalRunFieldId === field.id ? timerLocalStartedAt : null
                  }
                  onTimerLocalStart={
                    onTimerLocalStart ? () => onTimerLocalStart(field.id) : undefined
                  }
                  onTimerLocalStop={onTimerLocalStop}
                />
              )}
              {fieldError && <p role="alert" className="mt-1 text-xs text-destructive">{fieldError}</p>}
            </div>
          );
        }

        // picklist_multi renders its own step headings (incl. the field label) —
        // no outer/floating label on top of it, except when masked (then FieldInput
        // never renders, so the wizard's heading never shows the field name).
        if (field.type === 'picklist_multi') {
          return (
            <div key={field.id} data-field-id={field.id} className="col-span-2">
              {masked ? (
                <>
                  <label className={cn('mb-2 block text-sm font-medium', fieldError ? 'text-destructive' : 'text-foreground')}>
                    {field.label}
                    {field.required && <span className="ml-1 text-destructive">*</span>}
                  </label>
                  <div className="min-h-[42px] rounded-lg border border-border bg-card px-3 py-2.5 text-sm text-muted-foreground">
                    <MaskedValue />
                  </div>
                </>
              ) : (
                <FieldInput
                  entityId={entityId}
                  field={field}
                  value={values[field.id]}
                  onChange={(val) => onChange(field.id, val)}
                  disabled={fieldDisabled}
                  invalid={!!fieldError}
                  documentPreviewEnabled={documentPreviewEnabled}
                />
              )}
              {fieldError && <p role="alert" className="mt-1 text-xs text-destructive">{fieldError}</p>}
            </div>
          );
        }

        const alwaysFloated = field.type === 'date' || field.type === 'datetime';
        const isFloated = alwaysFloated || masked || focusedFields.has(field.id) || hasValue(field.id);
        const fieldWithoutPlaceholder: FormField = { ...field, placeholder: undefined };

        // Full width with the label above, like table/textarea: the uploader is
        // a block, and the default branch's floating label would sit on top of it.
        if (field.type === 'document') {
          return (
            <div key={field.id} data-field-id={field.id} className="col-span-2">
              <div className="mb-2 flex items-center gap-1">
                <label className={cn('text-sm font-medium', fieldError ? 'text-destructive' : 'text-foreground')}>
                  {field.label}
                  {field.required && <span className="ml-0.5 text-destructive">*</span>}
                </label>
              </div>
              {masked ? (
                <div className="min-h-[42px] rounded-lg border border-border bg-card px-3 py-2.5 text-sm text-muted-foreground">
                  <MaskedValue />
                </div>
              ) : (
                <FieldInput
                  entityId={entityId}
                  field={field}
                  value={values[field.id]}
                  onChange={(val) => onChange(field.id, val)}
                  disabled={isReadOnly}
                  invalid={!!fieldError}
                  documentPreviewEnabled={documentPreviewEnabled}
                />
              )}
              {field.placeholder && !fieldError && (
                <p className="mt-1 text-xs text-muted-foreground">{field.placeholder}</p>
              )}
              {fieldError && <p role="alert" className="mt-1 text-xs text-destructive">{fieldError}</p>}
            </div>
          );
        }

        if (field.type === 'table') {
          return (
            <div key={field.id} data-field-id={field.id} className="col-span-2">
              <div className="mb-2 flex items-center gap-1">
                <label className={cn('text-sm font-medium', fieldError ? 'text-destructive' : 'text-foreground')}>
                  {field.label}
                  {field.required && <span className="ml-0.5 text-destructive">*</span>}
                </label>
              </div>
              {masked ? (
                <div className="min-h-[42px] rounded-lg border border-border bg-card px-3 py-2.5 text-sm text-muted-foreground">
                  <MaskedValue />
                </div>
              ) : (
                <FieldInput
                  entityId={entityId}
                  field={field}
                  value={values[field.id]}
                  onChange={(val) => onChange(field.id, val)}
                  disabled={fieldDisabled}
                  invalid={!!fieldError}
                />
              )}
              {field.placeholder && (
                <p className={cn('mt-1 text-xs', fieldError ? 'text-destructive' : 'text-muted-foreground')}>
                  {field.placeholder}
                </p>
              )}
              {fieldError && <p role="alert" className="mt-1 text-xs text-destructive">{fieldError}</p>}
            </div>
          );
        }

        if (field.type === 'textarea') {
          return (
            <div
              key={field.id}
              data-field-id={field.id}
              className="col-span-2"
            >
              <div className="mb-2 flex items-center gap-1">
                <label className={cn('text-sm font-medium', fieldError ? 'text-destructive' : 'text-foreground')}>
                  {field.label}
                  {field.required && <span className="ml-0.5 text-destructive">*</span>}
                </label>
              </div>
              {masked ? (
                <div className="min-h-[220px] rounded-lg border border-border bg-card px-3 py-2.5 text-sm text-muted-foreground">
                  <MaskedValue />
                </div>
              ) : (
                <FieldInput
                  entityId={entityId}
                  field={fieldWithoutPlaceholder}
                  value={values[field.id]}
                  onChange={(val) => onChange(field.id, val)}
                  disabled={fieldDisabled}
                  invalid={!!fieldError}
                />
              )}
              {fieldError ? (
                <p role="alert" className="mt-1 text-xs text-destructive">{fieldError}</p>
              ) : (
                field.placeholder && (
                  <p className="mt-1 text-xs text-muted-foreground">{field.placeholder}</p>
                )
              )}
            </div>
          );
        }

        return (
          <div
            key={field.id}
            data-field-id={field.id}
            className={cn(isHalf ? 'col-span-1' : 'col-span-2')}
            onFocusCapture={() => setFocused(field.id, true)}
            onBlurCapture={() => setFocused(field.id, false)}
          >
            {/* A coloured field takes the text-area treatment: a plain label
                above the control. The floating label would otherwise sit on
                top of the colour, where no background reads well. */}
            {styledField && (
              <div className="mb-2 flex items-center gap-1">
                <label className={cn('text-sm font-medium', fieldError ? 'text-destructive' : 'text-foreground')}>
                  {field.label}
                  {field.required && <span className="ml-0.5 text-destructive">*</span>}
                </label>
              </div>
            )}
            {/* Input + floating label wrapper — isolated so top-1/2 is relative to input height only */}
            <div className="relative">
              {masked ? (
                <div className="min-h-[42px] rounded-lg border border-border bg-card px-3 py-2.5 text-sm text-muted-foreground">
                  <MaskedValue />
                </div>
              ) : (
                <FieldInput
                  entityId={entityId}
                  field={fieldWithoutPlaceholder}
                  value={values[field.id]}
                  onChange={(val) => onChange(field.id, val)}
                  disabled={fieldDisabled}
                  invalid={!!fieldError}
                />
              )}
              {!styledField && (
                <label
                  className={cn(
                    'pointer-events-none absolute left-3 z-10 bg-card px-1 transition-all duration-200',
                    isFloated
                      ? cn('top-0 -translate-y-1/2 text-xs font-medium', fieldError ? 'text-destructive' : 'text-primary')
                      : cn('top-1/2 -translate-y-1/2 text-sm', fieldError ? 'text-destructive' : 'text-muted-foreground'),
                  )}
                >
                  {field.label}
                  {field.required && <span className="ml-0.5 text-destructive">*</span>}
                </label>
              )}
            </div>
            {/* Error replaces the helper text so a single line sits under the input. */}
            {fieldError ? (
              <p role="alert" className="mt-1 pl-4 text-xs text-destructive">{fieldError}</p>
            ) : (
              field.placeholder && (
                <p className="mt-1 pl-4 text-xs text-muted-foreground">{field.placeholder}</p>
              )
            )}
          </div>
        );
      })}
    </div>
  );
}
