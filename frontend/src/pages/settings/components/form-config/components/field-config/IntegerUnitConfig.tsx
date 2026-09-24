/**
 * The optional display unit of an `integer` field, grouped so the long
 * catalogue stays scannable, with a free-text escape hatch for anything the
 * catalogue doesn't list.
 *
 * "Other unit…" mode is local state rather than a field key: the field itself
 * only ever stores the unit string. It is seeded from the current unit, and the
 * component unmounts when the field stops being an integer, which is what
 * resets it.
 */

import { useState } from 'react';
import type { FormField } from '@/core/types';
import { FIELD_UNIT_GROUPS, FIELD_UNIT_VALUES, UNIT_OTHER_VALUE } from '../../../fields/fieldUnits';
import { CONFIG_INPUT_CLASS, CONFIG_LABEL_CLASS } from './styles';

type IntegerUnitConfigProps = {
  field: FormField;
  canWrite: boolean;
  onChange: (patch: Partial<FormField>) => void;
};

export default function IntegerUnitConfig({ field, canWrite, onChange }: IntegerUnitConfigProps) {
  const [customUnitMode, setCustomUnitMode] = useState(
    () => Boolean(field.unit && !FIELD_UNIT_VALUES.has(field.unit)),
  );

  return (
    <div className="space-y-2 rounded-xl border border-border bg-muted/20 p-3">
      <div>
        <label className={CONFIG_LABEL_CLASS}>
          Unit <span className="font-normal">· optional</span>
        </label>
        <p className="text-xs text-muted-foreground">Choose a display unit for this integer field.</p>
      </div>
      <select
        value={customUnitMode ? UNIT_OTHER_VALUE : (field.unit ?? '')}
        onChange={(event) => {
          const next = event.target.value;
          if (next === UNIT_OTHER_VALUE) {
            setCustomUnitMode(true);
            return;
          }
          setCustomUnitMode(false);
          onChange({ unit: next || undefined });
        }}
        disabled={!canWrite}
        className={`${CONFIG_INPUT_CLASS} bg-background`}
      >
        <option value="">No unit</option>
        {FIELD_UNIT_GROUPS.map((group) => (
          <optgroup key={group.label} label={group.label}>
            {group.options.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </optgroup>
        ))}
        <option value={UNIT_OTHER_VALUE}>Other unit…</option>
      </select>
      {customUnitMode && (
        <input
          type="text"
          value={FIELD_UNIT_VALUES.has(field.unit ?? '') ? '' : (field.unit ?? '')}
          onChange={(event) => onChange({ unit: event.target.value || undefined })}
          disabled={!canWrite}
          autoFocus
          placeholder="e.g., boxes, trays, colonies"
          className={`${CONFIG_INPUT_CLASS} bg-background`}
        />
      )}
    </div>
  );
}
