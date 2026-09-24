/** Step 3's item grid for the active row, or why it is empty. */

import ItemCell from './ItemCell';
import type { Row } from './rows';

type ItemGridProps = {
  items: string[];
  activeRow: Row | undefined;
  itemFilter: string;
  itemLabel: (item: string) => string;
  disabled: boolean;
  onToggleItem: (dropdown: string, item: string) => void;
};

export default function ItemGrid({
  items,
  activeRow,
  itemFilter,
  itemLabel,
  disabled,
  onToggleItem,
}: ItemGridProps) {
  if (items.length === 0) {
    return (
      <p className="px-1 py-4 text-sm text-muted-foreground">
        {itemFilter.trim()
          ? `No items match “${itemFilter.trim()}”`
          : 'No items chosen in step 2 yet.'}
      </p>
    );
  }

  return (
    <div className="grid grid-cols-2 gap-1.5 max-[720px]:grid-cols-1">
      {items.map((item) => (
        <ItemCell
          key={item}
          label={itemLabel(item)}
          isOn={activeRow?.toggles.includes(item) ?? false}
          disabled={disabled || !activeRow}
          onClick={() => activeRow && onToggleItem(activeRow.dropdown, item)}
        />
      ))}
    </div>
  );
}
