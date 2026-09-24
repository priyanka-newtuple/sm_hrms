/**
 * ExtensionFieldPickerModal
 *
 * Picks the Field Library fields one picklist_multi option reveals, by hosting
 * the Methods editor's `FieldLibraryPanel` in a modal — the same browser, with
 * its search, type filter, pagination and multi-select, so there is only one
 * Field Library picker in the product.
 *
 * Each pick is snapshotted with `toFormField()` and stamped with the library id
 * it came from, which is what lets a form render an extended field without
 * resolving the library at runtime.
 */

import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { fieldLibrary } from '@/core/services/api';
import { getApiErrorMessage } from '@/core/services/api/client';
import type { ExtensionField, FieldWithVersion } from '@/core/types';
import FieldLibraryPanel from '../../methods/components/FieldLibraryPanel';
import { toFormField } from '../../fields/fieldLibraryUtils';
import { EXTENSION_DISALLOWED_TYPES } from '../constants';

type ExtensionFieldPickerModalProps = {
  /** The option these fields are revealed by, as the administrator sees it. */
  optionLabel: string;
  existingFields: ExtensionField[];
  canWrite: boolean;
  onAdd: (fields: ExtensionField[]) => void;
  onClose: () => void;
};

export default function ExtensionFieldPickerModal({
  optionLabel,
  existingFields,
  canWrite,
  onAdd,
  onClose,
}: ExtensionFieldPickerModalProps) {
  const [, setSearchParams] = useSearchParams();
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleAdd = async (libraryFieldIds: string[], picked: FieldWithVersion[]) => {
    setAdding(true);
    setError(null);
    try {
      // The panel hands over the entries it has already loaded, so the usual
      // pick costs no request at all. Anything it could not resolve is fetched.
      const byId = new Map(picked.map((entry) => [entry.identity.library_field_id, entry]));
      const missing = libraryFieldIds.filter((id) => !byId.has(id));
      for (const entry of await Promise.all(missing.map((id) => fieldLibrary.get(id)))) {
        byId.set(entry.identity.library_field_id, entry);
      }
      const entries = libraryFieldIds
        .map((id) => byId.get(id))
        .filter((entry): entry is FieldWithVersion => entry !== undefined);
      // The panel de-duplicates by library id, but two different library fields
      // can share a field key, and the key is where the entered value is
      // stored — so a colliding pick is reported rather than silently merged.
      const takenKeys = new Set(existingFields.map((field) => field.id));
      const added: ExtensionField[] = [];
      const skipped: string[] = [];
      for (const entry of entries) {
        const snapshot: ExtensionField = {
          ...toFormField(entry),
          library_field_id: entry.identity.library_field_id,
        };
        if (takenKeys.has(snapshot.id)) {
          skipped.push(entry.identity.name);
          continue;
        }
        takenKeys.add(snapshot.id);
        added.push(snapshot);
      }
      if (added.length > 0) onAdd(added);
      if (skipped.length > 0) {
        setError(`Already added under the key it uses: ${skipped.join(', ')}`);
        return;
      }
      onClose();
    } catch (e) {
      setError(getApiErrorMessage(e, 'Failed to add extended fields'));
    } finally {
      setAdding(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden rounded-xl bg-card shadow-xl">
        <div className="border-b border-border px-4 py-3">
          <h3 className="text-base font-semibold text-foreground">Add extended fields</h3>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Shown to the end user when <span className="font-medium text-foreground">{optionLabel}</span> is
            selected.
          </p>
        </div>
        {error && <p className="px-4 pt-3 text-xs text-destructive">{error}</p>}
        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          <FieldLibraryPanel
            existingFieldIds={existingFields.map((field) => field.library_field_id)}
            excludeTypes={EXTENSION_DISALLOWED_TYPES}
            adding={adding}
            canWrite={canWrite}
            collapsed={false}
            onToggleCollapsed={onClose}
            onAdd={(ids, picked) => void handleAdd(ids, picked)}
            onGoToFieldLibrary={() => setSearchParams({ tab: 'fields' }, { replace: false })}
            parentLabel="field"
          />
        </div>
      </div>
    </div>
  );
}
