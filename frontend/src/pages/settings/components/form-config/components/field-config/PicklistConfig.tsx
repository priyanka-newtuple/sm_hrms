/**
 * The picklist binding of a `select`, `multi_select` or `picklist_multi` field,
 * plus the "Extend Field" block a `picklist_multi` adds on top.
 *
 * Mounted through `FieldTypeConfig` by both configurators — Settings -> Forms
 * (`FieldRow`) and Settings -> Fields (`LibraryFieldEditor`) — so the two
 * surfaces bind picklists the same way.
 */

import type { FormField, Picklist } from '@/core/types';
import PicklistExtensionsEditor from '../PicklistExtensionsEditor';
import { CONFIG_INPUT_CLASS, CONFIG_LABEL_CLASS } from './styles';

type PicklistConfigProps = {
  field: FormField;
  picklists: Picklist[];
  canWrite: boolean;
  onChange: (patch: Partial<FormField>) => void;
};

/**
 * `enum_values` snapshots the option *labels* here, not the values, because
 * that is what the field editors have always written; `resolveFieldForSave`
 * re-reads the picklist and replaces them with values (and their labels) on
 * save. Kept verbatim so the drafts the editors hold are unchanged.
 */
function optionLabels(picklists: Picklist[], picklistId: string | undefined): string[] | undefined {
  if (!picklistId) return undefined;
  return picklists.find((picklist) => picklist.id === picklistId)?.options.map((option) => option.label);
}

export default function PicklistConfig({ field, picklists, canWrite, onChange }: PicklistConfigProps) {
  const picklistSelect = (
    value: string | undefined,
    placeholder: string,
    onSelect: (picklistId: string | undefined) => void,
  ) => (
    <select
      value={value || ''}
      onChange={(event) => onSelect(event.target.value || undefined)}
      disabled={!canWrite}
      className={CONFIG_INPUT_CLASS}
    >
      <option value="">{placeholder}</option>
      {picklists.map((picklist) => (
        <option key={picklist.id} value={picklist.id}>{picklist.name}</option>
      ))}
    </select>
  );

  if (field.type === 'select' || field.type === 'multi_select') {
    return (
      <div>
        <label className={CONFIG_LABEL_CLASS}>Picklist</label>
        {picklistSelect(field.picklist_id, 'Select a picklist...', (picklistId) =>
          onChange({
            picklist_id: picklistId,
            enum_values: optionLabels(picklists, picklistId) ?? field.enum_values ?? [],
          }),
        )}
      </div>
    );
  }

  if (field.type !== 'picklist_multi') return null;

  return (
    <>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className={CONFIG_LABEL_CLASS}>Dropdown picklist</label>
          {picklistSelect(field.picklist_id, 'Select...', (picklistId) =>
            onChange({
              picklist_id: picklistId,
              enum_values: optionLabels(picklists, picklistId) ?? [],
            }),
          )}
        </div>
        <div>
          <label className={CONFIG_LABEL_CLASS}>Multi-select picklist</label>
          {picklistSelect(field.picklist_id_2, 'Select...', (picklistId2) =>
            onChange({
              picklist_id_2: picklistId2,
              enum_values_2: optionLabels(picklists, picklistId2) ?? [],
            }),
          )}
        </div>
      </div>

      {/* Outside the Extend Field block on purpose: the wizard has these three
          steps whether or not any option reveals extra fields. */}
      <div className="rounded-xl border border-border bg-muted/20 p-3">
        <p className="text-sm font-medium text-foreground">Wizard wording</p>
        <p className="mt-0.5 mb-2 text-xs text-muted-foreground">
          Leave a box empty to keep the wording shown in it.
        </p>
        {stepCopyRows(field).map((step) => (
          <div key={step.number} className="mt-2 grid grid-cols-[auto_1fr_1.5fr] items-end gap-2">
            <span className="pb-2 text-xs font-semibold text-muted-foreground">
              {step.number}.
            </span>
            <StepCopyInput
              id={`step${step.number}-label`}
              label="Heading"
              value={step.label}
              fallback={step.labelFallback}
              canWrite={canWrite}
              onChange={(next) => onChange({ [`step${step.number}_label`]: next })}
            />
            <StepCopyInput
              id={`step${step.number}-description`}
              label="Description"
              value={step.description}
              fallback={step.descriptionFallback}
              canWrite={canWrite}
              onChange={(next) => onChange({ [`step${step.number}_description`]: next })}
            />
          </div>
        ))}
      </div>

      <PicklistExtensionsEditor
        field={field}
        picklists={picklists}
        canWrite={canWrite}
        onChange={onChange}
      />
    </>
  );
}

/**
 * The wizard's three steps and the wording each falls back to, so the editor
 * can show the real default as a placeholder rather than describing it.
 * Fallbacks are duplicated from the step components on purpose — the component
 * is what renders, and a stale placeholder here is a cosmetic mismatch rather
 * than a wrong form.
 */
function stepCopyRows(field: FormField) {
  return [
    {
      number: 1 as const,
      label: field.step1_label ?? '',
      description: field.step1_description ?? '',
      labelFallback: `Choose ${field.label || 'options'}`,
      descriptionFallback: 'Search and select every option that applies.',
    },
    {
      number: 2 as const,
      label: field.step2_label ?? '',
      description: field.step2_description ?? '',
      labelFallback: 'Choose items to apply to all',
      descriptionFallback:
        'Every option from step 1 starts with all of these ticked. Fine-tune per card in step 3.',
    },
    {
      number: 3 as const,
      label: field.step3_label ?? '',
      description: field.step3_description ?? '',
      labelFallback: `Assign items per ${field.label || 'option'} (optional)`,
      descriptionFallback: 'Pick a card on the left, then check items on the right.',
    },
  ];
}

type StepCopyInputProps = {
  id: string;
  label: string;
  value: string;
  /** What the wizard renders when this is blank. */
  fallback: string;
  canWrite: boolean;
  onChange: (next: string | undefined) => void;
};

/**
 * One piece of a step's wording. The step number is not editable — it is the
 * wizard's own structure — so the placeholder carries only the wording, which
 * is exactly what an empty box falls back to.
 */
function StepCopyInput({ id, label, value, fallback, canWrite, onChange }: StepCopyInputProps) {
  return (
    <div className="min-w-0">
      <label className={CONFIG_LABEL_CLASS} htmlFor={id}>
        {label}
      </label>
      <input
        id={id}
        type="text"
        value={value}
        maxLength={STEP_COPY_MAX_LENGTH}
        disabled={!canWrite}
        placeholder={fallback}
        // Not trimmed here: a controlled input that trims on every keystroke
        // eats the space before the next word. `pickWizardCopy` trims on the way
        // out, and the engine drops a blank on the way in.
        onChange={(event) => onChange(event.target.value || undefined)}
        className={CONFIG_INPUT_CLASS}
      />
    </div>
  );
}

/** Mirrors `PICKLIST_MULTI_COPY_MAX_LENGTH` (workflow/models/interface.py). */
const STEP_COPY_MAX_LENGTH = 200;
