/**
 * MethodFieldVersionDialog
 *
 * Repins one method field to a different version of that same Field Library
 * field. A method field stays pinned to the version it was added at, even after
 * the field gets newer versions — this dialog is the deliberate, explicit way to
 * move that pin, mirroring how a form repins a field. Choosing a version and
 * confirming produces a new method version server-side.
 */

import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { fieldLibrary } from '@/core/services/api';
import { getApiErrorMessage } from '@/core/services/api/client';
import type { FieldVersion, MethodVersionField } from '@/core/types';

interface VersionOptionRowProps {
  version: FieldVersion;
  isCurrent: boolean;
  isSelected: boolean;
  disabled: boolean;
  onSelect: () => void;
}

/** One selectable version in the picker: a radio dot, the version number with
 *  "current pin" / "latest" badges, and the version's field type + description. */
function VersionOptionRow({
  version,
  isCurrent,
  isSelected,
  disabled,
  onSelect,
}: VersionOptionRowProps) {
  return (
    <button
      type="button"
      onClick={onSelect}
      disabled={disabled}
      className={`flex w-full items-center gap-3 rounded-lg border px-3 py-2.5 text-left transition-colors disabled:opacity-60 ${
        isSelected ? 'border-primary/40 bg-primary/5' : 'border-border hover:bg-muted/50'
      }`}
    >
      <span
        className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full border ${
          isSelected ? 'border-primary' : 'border-border'
        }`}
      >
        {isSelected && <span className="h-2 w-2 rounded-full bg-primary" />}
      </span>
      <span className="flex-1 min-w-0">
        <span className="flex items-center gap-2">
          <span className="text-sm font-medium text-foreground">v{version.version}</span>
          {isCurrent && (
            <span className="rounded-full border border-border bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
              current pin
            </span>
          )}
          {version.is_latest && (
            <span className="rounded-full border border-info/30 bg-info-subtle px-1.5 py-0.5 text-[10px] font-medium text-info">
              latest
            </span>
          )}
        </span>
        <span className="mt-0.5 block truncate text-xs text-muted-foreground">
          {version.field_type}
          {version.description ? ` · ${version.description}` : ''}
        </span>
      </span>
    </button>
  );
}

interface MethodFieldVersionDialogProps {
  field: MethodVersionField;
  busy: boolean;
  onRepin: (versionId: string) => void;
  onClose: () => void;
  entityLabel?: string;
  libraryItemTitle?: string;
}

export default function MethodFieldVersionDialog({
  field,
  busy,
  onRepin,
  onClose,
  entityLabel = 'Form',
  libraryItemTitle = 'Field',
}: MethodFieldVersionDialogProps) {
  const [versions, setVersions] = useState<FieldVersion[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Start on the version currently pinned, so confirming without a change is a
  // no-op the button disables rather than a wasteful re-pin.
  const [selectedId, setSelectedId] = useState<string>(field.field_version_id);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const res = await fieldLibrary.listVersions(field.library_field_id);
        if (cancelled) return;
        // Newest first, so the latest version and the likely target sit on top.
        setVersions([...res.items].sort((a, b) => b.version - a.version));
      } catch (e) {
        if (!cancelled) setError(getApiErrorMessage(e, 'Failed to load field versions'));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [field.library_field_id]);

  const fieldName = field.label?.trim() || field.field_key;
  const itemLower = libraryItemTitle.toLowerCase();
  const changed = selectedId !== field.field_version_id;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="presentation"
    >
      <div
        className="w-full max-w-md rounded-xl bg-card p-6 shadow-xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="method-field-version-title"
      >
        <h3
          id="method-field-version-title"
          className="mb-1 text-lg font-semibold text-foreground"
        >
          Change {itemLower} version
        </h3>
        <p className="mb-4 text-sm text-muted-foreground">
          Pick which version of <span className="font-medium text-foreground">{fieldName}</span> this{' '}
          {entityLabel.toLowerCase()} pins. Changing it creates a new {entityLabel.toLowerCase()}{' '}
          version; other {itemLower}s keep their pins.
        </p>

        {error && (
          <div className="mb-3 rounded-lg border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive">
            {error}
          </div>
        )}

        {!versions && !error ? (
          <div className="flex items-center justify-center py-10 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
          </div>
        ) : (
          <div className="max-h-72 space-y-1.5 overflow-y-auto">
            {versions?.map((version) => (
              <VersionOptionRow
                key={version.version_id}
                version={version}
                isCurrent={version.version_id === field.field_version_id}
                isSelected={version.version_id === selectedId}
                disabled={busy}
                onSelect={() => setSelectedId(version.version_id)}
              />
            ))}
          </div>
        )}

        <div className="mt-5 flex items-center justify-end gap-3">
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button
            variant="ghost"
            onClick={() => onRepin(selectedId)}
            disabled={busy || !changed || !versions}
          >
            {busy ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : null}
            {busy ? 'Repinning…' : 'Repin to this version'}
          </Button>
        </div>
      </div>
    </div>
  );
}
