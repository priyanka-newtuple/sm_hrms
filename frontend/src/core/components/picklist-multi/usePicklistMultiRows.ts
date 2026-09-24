/**
 * Every piece of state the three-step wizard holds, and every write it makes to
 * the field's value. The step components are presentational; the row shape and
 * the transforms on it live in `rows.ts`, and this is the wiring between them.
 */

import { useMemo, useState } from 'react';
import type { FormField } from '../../types';
import {
  assignmentCount,
  makeItemBadge,
  makeItemLabel,
  parseRows,
  withExtensionValue,
  withItemsRemovedEverywhere,
  withItemToggled,
  withSelected,
  withStagedAppliedToAll,
  withToggles,
  type Row,
} from './rows';

/**
 * Step 2's checked set, and with it step 3's grid: every item already assigned
 * to some row (read straight off `value`, so unchecking a box — which strips
 * that item from every row — drops it here on the same render, and swapping the
 * record under a mounted modal can't leave a stale pool behind) plus items
 * checked in step 2 but not yet applied anywhere. Ordered by `enum_values_2` so
 * the grid matches step 2's order; assigned values the picklist no longer lists
 * are appended rather than hidden, or their left-rail count would reference an
 * item that can't be seen or removed.
 */
function stagedItems(rows: Row[], extraStaged: string[], itemOptions: string[]): string[] {
  const chosen = new Set(extraStaged);
  rows.forEach((row) => row.toggles.forEach((item) => chosen.add(item)));
  const ordered = itemOptions.filter((item) => chosen.has(item));
  chosen.forEach((item) => {
    if (!itemOptions.includes(item)) ordered.push(item);
  });
  return ordered;
}

export function usePicklistMultiRows(
  field: FormField,
  value: unknown,
  onChange: (v: unknown) => void,
) {
  const rows = useMemo(() => parseRows(value), [value]);
  const [extraStaged, setExtraStaged] = useState<string[]>([]);
  const [active, setActive] = useState('');
  const [itemFilter, setItemFilter] = useState('');
  const activeDropdown = rows.some((row) => row.dropdown === active) ? active : rows[0]?.dropdown ?? '';
  const staged = useMemo(
    () => stagedItems(rows, extraStaged, field.enum_values_2 ?? []),
    [rows, extraStaged, field.enum_values_2],
  );

  /**
   * Step 2's new checked set, applied to every row in both directions: an item
   * checked here is assigned to every option from step 1, and one unchecked is
   * pulled out of all of them. Step 2 is the default for every card, and step 3
   * is where a card departs from it.
   *
   * `extraStaged` still holds the items checked while no option is selected
   * yet — there is nothing to write them into until step 1 has a row, and
   * `withSelected` seeds them in when one appears.
   */
  const setStaged = (next: string[]) => {
    const added = next.filter((item) => !staged.includes(item));
    const removed = staged.filter((item) => !next.includes(item));
    if (added.length === 0 && removed.length === 0) return;
    setExtraStaged((prev) => [...prev.filter((item) => !removed.includes(item)), ...added]);
    // Both directions in one write: `rows` here is the value before either, so
    // folding two onChange calls would lose whichever landed first.
    let updated = rows;
    if (removed.length > 0) updated = withItemsRemovedEverywhere(updated, removed);
    if (added.length > 0 && rows.length > 0) updated = withStagedAppliedToAll(updated, added);
    if (updated !== rows) onChange(updated);
  };

  return {
    rows,
    staged,
    /** What an unselect-all in step 1 or step 2 would throw away. */
    assignedCount: assignmentCount(rows),
    activeDropdown,
    itemFilter,
    activeRow: rows.find((row) => row.dropdown === activeDropdown),
    itemLabel: useMemo(() => makeItemLabel(field), [field]),
    itemBadge: useMemo(() => makeItemBadge(field), [field]),
    selected: rows.map((row) => row.dropdown),
    setItemFilter,
    setStaged,
    activate: (dropdown: string) => {
      setActive(dropdown);
      setItemFilter('');
    },
    setSelected: (next: string[]) => onChange(withSelected(rows, next, staged)),
    setRowToggles: (dropdown: string, toggles: string[]) =>
      onChange(rows.map((row) => (row.dropdown === dropdown ? withToggles(row, toggles) : row))),
    toggleItem: (dropdown: string, item: string) => onChange(withItemToggled(rows, dropdown, item)),
    setExtensionValue: (option: string, fieldKey: string, next: unknown) =>
      onChange(withExtensionValue(rows, activeDropdown, option, fieldKey, next)),
    applyToAll: () => onChange(withStagedAppliedToAll(rows, staged)),
  };
}

export type PicklistMultiRows = ReturnType<typeof usePicklistMultiRows>;
