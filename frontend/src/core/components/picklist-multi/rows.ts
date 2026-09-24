/**
 * The stored shape of a `picklist_multi` value, and the pure operations on it.
 *
 * One row per selected primary option: `toggles` are that option's selected
 * items, and `extensions` the values entered for the fields those items reveal
 * ("Extend Field"), keyed by item then by field key. `extensions` is absent on
 * every row saved before that feature, and on every field that does not use it.
 */

import type { FormField } from '../../types';
import type { ExtensionValues } from '../PicklistExtensionCards';
import { extensionWording } from './extensionWording';

export type Row = {
  dropdown: string;
  toggles: string[];
  extensions?: Record<string, ExtensionValues>;
};

export function parseRows(value: unknown): Row[] {
  if (!Array.isArray(value)) return [];
  return (value as unknown[])
    .map((raw) => {
      const row = (raw ?? {}) as Partial<Row>;
      const extensions =
        row.extensions && typeof row.extensions === 'object' && !Array.isArray(row.extensions)
          ? row.extensions
          : undefined;
      return {
        dropdown: typeof row.dropdown === 'string' ? row.dropdown : '',
        toggles: Array.isArray(row.toggles) ? row.toggles.map(String) : [],
        ...(extensions ? { extensions } : {}),
      };
    })
    .filter((row) => row.dropdown !== '');
}

/**
 * Apply a row's new toggle list, dropping the extension values of every option
 * that is no longer selected — an option that is off reveals no fields, so
 * carrying its values would put data in the payload the form cannot show.
 */
export function withToggles(row: Row, toggles: string[]): Row {
  if (!row.extensions) return { ...row, toggles };
  const kept: Record<string, ExtensionValues> = {};
  for (const option of toggles) {
    const values = row.extensions[option];
    if (values) kept[option] = values;
  }
  return Object.keys(kept).length > 0
    ? { ...row, toggles, extensions: kept }
    : { dropdown: row.dropdown, toggles };
}

/**
 * The rows for a new primary selection, keeping the rows that survive it.
 *
 * A row that is new to the selection starts with `seed` already assigned — the
 * items staged in step 2 — so an option picked in step 1 arrives in step 3
 * fully ticked rather than empty. Rows that were already there keep exactly
 * what they had, including any per-card unticking.
 */
export function withSelected(rows: Row[], next: string[], seed: string[] = []): Row[] {
  const byKey = new Map(rows.map((row) => [row.dropdown, row]));
  return next.map((key) => byKey.get(key) ?? { dropdown: key, toggles: [...seed] });
}

/** One row's item flipped on or off. */
export function withItemToggled(rows: Row[], dropdown: string, item: string): Row[] {
  return rows.map((row) =>
    row.dropdown === dropdown
      ? withToggles(
          row,
          row.toggles.includes(item)
            ? row.toggles.filter((existing) => existing !== item)
            : [...row.toggles, item],
        )
      : row,
  );
}

/**
 * Items pulled out of play everywhere, not just out of one row. Takes a list
 * rather than one item so clearing several at once is a single write — folding
 * a per-item call would read `rows` from before the previous removal.
 */
export function withItemsRemovedEverywhere(rows: Row[], items: string[]): Row[] {
  if (items.length === 0) return rows;
  return rows.map((row) =>
    withToggles(row, row.toggles.filter((existing) => !items.includes(existing))),
  );
}

/** Every item assigned across every row — what an unselect-all would discard. */
export function assignmentCount(rows: Row[]): number {
  return rows.reduce((sum, row) => sum + row.toggles.length, 0);
}

/**
 * A selection with every option added to it. Additive on purpose: a "Select
 * all" that replaced the selection would drop values the picklist no longer
 * lists, and in step 1 those values are whole rows.
 */
export function withOptionsAdded(selected: string[], options: string[]): string[] {
  return [...selected, ...options.filter((option) => !selected.includes(option))];
}

/** Every row gains the staged items it does not already have. */
export function withStagedAppliedToAll(rows: Row[], staged: string[]): Row[] {
  return rows.map((row) => ({
    ...row,
    toggles: [...row.toggles, ...staged.filter((item) => !row.toggles.includes(item))],
  }));
}

/** One extension field's value written into the row that owns it. */
export function withExtensionValue(
  rows: Row[],
  dropdown: string,
  option: string,
  fieldKey: string,
  value: unknown,
): Row[] {
  return rows.map((row) =>
    row.dropdown === dropdown
      ? {
          ...row,
          extensions: {
            ...(row.extensions ?? {}),
            [option]: { ...(row.extensions?.[option] ?? {}), [fieldKey]: value },
          },
        }
      : row,
  );
}

/**
 * Items are stored as picklist *values*; `enum_labels_2` is the parallel
 * display list. Falls back to the value, which is all a field configured
 * before labels were persisted has.
 */
export function makeItemLabel(field: FormField): (item: string) => string {
  const itemOptions = field.enum_values_2 ?? [];
  return (item: string) => {
    const index = itemOptions.indexOf(item);
    return (index >= 0 ? field.enum_labels_2?.[index] : undefined) || item;
  };
}

/**
 * The badge an item carries in step 2's list when "Extend Field" configures
 * anything for it, so a reader can see which ticks will ask for more before
 * ticking them. Deliberately blind to whether those fields are themselves
 * required — the point is that the option opens a form, not that it blocks
 * save. Step 3's cards draw that distinction once the option is selected.
 */
export function makeItemBadge(field: FormField): (item: string) => string | undefined {
  const extensions = field.extensions;
  if (!extensions) return () => undefined;
  const { listBadge } = extensionWording(field.extension_label);
  return (item: string) =>
    (extensions[item]?.fields.length ?? 0) > 0 ? listBadge : undefined;
}

export const pillClass =
  'shrink-0 rounded-full border border-border bg-card px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:border-cobalt hover:text-cobalt disabled:cursor-not-allowed disabled:opacity-50';
