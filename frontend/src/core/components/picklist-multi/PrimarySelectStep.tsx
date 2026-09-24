/** Step 1: search and select the primary options, one row each. */

import MultiSelectDropdown from '../MultiSelectDropdown';
import SelectAllButton from './SelectAllButton';
import type { FormField } from '../../types';

type PrimarySelectStepProps = {
  field: FormField;
  selected: string[];
  onChange: (next: string[]) => void;
  disabled: boolean;
  invalid: boolean;
  /** Item assignments an unselect-all would discard along with the rows. */
  assignedCount: number;
};

export default function PrimarySelectStep({
  field,
  selected,
  onChange,
  disabled,
  invalid,
  assignedCount,
}: PrimarySelectStepProps) {
  return (
    <div>
      {/* Bulk action on the heading line, directly above the control it fills
          — the same placement step 2 uses and step 3's own All/Clear pair. */}
      <div className="flex items-center justify-between gap-3">
        <h4 className="min-w-0 text-base font-semibold text-foreground">
          1. {field.step1_label?.trim() || `Choose ${field.label}`}
          {field.required && <span className="ml-0.5 text-destructive">*</span>}
        </h4>
        <SelectAllButton
          options={field.enum_values ?? []}
          selected={selected}
          disabled={disabled}
          onChange={onChange}
          confirmUnselect={
            assignedCount > 0
              ? `Unselecting every option discards ${assignedCount} item assignment(s), and any details entered under them. Continue?`
              : undefined
          }
        />
      </div>
      <p className="mt-0.5 text-sm text-muted-foreground">
        {field.step1_description?.trim() || 'Search and select every option that applies.'}
      </p>
      <div className="mt-2">
        <MultiSelectDropdown
          options={field.enum_values ?? []}
          value={selected}
          onChange={onChange}
          placeholder={field.placeholder ?? 'Search…'}
          chipTone="primary"
          disabled={disabled}
          invalid={invalid}
        />
      </div>
      <p className="mt-1.5 pl-4 text-sm text-muted-foreground">
        These receive the items from step 2.
      </p>
      <p className="mt-2 text-sm text-foreground">{selected.length} selected</p>
    </div>
  );
}
