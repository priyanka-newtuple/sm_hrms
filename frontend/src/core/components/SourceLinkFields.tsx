import { useEffect, useState } from 'react';
import { Loader2, Search, X } from 'lucide-react';
import {
  searchSourceRecords,
  type SourcePicker,
  type SourceRecordOption,
} from '../hooks/useSourcePickers';

const SEARCH_LIMIT = 20;
const DEBOUNCE_MS = 300;

type ComboboxProps = {
  picker: SourcePicker;
  selectedId: string;
  onSelect: (entityId: string) => void;
  requireReference?: boolean;
};

function SourceLinkCombobox({ picker, selectedId, onSelect, requireReference = true }: ComboboxProps) {
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [options, setOptions] = useState<SourceRecordOption[]>([]);
  const [searching, setSearching] = useState(false);
  // Label of the picked record — options churn with every search, so the
  // selection's label must survive independently of the current result set.
  const [selectedLabel, setSelectedLabel] = useState('');

  const required = requireReference && picker.declaration.relation_type === 'REFERENCE';
  const defId = picker.declaration.relation_def_id;
  const providerName = picker.providerName;

  // Debounced server-side search while the list is open.
  useEffect(() => {
    if (!open) return;
    setSearching(true);
    let cancelled = false;
    const timer = setTimeout(() => {
      searchSourceRecords(providerName, query, SEARCH_LIMIT)
        .then((results) => {
          if (!cancelled) setOptions(results);
        })
        .catch(() => {
          if (!cancelled) setOptions([]);
        })
        .finally(() => {
          if (!cancelled) setSearching(false);
        });
    }, DEBOUNCE_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [open, query, providerName]);

  const handlePick = (option: SourceRecordOption) => {
    onSelect(option.entity_id);
    setSelectedLabel(option.label);
    setQuery('');
    setOpen(false);
  };

  const handleClear = () => {
    onSelect('');
    setSelectedLabel('');
  };

  return (
    <div className="mb-4">
      <label
        htmlFor={`source-${defId}`}
        className="mb-2 block text-sm font-medium text-foreground"
      >
        Link {providerName}
        {required ? (
          <span className="ml-1 text-destructive">*</span>
        ) : (
          <span className="ml-1 font-normal text-muted-foreground">(optional)</span>
        )}
      </label>

      <div className="relative">
        <Search
          className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
          aria-hidden="true"
        />
        <input
          id={`source-${defId}`}
          type="text"
          role="combobox"
          aria-expanded={open}
          aria-controls={`source-${defId}-listbox`}
          autoComplete="off"
          value={open ? query : (selectedId ? selectedLabel : '')}
          placeholder={`Search ${providerName} records…`}
          onFocus={() => {
            setQuery('');
            setOpen(true);
          }}
          onBlur={() => setOpen(false)}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Escape') setOpen(false);
            if (e.key === 'Enter') {
              e.preventDefault();
              if (open && !searching && options.length > 0) handlePick(options[0]);
            }
          }}
          className="w-full rounded-lg border border-border py-2 pl-9 pr-8 text-sm focus:border-cobalt focus:ring-2 focus:ring-cobalt"
        />
        {selectedId && !open && (
          <button
            type="button"
            aria-label={`Clear ${providerName} link`}
            onClick={handleClear}
            className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-0.5 text-muted-foreground hover:text-foreground"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        )}

        {open && (
          <div
            id={`source-${defId}-listbox`}
            role="listbox"
            className="absolute z-20 mt-1 max-h-64 w-full overflow-y-auto rounded-lg border border-border bg-card py-1 shadow-lg"
          >
            {searching ? (
              <p className="flex items-center gap-2 px-3 py-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                Searching…
              </p>
            ) : options.length === 0 ? (
              <p className="px-3 py-2 text-sm text-muted-foreground">
                {query.trim()
                  ? `No ${providerName} records match “${query}”`
                  : `No ${providerName} records found`}
              </p>
            ) : (
              <>
                {options.map((r) => (
                  <button
                    key={r.entity_id}
                    type="button"
                    role="option"
                    aria-selected={r.entity_id === selectedId}
                    // preventDefault keeps the input's blur from closing the list before the click lands
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => handlePick(r)}
                    className={`block w-full px-3 py-2 text-left text-sm hover:bg-accent/40 ${
                      r.entity_id === selectedId ? 'bg-primary/10 text-primary' : 'text-foreground'
                    }`}
                  >
                    {r.label}
                  </button>
                ))}
                {options.length === SEARCH_LIMIT && (
                  <p className="border-t border-border px-3 py-1.5 text-xs text-muted-foreground">
                    Top {SEARCH_LIMIT} matches — keep typing to narrow down
                  </p>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

type Props = {
  pickers: SourcePicker[];
  selections: Record<string, string>;
  onChange: (defId: string, entityId: string) => void;
  requireReference?: boolean;
};

/** One searchable "Link {provider}" picker per relation declaration targeting the entity type. */
export default function SourceLinkFields({ pickers, selections, onChange, requireReference = true }: Props) {
  if (pickers.length === 0) return null;
  return (
    <>
      {pickers.map((p) => (
        <SourceLinkCombobox
          key={p.declaration.relation_def_id}
          picker={p}
          selectedId={selections[p.declaration.relation_def_id] ?? ''}
          onSelect={(entityId) => onChange(p.declaration.relation_def_id, entityId)}
          requireReference={requireReference}
        />
      ))}
    </>
  );
}
