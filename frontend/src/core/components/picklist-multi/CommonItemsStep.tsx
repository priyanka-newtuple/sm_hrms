/** Step 2: check the items that apply broadly and seed them onto every row. */

import Button from '@/components/ui/button';
import MultiSelectDropdown from '../MultiSelectDropdown';
import SelectAllButton from './SelectAllButton';

type CommonItemsStepProps = {
  itemOptions: string[];
  staged: string[];
  itemLabel: (item: string) => string;
  /** Heading and description, already resolved against the field's own wording. */
  heading: string;
  description: string;
  /** Flags the items whose selection reveals extra fields in step 3. */
  itemBadge: (item: string) => string | undefined;
  hasRows: boolean;
  disabled: boolean;
  /** Item assignments an unselect-all would strip from every card. */
  assignedCount: number;
  onStagedChange: (next: string[]) => void;
  onApplyToAll: () => void;
};

export default function CommonItemsStep({
  itemOptions,
  staged,
  itemLabel,
  itemBadge,
  heading,
  description,
  hasRows,
  disabled,
  assignedCount,
  onStagedChange,
  onApplyToAll,
}: CommonItemsStepProps) {
  return (
    <div>
      <div className="flex items-center justify-between gap-3">
        <h4 className="min-w-0 text-base font-semibold text-foreground">2. {heading}</h4>
        <SelectAllButton
          options={itemOptions}
          selected={staged}
          disabled={disabled}
          onChange={onStagedChange}
          confirmUnselect={
            assignedCount > 0
              ? `Unselecting every item strips ${assignedCount} item assignment(s) from every card, with any details entered under them. Continue?`
              : undefined
          }
        />
      </div>
      <p className="mt-0.5 text-sm text-muted-foreground">{description}</p>
      {/* The same control step 1 uses, so both selections read the same way.
          Neither direction is a local pick: adding a chip assigns that item to
          every card below, removing one takes it off all of them. */}
      <div className="mt-2">
        <MultiSelectDropdown
          options={itemOptions}
          value={staged}
          onChange={onStagedChange}
          labelFor={itemLabel}
          badgeFor={itemBadge}
          placeholder="Search items…"
          chipTone="primary"
          disabled={disabled}
        />
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <Button
          variant="primary"
          size="md"
          onClick={onApplyToAll}
          disabled={disabled || staged.length === 0 || !hasRows}
          className="transition-colors"
        >
          Apply selected items to all
        </Button>
        <span className="text-sm text-muted-foreground">
          Puts every item above back on every card, undoing per-card changes made in step 3.
        </span>
      </div>
    </div>
  );
}
