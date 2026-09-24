/**
 * EntityTypeTagPicker
 *
 * Picks the entity types a Method Block is offered on: a removable chip per
 * picked type, plus a type-ahead that narrows the remaining ones. Deliberately
 * not a checkbox list — an org can register any number of entity types, and
 * rendering all of them at once stops being usable well before that.
 *
 * Selection only. Persisting a change is the caller's job, via onChange.
 */

import { useMemo, useRef, useState } from 'react';
import { X } from 'lucide-react';

/** Suggestions shown at once. Enough to browse, short enough not to be a wall. */
const MAX_SUGGESTIONS = 8;

interface EntityTypeTagPickerProps {
  /** Every entity type registered in the org. */
  available: string[];
  /** The ones currently tagged on this method. */
  selected: string[];
  disabled?: boolean;
  onChange: (next: string[]) => void;
  /** True (Forms) replaces the current tag instead of adding alongside it —
   *  Forms don't support multiple linked entity types yet. False (Composite
   *  Blocks) keeps the original add-alongside behavior. Required rather than
   *  defaulted so every call site states its mode explicitly. */
  singleSelect: boolean;
}

export default function EntityTypeTagPicker({
  available,
  selected,
  disabled = false,
  onChange,
  singleSelect,
}: EntityTypeTagPickerProps) {
  const [query, setQuery] = useState('');
  const [focused, setFocused] = useState(false);
  const blurTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const suggestions = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const picked = new Set(selected);
    return available
      .filter((name) => !picked.has(name))
      .filter((name) => !needle || name.toLowerCase().includes(needle))
      .slice(0, MAX_SUGGESTIONS);
  }, [available, query, selected]);

  const add = (name: string) => {
    if (selected.includes(name)) return;
    onChange(singleSelect ? [name] : [...selected, name]);
    // Picking the only allowed type unmounts the input below (no DOM blur
    // fires, since the suggestion's onMouseDown preempts it) — clear the
    // open-dropdown flag now so a later remove doesn't remount it expanded.
    if (singleSelect) setFocused(false);
    setQuery('');
  };

  const remove = (name: string) => onChange(selected.filter((item) => item !== name));

  return (
    <div data-testid="method-entity-types">
      {selected.length > 0 && (
        <div className="mb-1.5 flex flex-wrap gap-1">
          {selected.map((name) => (
            <span
              key={name}
              data-testid="entity-type-chip"
              className="inline-flex items-center gap-1 rounded-md bg-muted px-2 py-0.5 text-xs text-foreground"
            >
              {name}
              {!disabled && (
                <button
                  type="button"
                  aria-label={`Remove ${name}`}
                  onClick={() => remove(name)}
                  className="rounded text-muted-foreground hover:text-foreground"
                >
                  <X className="h-3 w-3" />
                </button>
              )}
            </span>
          ))}
        </div>
      )}

      {/* Single-select: once a type is tagged, remove it before picking another
          rather than exposing an "add another" affordance that implies more. */}
      {(!singleSelect || selected.length === 0) && (
        <div className="relative">
          <input
            type="text"
            value={query}
            disabled={disabled}
            onChange={(e) => setQuery(e.target.value)}
            onFocus={() => {
              if (blurTimer.current) clearTimeout(blurTimer.current);
              setFocused(true);
            }}
            // Deferred so a click on a suggestion lands before the list unmounts.
            onBlur={() => {
              blurTimer.current = setTimeout(() => setFocused(false), 150);
            }}
            placeholder={selected.length ? 'Add another…' : 'Search entity types…'}
            aria-label="Search entity types"
            className="h-9 w-full rounded-lg border border-border px-3 text-sm focus:border-cobalt focus:outline-none focus:ring-2 focus:ring-cobalt/20 disabled:opacity-60"
          />

          {focused && !disabled && (
            <div className="absolute left-0 right-0 top-full z-20 mt-1 overflow-hidden rounded-lg border border-border bg-card shadow-lg">
              {suggestions.length === 0 ? (
                <p className="px-3 py-2 text-xs text-muted-foreground">
                  {query.trim() ? 'No matching entity types' : 'All entity types are tagged'}
                </p>
              ) : (
                <ul className="max-h-56 overflow-y-auto py-1">
                  {suggestions.map((name) => (
                    <li key={name}>
                      <button
                        type="button"
                        data-testid="entity-type-suggestion"
                        onMouseDown={(e) => e.preventDefault()}
                        onClick={() => add(name)}
                        className="block w-full truncate px-3 py-1.5 text-left text-sm text-foreground hover:bg-muted"
                      >
                        {name}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
