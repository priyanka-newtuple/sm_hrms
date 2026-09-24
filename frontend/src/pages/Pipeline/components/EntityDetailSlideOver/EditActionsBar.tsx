import { Check, Loader2, Save, Undo2 } from 'lucide-react';
import type { ReactElement } from 'react';

interface EditActionsBarProps {
  /** Set by any edit since the last save/undo — not diffed against the
   * seeded values, so a no-op edit (type then backspace) still counts. */
  isDirty: boolean;
  saving: boolean;
  /** Brief post-save confirmation; cleared by the parent after a short delay. */
  justSaved: boolean;
  /**
   * A real save attempt failed server-side — as opposed to a client-side
   * validation rejection, where nothing was ever sent and "Retry" would be
   * misleading. The specific message either way renders inline next to the
   * fields (not repeated here) — this bar is actions only.
   */
  saveFailed: boolean;
  onSave: () => void;
  onUndo: () => void;
}

/**
 * Explicit Save / Undo controls shown in the Details header once the user has
 * made an edit — nothing renders until then. There is no auto-save: Save only
 * persists on click, Undo discards the draft back to the last-saved data.
 */
export default function EditActionsBar({
  isDirty,
  saving,
  justSaved,
  saveFailed,
  onSave,
  onUndo,
}: EditActionsBarProps): ReactElement | null {
  if (isDirty || saving) {
    return (
      <div className="flex items-center gap-1.5">
        <button
          type="button"
          onClick={onUndo}
          disabled={saving}
          className="inline-flex items-center gap-1 rounded-lg border border-border bg-card px-2.5 py-1 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted disabled:opacity-50"
        >
          <Undo2 className="h-3 w-3" />
          Undo
        </button>
        <button
          type="button"
          onClick={onSave}
          disabled={saving}
          className="inline-flex items-center gap-1 rounded-lg bg-cobalt px-2.5 py-1 text-xs font-semibold text-white transition-colors hover:bg-cobalt/90 disabled:opacity-50"
        >
          {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
          {saving ? 'Saving…' : saveFailed ? 'Retry' : 'Save'}
        </button>
      </div>
    );
  }

  if (justSaved) {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs font-medium text-emerald-600 dark:text-emerald-400">
        <Check className="h-3 w-3" />
        Saved
      </span>
    );
  }

  return null;
}
