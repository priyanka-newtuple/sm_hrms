/**
 * The shared look of the per-type field-config sections.
 *
 * The Forms tab and the Field Library render the same sections, and before they
 * shared components each carried its own copy of these class strings — they had
 * already drifted on focus ring and disabled styling. One definition each, so
 * they cannot drift again.
 */

export const CONFIG_LABEL_CLASS = 'mb-1 block text-xs font-medium text-muted-foreground';

export const CONFIG_INPUT_CLASS =
  'w-full rounded-lg border border-border px-3 py-2 text-sm focus:border-cobalt focus:outline-none focus:ring-2 focus:ring-cobalt/20 disabled:cursor-not-allowed disabled:bg-muted';

export const CONFIG_PANEL_CLASS = 'space-y-3 rounded-xl border border-border bg-card p-3';
