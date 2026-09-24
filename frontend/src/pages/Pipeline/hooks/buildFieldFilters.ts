import type { FilterBarItem } from '@/skins';

/**
 * Turns raw filter-bar string values into the field_filters shape the
 * backend accepts. Only 'select' and 'multiselect' filters map to a
 * field_filters entry — 'search'/'daterange'/'assignee' are handled through
 * their own dedicated params elsewhere and must NOT leak in here, since a
 * skin's filterBar config (unlike the agent-mode widget's custom-filter-only
 * options) can include those other types too. A multi-select filter's value
 * is stored comma-joined (in the URL, or in local widget state) and gets
 * split back into the OR'd value list here; a select filter passes through
 * as a scalar. Shared by the main /pipeline page and the agent-mode
 * PipelineBoardWidget so the serialization convention can't drift between
 * the two call sites.
 */
export function buildFieldFilters(
  values: Record<string, string>,
  optionsByKey: Map<string, FilterBarItem>,
): Record<string, string | string[]> {
  const entries: Array<[string, string | string[]]> = [];
  for (const [key, value] of Object.entries(values)) {
    if (!value) continue;
    const type = optionsByKey.get(key)?.type;
    if (type === 'multiselect') {
      const split = value.split(',').filter(Boolean);
      if (split.length) entries.push([key, split]);
    } else if (type === 'select') {
      entries.push([key, value]);
    }
  }
  return Object.fromEntries(entries);
}
