/**
 * FieldLibraryPanel
 *
 * The persistent Field Library browser for the Methods editor. Fields are
 * staged here and added to the method in one request, so the library stays
 * useful while the author reviews the selected field list on the right.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  Filter,
  Loader2,
  Plus,
  RefreshCw,
  Rows3,
  Search,
  SlidersHorizontal,
  X,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { fieldLibrary } from '@/core/services/api';
import { getApiErrorMessage } from '@/core/services/api/client';
import type { FieldType, FieldWithVersion } from '@/core/types';
import { FIELD_TYPES, FIELD_TYPE_LABELS } from '../../form-config/constants';

const PAGE_SIZE = 25;

interface FieldLibraryPanelProps {
  existingFieldIds: string[];
  /** Field types this caller cannot accept, hidden from the results and from
   *  the type filter. Omitted means every type is offered. */
  excludeTypes?: readonly FieldType[];
  adding: boolean;
  canWrite: boolean;
  collapsed: boolean;
  onToggleCollapsed: () => void;
  /** The picked ids, plus the entries the panel already holds for them, so a
   *  caller that needs a field's full shape does not have to re-fetch it. */
  onAdd: (libraryFieldIds: string[], entries: FieldWithVersion[]) => void;
  onGoToFieldLibrary: () => void;
  entity?: 'field' | 'step-object';
  parentLabel?: string;
}

export default function FieldLibraryPanel({
  existingFieldIds,
  excludeTypes,
  adding,
  canWrite,
  collapsed,
  onToggleCollapsed,
  onAdd,
  onGoToFieldLibrary,
  entity = 'field',
  parentLabel = 'form',
}: FieldLibraryPanelProps) {
  const isStepObject = entity === 'step-object';
  const itemLabel = isStepObject ? 'step object' : 'field';
  const itemLabelPlural = isStepObject ? 'step objects' : 'fields';
  const libraryTitle = isStepObject ? 'Step Objects' : 'Field Library';
  const [entries, setEntries] = useState<FieldWithVersion[]>([]);
  // Every entry this panel has loaded, across pages and searches. Selection
  // survives paging, so the current page alone cannot resolve every pick.
  const loadedEntries = useRef(new Map<string, FieldWithVersion>());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [appliedSearch, setAppliedSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState<FieldType | 'all'>('all');
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<string[]>([]);
  const requestId = useRef(0);
  const hasLoaded = useRef(false);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setAppliedSearch(search);
      setOffset(0);
    }, 250);
    return () => window.clearTimeout(timer);
  }, [search]);

  const load = useCallback(async () => {
    const id = ++requestId.current;
    const isInitialLoad = !hasLoaded.current;
    if (isInitialLoad) setLoading(true);
    setError(null);
    try {
      const res = await fieldLibrary.list({
        search: appliedSearch.trim() || undefined,
        fieldType: typeFilter === 'all' ? undefined : typeFilter,
        limit: PAGE_SIZE,
        offset,
      });
      if (id === requestId.current) {
        for (const entry of res.items) loadedEntries.current.set(entry.identity.library_field_id, entry);
        setEntries(res.items);
        setTotal(res.total);
      }
    } catch (e) {
      if (id === requestId.current) {
        setError(getApiErrorMessage(e, `Failed to load ${libraryTitle}`));
      }
    } finally {
      if (id === requestId.current) {
        hasLoaded.current = true;
        if (isInitialLoad) setLoading(false);
      }
    }
  }, [appliedSearch, libraryTitle, offset, typeFilter]);

  useEffect(() => {
    void load();
  }, [load]);

  const alreadyAdded = useMemo(() => new Set(existingFieldIds), [existingFieldIds]);

  // A successful add makes the selected ids part of the right-hand list. Keep
  // the panel selection in sync so stale selections cannot be submitted twice.
  useEffect(() => {
    setSelected((current) => {
      const next = current.filter((id) => !alreadyAdded.has(id));
      return next.length === current.length ? current : next;
    });
  }, [alreadyAdded]);

  const visible = useMemo(() => {
    const excluded = new Set(excludeTypes ?? []);
    // Excluding client-side rather than per request: the backend filters by a
    // single type, so an exclusion list can only be applied to the page it
    // returned. A page may therefore show fewer rows than `total` claims.
    return entries.filter(
      (entry) =>
        !entry.identity.is_archived && !excluded.has(entry.version.field_type as FieldType),
    );
  }, [entries, excludeTypes]);

  const toggle = (libraryFieldId: string) => {
    if (!canWrite || alreadyAdded.has(libraryFieldId) || adding) return;
    setSelected((current) =>
      current.includes(libraryFieldId)
        ? current.filter((id) => id !== libraryFieldId)
        : [...current, libraryFieldId],
    );
  };

  const clearFilters = () => {
    setSearch('');
    setTypeFilter('all');
  };

  const hasFilters = Boolean(search.trim()) || typeFilter !== 'all';
  const selectableTypes = useMemo(
    () => FIELD_TYPES.filter((option) => !(excludeTypes ?? []).includes(option.value)),
    [excludeTypes],
  );

  return (
    <aside
      className={`self-start overflow-hidden rounded-xl border border-border bg-card transition-all ${
        collapsed ? 'lg:w-[76px]' : ''
      }`}
    >
      {collapsed ? (
        <div className="flex h-12 items-center justify-center border-b border-border p-2">
          <button
            type="button"
            onClick={onToggleCollapsed}
            className="flex items-center gap-1 rounded-md px-2 py-1.5 text-xs font-medium text-primary transition-colors hover:bg-primary/10"
        title={`Expand ${libraryTitle}`}
            aria-label={`Expand ${libraryTitle}`}
          >
            <Plus className="h-3.5 w-3.5" />
            Add
          </button>
        </div>
      ) : (
        <div className="flex items-center justify-between border-b border-border px-2.5 py-2.5">
          <div className="flex min-w-0 items-center gap-2">
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
              <Rows3 className="h-3.5 w-3.5" />
            </div>
            <div className="min-w-0">
              <h3 className="truncate text-sm font-semibold text-foreground">{libraryTitle}</h3>
              <p className="text-[11px] text-muted-foreground">Choose {itemLabelPlural} to add</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onToggleCollapsed}
            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            title={`Collapse ${libraryTitle}`}
            aria-label={`Collapse ${libraryTitle}`}
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      {!collapsed && (
        <>
          <div className="space-y-2 border-b border-border p-3">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <input
                type="text"
                inputMode="search"
                value={search}
                onChange={(e) => {
                  setOffset(0);
                  setSearch(e.target.value);
                }}
                placeholder={`Search ${itemLabelPlural}…`}
                aria-label={`Search ${itemLabelPlural}`}
                className="h-9 w-full rounded-lg border border-border bg-background pl-9 pr-9 text-sm focus:border-cobalt focus:outline-none focus:ring-2 focus:ring-cobalt/20"
              />
              {search && (
                <button
                  type="button"
                  onClick={() => {
                    setOffset(0);
                    setSearch('');
                  }}
                  className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
                  aria-label="Clear search"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
            <div className="flex items-center gap-2">
              <div className="relative min-w-0 flex-1">
                <Filter className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                <select
                  value={typeFilter}
                  onChange={(e) => {
                    setOffset(0);
                    setTypeFilter(e.target.value as FieldType | 'all');
                  }}
                  aria-label={`Filter ${itemLabelPlural} by type`}
                  className="h-8 w-full appearance-none rounded-lg border border-border bg-background pl-8 pr-7 text-xs focus:border-cobalt focus:outline-none focus:ring-2 focus:ring-cobalt/20"
                >
                  <option value="all">All {itemLabel} types</option>
                  {selectableTypes.map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
                <ChevronDown className="pointer-events-none absolute right-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              </div>
              {hasFilters && (
                <button
                  type="button"
                  onClick={clearFilters}
                  className="shrink-0 text-xs font-medium text-primary hover:underline"
                >
                  Clear
                </button>
              )}
            </div>
          </div>

          <div className="flex items-center justify-between px-4 py-2.5 text-xs text-muted-foreground">
            <span className="flex items-center gap-1.5 font-medium">
              <SlidersHorizontal className="h-3.5 w-3.5" />
              {total} available
            </span>
            {selected.length > 0 && (
              <span className="rounded-full bg-primary/10 px-2 py-0.5 font-semibold text-primary">
                {selected.length} selected
              </span>
            )}
          </div>

          <div className="max-h-[570px] space-y-2 overflow-y-auto px-3 pb-3">
            {error && (
              <div className="rounded-lg border border-destructive/20 bg-destructive/10 p-3 text-xs text-destructive">
                <p>{error}</p>
                <button type="button" onClick={() => void load()} className="mt-2 inline-flex items-center gap-1 font-medium hover:underline">
                  <RefreshCw className="h-3 w-3" /> Try again
                </button>
              </div>
            )}

            {loading ? (
              <div className="flex flex-col items-center justify-center gap-2 py-12 text-xs text-muted-foreground">
                <Loader2 className="h-5 w-5 animate-spin" />
                Loading {itemLabelPlural}…
              </div>
            ) : visible.length === 0 ? (
              <div className="rounded-lg border border-dashed border-border px-3 py-10 text-center text-muted-foreground">
                <Rows3 className="mx-auto mb-2 h-8 w-8 text-muted-foreground/50" />
                <p className="text-xs font-medium text-foreground">
                  {!hasFilters && total === 0 ? `Your ${libraryTitle} is empty` : `No ${itemLabelPlural} match these filters`}
                </p>
                <p className="mt-1 text-xs">
                  {!hasFilters && total === 0 ? `Create a ${itemLabel} to start building this ${parentLabel.toLowerCase()}.` : 'Try a different search or type.'}
                </p>
                {!hasFilters && total === 0 && (
                  <Button variant="outline" size="sm" onClick={onGoToFieldLibrary} className="mt-3" icon={<ExternalLink className="h-3.5 w-3.5" />}>
                    Create a {itemLabel}
                  </Button>
                )}
              </div>
            ) : (
              visible.map((entry) => {
                const libraryFieldId = entry.identity.library_field_id;
                const isAdded = alreadyAdded.has(libraryFieldId);
                const isSelected = selected.includes(libraryFieldId);
                const fieldType = FIELD_TYPE_LABELS[entry.identity.field_type as FieldType] ?? entry.identity.field_type;
                return (
                  <button
                    key={libraryFieldId}
                    type="button"
                    onClick={() => toggle(libraryFieldId)}
                    disabled={isAdded || !canWrite || adding}
                    className={`group w-full rounded-lg border p-3 text-left transition-all ${
                      isAdded
                        ? 'cursor-not-allowed border-border bg-muted/40 opacity-55'
                        : isSelected
                          ? 'border-primary/40 bg-primary/10 shadow-sm'
                          : 'border-border bg-background hover:border-primary/35 hover:bg-accent/40'
                    } ${!canWrite ? 'cursor-not-allowed' : ''}`}
                  >
                    <div className="flex items-start gap-2.5">
                      <span className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded border ${
                        isSelected ? 'border-primary bg-primary text-primary-foreground' : 'border-border bg-card'
                      }`}>
                        {isSelected && <Check className="h-3 w-3" />}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-medium text-foreground">{entry.identity.name}</span>
                        <span className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
                          <code className="max-w-full truncate rounded bg-muted px-1 py-0.5 font-mono">{entry.identity.field_key}</code>
                          <span>·</span>
                          <span>{fieldType}</span>
                        </span>
                      </span>
                      {isAdded ? (
                        <span className="shrink-0 text-[11px] font-medium text-muted-foreground">Added</span>
                      ) : (
                        <Plus className={`mt-0.5 h-4 w-4 shrink-0 transition-colors ${isSelected ? 'text-primary' : 'text-muted-foreground/50 group-hover:text-primary'}`} />
                      )}
                    </div>
                  </button>
                );
              })
            )}
          </div>

          {total > PAGE_SIZE && (
            <div className="flex items-center justify-between border-t border-border px-3 py-2 text-[11px] text-muted-foreground">
              <span>{offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of {total}</span>
              <div className="flex items-center gap-1">
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  disabled={offset === 0 || loading}
                  onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                  title="Previous page"
                >
                  <ChevronLeft className="h-3.5 w-3.5" />
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  disabled={offset + PAGE_SIZE >= total || loading}
                  onClick={() => setOffset(offset + PAGE_SIZE)}
                  title="Next page"
                >
                  <ChevronRight className="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>
          )}

          <div className="space-y-2 border-t border-border bg-muted/30 p-3">
            <Button
              variant="primary"
              className="w-full justify-center"
              onClick={() =>
                onAdd(
                  selected,
                  selected
                    .map((id) => loadedEntries.current.get(id))
                    .filter((entry): entry is FieldWithVersion => entry !== undefined),
                )
              }
              disabled={!canWrite || adding || selected.length === 0}
              icon={adding ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
            >
              {adding ? `Adding ${itemLabelPlural}…` : selected.length > 0 ? `Add ${selected.length} selected` : `Select ${itemLabelPlural} to add`}
            </Button>
            <button
              type="button"
              onClick={onGoToFieldLibrary}
              className="flex w-full items-center justify-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
            >
              <ExternalLink className="h-3 w-3" /> Manage {libraryTitle}
            </button>
          </div>
        </>
      )}
    </aside>
  );
}
