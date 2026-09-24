/**
 * PicklistExtensionCards
 *
 * The "Extend Field" half of a `picklist_multi` value: one card per selected
 * option, holding the extra Field Library fields an administrator configured for
 * it, each rendered through the ordinary `FieldInput` so an extended field
 * behaves exactly as it does anywhere else in a form. An option configured with
 * no fields still gets a card, marked as asking for nothing, so the reader can
 * see every selection was accounted for.
 *
 * Scoped to one row of the wizard — the values it reads and writes belong to
 * that row's `extensions`, so the same option carries different values under
 * different primary options.
 */

import FieldInput from './FieldInput';
import { extensionWording, type ExtensionWording } from './picklist-multi/extensionWording';
import type { ExtensionField, FormField } from '../types';
import { cn } from '@/lib/utils';

/** One option's entered values, keyed by the extension field's key. */
export type ExtensionValues = Record<string, unknown>;

type PicklistExtensionCardsProps = {
  field: FormField;
  /** The options currently selected in this row. */
  selected: string[];
  /** This row's stored extension values, keyed by option. */
  values: Record<string, ExtensionValues>;
  onChange: (option: string, fieldKey: string, value: unknown) => void;
  disabled?: boolean;
  entityId?: string;
};

export default function PicklistExtensionCards({
  field,
  selected,
  values,
  onChange,
  disabled = false,
  entityId,
}: PicklistExtensionCardsProps) {
  const extensions = field.extensions;
  if (!extensions || selected.length === 0) return null;

  const wording = extensionWording(field.extension_label);

  const optionLabel = (option: string) => {
    const index = (field.enum_values_2 ?? []).indexOf(option);
    return (index >= 0 ? field.enum_labels_2?.[index] : undefined) || option;
  };

  // Ordered by the picklist, not by the order the user happened to tick things.
  const ordering = field.enum_values_2 ?? [];
  const ordered = [...selected].sort((a, b) => {
    const left = ordering.indexOf(a);
    const right = ordering.indexOf(b);
    return (left === -1 ? ordering.length : left) - (right === -1 ? ordering.length : right);
  });

  return (
    <div className="mt-5 border-t border-border pt-4">
      <h5 className="text-sm font-semibold text-foreground">{wording.heading}</h5>
      <p className="mt-0.5 text-xs text-muted-foreground">
        Filled in per {field.label || 'option'} selected above. An option that asks for
        nothing is marked as such.
      </p>

      <div className="mt-3 space-y-2.5">
        {ordered.map((option) => (
          <OptionCard
            key={option}
            label={optionLabel(option)}
            wording={wording}
            fields={extensions[option]?.fields ?? []}
            values={values[option] ?? {}}
            onChange={(fieldKey, next) => onChange(option, fieldKey, next)}
            disabled={disabled}
            entityId={entityId}
          />
        ))}
      </div>
    </div>
  );
}

/**
 * Extended fields sit inside a card in a form, so they use the compact control
 * size the rest of a card does — `FieldInput`'s own sizing is tuned for a
 * full-width form row (`px-4 py-3 text-base`) and looks oversized here. Applied
 * as a scoped override rather than a `FieldInput` prop because each field type
 * renders its own control (input, select, textarea, phone, currency…) and this
 * reaches all of them at once.
 */
const COMPACT_CONTROLS = [
  '[&_input]:rounded-lg [&_input]:px-3 [&_input]:py-2 [&_input]:text-sm',
  '[&_select]:rounded-lg [&_select]:px-3 [&_select]:py-2 [&_select]:text-sm',
  '[&_textarea]:rounded-lg [&_textarea]:px-3 [&_textarea]:py-2 [&_textarea]:text-sm',
  // Checkboxes and radios size themselves; the padding above would inflate them.
  '[&_input[type=checkbox]]:h-4 [&_input[type=checkbox]]:w-4 [&_input[type=checkbox]]:p-0',
].join(' ');

type OptionCardProps = {
  label: string;
  wording: ExtensionWording;
  fields: ExtensionField[];
  values: ExtensionValues;
  onChange: (fieldKey: string, value: unknown) => void;
  disabled: boolean;
  entityId?: string;
};

/**
 * The badge on an option's card, so a reader can tell at a glance which
 * selections still want input. Semantic status tokens, so it reads correctly in
 * both themes: solid warning for "this one asks for something", subtle success
 * for "nothing to do".
 *
 * An option whose fields are all optional reads the same as one with a required
 * field. The badge answers "does this ask me for anything", not "will this block
 * save" — the asterisk on each field label is what marks the required ones.
 */
function optionBadge(
  fields: ExtensionField[],
  wording: ExtensionWording,
): { text: string; className: string } {
  return fields.length === 0
    ? { text: wording.none, className: 'bg-success-subtle text-success' }
    : { text: wording.required, className: 'bg-warning text-warning-foreground' };
}

function OptionCard({ label, wording, fields, values, onChange, disabled, entityId }: OptionCardProps) {
  const badge = optionBadge(fields, wording);
  return (
    // Tinted rather than `bg-card`: the panel these sit in is already `bg-card`,
    // so a card on a card needs more than a border to read as nested.
    <div className="rounded-xl border border-border bg-muted/20 px-4 py-3.5">
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-baseline gap-2">
          <h6 className="shrink-0 truncate text-sm font-semibold text-foreground">{label}</h6>
          {/* The option restated as the authority it stands for. Same text as the
              heading today; the arrow is decorative, so it is hidden from screen
              readers rather than read out as "right arrow". */}
          <span className="min-w-0 truncate text-sm text-muted-foreground">
            <span aria-hidden="true">→ </span>
            Authority: {label}
          </span>
          {fields.length > 0 && (
            <span className="shrink-0 text-xs text-muted-foreground">
              {fields.length} {fields.length === 1 ? 'field' : 'fields'}
            </span>
          )}
        </div>
        <span
          className={cn(
            'shrink-0 rounded-full px-2.5 py-0.5 text-[11px] font-semibold',
            badge.className,
          )}
        >
          {badge.text}
        </span>
      </div>
      {fields.length > 0 && (
        <div
          className={cn(
            'mt-3 grid grid-cols-1 gap-x-4 gap-y-3 sm:grid-cols-2 lg:grid-cols-3',
            COMPACT_CONTROLS,
          )}
        >
          {fields.map((extensionField) => (
            <ExtensionFieldControl
              key={extensionField.id}
              field={extensionField}
              value={values[extensionField.id]}
              onChange={(next) => onChange(extensionField.id, next)}
              disabled={disabled}
              entityId={entityId}
            />
          ))}
        </div>
      )}
    </div>
  );
}

/** Types with no useful half-width form; they take the whole row. */
const FULL_WIDTH_TYPES = new Set(['table', 'textarea', 'multi_select']);

type ExtensionFieldControlProps = {
  field: ExtensionField;
  value: unknown;
  onChange: (value: unknown) => void;
  disabled: boolean;
  entityId?: string;
};

function ExtensionFieldControl({
  field,
  value,
  onChange,
  disabled,
  entityId,
}: ExtensionFieldControlProps) {
  return (
    <div
      className={cn(
        'min-w-0',
        FULL_WIDTH_TYPES.has(field.type) && 'sm:col-span-2 lg:col-span-3',
      )}
    >
      <label className="mb-1 block text-xs font-semibold text-foreground">
        {field.label}
        {field.required && <span className="ml-0.5 text-destructive">*</span>}
      </label>
      {/* `placeholder` is already rendered inside the control by FieldInput —
          repeating it as a hint line below said everything twice. */}
      <FieldInput
        field={field}
        value={value}
        onChange={onChange}
        disabled={disabled}
        entityId={entityId}
      />
    </div>
  );
}
