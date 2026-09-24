/**
 * The bulk action shared by step 1 and step 2, sitting on the step heading so
 * both read the same way — and the same way step 3's own All/Clear pair does.
 *
 * One button that flips: "Select all" until everything is in, "Unselect all"
 * after, so a select-all hit by mistake is undone by clicking the same place
 * again rather than by removing chips one at a time.
 *
 * Selecting only ever adds — replacing the selection would drop values the
 * picklist no longer lists, and in step 1 those are whole rows. Unselecting is
 * the destructive direction, so it asks first when there is anything to lose
 * (`confirmUnselect`), and goes straight through when there is not — the
 * just-clicked-it-by-mistake case stays one click.
 */

import { pillClass, withOptionsAdded } from './rows';

type SelectAllButtonProps = {
  options: string[];
  selected: string[];
  disabled: boolean;
  onChange: (next: string[]) => void;
  /** Shown before unselecting. Omit when nothing would be discarded. */
  confirmUnselect?: string;
};

export default function SelectAllButton({
  options,
  selected,
  disabled,
  onChange,
  confirmUnselect,
}: SelectAllButtonProps) {
  const missing = options.filter((option) => !selected.includes(option));
  const isAllSelected = options.length > 0 && missing.length === 0;

  const handleClick = () => {
    if (!isAllSelected) {
      onChange(withOptionsAdded(selected, options));
      return;
    }
    if (!confirmUnselect || window.confirm(confirmUnselect)) onChange([]);
  };

  return (
    <button
      type="button"
      disabled={disabled || options.length === 0}
      onClick={handleClick}
      className={pillClass}
    >
      {isAllSelected ? 'Unselect all' : 'Select all'}
    </button>
  );
}
