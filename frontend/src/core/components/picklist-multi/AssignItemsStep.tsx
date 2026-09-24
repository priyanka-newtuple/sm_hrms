/** Step 3: the dual panel — rows on the left, the active row's items on the right. */

import type { FormField } from '../../types';
import AssignmentStats from './AssignmentStats';
import ItemPanel from './ItemPanel';
import RowRail from './RowRail';
import type { PicklistMultiRows } from './usePicklistMultiRows';

type AssignItemsStepProps = {
  field: FormField;
  model: PicklistMultiRows;
  disabled: boolean;
  entityId?: string;
};

export default function AssignItemsStep({ field, model, disabled, entityId }: AssignItemsStepProps) {
  const { rows } = model;

  return (
    <div>
      <h4 className="min-w-0 text-base font-semibold text-foreground">
        3. {field.step3_label?.trim() || `Assign items per ${field.label || 'option'} (optional)`}
      </h4>
      <p className="mt-0.5 text-sm text-muted-foreground">
        {field.step3_description?.trim() || 'Pick a card on the left, then check items on the right.'}
      </p>

      {rows.length === 0 ? (
        <div className="mt-2 flex flex-col items-center justify-center gap-2 rounded-xl border border-border bg-card px-4 py-10 text-center">
          <p className="text-sm font-medium text-foreground">
            No {field.label || 'options'} selected yet
          </p>
          <p className="text-sm text-muted-foreground">Choose some in step 1 to begin.</p>
        </div>
      ) : (
        <div className="mt-2 flex h-[460px] overflow-hidden rounded-xl border border-border bg-card max-[720px]:h-auto max-[720px]:flex-col">
          <RowRail rows={rows} activeDropdown={model.activeDropdown} onActivate={model.activate} />
          <ItemPanel field={field} model={model} disabled={disabled} entityId={entityId} />
        </div>
      )}

      {rows.length > 0 && <AssignmentStats rows={rows} />}
    </div>
  );
}
