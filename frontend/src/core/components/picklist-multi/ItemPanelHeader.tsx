/** Step 3's panel header: the active row, its bulk actions, and the filter. */

import CopyFromMenu from './CopyFromMenu';
import ItemFilterInput from './ItemFilterInput';
import { pillClass, type Row } from './rows';

type ItemPanelHeaderProps = {
  activeRow: Row | undefined;
  copyOptions: Row[];
  staged: string[];
  itemFilter: string;
  disabled: boolean;
  onFilterChange: (value: string) => void;
  onSetRowToggles: (dropdown: string, toggles: string[]) => void;
};

export default function ItemPanelHeader({
  activeRow,
  copyOptions,
  staged,
  itemFilter,
  disabled,
  onFilterChange,
  onSetRowToggles,
}: ItemPanelHeaderProps) {
  const setToggles = (toggles: string[]) => activeRow && onSetRowToggles(activeRow.dropdown, toggles);

  return (
    <div className="border-b border-border px-4 pb-2.5 pt-3.5">
      <div className="flex flex-wrap items-center gap-2.5">
        <h5 className="m-0 text-base font-medium text-foreground">{activeRow?.dropdown}</h5>
        <span className="text-xs text-muted-foreground">
          {activeRow?.toggles.length ?? 0} of {staged.length}
        </span>
        <span className="flex-1" />
        <button
          type="button"
          disabled={disabled || !activeRow}
          onClick={() => setToggles(staged)}
          className={pillClass}
        >
          All
        </button>
        <button
          type="button"
          disabled={disabled || !activeRow}
          onClick={() => setToggles([])}
          className={pillClass}
        >
          Clear
        </button>
        <CopyFromMenu options={copyOptions} disabled={disabled} onCopy={setToggles} />
      </div>
      <ItemFilterInput value={itemFilter} itemCount={staged.length} onChange={onFilterChange} />
    </div>
  );
}
