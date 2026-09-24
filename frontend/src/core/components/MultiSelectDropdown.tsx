'use client';

import * as React from 'react';
import { useMemo } from 'react';
import {
  Combobox,
  ComboboxChips,
  ComboboxChip,
  ComboboxChipsInput,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxList,
  ComboboxItem,
  ComboboxGroup,
  ComboboxLabel,
  ComboboxValue,
  useComboboxAnchor,
} from '@/components/ui/combobox';
import { cn } from '@/lib/utils';

export type MultiSelectGroup = {
  id: string;
  label: string;
  options: string[];
};

interface MultiSelectDropdownProps {
  options: string[] | MultiSelectGroup[];
  value: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
  disabled?: boolean;
  invalid?: boolean;
  /**
   * 'wrap' (default): chips wrap onto new lines as more are selected, so the
   * control grows taller — the right fit for a standalone form field.
   * 'scroll': chips stay on one line at a fixed height and scroll
   * horizontally instead — for compact toolbar/filter-bar placements where
   * neighbouring controls must not be pushed around as selections grow.
   */
  chipsLayout?: 'wrap' | 'scroll';
  /**
   * Fixed height applied when `chipsLayout="scroll"` (ignored otherwise) —
   * pass the exact height of the neighbouring controls in the row (e.g.
   * `'h-9'` or `'h-11'`) so this control lines up with them instead of
   * assuming one fixed height everywhere it's embedded.
   */
  chipsHeightClassName?: string;
  /**
   * Display text for an option, when the stored value is not what should be
   * read (a picklist stores `value` and shows `label`). Also what the typed
   * filter matches on, so searching finds what the list shows. Defaults to the
   * option itself.
   */
  labelFor?: (option: string) => string;
  /**
   * Trailing badge for an option in the list, for a note that belongs on the
   * choice rather than in its name (e.g. "this one asks for more input").
   * Return undefined for options that carry none.
   */
  badgeFor?: (option: string) => string | undefined;
  /**
   * 'muted' (default): neutral chips, what every existing caller renders.
   * 'primary': chips tinted with the organization's brand colour, for places
   * where the selection is the point of the control rather than a filter on
   * something else.
   */
  chipTone?: 'muted' | 'primary';
}

function isGroupedOptions(
  opts: string[] | MultiSelectGroup[]
): opts is MultiSelectGroup[] {
  return Array.isArray(opts) && opts.length > 0 && typeof opts[0] === 'object' && 'id' in opts[0];
}

function normalizeGroups(
  options: string[] | MultiSelectGroup[]
): MultiSelectGroup[] {
  if (isGroupedOptions(options)) {
    return options;
  }
  return [{ id: '__flat', label: '', options }];
}

export default function MultiSelectDropdown({
  options,
  value,
  onChange,
  placeholder = 'Select…',
  disabled = false,
  invalid = false,
  chipsLayout = 'wrap',
  chipsHeightClassName = 'h-9',
  labelFor,
  badgeFor,
  chipTone = 'muted',
}: MultiSelectDropdownProps) {
  const anchor = useComboboxAnchor();
  const isScroll = chipsLayout === 'scroll';
  // Derived from --primary, which is the only thing applyTheme writes, so this
  // follows the org's brand without knowing what it is. The remove button is a
  // ghost Button with its own colour, hence reaching into it.
  // Taller, rounder and a size up from the default chip — these carry the
  // control's whole answer rather than annotating something else, so they read
  // as content. `pr` is left to the base class, which zeroes it when a remove
  // button is present so the X keeps its own spacing.
  const chipClass =
    chipTone === 'primary'
      ? [
          'bg-primary-subtle text-primary-subtle-foreground',
          '[&_button]:text-primary-subtle-foreground',
          'h-7 gap-1.5 rounded-md pl-2.5 text-sm',
        ].join(' ')
      : undefined;

  const groups = useMemo(() => normalizeGroups(options), [options]);
  const allOptions = useMemo(
    () => groups.flatMap((g) => g.options),
    [groups]
  );

  const isGrouped = groups.length > 1 || (groups[0]?.label !== '' && groups[0]?.label !== undefined);

  const renderItem = (item: string) => {
    const badge = badgeFor?.(item);
    return (
      <ComboboxItem key={item} value={item}>
        <span className="min-w-0 truncate">{labelFor ? labelFor(item) : item}</span>
        {badge && (
          // `ml-auto` parks it against the item's right padding, which already
          // reserves room for the selected-state check.
          <span className="ml-auto shrink-0 rounded-full bg-warning-subtle px-2 py-0.5 text-[11px] font-semibold text-warning">
            {badge}
          </span>
        )}
      </ComboboxItem>
    );
  };

  return (
    <Combobox
      multiple
      autoHighlight
      items={allOptions}
      value={value}
      onValueChange={onChange}
      disabled={disabled}
      itemToStringLabel={labelFor}
    >
      <ComboboxChips
        ref={anchor}
        className={cn(
          'w-full min-h-10',
          isScroll && [chipsHeightClassName, 'flex-nowrap overflow-x-auto overflow-y-hidden'],
          invalid && 'has-aria-invalid:border-destructive has-aria-invalid:ring-destructive/20'
        )}
      >
        <ComboboxValue>
          {(values) => (
            <React.Fragment>
              {values.length === 0 && (
                <span className={cn('text-sm text-muted-foreground pointer-events-none', isScroll && 'shrink-0')}>
                  {placeholder}
                </span>
              )}
              {values.map((value: string) => (
                <ComboboxChip key={value} className={cn(chipClass, isScroll && 'shrink-0')}>
                  {labelFor ? labelFor(value) : value}
                </ComboboxChip>
              ))}
              <ComboboxChipsInput
                placeholder={values.length === 0 ? undefined : 'Add more…'}
                aria-invalid={invalid}
                className={isScroll ? 'shrink-0' : undefined}
              />
            </React.Fragment>
          )}
        </ComboboxValue>
      </ComboboxChips>

      <ComboboxContent anchor={anchor}>
        <ComboboxEmpty>No options found.</ComboboxEmpty>
        <ComboboxList>
          {isGrouped ? (
            groups.map((group) => (
              <ComboboxGroup key={group.id}>
                {group.label && (
                  <ComboboxLabel>{group.label}</ComboboxLabel>
                )}
                {group.options.map(renderItem)}
              </ComboboxGroup>
            ))
          ) : (
            renderItem
          )}
        </ComboboxList>
      </ComboboxContent>
    </Combobox>
  );
}
