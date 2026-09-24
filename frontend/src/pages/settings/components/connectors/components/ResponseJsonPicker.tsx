import { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';

interface ResponseJsonPickerProps {
  data: unknown;
  onPickPath: (path: string) => void;
}

/**
 * Collapsible JSON tree. Clicking a leaf or array value emits its dotted path
 * so the user can auto-fill a response mapping row without typing.
 */
export default function ResponseJsonPicker({ data, onPickPath }: ResponseJsonPickerProps) {
  return (
    <div className="overflow-x-auto rounded-lg border border-border bg-muted/40 p-3 font-mono text-xs">
      <p className="mb-2 font-sans text-[11px] font-medium text-muted-foreground">
        Click any value to use its path in response mapping ↓
      </p>
      <JsonNode value={data} path="" onPickPath={onPickPath} />
    </div>
  );
}

interface JsonNodeProps {
  value: unknown;
  path: string;
  onPickPath: (path: string) => void;
}

function JsonNode({ value, path, onPickPath }: JsonNodeProps) {
  const [open, setOpen] = useState(true);

  if (Array.isArray(value)) {
    const wildcardPath = path ? `${path}[]` : '[]';
    return (
      <span>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="inline-flex items-center gap-0.5 text-info hover:underline"
        >
          {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
          [{value.length}]
        </button>
        {/* Wildcard shortcut: pick all items' sub-values */}
        {value.length > 0 && (
          <button
            type="button"
            title={`Use path: ${wildcardPath}`}
            onClick={() => onPickPath(wildcardPath)}
            className="ml-1 rounded bg-primary/10 px-1 text-[10px] text-primary hover:bg-primary/20"
          >
            [] all
          </button>
        )}
        {open && (
          <div className="ml-4 border-l border-border pl-3">
            {value.map((item, i) => (
              <div key={i} className="flex items-start gap-1">
                <span className="text-muted-foreground">{i}:</span>
                <JsonNode
                  value={item}
                  path={path ? `${path}[${i}]` : `[${i}]`}
                  onPickPath={onPickPath}
                />
              </div>
            ))}
          </div>
        )}
      </span>
    );
  }

  if (value !== null && typeof value === 'object') {
    return (
      <span>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="inline-flex items-center gap-0.5 text-warning hover:underline"
        >
          {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
          {'{…}'}
        </button>
        {open && (
          <div className="ml-4 border-l border-border pl-3">
            {Object.entries(value as Record<string, unknown>).map(([key, val]) => {
              const childPath = path ? `${path}.${key}` : key;
              return (
                <div key={key} className="flex items-start gap-1">
                  <span className="text-muted-foreground">{key}:</span>
                  <JsonNode value={val} path={childPath} onPickPath={onPickPath} />
                </div>
              );
            })}
          </div>
        )}
      </span>
    );
  }

  // Leaf — clickable
  const display =
    value === null ? 'null' : typeof value === 'string' ? `"${value}"` : String(value);
  const colorClass =
    value === null
      ? 'text-muted-foreground'
      : typeof value === 'string'
        ? 'text-success'
        : typeof value === 'boolean'
          ? 'text-info'
          : 'text-warning';

  return (
    <button
      type="button"
      title={path ? `Use path: ${path}` : undefined}
      onClick={() => path && onPickPath(path)}
      className={`${colorClass} rounded px-0.5 hover:bg-primary/10 hover:underline`}
    >
      {display}
    </button>
  );
}
