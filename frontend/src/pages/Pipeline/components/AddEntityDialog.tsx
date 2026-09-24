import { useEffect, useMemo, useState } from 'react';
import { AlertCircle, CalendarDays, Check, X } from 'lucide-react';
import { workflowEntities, entityTypes } from '../../../core/services/api';
import type { FormField, FormSchema, StateMachineRecord } from '../../../core/types';
import { Button } from '@/components/ui/button';
import { usePermissions } from '@/core/hooks/usePermissions';
import { useFeatureFlags } from '@/core/hooks/useFeatureFlags';
import { useSourcePickers } from '@/core/hooks/useSourcePickers';
import { useDocumentUploadEntity } from '@/core/hooks/useDocumentUploadEntity';
import SourceLinkFields from '@/core/components/SourceLinkFields';
import TimerDurationField from '@/core/components/TimerDurationField';
import { useRecordTimer } from '@/shared/hooks/useRecordTimer';
import { SchemaStepper, SchemaReviewStep } from '@/core/components';
import CreateEntityDocumentUpload from '@/core/components/CreateEntityDocumentUpload';
import {
  getFormFields,
  getEnterableFields,
  getCalculatedFields,
  buildDefaultFormDataForSchemas,
  isMissingRequiredFieldValue,
  validateFieldValue,
  buildCompleteSchemaFieldsForSchemas,
  pickEnterableData,
  collectTimerFields,
  withoutTimerFields,
  IDENTIFIER_FIELD,
  IDENTIFIER_FIELD_KEY,
} from '../../../shared/utils/entityForm';
import { useIdentifierConfig } from '@/shared/hooks/useIdentifierConfig';
import { applyCalculations } from '@/shared/utils/calc';
import EntityFormFields from '@/pages/records/detail/components/EntityFormFields';

interface Props {
  open: boolean;
  onClose: () => void;
  workflow: StateMachineRecord;
  /** All forms attached to the entity type; each renders as its own tab. */
  schemas: FormSchema[];
  schemasLoading?: boolean;
  schemasError?: string | null;
  onCreated: () => void;
}

/** Index of the first form whose fields include the given field id. */
function tabIndexForField(schemas: FormSchema[], fieldId: string): number {
  const idx = schemas.findIndex((s) => getFormFields(s).some((f) => f.id === fieldId));
  return idx < 0 ? 0 : idx;
}

export default function AddEntityDialog({
  open,
  onClose,
  workflow,
  schemas,
  schemasLoading = false,
  schemasError = null,
  onCreated,
}: Props) {
  const [formData, setFormData] = useState<Record<string, unknown>>(() =>
    buildDefaultFormDataForSchemas(schemas)
  );
  const [dueDate, setDueDate] = useState('');
  const [activeTab, setActiveTab] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [errorsSeq, setErrorsSeq] = useState(0);
  // Held here rather than in the field so the run survives leaving a step: on
  // a multi-step form each step unmounts as you move on, and the timer has to
  // keep running across all of them.
  const timer = useRecordTimer();
  // Every validation round goes through here so EntityFormFields can scroll to the
  // first offender exactly once per round — even a round reporting fewer errors
  // than the last one.
  const failValidation = (errs: Record<string, string>) => {
    setFieldErrors(errs);
    setErrorsSeq((n) => n + 1);
  };
  // Set once a document-upload has had the agent create the entity for us — from then
  // on, Save updates that entity instead of creating a second one.
  const {
    entityId: createdEntityId,
    handleEntityCreated: handleEntityCreatedFromUpload,
    reset: resetCreatedEntityId,
  } = useDocumentUploadEntity({
    resolveMachineName: () => workflow.machine_name,
    setFormData,
    setError,
    describeEnrollError: (message) =>
      `Entity created, but could not be added to this board: ${message}. It's visible on the Records page.`,
  });
  const { filterVisibleFields, filterEditablePayload } = usePermissions();
  const { hideDueDate } = useFeatureFlags();
  const sourceLinks = useSourcePickers();
  const {
    templateMode,
    label: identifierLabel,
    requiredMessage: identifierRequiredMessage,
  } = useIdentifierConfig(workflow.entity_type);
  const identifierField = useMemo(
    () => ({ ...IDENTIFIER_FIELD, label: identifierLabel }),
    [identifierLabel]
  );

  // Forms load asynchronously, so seed defaults for any fields not yet present
  // once they arrive — without clobbering values the user has already entered.
  useEffect(() => {
    setFormData((prev) => ({ ...buildDefaultFormDataForSchemas(schemas), ...prev }));
  }, [schemas]);

  // Fetch next auto_number preview values on open so the user sees the real format.
  useEffect(() => {
    if (!open || !schemas.length) return;
    entityTypes.getAutoNumberPreviews(schemas[0].entity_type)
      .then((previews) => setFormData((prev) => ({ ...prev, ...previews })))
      .catch(() => {});
  }, [open, schemas]);

  // Load one link picker per relation declaration targeting this entity type.
  const sourceLinksLoad = sourceLinks.load;
  useEffect(() => {
    if (!open) return;
    void sourceLinksLoad(workflow.entity_type);
  }, [open, workflow.entity_type, sourceLinksLoad]);

  if (!open) return null;

  const hasSchemas = schemas.length > 0;
  const isMultiStep = schemas.length > 1;
  const isReview = isMultiStep && activeTab >= schemas.length;
  const activeSchema = isReview ? null : (schemas[activeTab] ?? schemas[0] ?? null);
  // Timers render once at record level (below), never inside a step.
  const activeFields = withoutTimerFields(getFormFields(activeSchema));
  // Fields the current role may view: active tab drives the empty-state, the
  // union across every tab drives validation so hidden fields never block submit.
  const activeVisibleFields = activeSchema
    ? filterVisibleFields(activeSchema.entity_type, getEnterableFields(activeSchema))
    : [];
  const visibleFields = schemas.flatMap((s) => filterVisibleFields(s.entity_type, getEnterableFields(s)));
  const displayEntityType = workflow.entity_type.replace(/^ATS\./i, '').trim();
  // Calc fields/columns update live from the raw entered values; kept separate
  // from `formData` so the raw, editable state is untouched (backend recomputes
  // authoritatively on submit regardless). Must include calc fields themselves
  // (excluded from `visibleFields`/enterable, but still rendered) or their
  // computed value never gets filled in — see `activeFields` below, which is
  // what's actually rendered.
  const calcInputFields = schemas.flatMap((s) =>
    filterVisibleFields(s.entity_type, [...getEnterableFields(s), ...getCalculatedFields(s)])
  );
  const computedValues = applyCalculations(calcInputFields, formData);

  const reset = () => {
    setFormData(buildDefaultFormDataForSchemas(schemas));
    setDueDate('');
    setActiveTab(0);
    setError(null);
    setFieldErrors({});
    timer.reset();
    resetCreatedEntityId();
    sourceLinks.reset();
  };

  // A timer measures the work of filling this form in, so it cannot stop until
  // that work is done. Computed over the union across *every* step, not just
  // the visible one — a timer on step 1 still has to wait for step 3.
  // `getEnterableFields` deliberately excludes timers because they are not
  // typed values. Collect them from the full visible schema instead, otherwise
  // the first-time Add dialog has no timer strip to Start.
  const timerFields = collectTimerFields(
    schemas.flatMap((schema) => filterVisibleFields(schema.entity_type, getFormFields(schema))),
  );
  const timerCanStop =
    timerFields.length === 0 ||
    (visibleFields.every(
      (f) => f.type === 'timer_duration' || !isMissingRequiredFieldValue(f, formData[f.id]),
    ) &&
      (templateMode || String(formData[IDENTIFIER_FIELD_KEY] ?? '').trim().length > 0));
  const timerStopBlockedHint = isMultiStep
    ? 'Fill in every required field, across all steps, before stopping the timer.'
    : 'Fill in every required field before stopping the timer.';

  // The timer that is currently running, if any: one that has been started and
  // has not yet recorded a value. Only one can run at a time, since a started
  // run is only stoppable into its own field.
  // The timer that is operated. Any others describe the same run and just
  // mirror its value, so only this one is rendered and started/stopped.
  const primaryTimerField = timerFields[0] ?? null;
  const timerRequiresStart = Boolean(primaryTimerField?.required);

  /** One elapsed value written to every timer field, so forms that each
   *  declare one all agree rather than holding times a second apart. */
  const recordTimerValue = (seconds: unknown) => {
    if (typeof seconds !== 'number') return;
    setFormData((prev) => {
      const next = { ...prev };
      for (const field of timerFields) next[field.id] = seconds;
      return next;
    });
    setFieldErrors((prev) => {
      const next = { ...prev };
      for (const field of timerFields) delete next[field.id];
      return next;
    });
  };

  const resetAndClose = () => {
    reset();
    onClose();
  };

  const handleClose = async () => {
    // A document upload can create the entity before this dialog is submitted.
    // Preserve a locally-running timer on that existing record before closing.
    if (createdEntityId && primaryTimerField) {
      const storedSeconds = formData[primaryTimerField.id];
      const baseSeconds =
        typeof storedSeconds === 'number'
          ? Math.max(0, Math.floor(storedSeconds))
          : 0;
      const elapsedSeconds =
        timer.startedAt !== null
          ? timer.recordedSeconds(baseSeconds)
          : typeof storedSeconds === 'number'
            ? baseSeconds
            : null;
      if (elapsedSeconds === null) {
        resetAndClose();
        return;
      }
      try {
        setSubmitting(true);
        setError(null);
        await workflowEntities.update(createdEntityId, {
          data: Object.fromEntries(timerFields.map((field) => [field.id, elapsedSeconds])),
        });
        onCreated();
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to save timer before closing');
        return;
      } finally {
        setSubmitting(false);
      }
    }
    resetAndClose();
  };

  const failOnField = (field: FormField, message: string) => {
    setActiveTab(tabIndexForField(schemas, field.id));
    failValidation({ [field.id]: message });
  };

  // Validate every visible field on the current step, collecting one message
  // per offending field. Returns false if any field is invalid.
  const validateActiveStep = (): boolean => {
    const errs: Record<string, string> = {};
    // The identifier renders on step 0 outside the schema fields, so it needs its
    // own check — Next must not skip past a blank one. In templateMode it is
    // auto-generated and never rendered, so there is nothing to require.
    if (activeTab === 0 && !templateMode && !String(formData[IDENTIFIER_FIELD_KEY] ?? '').trim()) {
      errs[IDENTIFIER_FIELD_KEY] = identifierRequiredMessage;
    }
    for (const f of activeVisibleFields) {
      if (isMissingRequiredFieldValue(f, formData[f.id])) {
        errs[f.id] = `${f.label} is required`;
        continue;
      }
      const msg = validateFieldValue(f, formData[f.id]);
      if (msg) errs[f.id] = msg;
    }
    failValidation(errs);
    return Object.keys(errs).length === 0;
  };

  // Check if all required fields are filled (used to enable/disable submit button).
  // A blank identifier is deliberately NOT gated here: disabling Save would leave the
  // user with no explanation, so handleSubmit lets it through and reports the
  // configured message inline on the field instead.
  const canSubmit = (() => {
    if (schemasLoading || schemasError) return false;
    if (sourceLinks.missingRequired) return false;
    const missingField = visibleFields.find((f) => isMissingRequiredFieldValue(f, formData[f.id]));
    return !missingField;
  })();

  const goToTab = (index: number) => {
    // Forward moves — stepper header or Next — must clear the current step's
    // validation; going back is always allowed so nothing gets trapped.
    // ponytail: validates only the step being left, not every step in between on
    // a multi-step jump; handleSubmit/canSubmit still gate the rest.
    if (index > activeTab && !validateActiveStep()) return;
    setError(null);
    setFieldErrors({});
    setActiveTab(index);
  };

  const handleNext = () => goToTab(activeTab + 1);

  const handleFieldChange = (id: string, value: unknown) => {
    setFormData((prev) => ({ ...prev, [id]: value }));
    setFieldErrors((prev) => {
      if (!prev[id]) return prev;
      const next = { ...prev };
      delete next[id];
      return next;
    });
  };

  const handleSubmit = async () => {
    // Every REFERENCE (live link) declaration requires a linked source record.
    if (sourceLinks.missingRequired) {
      setActiveTab(0);
      setError(`Link a ${sourceLinks.missingRequired.providerName} record before creating`);
      return;
    }

    // The unique identifier lives on the first tab and is always required.
    if (!templateMode && !String(formData[IDENTIFIER_FIELD_KEY] ?? '').trim()) {
      setActiveTab(0);
      failValidation({ [IDENTIFIER_FIELD_KEY]: identifierRequiredMessage });
      return;
    }

    // Validate every viewable field across all tabs, not just the active one.
    const missingField = visibleFields.find((f) => isMissingRequiredFieldValue(f, formData[f.id]));
    if (missingField) {
      failOnField(missingField, `${missingField.label} is required`);
      return;
    }

    const invalidField = visibleFields.find((f) => validateFieldValue(f, formData[f.id]));
    if (invalidField) {
      failOnField(invalidField, validateFieldValue(invalidField, formData[invalidField.id])!);
      return;
    }

    try {
      setSubmitting(true);
      setError(null);
      // Merge identifier explicitly so the permission filter can't strip it — skipped
      // entirely in templateMode, where this entity type has no identifier field.
      const editableData = filterEditablePayload(
        workflow.entity_type,
        pickEnterableData(schemas, computedValues),
      );
      if (templateMode) delete editableData[IDENTIFIER_FIELD_KEY];
      // A pre-create timer is local until this record has an id. Capture its
      // cumulative value in the normal save payload before closing resets it.
      const baseSeconds =
        primaryTimerField && typeof formData[primaryTimerField.id] === 'number'
          ? Number(formData[primaryTimerField.id])
          : 0;
      const recordedTimerSeconds =
        timer.startedAt !== null
          ? timer.recordedSeconds(baseSeconds)
          : primaryTimerField && typeof formData[primaryTimerField.id] === 'number'
            ? baseSeconds
            : null;
      const timerData =
        recordedTimerSeconds === null
          ? {}
          : Object.fromEntries(timerFields.map((field) => [field.id, recordedTimerSeconds]));
      const payloadData = {
        ...editableData,
        ...timerData,
        ...(!templateMode
          ? { [IDENTIFIER_FIELD_KEY]: String(formData[IDENTIFIER_FIELD_KEY] ?? '').trim() }
          : {}),
      };
      await (createdEntityId
        ? workflowEntities.update(createdEntityId, {
            data: payloadData,
            ...(!hideDueDate && dueDate ? { due_date: dueDate } : {}),
            schema_fields: buildCompleteSchemaFieldsForSchemas(schemas),
            ...(sourceLinks.sourceEntityIds.length
              ? { source_entity_ids: sourceLinks.sourceEntityIds }
              : {}),
          })
        : workflowEntities.create({
            entity_type: workflow.entity_type,
            machine_name: workflow.machine_name,
            data: payloadData,
            ...(!hideDueDate && dueDate ? { due_date: dueDate } : {}),
            schema_fields: buildCompleteSchemaFieldsForSchemas(schemas),
            ...(sourceLinks.sourceEntityIds.length
              ? { source_entity_ids: sourceLinks.sourceEntityIds }
              : {}),
          }));
      onCreated();
      resetAndClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create entity');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/45 p-4 backdrop-blur-sm">
      {/* role/aria-modal are what scopes EntityFormFields' error scroll to this dialog. */}
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="add-entity-dialog-title"
        className="flex h-[92vh] w-full max-w-5xl flex-col rounded-3xl bg-card p-2.5 shadow-2xl"
      >
       <div className="flex h-full w-full flex-col overflow-hidden rounded-2xl border border-border bg-card text-card-foreground">
        {/* Header */}
        <div className="flex flex-shrink-0 items-center justify-between border-b border-border bg-[var(--modal-header-background)] px-8 py-9 text-[var(--modal-header-foreground)]">
          <h3 id="add-entity-dialog-title" className="text-xl font-medium">
            {workflow.name} – {displayEntityType}
          </h3>
          <Button
            onClick={() => void handleClose()}
            variant="ghost"
            size="icon-lg"
            className="rounded-full opacity-70 hover:bg-current/10 hover:opacity-100"
          >
            <X className="w-6 h-6" />
          </Button>
        </div>

        {/* The record-level timer remains visible above every step. */}
        {primaryTimerField && (
          <div className="flex-shrink-0 border-b border-border px-8 py-2.5">
            <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              {primaryTimerField.label}
              {timerFields.length > 1 && (
                <span className="ml-1 font-normal">
                  · recorded on {timerFields.length} forms
                </span>
              )}
            </p>
            <TimerDurationField
              fieldKey={primaryTimerField.id}
              value={formData[primaryTimerField.id]}
              onChange={recordTimerValue}
              canStop={timerCanStop}
              stopBlockedHint={timerStopBlockedHint}
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

        <SchemaStepper
          schemas={schemas}
          activeIndex={activeTab}
          showReview={isMultiStep}
          onSelect={goToTab}
        />

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-8 py-6">
          {error && (
            <div className="mb-4 flex items-center gap-2 rounded-lg border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              {error}
            </div>
          )}

          {isReview ? (
            <SchemaReviewStep
              schemas={schemas}
              values={computedValues}
              onEdit={(i) => setActiveTab(i)}
            />
          ) : (
            <div className="space-y-8">
              {/* Unique identifier — always shown on the first step, bypassing
                  field permissions since it is a synthetic required field. */}
              {activeTab === 0 && (
                <>
                  {!templateMode && (
                    <EntityFormFields
                      fields={[identifierField]}
                      values={formData}
                      onChange={handleFieldChange}
                      errors={fieldErrors}
                      errorsSeq={errorsSeq}
                    />
                  )}
                  <SourceLinkFields
                    pickers={sourceLinks.pickers}
                    selections={sourceLinks.selections}
                    onChange={sourceLinks.setSelection}
                  />
                  {!hideDueDate && (
                    <div>
                      <label htmlFor="new-entity-due-date" className="mb-1.5 block text-sm font-medium text-foreground">
                        Due date
                      </label>
                      <div className="relative max-w-xs">
                        <CalendarDays className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                        <input
                          id="new-entity-due-date"
                          type="date"
                          value={dueDate}
                          onChange={(event) => setDueDate(event.target.value)}
                          className="h-10 w-full rounded-md border border-border bg-background pl-9 pr-3 text-sm text-foreground outline-none focus:ring-2 focus:ring-primary/25"
                        />
                      </div>
                      <p className="mt-1 text-xs text-muted-foreground">Optional. Independent of workflow stage and SLA.</p>
                    </div>
                  )}
                </>
              )}
              {schemasLoading ? (
                <p className="text-sm text-muted-foreground">Loading form configuration…</p>
              ) : schemasError ? (
                <p className="text-sm text-destructive">
                  Form configuration could not be loaded. Refresh the page to retry.
                </p>
              ) : hasSchemas ? (
                <EntityFormFields
                  fields={activeFields}
                  values={computedValues}
                  onChange={handleFieldChange}
                  entityType={activeSchema?.entity_type}
                  emptyMessage='No fields to fill in. Click "Next" to continue.'
                  errors={fieldErrors}
                  errorsSeq={errorsSeq}
                  fieldsLocked={timerRequiresStart && (!timer.isActive || timer.isPaused)}
                  fieldsLockedHint={timer.isPaused
                    ? `${primaryTimerField?.label ?? 'The timer'} is paused. Resume it to carry on filling this form in.`
                    : `Start ${primaryTimerField?.label ?? 'the timer'} to fill this form.`}
                />
              ) : (
                <p className="text-sm text-muted-foreground">
                  No form is configured. This record will contain only its base details.
                </p>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex flex-shrink-0 items-center justify-end gap-3 border-t border-border bg-muted/30 px-8 py-5">
          {activeTab > 0 ? (
            <Button variant="ghost" size="lg" onClick={() => goToTab(activeTab - 1)}>
              Back
            </Button>
          ) : (
            <Button variant="ghost" size="lg" onClick={() => void handleClose()}>
              Cancel
            </Button>
          )}
          <CreateEntityDocumentUpload
            entityType={workflow.entity_type}
            disabled={!!createdEntityId || submitting}
            onEntityCreated={handleEntityCreatedFromUpload}
          />
          {!isReview && isMultiStep && activeTab < schemas.length - 1 && (
            <Button variant="primary" size="lg" onClick={handleNext}>
              Next
            </Button>
          )}
          <Button
            variant="primary"
            size="lg"
            onClick={handleSubmit}
            disabled={!canSubmit}
            loading={submitting}
            icon={!submitting ? <Check className="w-4 h-4" /> : undefined}
          >
            Save
          </Button>
        </div>
       </div>
      </div>
    </div>
  );
}
