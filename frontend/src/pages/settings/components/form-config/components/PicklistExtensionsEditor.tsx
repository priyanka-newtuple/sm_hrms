/**
 * PicklistExtensionsEditor
 *
 * The "Extend Field" block of the picklist_multi configuration: per option of
 * the second (multi-select) picklist, which Field Library fields that option
 * reveals once an end user selects it.
 *
 * Mounted through `FieldTypeConfig` by both configurators — Settings -> Forms
 * (`FieldRow`) and Settings -> Fields (`LibraryFieldEditor`) — so the two
 * surfaces cannot drift.
 *
 * The exported component is state and composition; the header, the option list
 * and one option's row are separate components below it.
 *
 * Options are read live from the picklist rather than from the field's
 * `enum_values_2` snapshot, because the snapshot is only refreshed by
 * `resolveFieldForSave` when the field is saved, and extension keys must always
 * be option *values*.
 */

import { useState } from 'react';
import { Plus, X } from 'lucide-react';
import { Switch } from '@/components/ui/switch';
import type { ExtensionField, FormField, Picklist, PicklistOption } from '@/core/types';
import { FIELD_TYPE_LABELS } from '../constants';
import ExtensionFieldPickerModal from './ExtensionFieldPickerModal';
import { extensionWording } from '@/core/components/picklist-multi/extensionWording';
import { CONFIG_INPUT_CLASS, CONFIG_LABEL_CLASS } from './field-config/styles';

type Extensions = NonNullable<FormField['extensions']>;

type PicklistExtensionsEditorProps = {
  field: FormField;
  picklists: Picklist[];
  canWrite: boolean;
  /** A patch, so the label can change without touching the option config. */
  onChange: (patch: Partial<Pick<FormField, 'extensions' | 'extension_label'>>) => void;
};

/** One option's fields replaced; an option that reveals nothing is stored as nothing. */
function withOptionFields(extensions: Extensions, optionValue: string, fields: ExtensionField[]): Extensions {
  const next = { ...extensions };
  if (fields.length > 0) next[optionValue] = { fields };
  else delete next[optionValue];
  return next;
}

/** Turning the toggle off throws the configuration away, so it asks first. */
function confirmDiscard(extensions: Extensions): boolean {
  const configured = Object.values(extensions).reduce((total, entry) => total + entry.fields.length, 0);
  if (configured === 0) return true;
  return window.confirm(
    `Turning Extend Field off discards ${configured} configured extended field(s). Continue?`,
  );
}

export default function PicklistExtensionsEditor({
  field, picklists, canWrite, onChange,
}: PicklistExtensionsEditorProps) {
  const [pickerOption, setPickerOption] = useState<PicklistOption | null>(null);
  const options = picklists.find((picklist) => picklist.id === field.picklist_id_2)?.options ?? [];
  const extensions = field.extensions;
  // Presence is the flag: `{}` is on-but-unconfigured, absent is off.
  const isOn = extensions !== undefined;

  const setOptionFields = (optionValue: string, fields: ExtensionField[]) =>
    onChange({ extensions: withOptionFields(extensions ?? {}, optionValue, fields) });

  const handleToggle = (checked: boolean) => {
    if (checked) onChange({ extensions: {} });
    else if (confirmDiscard(extensions ?? {})) {
      onChange({ extensions: undefined, extension_label: undefined });
    }
  };

  return (
    <div className="rounded-xl border border-border bg-muted/20 p-3">
      <ExtendFieldHeader
        isOn={isOn}
        canWrite={canWrite}
        hasOptionPicklist={Boolean(field.picklist_id_2)}
        onToggle={handleToggle}
      />

      {isOn && field.picklist_id_2 && (
        <ExtensionLabelInput
          value={field.extension_label ?? ''}
          canWrite={canWrite}
          // Untrimmed for the same reason as the step wording: trimming a
          // controlled input per keystroke makes a multi-word label untypeable.
          // `_optional_non_empty` blanks it server-side.
          onChange={(next) => onChange({ extension_label: next || undefined })}
        />
      )}

      {isOn && field.picklist_id_2 && (
        <OptionList
          options={options}
          extensions={extensions ?? {}}
          canWrite={canWrite}
          onSetOptionFields={setOptionFields}
          onAddFields={setPickerOption}
        />
      )}

      {pickerOption && (
        <OptionFieldPicker
          option={pickerOption}
          fields={extensions?.[pickerOption.value]?.fields ?? []}
          canWrite={canWrite}
          onSetOptionFields={setOptionFields}
          onClose={() => setPickerOption(null)}
        />
      )}
    </div>
  );
}

type OptionFieldPickerProps = {
  option: PicklistOption;
  fields: ExtensionField[];
  canWrite: boolean;
  onSetOptionFields: (optionValue: string, fields: ExtensionField[]) => void;
  onClose: () => void;
};

/** The picker for one option, appending its picks to what that option already has. */
function OptionFieldPicker({ option, fields, canWrite, onSetOptionFields, onClose }: OptionFieldPickerProps) {
  return (
    <ExtensionFieldPickerModal
      optionLabel={option.label || option.value}
      existingFields={fields}
      canWrite={canWrite}
      onAdd={(added) => onSetOptionFields(option.value, [...fields, ...added])}
      onClose={onClose}
    />
  );
}

type ExtendFieldHeaderProps = {
  isOn: boolean;
  canWrite: boolean;
  hasOptionPicklist: boolean;
  onToggle: (checked: boolean) => void;
};

function ExtendFieldHeader({ isOn, canWrite, hasOptionPicklist, onToggle }: ExtendFieldHeaderProps) {
  return (
    <>
      <div className="flex items-start justify-between gap-3">
        <div>
          <span className="text-sm font-medium text-foreground">Extend Field</span>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Reveal extra Field Library fields when a specific option is selected.
          </p>
        </div>
        <Switch
          checked={isOn}
          onCheckedChange={onToggle}
          disabled={!canWrite || !hasOptionPicklist}
          aria-label="Extend Field"
        />
      </div>

      {!hasOptionPicklist && (
        <p className="mt-2 text-xs text-muted-foreground">
          Choose a multi-select picklist first — its options are what get extended.
        </p>
      )}
    </>
  );
}

type OptionListProps = {
  options: PicklistOption[];
  extensions: Extensions;
  canWrite: boolean;
  onSetOptionFields: (optionValue: string, fields: ExtensionField[]) => void;
  onAddFields: (option: PicklistOption) => void;
};

function OptionList({ options, extensions, canWrite, onSetOptionFields, onAddFields }: OptionListProps) {
  if (options.length === 0) {
    return (
      <p className="mt-3 text-xs text-muted-foreground">
        The selected multi-select picklist has no options yet.
      </p>
    );
  }

  return (
    <div className="mt-3 space-y-1.5">
      {options.map((option) => {
        const fields = extensions[option.value]?.fields ?? [];
        return (
          <OptionRow
            key={option.value}
            option={option}
            fields={fields}
            canWrite={canWrite}
            onRemoveField={(fieldKey) =>
              onSetOptionFields(option.value, fields.filter((entry) => entry.id !== fieldKey))
            }
            onAddFields={() => onAddFields(option)}
          />
        );
      })}
    </div>
  );
}

type OptionRowProps = {
  option: PicklistOption;
  fields: ExtensionField[];
  canWrite: boolean;
  onRemoveField: (fieldKey: string) => void;
  onAddFields: () => void;
};

function OptionRow({ option, fields, canWrite, onRemoveField, onAddFields }: OptionRowProps) {
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-card px-3 py-2">
      <span className="min-w-[120px] text-sm font-medium text-foreground">
        {option.label || option.value}
      </span>
      {fields.length === 0 ? (
        <span className="text-xs text-muted-foreground">No extended fields</span>
      ) : (
        fields.map((field) => (
          <span
            key={field.id}
            title={`${field.label} — ${FIELD_TYPE_LABELS[field.type] ?? field.type}`}
            className="inline-flex items-center gap-1 rounded-full border border-border bg-muted/40 px-2.5 py-1 text-xs text-foreground"
          >
            {field.label}
            {field.required && <span className="text-destructive">*</span>}
            <button
              type="button"
              onClick={() => onRemoveField(field.id)}
              disabled={!canWrite}
              aria-label={`Remove ${field.label}`}
              className="text-muted-foreground transition-colors hover:text-destructive disabled:cursor-not-allowed disabled:opacity-50"
            >
              <X className="h-3 w-3" />
            </button>
          </span>
        ))
      )}
      <button
        type="button"
        onClick={onAddFields}
        disabled={!canWrite}
        className="ml-auto inline-flex items-center gap-1 rounded-lg border border-border px-2.5 py-1.5 text-xs font-medium text-cobalt transition-colors hover:border-cobalt/40 disabled:cursor-not-allowed disabled:opacity-50"
      >
        <Plus className="h-3.5 w-3.5" />
        Add fields
      </button>
    </div>
  );
}

type ExtensionLabelInputProps = {
  value: string;
  canWrite: boolean;
  onChange: (next: string) => void;
};

/**
 * Names what these fields collect, so the form says "Certificate required"
 * rather than the generic "Details required". The preview is live because the
 * short form is derived, not typed — seeing "Cert Req'd" beats reading a rule
 * about when a long word gets cut.
 */
function ExtensionLabelInput({ value, canWrite, onChange }: ExtensionLabelInputProps) {
  const wording = extensionWording(value);
  return (
    <div className="mt-3">
      <label className={CONFIG_LABEL_CLASS} htmlFor="extension-label">
        Badge label
      </label>
      <input
        id="extension-label"
        type="text"
        value={value}
        maxLength={EXTENSION_LABEL_MAX_LENGTH}
        disabled={!canWrite}
        placeholder="Details"
        onChange={(event) => onChange(event.target.value)}
        className={CONFIG_INPUT_CLASS}
      />
      <p className="mt-1 text-xs text-muted-foreground">
        What these fields collect, in your words. Shown as{' '}
        <span className="font-medium text-foreground">{wording.listBadge}</span> in the
        item picker and{' '}
        <span className="font-medium text-foreground">{wording.required}</span> on the
        record.
      </p>
    </div>
  );
}

/** Mirrors the backend cap in `EntityField` (workflow/models/interface.py). */
const EXTENSION_LABEL_MAX_LENGTH = 60;
