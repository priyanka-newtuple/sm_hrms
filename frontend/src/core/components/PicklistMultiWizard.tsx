/**
 * Renders a `picklist_multi` field as a 3-step wizard:
 *  1. search/select primary options (`field.enum_values`) as removable chips
 *  2. check common items (`field.enum_values_2`) and apply them to every
 *     selected primary option in one click (union — existing items survive)
 *  3. fine-tune items per primary option in a dual panel — pick a primary
 *     option on the left, toggle its items in the grid on the right
 *
 * When the field configures "Extend Field", step 3 also renders the extra
 * fields each selected item asks for (see `PicklistExtensionCards`), per row.
 *
 * `value`/`onChange` carry the field's stored data contract, an array of
 * `{ dropdown: string; toggles: string[]; extensions?: … }` rows — one row per
 * selected primary option, `toggles` being that option's selected items and
 * `extensions` the values entered for the fields those items reveal, keyed by
 * item then by field key. That shape, and every write to it, lives in
 * `picklist-multi/` — this is the three steps in order.
 */

import AssignItemsStep from './picklist-multi/AssignItemsStep';
import CommonItemsStep from './picklist-multi/CommonItemsStep';
import PrimarySelectStep from './picklist-multi/PrimarySelectStep';
import { usePicklistMultiRows } from './picklist-multi/usePicklistMultiRows';
import type { FormField } from '../types';

type PicklistMultiWizardProps = {
  field: FormField;
  value: unknown;
  onChange: (v: unknown) => void;
  disabled?: boolean;
  invalid?: boolean;
  /** Forwarded to extended fields, so a document one uploads against the record. */
  entityId?: string;
};

export default function PicklistMultiWizard({
  field,
  value,
  onChange,
  disabled = false,
  invalid = false,
  entityId,
}: PicklistMultiWizardProps) {
  const model = usePicklistMultiRows(field, value, onChange);

  return (
    <div className="space-y-6">
      <PrimarySelectStep
        field={field}
        selected={model.selected}
        onChange={model.setSelected}
        disabled={disabled}
        invalid={invalid}
        assignedCount={model.assignedCount}
      />

      <CommonItemsStep
        itemOptions={field.enum_values_2 ?? []}
        staged={model.staged}
        itemLabel={model.itemLabel}
        itemBadge={model.itemBadge}
        heading={field.step2_label?.trim() || 'Choose items to apply to all'}
        description={
          field.step2_description?.trim() ||
          'Every option from step 1 starts with all of these ticked. Fine-tune per card in step 3.'
        }
        hasRows={model.rows.length > 0}
        disabled={disabled}
        assignedCount={model.assignedCount}
        onStagedChange={model.setStaged}
        onApplyToAll={model.applyToAll}
      />

      <AssignItemsStep field={field} model={model} disabled={disabled} entityId={entityId} />
    </div>
  );
}
