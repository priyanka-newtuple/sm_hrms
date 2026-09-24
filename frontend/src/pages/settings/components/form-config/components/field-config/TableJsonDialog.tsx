/**
 * The raw `table_config` editor, for pasting a long column set in rather than
 * clicking one out in `TableFieldBuilder`.
 *
 * Exported as a hook because the two configurators open it from different
 * chrome — the Forms tab from a field's "···" menu, the Field Library from two
 * links under the form — but everything behind the trigger (mode, draft, parse
 * errors, Escape handling) is identical.
 */

import { useEffect, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import type { FormField } from '@/core/types';

type TableJsonMode = 'view' | 'edit';

const EMPTY_TABLE_CONFIG: FormField['table_config'] = {
  row_mode: 'dynamic',
  display_mode: 'grid',
  columns: [],
};

export function useTableJsonDialog(
  config: FormField['table_config'],
  onChange: (config: FormField['table_config']) => void,
  canWrite: boolean,
  fieldLabel: string,
  titleId: string,
) {
  const [mode, setMode] = useState<TableJsonMode | null>(null);
  const [draft, setDraft] = useState('');
  const [error, setError] = useState<string | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const close = () => {
    setMode(null);
    setError(null);
  };

  const open = (next: TableJsonMode) => {
    setMode(next);
    setDraft(JSON.stringify(config ?? EMPTY_TABLE_CONFIG, null, 2));
    setError(null);
  };

  useEffect(() => {
    if (!mode) return;
    const target = mode === 'edit' ? textareaRef.current : panelRef.current;
    target?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [mode]);

  const apply = () => {
    if (!canWrite) return;
    try {
      const parsed = JSON.parse(draft);
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
        setError('Table JSON must be an object.');
        return;
      }
      onChange(parsed as FormField['table_config']);
      close();
    } catch {
      setError('Invalid JSON.');
    }
  };

  const dialog = mode ? (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className="w-full max-w-3xl rounded-xl bg-card shadow-xl outline-none"
      >
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <div>
            <h3 id={titleId} className="text-base font-semibold text-foreground">
              {mode === 'edit' ? 'Edit table JSON' : 'View table JSON'}
            </h3>
            <p className="mt-0.5 text-xs text-muted-foreground">{fieldLabel} · table_config</p>
          </div>
          <button
            type="button"
            onClick={close}
            className="rounded-lg px-2 py-1 text-sm text-muted-foreground hover:bg-muted"
          >
            Close
          </button>
        </div>
        <div className="space-y-2 p-5">
          <textarea
            ref={textareaRef}
            value={draft}
            onChange={(event) => {
              setDraft(event.target.value);
              setError(null);
            }}
            readOnly={mode === 'view'}
            rows={18}
            spellCheck={false}
            className="w-full rounded-lg border border-border bg-muted/50 px-3 py-2 font-mono text-xs text-foreground outline-none read-only:cursor-default focus:border-cobalt focus:ring-2 focus:ring-cobalt"
          />
          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>
        <div className="flex items-center justify-end gap-2 border-t border-border px-5 py-4">
          <Button type="button" variant="secondary" onClick={close}>
            {mode === 'edit' ? 'Cancel' : 'Close'}
          </Button>
          {mode === 'edit' && (
            <Button type="button" variant="ghost" onClick={apply} disabled={!canWrite}>
              Apply JSON
            </Button>
          )}
        </div>
      </div>
    </div>
  ) : null;

  return { openTableJson: open, dialog };
}
