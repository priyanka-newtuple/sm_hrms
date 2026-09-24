import { useEffect, useMemo, useState } from 'react';
import { Filter, Loader2, Search, X } from 'lucide-react';
import { useLocation } from 'react-router-dom';

import { cn } from '@/lib/utils';
import {
  searchSourceRecords,
  type SourceRecordOption,
} from '../hooks/useSourcePickers';
import { useGlobalEntityFilter } from '../contexts/GlobalEntityFilterContext';
import { useSkin } from '../../skins';

const CLIENT_ROUTES = ['/workflows', '/pipeline', '/records', '/dashboard'];
const DEBOUNCE_MS = 250;
const MAX_SEARCH_RESULTS = 20;
const BLUR_TIMEOUT_MS = 120;

function isClientFacingRoute(pathname: string, extraRoutes: string[] = []): boolean {
  return [...CLIENT_ROUTES, ...extraRoutes].some(
    (route) => pathname === route || pathname.startsWith(`${route}/`),
  );
}

/**
 * Top-bar record picker for the global entity filter.
 * Searches the configured anchor entity type and updates GlobalEntityFilterContext.
 */
export default function GlobalEntityFilterSelector() {
  const location = useLocation();
  const { skin } = useSkin();
  const {
    settings,
    activeAnchorEntityId,
    activeAnchorLabel,
    setActiveAnchor,
    clearActiveAnchor,
  } = useGlobalEntityFilter();
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [options, setOptions] = useState<SourceRecordOption[]>([]);
  const [loading, setLoading] = useState(false);

  // Skin custom pages that opted in count as client-facing too, so a skin can
  // keep the filter on its own pages without the platform knowing their paths.
  const skinFilterRoutes = useMemo(
    () => (skin.customPages ?? []).filter((page) => page.showGlobalFilter).map((page) => page.path),
    [skin.customPages],
  );

  const visible = Boolean(
    settings.enabled &&
      settings.anchorEntityType &&
      isClientFacingRoute(location.pathname, skinFilterRoutes),
  );
  const placeholder = settings.anchorEntityType
    ? `Filter by ${settings.anchorEntityType}`
    : 'Filter records';
  const inputValue = open ? query : activeAnchorEntityId ? activeAnchorLabel : '';

  useEffect(() => {
    if (!visible || !open || !settings.anchorEntityType) return;
    setLoading(true);
    let cancelled = false;
    const timer = setTimeout(() => {
      searchSourceRecords(settings.anchorEntityType || '', query, MAX_SEARCH_RESULTS)
        .then((items) => {
          if (!cancelled) setOptions(items);
        })
        .catch((error) => {
          if (!cancelled) {
            console.error('Global entity search failed:', error);
            setOptions([]);
          }
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    }, DEBOUNCE_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [open, query, settings.anchorEntityType, visible]);

  const label = useMemo(
    () => activeAnchorLabel || activeAnchorEntityId || '',
    [activeAnchorEntityId, activeAnchorLabel],
  );

  if (!visible) return null;

  const pick = (option: SourceRecordOption) => {
    setActiveAnchor(option.entity_id, option.label);
    setQuery('');
    setOpen(false);
  };

  return (
    <div className="relative w-64 max-w-[32vw] shrink-0">
      <Filter
        className="pointer-events-none absolute left-2.5 top-1/2 z-10 h-4 w-4 -translate-y-1/2 opacity-70"
        aria-hidden="true"
      />
      <input
        type="text"
        role="combobox"
        aria-label={placeholder}
        aria-expanded={open}
        value={inputValue}
        placeholder={placeholder}
        autoComplete="off"
        onFocus={() => {
          setQuery('');
          setOpen(true);
        }}
        onBlur={() => setTimeout(() => setOpen(false), BLUR_TIMEOUT_MS)}
        onChange={(event) => setQuery(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Escape') setOpen(false);
          if (event.key === 'Enter' && options[0]) {
            event.preventDefault();
            pick(options[0]);
          }
        }}
        className={cn(
          'h-9 w-full rounded-xl border py-1.5 pl-8 pr-8 text-sm shadow-sm outline-none',
          'border-[color-mix(in_srgb,var(--header-foreground)_20%,transparent)]',
          'bg-[color-mix(in_srgb,var(--header-foreground)_8%,transparent)]',
          'text-[var(--header-foreground)] placeholder:text-[color-mix(in_srgb,var(--header-foreground)_62%,transparent)]',
          'focus:border-[color-mix(in_srgb,var(--header-foreground)_44%,transparent)]',
        )}
      />
      {activeAnchorEntityId && !open ? (
        <button
          type="button"
          aria-label={`Clear ${label}`}
          onClick={clearActiveAnchor}
          className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-0.5 opacity-70 hover:opacity-100"
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </button>
      ) : loading ? (
        <Loader2 className="absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin opacity-70" />
      ) : (
        <Search className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 opacity-60" />
      )}

      {open && (
        <div className="absolute right-0 z-50 mt-1 max-h-64 w-full overflow-auto rounded-xl border border-border bg-popover p-1 text-popover-foreground shadow-lg">
          {loading ? (
            <div className="px-3 py-2 text-sm text-muted-foreground">Searching…</div>
          ) : options.length === 0 ? (
            <div className="px-3 py-2 text-sm text-muted-foreground">No records found.</div>
          ) : (
            options.map((option) => (
              <button
                key={option.entity_id}
                type="button"
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => pick(option)}
                className="block w-full rounded-lg px-3 py-2 text-left text-sm hover:bg-accent"
              >
                <span className="block truncate">{option.label}</span>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}
