import type { ReactNode } from 'react';
import { Search } from 'lucide-react';
import { useSkin } from '@/skins';
import type { FilterBarItem } from '@/skins';
import MultiSelectDropdown from '@/core/components/MultiSelectDropdown';
import { ASSIGNEE_FILTER_VALUE_MINE } from '../hooks/useBoardFilters';

interface BoardFilterBarProps {
  filters: FilterBarItem[];
  values: Record<string, string>;
  onChange: (key: string, value: string) => void;
  /**
   * 'default': renders as a flat Fragment (no wrapping element) — the
   * caller's own flex-wrap row owns line-breaking, so these filters sit as
   * plain siblings among the caller's other controls (e.g. view tabs)
   * instead of being wrapped as one atomic block.
   * 'toolbar': search + labeled filters + trailingSlot all sit in the
   * component's own single flex-wrap row (search grows, filters/export
   * cluster right) — used by `board.toolbarLayout: 'unified'`, where
   * BoardFilterBar is the sole child of its parent.
   */
  layout?: 'default' | 'toolbar';
  /**
   * Extra control rendered at the end of the row in 'toolbar' layout
   * (e.g. an export button), pinned to the right via `ml-auto`.
   * Ignored in 'default' layout.
   */
  trailingSlot?: ReactNode;
  /**
   * Extra control rendered before the search filter(s) — e.g. an assignee
   * avatar stack, when it should read as the row's leading "who" control
   * rather than trailing search. Rendered in both 'default' and 'toolbar'
   * layouts.
   */
  beforeSearchSlot?: ReactNode;
  /**
   * Extra control rendered right after the search filter(s), before any
   * other configured filters (e.g. the "Filters (N)" customize-filters
   * picker). Rendered in both 'default' and 'toolbar' layouts.
   */
  afterSearchSlot?: ReactNode;
  /**
   * Extra control rendered after the configured filters, before `trailingSlot`
   * (e.g. a "Hide Done" visibility toggle) — a true filter-bar slot rather
   * than a sibling of the whole bar, so it wraps together with the other
   * filter chips instead of being pushed onto its own line when they grow.
   */
  afterFiltersSlot?: ReactNode;
}

// w-full: without it, a native <select> renders at its own narrow intrinsic
// width inside its fixed-width wrapper div, leaving dead space in the rest
// of that column before the next filter starts — looks like an oversized gap.
// rounded-lg matches every other toolbar control (buttons, multiselect chips,
// TOOLBAR_SELECT_CLASS below) for one consistent corner radius across the row.
const INPUT_CLASS =
  'h-9 w-full rounded-lg border border-border bg-muted/50 px-3 text-sm text-foreground ' +
  'focus:border-cobalt/40 focus:outline-none focus:ring-2 focus:ring-cobalt/10';

/** Toolbar-layout select: bordered white card with a soft shadow, no visible
 *  outline ring — matches a compact single-row toolbar look. */
const TOOLBAR_SELECT_CLASS =
  'h-11 w-full rounded-lg shadow-deep bg-card px-3 text-sm text-foreground ' +
  'outline-none transition focus:border-cobalt/40';

/** Renders the skin-configured filter bar above the Kanban / List tabs. */
export default function BoardFilterBar({
  filters,
  values,
  onChange,
  layout = 'default',
  trailingSlot,
  beforeSearchSlot,
  afterSearchSlot,
  afterFiltersSlot,
}: BoardFilterBarProps) {
  const { skin } = useSkin();

  // Slots are independent of skin-configured filters — a workflow with no
  // filterBar config at all should still show them, not lose them silently.
  if (!filters.length && !beforeSearchSlot && !afterSearchSlot && !afterFiltersSlot && !trailingSlot) return null;

  const isToolbar = layout === 'toolbar';
  const searchFilters = filters.filter((f) => f.type === 'search');
  const otherFilters = filters.filter((f) => f.type !== 'search');

  // Always wraps the control in a width-constrained box — without it, a
  // control like MultiSelectDropdown (which sets `w-full` on its own root)
  // has nothing to constrain it, so `w-full` resolves against the whole flex
  // row: alone on a wrapped line, it balloons to fill that entire line and
  // shoves any sibling (e.g. the "Hide Done" toggle) onto the next line.
  function withToolbarLabel(filter: FilterBarItem, wrapperClassName: string, control: ReactNode): ReactNode {
    if (!isToolbar) {
      return (
        <div key={filter.key} className={wrapperClassName}>
          {control}
        </div>
      );
    }
    return (
      <div key={filter.key} className={wrapperClassName}>
        <label className="block px-0.5 text-xs font-medium text-muted-foreground">{filter.label}</label>
        {control}
      </div>
    );
  }

  function renderSearchFilter(filter: FilterBarItem, wrapperClassName: string): ReactNode {
    return (
      <div key={filter.key} className={`relative ${isToolbar ? 'mt-4 ' : ''}${wrapperClassName}`}>
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <input
          type="search"
          placeholder={filter.placeholder ?? filter.label}
          value={values[filter.key] ?? ''}
          onChange={(e) => onChange(filter.key, e.target.value)}
          className={
            isToolbar
              ? 'h-11 w-full rounded-lg shadow-deep bg-card pl-10 pr-3 text-sm text-foreground outline-none transition focus:border-cobalt/40'
              : 'h-9 w-full rounded-lg border border-border bg-muted/50 pl-8 pr-3 text-sm text-foreground placeholder:text-muted-foreground focus:border-cobalt/40 focus:outline-none focus:ring-2 focus:ring-cobalt/10'
          }
        />
      </div>
    );
  }

  function renderSelectFilter(filter: FilterBarItem, wrapperClassName: string): ReactNode {
    const options =
      (filter.staticListKey ? skin.staticLists[filter.staticListKey] : null) ??
      filter.staticOptions ??
      [];

    return withToolbarLabel(
      filter,
      wrapperClassName,
      <select
        key={isToolbar ? undefined : filter.key}
        value={values[filter.key] ?? ''}
        onChange={(e) => onChange(filter.key, e.target.value)}
        className={isToolbar ? TOOLBAR_SELECT_CLASS : INPUT_CLASS}
      >
        <option value="">All {filter.label.toLowerCase()}</option>
        {options.map((opt, index) => (
          <option key={opt} value={opt}>
            {filter.staticOptionLabels?.[index] ?? opt}
          </option>
        ))}
      </select>,
    );
  }

  function renderMultiSelectFilter(filter: FilterBarItem, wrapperClassName: string): ReactNode {
    const options =
      (filter.staticListKey ? skin.staticLists[filter.staticListKey] : null) ??
      filter.staticOptions ??
      [];
    // Stored comma-joined in the URL (see index.tsx's `fieldFilters` builder,
    // which splits it back into the OR'd list the backend accepts) — same
    // pattern as assignee_ids/exclude_states elsewhere on this page.
    const selected = values[filter.key] ? values[filter.key].split(',').filter(Boolean) : [];

    return withToolbarLabel(
      filter,
      wrapperClassName,
      <MultiSelectDropdown
        key={isToolbar ? undefined : filter.key}
        options={options}
        value={selected}
        onChange={(next) => onChange(filter.key, next.join(','))}
        placeholder={`All ${filter.label.toLowerCase()}`}
        chipsLayout="scroll"
        chipsHeightClassName={isToolbar ? 'h-11' : 'h-9'}
      />,
    );
  }

  function renderDateRangeFilter(filter: FilterBarItem, wrapperClassName: string): ReactNode {
    return withToolbarLabel(
      filter,
      wrapperClassName,
      <select
        key={isToolbar ? undefined : filter.key}
        value={values[filter.key] ?? ''}
        onChange={(e) => onChange(filter.key, e.target.value)}
        className={isToolbar ? TOOLBAR_SELECT_CLASS : INPUT_CLASS}
      >
        <option value="">All time</option>
        <option value="today">Today</option>
        <option value="7d">Last 7 days</option>
        <option value="30d">Last 30 days</option>
        <option value="90d">Last 90 days</option>
      </select>,
    );
  }

  function renderAssigneeFilter(filter: FilterBarItem, wrapperClassName: string): ReactNode {
    return withToolbarLabel(
      filter,
      wrapperClassName,
      <select
        key={isToolbar ? undefined : filter.key}
        value={values[filter.key] ?? ''}
        onChange={(e) => onChange(filter.key, e.target.value)}
        className={isToolbar ? TOOLBAR_SELECT_CLASS : INPUT_CLASS}
      >
        <option value="">All {filter.label.toLowerCase()}</option>
        <option value={ASSIGNEE_FILTER_VALUE_MINE}>Assigned to me</option>
      </select>,
    );
  }

  function renderFilter(filter: FilterBarItem, wrapperClassName: string): ReactNode {
    switch (filter.type) {
      case 'search':
        return renderSearchFilter(filter, wrapperClassName);
      case 'select':
        return renderSelectFilter(filter, wrapperClassName);
      case 'daterange':
        return renderDateRangeFilter(filter, wrapperClassName);
      case 'assignee':
        return renderAssigneeFilter(filter, wrapperClassName);
      case 'multiselect':
        return renderMultiSelectFilter(filter, wrapperClassName);
      default:
        return null;
    }
  }

  if (isToolbar) {
    return (
      <div className="flex flex-1 flex-wrap items-center gap-2.5">
        {beforeSearchSlot && <div className="mt-4">{beforeSearchSlot}</div>}
        {searchFilters.map((f) => renderFilter(f, 'min-w-[280px] flex-1'))}
        {afterSearchSlot && <div className="mt-4">{afterSearchSlot}</div>}
        {otherFilters.map((f) => renderFilter(f, 'min-w-40'))}
        {afterFiltersSlot && <div className="mt-4">{afterFiltersSlot}</div>}
        {trailingSlot && <div className="ml-auto mt-4">{trailingSlot}</div>}
      </div>
    );
  }

  // No wrapping <div> here: this renders directly into the caller's own
  // flex-wrap row (alongside e.g. view tabs) as flat sibling items. A second,
  // independently-wrapping flex container around just these filters caused
  // the whole block to be treated as one atomic item by the outer row's
  // line-breaking — so it got pushed onto its own line in full even when
  // individual filters would have fit in the space left on the first line.
  // A thin vertical rule between logical clusters (beforeSearchSlot / search
  // / afterSearchSlot / the configured filters) — at a uniform gap-2 with no
  // boundary, those clusters read as one indiscriminate row of controls
  // instead of grouped sections.
  // hidden below sm: on a narrow/mobile viewport the row stacks one control
  // per line, so a divider meant to separate two same-line neighbors instead
  // wraps alone onto its own line — a stray mark with nothing to separate.
  function divider(key: string): ReactNode {
    return <div key={key} className="hidden h-6 w-px shrink-0 self-center bg-border sm:block" aria-hidden />;
  }

  const hasSearch = searchFilters.length > 0;

  return (
    <>
      {beforeSearchSlot}
      {beforeSearchSlot && hasSearch && divider('divider-before-search')}
      {/* min-w-[180px] keeps the placeholder ("Search this workflow…")
          readable instead of clipping it; flex-1/max-w-xs lets it use
          spare room on a wide row without growing unbounded. */}
      {searchFilters.map((f) => renderFilter(f, 'min-w-[180px] max-w-xs flex-1'))}
      {afterSearchSlot && (hasSearch || beforeSearchSlot) && divider('divider-search')}
      {afterSearchSlot}
      {otherFilters.length > 0 && (afterSearchSlot || hasSearch || beforeSearchSlot) && divider('divider-filters')}
      {otherFilters.map((f) => renderFilter(f, 'w-52'))}
      {afterFiltersSlot}
    </>
  );
}
