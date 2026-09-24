import { useState, useCallback } from 'react';
import { picklists as picklistsApi } from '../../../../../core/services/api';
import type { Picklist, PicklistUpdateRequest } from '../../../../../core/types';
import type { EditingPicklist } from '../types';

const autoValueFromLabel = (label: string): string => label.toLowerCase().replace(/\s+/g, '_');

export function usePicklists() {
  const [picklists, setPicklists] = useState<Picklist[]>([]);
  const [editingPicklist, setEditingPicklist] = useState<EditingPicklist | null>(null);
  const [savingPicklist, setSavingPicklist] = useState(false);
  const [deletingPicklist, setDeletingPicklist] = useState<string | null>(null);

  const fetchPicklists = useCallback(async () => {
    try {
      const result = await picklistsApi.list();
      setPicklists(result.items);
    } catch {
      setPicklists([]);
    }
  }, []);

  const handleCreatePicklist = useCallback(() => {
    setEditingPicklist({ id: '', name: '', options: [{ value: '', label: '' }], isNew: true });
  }, []);

  const handleEditPicklist = useCallback((picklist: Picklist) => {
    setEditingPicklist({
      id: picklist.id,
      name: picklist.name,
      options: [...picklist.options],
      isNew: false,
    });
  }, []);

  const handleDeletePicklist = useCallback(
    async (picklistId: string, onError: (msg: string) => void) => {
      if (!confirm('Are you sure you want to delete this picklist?')) return;
      try {
        setDeletingPicklist(picklistId);
        await picklistsApi.delete(picklistId);
        setPicklists((prev) => prev.filter((p) => p.id !== picklistId));
      } catch (e) {
        onError(e instanceof Error ? e.message : 'Failed to delete picklist');
      } finally {
        setDeletingPicklist(null);
      }
    },
    []
  );

  const handleSavePicklist = useCallback(
    async (onError: (msg: string) => void, override?: EditingPicklist) => {
      const picklistToSave = override ?? editingPicklist;
      if (!picklistToSave) return;
      if (!picklistToSave.name.trim()) { onError('Picklist name is required'); return; }
      const validOptions = picklistToSave.options.filter(
        (o) => o.value.trim() && o.label.trim()
      );
      if (validOptions.length === 0) {
        onError('At least one valid picklist option is required');
        return;
      }
      try {
        setSavingPicklist(true);
        if (picklistToSave.isNew) {
          const created = await picklistsApi.create({
            name: picklistToSave.name,
            options: validOptions,
          });
          setPicklists((prev) =>
            [...prev, created].sort((a, b) => a.name.localeCompare(b.name))
          );
        } else {
          const updated = await picklistsApi.update(picklistToSave.id, {
            name: picklistToSave.name,
            options: validOptions,
          });
          setPicklists((prev) =>
            prev
              .map((p) => (p.id === updated.id ? updated : p))
              .sort((a, b) => a.name.localeCompare(b.name))
          );
        }
        setEditingPicklist(null);
      } catch (e) {
        onError(e instanceof Error ? e.message : 'Failed to save picklist');
      } finally {
        setSavingPicklist(false);
      }
    },
    [editingPicklist]
  );

  const handleAddPicklistOption = useCallback(() => {
    setEditingPicklist((prev) =>
      prev ? { ...prev, options: [...prev.options, { value: '', label: '' }] } : prev
    );
  }, []);

  const handleRemovePicklistOption = useCallback((index: number) => {
    setEditingPicklist((prev) =>
      prev ? { ...prev, options: prev.options.filter((_, i) => i !== index) } : prev
    );
  }, []);

  const handlePicklistOptionChange = useCallback(
    (index: number, field: 'value' | 'label', value: string) => {
      setEditingPicklist((prev) => {
        if (!prev) return prev;
        const nextOptions = [...prev.options];
        const current = nextOptions[index];
        nextOptions[index] = { ...current, [field]: value };
        if (field === 'label') {
          // The old behaviour filled the value after the first keypress
          // (`M` -> `m`) then treated it as manual input, leaving “Mumbai”
          // with the value “m”. Keep generated values in sync as a label is
          // typed, but never overwrite a deliberately custom value.
          const valueWasGenerated = !current.value || current.value === autoValueFromLabel(current.label);
          if (valueWasGenerated) nextOptions[index].value = autoValueFromLabel(value);
        }
        return { ...prev, options: nextOptions };
      });
    },
    []
  );

  const handleUpdatePicklistJson = useCallback(
    async (picklist: Picklist, data: PicklistUpdateRequest) => {
      const updated = await picklistsApi.update(picklist.id, data);
      setPicklists((prev) => prev
        .map((candidate) => candidate.id === updated.id ? updated : candidate)
        .sort((a, b) => a.name.localeCompare(b.name))
      );
    },
    []
  );

  return {
    picklists,
    setPicklists,
    editingPicklist,
    setEditingPicklist,
    savingPicklist,
    deletingPicklist,
    fetchPicklists,
    handleCreatePicklist,
    handleEditPicklist,
    handleDeletePicklist,
    handleSavePicklist,
    handleAddPicklistOption,
    handleRemovePicklistOption,
    handlePicklistOptionChange,
    handleUpdatePicklistJson,
  };
}
