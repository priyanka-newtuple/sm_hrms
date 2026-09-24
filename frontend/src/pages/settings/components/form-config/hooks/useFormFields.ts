import { useState, useCallback, useMemo } from 'react';
import { arrayMove } from '@dnd-kit/sortable';
import {
  entityTypes as entityTypesApi,
  formSchemas as formSchemasApi,
} from '../../../../../core/services/api';
import type {
  FormField,
  FormSchema,
  Picklist,
  RelationDeclaration,
} from '../../../../../core/types';
import type { EditingField } from '../types';
import { injectMissingSectionFields, generateFieldId, toFieldId } from '../constants';
import {
  getFormFields,
  hasIdentifierTemplate,
  templateTokens,
} from '@/shared/utils/entityForm';
import { removeReferenceMapping, upsertReferenceMapping } from '../referenceMappings';
import { resolveFieldForSave } from '../fieldSaveValidation';

export { resolveFieldForSave } from '../fieldSaveValidation';

/** Entity types whose identifier template references any supplied field. */
export async function typesUsingFieldsInIdentifierTemplate(
  fieldIds: string[],
  entityTypeName?: string,
): Promise<string[]> {
  const wanted = new Set(fieldIds.map((id) => id.toLowerCase()));
  if (wanted.size === 0) return [];
  const normalizedTypeName = entityTypeName?.replace(/^ATS\./i, '').trim().toLowerCase();
  const response = await entityTypesApi.list();
  return (response.items ?? [])
    .filter((type) =>
      normalizedTypeName
        ? type.name.replace(/^ATS\./i, '').trim().toLowerCase() === normalizedTypeName
        : true,
    )
    .filter((type) => hasIdentifierTemplate(type.schema_definition))
    .filter((type) =>
      templateTokens(String(type.schema_definition?.identifier_template ?? '')).some((token) =>
        wanted.has(token),
      ),
    )
    .map((type) => type.name);
}

export async function typesUsingFieldInIdentifierTemplate(
  fieldId: string,
  entityTypeName?: string,
): Promise<string[]> {
  return typesUsingFieldsInIdentifierTemplate([fieldId], entityTypeName);
}

export function useFormFields(
  selectedSchema: FormSchema | null,
  picklists: Picklist[],
  onSchemaUpdated: () => Promise<void>,
  onError: (msg: string | null) => void,
  allSchemas: FormSchema[] = [],
  typeIdByName: Map<string, string> = new Map()
) {
  const [editingField, setEditingField] = useState<EditingField | null>(null);
  const [savingField, setSavingField] = useState(false);
  const [reorderingIndex, setReorderingIndex] = useState<number | null>(null);
  const [pendingDeleteIndex, setPendingDeleteIndex] = useState<number | null>(null);

  // Include injected section fields (e.g., Application's "Comments" section) in the
  // displayed list. The API filters sections out on save, so they are cosmetic only.
  const currentFields = injectMissingSectionFields(
    selectedSchema?.entity_type ?? '',
    selectedSchema?.schema.fields ?? []
  );

  // Fields from every OTHER form attached to this same entity type — entity
  // data is shared across all its forms, so a calc field being authored here
  // can validly reference a field that lives in a sibling form. Deduped by id
  // against currentFields (current form wins on a shared field id).
  const siblingFields = useMemo(() => {
    const currentIds = new Set(currentFields.map((f) => f.id));
    const seen = new Set<string>();
    const result: FormField[] = [];
    for (const schema of allSchemas) {
      if (schema.id === selectedSchema?.id || schema.entity_type !== selectedSchema?.entity_type) continue;
      for (const field of getFormFields(schema)) {
        if (currentIds.has(field.id) || seen.has(field.id)) continue;
        seen.add(field.id);
        result.push(field);
      }
    }
    return result;
  }, [allSchemas, selectedSchema, currentFields]);

  const saveToApi = useCallback(
    async (updatedFields: FormField[]) => {
      if (!selectedSchema) return;
      await formSchemasApi.update(selectedSchema.schema_key, {
        schema: { fields: updatedFields },
        activate: true,
      });
      await onSchemaUpdated();
    },
    [selectedSchema, onSchemaUpdated]
  );

  const handleAddField = useCallback(() => {
    setEditingField({
      index: currentFields.length,
      field: { id: '', label: '', type: 'text', required: false, system: false },
      isNew: true,
    });
  }, [currentFields.length]);

  const handleEditField = useCallback(
    (index: number) => {
      const field = currentFields[index];
      if (!field) return;
      let nextField = { ...field };
      if (
        (field.type === 'select' ||
          field.type === 'multi_select' ||
          field.type === 'picklist_multi') &&
        !field.picklist_id
      ) {
        const inferredPicklist = picklists.find((pl) => {
          const values = pl.options.map((o) => o.value);
          const labels = pl.options.map((o) => o.label);
          const ev = field.enum_values ?? [];
          const el = field.enum_labels ?? [];
          // Match by stored values (new format) or by labels (legacy format)
          return (
            values.length > 0 && values.length === ev.length &&
            (values.every((v, i) => v === ev[i]) || labels.every((l, i) => l === ev[i] || l === el[i]))
          );
        });
        if (inferredPicklist) nextField = { ...nextField, picklist_id: inferredPicklist.id };
      }
      setEditingField({ index, field: nextField, isNew: false, originalId: field.id });
    },
    [currentFields, picklists]
  );

  const handleSaveField = useCallback(async () => {
    if (!editingField) return;
    const { isNew, originalId } = editingField;

    const liveIndex = isNew ? -1 : currentFields.findIndex((f) => f.id === originalId);
    if (!isNew && liveIndex === -1) {
      onError('This field was removed while editing. Please close and try again.');
      return;
    }

    let fieldToSave = editingField.field;
    if (!fieldToSave.id.trim()) {
      fieldToSave = { ...fieldToSave, id: generateFieldId(fieldToSave.label, currentFields, liveIndex) };
    }
    const { resolved, error } = resolveFieldForSave(fieldToSave, picklists);
    if (error) { onError(error); return; }

    if (isNew || currentFields[liveIndex]?.id !== resolved.id) {
      const duplicate = currentFields.find((f, i) => f.id === resolved.id && i !== liveIndex);
      if (duplicate) { onError('Field ID must be unique'); return; }
    }

    const newFields = [...currentFields];
    if (isNew) {
      newFields.push(resolved);
    } else {
      newFields[liveIndex] = resolved;
    }

    try {
      setSavingField(true);
      onError(null);
      await saveToApi(newFields);
      setEditingField(null);
    } catch (e) {
      onError(e instanceof Error ? e.message : 'Failed to save field');
    } finally {
      setSavingField(false);
    }
  }, [editingField, currentFields, picklists, saveToApi, onError]);

  const handleSaveAndAddNew = useCallback(async () => {
    if (!editingField) return;
    const { isNew, originalId } = editingField;

    const liveIndex = isNew ? -1 : currentFields.findIndex((f) => f.id === originalId);
    if (!isNew && liveIndex === -1) {
      onError('This field was removed while editing. Please close and try again.');
      return;
    }

    let fieldToSave = editingField.field;
    if (!fieldToSave.id.trim()) {
      fieldToSave = { ...fieldToSave, id: generateFieldId(fieldToSave.label, currentFields, liveIndex) };
    }
    const { resolved, error } = resolveFieldForSave(fieldToSave, picklists);
    if (error) { onError(error); return; }

    if (isNew || currentFields[liveIndex]?.id !== resolved.id) {
      const duplicate = currentFields.find((f, i) => f.id === resolved.id && i !== liveIndex);
      if (duplicate) { onError('Field ID must be unique'); return; }
    }

    const newFields = [...currentFields];
    if (isNew) {
      newFields.push(resolved);
    } else {
      newFields[liveIndex] = resolved;
    }

    try {
      setSavingField(true);
      onError(null);
      await saveToApi(newFields);
      setEditingField({
        index: newFields.length,
        field: { id: '', label: '', type: 'text', required: false, system: false },
        isNew: true,
      });
    } catch (e) {
      onError(e instanceof Error ? e.message : 'Failed to save field');
    } finally {
      setSavingField(false);
    }
  }, [editingField, currentFields, picklists, saveToApi, onError]);

  const handleAddReferenceField = useCallback(
    async (
      declaration: RelationDeclaration,
      providerName: string,
      sourceField: FormField,
      onClose: () => void
    ) => {
      if (!selectedSchema) return;
      // Flat id (e.g. `job_title`) — dotted ids break the backend's
      // `local_field_name` prefix-stripping.
      const targetFieldId = generateFieldId(
        toFieldId(`${providerName}_${sourceField.id}`),
        currentFields,
        -1
      );
      const newField: FormField = {
        id: targetFieldId,
        label: sourceField.label,
        type: 'reference',
        required: false,
        system: false,
        source_entity: providerName,
        source_field: sourceField.id,
      };
      try {
        setSavingField(true);
        onError(null);
        await saveToApi([...currentFields, newField]);
        try {
          await upsertReferenceMapping({
            sourceEntityTypeId: declaration.from_entity_type_id,
            targetEntityTypeId: declaration.to_entity_type_id,
            sourceEntity: providerName,
            sourceField: sourceField.id,
            targetEntity: selectedSchema.entity_type,
            targetField: targetFieldId,
          });
        } catch (mappingError) {
          await saveToApi(currentFields); // roll back the just-added field
          throw mappingError;
        }
        onClose();
      } catch (e) {
        onError(e instanceof Error ? e.message : 'Failed to add reference field');
      } finally {
        setSavingField(false);
      }
    },
    [selectedSchema, currentFields, saveToApi, onError]
  );

  const reorderFields = useCallback(
    async (fromIndex: number, toIndex: number) => {
      if (fromIndex === toIndex) return;
      const newFields = arrayMove([...currentFields], fromIndex, toIndex);
      try {
        setReorderingIndex(fromIndex);
        await saveToApi(newFields);
      } catch (e) {
        onError(e instanceof Error ? e.message : 'Failed to reorder fields');
      } finally {
        setReorderingIndex(null);
      }
    },
    [currentFields, saveToApi, onError]
  );

  const requestDeleteField = useCallback(
    async (index: number) => {
      const field = currentFields[index];
      if (field?.system) { onError('System fields cannot be deleted'); return; }
      if (!field || !selectedSchema) return;
      const fieldStillProvided = allSchemas.some(
        (schema) =>
          schema.id !== selectedSchema.id &&
          schema.is_active &&
          schema.entity_type === selectedSchema.entity_type &&
          schema.schema.fields.some((candidate) => candidate.id === field.id),
      );
      if (!fieldStillProvided) {
        try {
          const users = await typesUsingFieldInIdentifierTemplate(
            field.id,
            selectedSchema.entity_type,
          );
          if (
            users.length > 0 &&
            !window.confirm(
              `Field "${field.label}" is used in the identifier template of: ${users.join(', ')}. ` +
                'New records will skip it until the template is updated. Delete anyway?',
            )
          ) {
            return;
          }
        } catch (error) {
          onError(error instanceof Error ? error.message : 'Failed to check identifier templates');
          return;
        }
      }
      setPendingDeleteIndex(index);
    },
    [currentFields, selectedSchema, allSchemas, onError]
  );

  const removeMappingEntryIfUnused = useCallback(
    async (field: FormField) => {
      if (!selectedSchema || !field.source_entity || !field.source_field) return;
      const stillUsed = allSchemas.some(
        (s) =>
          s.id !== selectedSchema.id &&
          s.is_active &&
          s.entity_type === selectedSchema.entity_type &&
          (s.schema.fields ?? []).some((f) => f.id === field.id)
      );
      if (stillUsed) return;
      const fromId = typeIdByName.get(field.source_entity.toLowerCase());
      const toId = typeIdByName.get(selectedSchema.entity_type.toLowerCase());
      if (!fromId || !toId) return;
      try {
        await removeReferenceMapping({
          sourceEntityTypeId: fromId,
          targetEntityTypeId: toId,
          sourceEntity: field.source_entity,
          sourceField: field.source_field,
        });
      } catch {
        // Best-effort: a stale mapping entry resolves onto a field id no form
        // renders, which is harmless. The field itself is already gone.
      }
    },
    [selectedSchema, allSchemas, typeIdByName]
  );

  const confirmDeleteField = useCallback(async () => {
    if (pendingDeleteIndex === null) return;
    const field = currentFields[pendingDeleteIndex];
    const newFields = currentFields.filter((_, i) => i !== pendingDeleteIndex);
    try {
      await saveToApi(newFields);
      if (field?.type === 'reference') {
        await removeMappingEntryIfUnused(field);
      }
      setPendingDeleteIndex(null);
    } catch (e) {
      onError(e instanceof Error ? e.message : 'Failed to delete field');
      setPendingDeleteIndex(null);
    }
  }, [pendingDeleteIndex, currentFields, saveToApi, removeMappingEntryIfUnused, onError]);

  const cancelDeleteField = useCallback(() => {
    setPendingDeleteIndex(null);
  }, []);

  return {
    currentFields,
    siblingFields,
    editingField,
    setEditingField,
    savingField,
    reorderingIndex,
    pendingDeleteIndex,
    pendingDeleteField: pendingDeleteIndex !== null ? currentFields[pendingDeleteIndex] ?? null : null,
    handleAddField,
    handleEditField,
    handleSaveField,
    handleSaveAndAddNew,
    handleAddReferenceField,
    reorderFields,
    requestDeleteField,
    confirmDeleteField,
    cancelDeleteField,
  };
}
