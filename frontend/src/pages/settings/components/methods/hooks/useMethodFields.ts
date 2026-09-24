/**
 * useMethodFields
 *
 * A method's field list: adding fields picked from the Field Library, editing
 * the method's own view of a field (label, placeholder, required), reordering
 * and removing. Mirrors the Forms tab's `useFormFields`, including its
 * no-dirty-buffer contract — every mutation is an immediate PUT.
 *
 * A method never defines a field's type or settings; those come from the Field
 * Library version each entry pins. So there is no field editor here, only a
 * picker, which is the whole difference between this and the Forms tab.
 */

import { useCallback, useMemo, useState } from 'react';
import { arrayMove } from '@dnd-kit/sortable';
import { methodLibrary } from '@/core/services/api';
import { getApiErrorMessage } from '@/core/services/api/client';
import type { MethodFieldInput, MethodVersionField, MethodWithFields } from '@/core/types';

/** The method's own editable view of one listed field. Type and settings are
 *  deliberately absent: they belong to the pinned Field Library version. */
export interface MethodFieldDraft {
  index: number;
  label: string;
  placeholder: string;
  required: boolean;
}

/** The API takes the list the method should now have, not a delta, so every
 *  mutation rebuilds it. `position` is re-derived from array order rather than
 *  trusted from the incoming rows, so a reorder is expressed by the array.
 *
 *  `version_id` carries each field's *existing* pin (`field_version_id`)
 *  forward. Without it, omitting the version re-pins to the field's current
 *  latest, so a label edit or reorder would silently move a field a user had
 *  deliberately pinned to an older version — the one thing pinning exists to
 *  prevent. Repinning is only ever explicit, via `repinField`. */
function toInputs(fields: MethodVersionField[]): MethodFieldInput[] {
  return fields.map((field, index) => ({
    library_field_id: field.library_field_id,
    version_id: field.field_version_id,
    label: field.label ?? null,
    placeholder: field.placeholder ?? null,
    required: field.required,
    position: index,
    // Inheritance markers ride along unchanged: the API replaces the whole
    // list, so leaving these out would silently turn an inherited field back
    // into an owned one on the next reorder or label edit.
    inherit_from: field.inherit_from ?? null,
    ownership: field.ownership ?? null,
    source_entity_type: field.source_entity_type ?? null,
    source_field_key: field.source_field_key ?? null,
  }));
}

/** What the "Add from related entity" picker hands back: which Field Library
 *  field to list, and which related record field it should read from. */
export interface InheritedFieldPick {
  libraryFieldId: string;
  label: string | null;
  sourceEntityType: string;
  sourceFieldKey: string;
}

export function useMethodFields(
  selectedMethod: MethodWithFields | null,
  onMethodUpdated: (updated: MethodWithFields) => void,
  onError: (message: string) => void,
  entityLower = 'form',
) {
  const [editingField, setEditingField] = useState<MethodFieldDraft | null>(null);
  const [savingField, setSavingField] = useState(false);
  const [reorderingIndex, setReorderingIndex] = useState<number | null>(null);
  const [pendingDeleteIndex, setPendingDeleteIndex] = useState<number | null>(null);
  const [repinningLinkId, setRepinningLinkId] = useState<string | null>(null);

  const currentFields = useMemo(
    () => [...(selectedMethod?.fields ?? [])].sort((a, b) => a.position - b.position),
    [selectedMethod],
  );

  const pendingDeleteField =
    pendingDeleteIndex !== null ? (currentFields[pendingDeleteIndex] ?? null) : null;

  /** The single choke point: replaces the whole list, which creates a new
   *  method version server-side, then hands back the resolved result so the
   *  caller sees the new version number and re-pinned field shapes. */
  const saveFields = useCallback(
    async (fields: MethodFieldInput[]) => {
      if (!selectedMethod) return false;
      try {
        const updated = await methodLibrary.replaceFields(selectedMethod.identity.method_id, {
          fields,
          connector_id: selectedMethod.version.connector_id ?? null,
        });
        onMethodUpdated(updated);
        return true;
      } catch (e) {
        onError(getApiErrorMessage(e, `Failed to save the ${entityLower}’s fields`));
        return false;
      }
    },
    [selectedMethod, onMethodUpdated, onError, entityLower],
  );

  /** Appends fields chosen in the Field Library picker. Each is sent by
   *  `library_field_id` only — the backend resolves the version pin from that
   *  field's current latest version, so the method captures the shape the
   *  author was looking at. */
  const addLibraryFields = useCallback(
    async (libraryFieldIds: string[]) => {
      if (!selectedMethod || libraryFieldIds.length === 0) return;
      setSavingField(true);
      const existing = toInputs(currentFields);
      const additions: MethodFieldInput[] = libraryFieldIds.map((libraryFieldId, i) => ({
        library_field_id: libraryFieldId,
        label: null,
        placeholder: null,
        required: false,
        position: existing.length + i,
      }));
      await saveFields([...existing, ...additions]);
      setSavingField(false);
    },
    [selectedMethod, currentFields, saveFields],
  );

  /** Appends one field that inherits its value from a related record. The
   *  field is listed like any other Field Library pick, plus the ownership
   *  marker and its source; publish then pins it into only the workflows that
   *  use this block, and the record shows it read-only. */
  const addInheritedField = useCallback(
    async (pick: InheritedFieldPick) => {
      if (!selectedMethod) return false;
      setSavingField(true);
      const existing = toInputs(currentFields);
      const ok = await saveFields([
        ...existing,
        {
          library_field_id: pick.libraryFieldId,
          label: pick.label,
          placeholder: null,
          required: false,
          position: existing.length,
          ownership: 'inherited',
          source_entity_type: pick.sourceEntityType,
          source_field_key: pick.sourceFieldKey,
        },
      ]);
      setSavingField(false);
      return ok;
    },
    [selectedMethod, currentFields, saveFields],
  );

  const startEditField = useCallback(
    (index: number) => {
      const field = currentFields[index];
      if (!field) return;
      setEditingField({
        index,
        label: field.label ?? '',
        placeholder: field.placeholder ?? '',
        required: field.required,
      });
    },
    [currentFields],
  );

  const cancelEditField = useCallback(() => setEditingField(null), []);

  const saveEditedField = useCallback(async () => {
    if (!editingField) return;
    const target = currentFields[editingField.index];
    // The list can move under an open editor (another tab, a concurrent
    // reorder), and silently writing to whatever now sits at that index would
    // relabel the wrong field.
    if (!target) {
      onError('That field was removed while you were editing it.');
      setEditingField(null);
      return;
    }
    setSavingField(true);
    const next = toInputs(currentFields);
    next[editingField.index] = {
      ...next[editingField.index],
      label: editingField.label.trim() || null,
      placeholder: editingField.placeholder.trim() || null,
      required: editingField.required,
    };
    const ok = await saveFields(next);
    setSavingField(false);
    if (ok) setEditingField(null);
  }, [editingField, currentFields, saveFields, onError]);

  const reorderFields = useCallback(
    async (fromIndex: number, toIndex: number) => {
      setReorderingIndex(fromIndex);
      const reordered = arrayMove([...currentFields], fromIndex, toIndex);
      await saveFields(toInputs(reordered));
      setReorderingIndex(null);
    },
    [currentFields, saveFields],
  );

  /** Repin one field to a different version of that same field. This is a
   *  dedicated endpoint, not a field-list rewrite, so the other fields' pins are
   *  untouched. It still creates a new method version, and the resolved result
   *  carries the new version's field rows (with fresh link ids). */
  const repinField = useCallback(
    async (linkId: string, versionId: string) => {
      if (!selectedMethod) return false;
      setRepinningLinkId(linkId);
      try {
        const updated = await methodLibrary.repinField(
          selectedMethod.identity.method_id,
          linkId,
          versionId,
        );
        onMethodUpdated(updated);
        return true;
      } catch (e) {
        onError(getApiErrorMessage(e, 'Failed to change the field’s version'));
        return false;
      } finally {
        setRepinningLinkId(null);
      }
    },
    [selectedMethod, onMethodUpdated, onError],
  );

  /** Attach a connector (making this a custom form) or clear it. A connector
   *  and fields are mutually exclusive server side, so attaching empties the
   *  list: the form is whatever the connector returns per record. */
  const setConnector = useCallback(
    async (connectorId: string | null) => {
      if (!selectedMethod) return false;
      try {
        const updated = await methodLibrary.replaceFields(selectedMethod.identity.method_id, {
          fields: connectorId ? [] : toInputs(selectedMethod.fields),
          connector_id: connectorId,
        });
        onMethodUpdated(updated);
        return true;
      } catch (e) {
        onError(getApiErrorMessage(e, 'Failed to change the data source'));
        return false;
      }
    },
    [selectedMethod, onMethodUpdated, onError],
  );

  const requestDeleteField = useCallback((index: number) => setPendingDeleteIndex(index), []);
  const cancelDeleteField = useCallback(() => setPendingDeleteIndex(null), []);

  const confirmDeleteField = useCallback(async () => {
    if (pendingDeleteIndex === null) return;
    setSavingField(true);
    const remaining = currentFields.filter((_, i) => i !== pendingDeleteIndex);
    await saveFields(toInputs(remaining));
    setSavingField(false);
    setPendingDeleteIndex(null);
    setEditingField(null);
  }, [pendingDeleteIndex, currentFields, saveFields]);

  return {
    currentFields,
    editingField,
    setEditingField,
    savingField,
    reorderingIndex,
    pendingDeleteIndex,
    pendingDeleteField,
    repinningLinkId,
    repinField,
    addLibraryFields,
    addInheritedField,
    startEditField,
    cancelEditField,
    saveEditedField,
    reorderFields,
    requestDeleteField,
    cancelDeleteField,
    confirmDeleteField,
    setConnector,
  };
}
