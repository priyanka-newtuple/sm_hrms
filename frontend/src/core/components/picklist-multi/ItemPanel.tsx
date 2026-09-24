/**
 * Step 3's right panel for the active row: bulk actions and filter on top, the
 * item grid below, and — when the field configures "Extend Field" — the extra
 * fields each selected item asks for.
 */

import PicklistExtensionCards from '../PicklistExtensionCards';
import type { FormField } from '../../types';
import ItemGrid from './ItemGrid';
import ItemPanelHeader from './ItemPanelHeader';
import type { PicklistMultiRows } from './usePicklistMultiRows';

type ItemPanelProps = {
  field: FormField;
  model: PicklistMultiRows;
  disabled: boolean;
  entityId?: string;
};

export default function ItemPanel({ field, model, disabled, entityId }: ItemPanelProps) {
  const { activeRow, staged, itemFilter, itemLabel } = model;
  const filter = itemFilter.trim().toLowerCase();
  const filteredItems = staged.filter(
    (item) => item.toLowerCase().includes(filter) || itemLabel(item).toLowerCase().includes(filter),
  );

  return (
    <div className="flex min-w-0 flex-1 flex-col">
      <ItemPanelHeader
        activeRow={activeRow}
        copyOptions={model.rows.filter(
          (row) => row.dropdown !== activeRow?.dropdown && row.toggles.length > 0,
        )}
        staged={staged}
        itemFilter={itemFilter}
        disabled={disabled}
        onFilterChange={model.setItemFilter}
        onSetRowToggles={model.setRowToggles}
      />
      <div className="flex-1 overflow-y-auto px-4 pb-2 pt-3">
        <ItemGrid
          items={filteredItems}
          activeRow={activeRow}
          itemFilter={itemFilter}
          itemLabel={itemLabel}
          disabled={disabled}
          onToggleItem={model.toggleItem}
        />

        {activeRow && (
          <PicklistExtensionCards
            field={field}
            selected={activeRow.toggles}
            values={activeRow.extensions ?? {}}
            onChange={model.setExtensionValue}
            disabled={disabled}
            entityId={entityId}
          />
        )}
      </div>
    </div>
  );
}
