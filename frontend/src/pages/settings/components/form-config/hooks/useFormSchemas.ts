import { useState, useCallback } from 'react';
import { formSchemas as formSchemasApi } from '../../../../../core/services/api';
import type { FormSchema } from '../../../../../core/types';
import type { PortableFormConfig } from '../../../../../core/types/portableForm';
import { normalizeEntityType } from '../constants';
import { typesUsingFieldsInIdentifierTemplate } from './useFormFields';
import {
  prepareReferenceMappingChange,
  referenceKeyFromFormField,
} from '../referenceMappings';

function referenceMappingsUsedByOtherForms(
  schemas: FormSchema[],
  targetEntity: string,
  excludedSchemaId?: string,
): Map<string, string> {
  const normalizedTarget = normalizeEntityType(targetEntity).toLowerCase();
  const mappings = new Map<string, string>();
  for (const schema of schemas) {
    if (
      schema.id === excludedSchemaId ||
      !schema.is_active ||
      normalizeEntityType(schema.entity_type).toLowerCase() !== normalizedTarget
    ) continue;
    for (const field of schema.schema.fields) {
      const key = referenceKeyFromFormField(field);
      if (key && !mappings.has(key)) {
        mappings.set(key, `${targetEntity}.${field.id}`);
      }
    }
  }
  return mappings;
}

function removedExclusiveFieldIds(
  original: PortableFormConfig,
  next: PortableFormConfig,
  schemas: FormSchema[],
  editedSchema: FormSchema,
): string[] {
  const nextFieldIds = new Set(next.fields.map((field) => field.field));
  return original.fields
    .map((field) => field.field)
    .filter((fieldId) => !nextFieldIds.has(fieldId))
    .filter((fieldId) => !schemas.some((candidate) =>
      candidate.id !== editedSchema.id &&
      candidate.is_active &&
      normalizeEntityType(candidate.entity_type) === normalizeEntityType(editedSchema.entity_type) &&
      candidate.schema.fields.some((field) => field.id === fieldId)
    ));
}

export function useFormSchemas() {
  const [schemas, setSchemas] = useState<FormSchema[]>([]);
  const [selectedSchema, setSelectedSchema] = useState<FormSchema | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showNewSchemaModal, setShowNewSchemaModal] = useState(false);
  const [creatingSchema, setCreatingSchema] = useState(false);
  const [deletingSchema, setDeletingSchema] = useState<string | null>(null);
  const [newSchemaError, setNewSchemaError] = useState<string | null>(null);
  const [editingSchemaName, setEditingSchemaName] = useState<{ schemaId: string; name: string } | null>(null);
  const [savingSchemaName, setSavingSchemaName] = useState(false);

  // silent=true skips the loading spinner — used after field mutations so the UI
  // doesn't flash while refreshing the selected schema's field list.
  const fetchData = useCallback(async (silent = false) => {
    try {
      if (!silent) setLoading(true);
      setError(null);
      const schemasResponse = await formSchemasApi.list();
      const activeSchemas = schemasResponse.items.filter((s) => s.is_active);
      setSchemas(activeSchemas);
      setSelectedSchema((prev) => {
        if (!prev && activeSchemas.length > 0) return activeSchemas[0];
        if (prev) {
          const refreshed = activeSchemas.find((s) => s.id === prev.id);
          return refreshed ?? prev;
        }
        return prev;
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load form configuration');
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  const createSchema = useCallback(
    async (
      entityType: string,
      name: string,
      createRequest: (normalizedEntityType: string, normalizedName: string) => Promise<FormSchema>,
      afterCreate?: (created: FormSchema) => Promise<void>,
    ) => {
      const normalizedEntityType = normalizeEntityType(entityType);
      if (!normalizedEntityType) { setNewSchemaError('Entity type is required'); return; }
      if (!name.trim()) { setNewSchemaError('Display name is required'); return; }
      try {
        setCreatingSchema(true);
        setNewSchemaError(null);
        const created = await createRequest(normalizedEntityType, name.trim());
        if (afterCreate) {
          try {
            await afterCreate(created);
          } catch (afterCreateError) {
            try {
              await formSchemasApi.delete(created.schema_key);
            } catch (cleanupError) {
              console.warn(
                'Failed to delete a form after reference mapping setup failed.',
                cleanupError,
              );
            }
            throw afterCreateError;
          }
        }
        setShowNewSchemaModal(false);
        await fetchData();
        window.dispatchEvent(new Event('form-schemas-changed'));
        setSelectedSchema(created);
      } catch (e) {
        setNewSchemaError(e instanceof Error ? e.message : 'Failed to create schema');
      } finally {
        setCreatingSchema(false);
      }
    },
    [fetchData]
  );

  const handleCreateSchema = useCallback(
    (entityType: string, name: string) => createSchema(
      entityType,
      name,
      (normalizedEntityType, normalizedName) => formSchemasApi.create({
        name: normalizedName,
        entity_type: normalizedEntityType,
        schema: { fields: [] },
        activate: true,
      }),
    ),
    [createSchema]
  );

  const handleCreateSchemaJson = useCallback(
    async (entityType: string, data: PortableFormConfig) => {
      let applyMappings: (() => Promise<void>) | undefined;
      await createSchema(
        entityType,
        data.name,
        async (normalizedEntityType) => {
          const prepared = await prepareReferenceMappingChange({
            targetEntity: normalizedEntityType,
            beforeFields: [],
            afterFields: data.fields,
            referenceMappingsUsedByOtherForms: referenceMappingsUsedByOtherForms(
              schemas,
              normalizedEntityType,
            ),
          });
          applyMappings = prepared.apply;
          return formSchemasApi.createPortable(normalizedEntityType, data);
        },
        async () => applyMappings?.(),
      );
    },
    [createSchema, schemas]
  );

  const handleDeleteSchema = useCallback(
    async (schema: FormSchema) => {
      try {
        const remainingFieldIds = new Set(
          schemas
            .filter(
              (candidate) =>
                candidate.id !== schema.id &&
                candidate.is_active &&
                candidate.entity_type === schema.entity_type,
            )
            .flatMap((candidate) => candidate.schema.fields.map((field) => field.id)),
        );
        const removedFieldIds = schema.schema.fields
          .map((field) => field.id)
          .filter((fieldId) => !remainingFieldIds.has(fieldId));
        const users = await typesUsingFieldsInIdentifierTemplate(
          removedFieldIds,
          schema.entity_type,
        );
        const warning = users.length
          ? ` This removes fields used in the identifier template of: ${users.join(', ')}. New records will skip them until the template is updated.`
          : '';
        if (!confirm(`Delete this form schema? This cannot be undone.${warning}`)) return;
        setDeletingSchema(schema.id);
        setError(null);
        await formSchemasApi.delete(schema.schema_key);
        setSelectedSchema((prev) => (prev?.id === schema.id ? null : prev));
        await fetchData();
        window.dispatchEvent(new Event('form-schemas-changed'));
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to delete schema');
      } finally {
        setDeletingSchema(null);
      }
    },
    [fetchData, schemas]
  );

  const handleRenameSchema = useCallback(async () => {
    if (!editingSchemaName) return;
    const name = editingSchemaName.name.trim();
    if (!name) { setError('Form name cannot be empty'); return; }
    const schema = schemas.find((s) => s.id === editingSchemaName.schemaId);
    if (!schema) return;
    if (name === schema.name) { setEditingSchemaName(null); return; }
    try {
      setSavingSchemaName(true);
      setError(null);
      await formSchemasApi.update(schema.schema_key, { name });
      setSchemas((prev) => prev.map((s) => (s.id === schema.id ? { ...s, name } : s)));
      setSelectedSchema((prev) => (prev?.id === schema.id ? { ...prev, name } : prev));
      setEditingSchemaName(null);
      window.dispatchEvent(new Event('form-schemas-changed'));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to rename form');
    } finally {
      setSavingSchemaName(false);
    }
  }, [editingSchemaName, schemas]);

  const handleSelectSchema = useCallback((schema: FormSchema) => {
    setSelectedSchema(schema);
  }, []);

  const handleResetSchema = useCallback(async () => {
    if (!selectedSchema) return;
    if (!confirm('Reset this form to its default configuration? This cannot be undone.')) return;
    try {
      setError(null);
      const resetSchema = await formSchemasApi.reset(selectedSchema.schema_key);
      await fetchData();
      setSelectedSchema(resetSchema);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to reset form schema');
    }
  }, [selectedSchema, fetchData]);

  const handleUpdateSchemaJson = useCallback(
    async (schema: FormSchema, data: PortableFormConfig) => {
      setError(null);
      const original = await formSchemasApi.getPortable(schema.schema_key);
      const removedFieldIds = removedExclusiveFieldIds(original, data, schemas, schema);
      const identifierUsers = await typesUsingFieldsInIdentifierTemplate(
        removedFieldIds,
        schema.entity_type,
      );
      if (
        identifierUsers.length > 0 &&
        !window.confirm(
          `This removes fields used in the identifier template of: ${identifierUsers.join(', ')}. ` +
          'New records will skip them until the template is updated. Save anyway?',
        )
      ) {
        return false;
      }

      const preparedMappings = await prepareReferenceMappingChange({
        targetEntity: schema.entity_type,
        beforeFields: original.fields,
        afterFields: data.fields,
        referenceMappingsUsedByOtherForms: referenceMappingsUsedByOtherForms(
          schemas,
          schema.entity_type,
          schema.id,
        ),
      });
      const updated = await formSchemasApi.updatePortable(schema.schema_key, data);
      try {
        await preparedMappings.apply();
      } catch (mappingError) {
        try {
          await formSchemasApi.updatePortable(schema.schema_key, original);
        } catch (rollbackError) {
          console.warn(
            'Failed to restore a form after reference mapping update failed.',
            rollbackError,
          );
        }
        throw mappingError;
      }
      setSchemas((prev) => prev.map((candidate) =>
        candidate.id === updated.id ? updated : candidate
      ));
      setSelectedSchema((prev) => prev?.id === updated.id ? updated : prev);
      window.dispatchEvent(new Event('form-schemas-changed'));
      return true;
    },
    [schemas]
  );

  const handleLoadSchemaJson = useCallback(
    (schema: FormSchema) => formSchemasApi.getPortable(schema.schema_key),
    []
  );

  return {
    schemas,
    setSchemas,
    selectedSchema,
    setSelectedSchema,
    loading,
    error,
    setError,
    showNewSchemaModal,
    setShowNewSchemaModal,
    creatingSchema,
    deletingSchema,
    newSchemaError,
    setNewSchemaError,
    editingSchemaName,
    setEditingSchemaName,
    savingSchemaName,
    fetchData,
    handleCreateSchema,
    handleCreateSchemaJson,
    handleDeleteSchema,
    handleRenameSchema,
    handleUpdateSchemaJson,
    handleLoadSchemaJson,
    handleSelectSchema,
    handleResetSchema,
  };
}
