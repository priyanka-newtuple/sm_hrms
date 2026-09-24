import { useState, useEffect } from 'react';
import { FileText, Plus, AlertCircle, Lock, X, Loader2, RefreshCw } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { entityRelations, entityTypes as entityTypesApi } from '../../../../core/services/api';
import type {
  FormSchema,
  Picklist,
  RelationDeclaration,
} from '../../../../core/types';
import { usePermissions } from '../../../../core/hooks/usePermissions';
import { useFormSchemas } from './hooks/useFormSchemas';
import { useWorkflowFieldsByEntityType } from '@/shared/hooks';
import { useFormFields } from './hooks/useFormFields';
import { usePicklists } from './hooks/usePicklists';
import { useFormOrdering } from './useFormOrdering';
import { normalizeEntityType } from './constants';
import type { NewSchemaForm } from './types';
import FormSchemaList from './components/FormSchemaList';
import PicklistPanel from './components/PicklistPanel';
import FieldsEditor from './components/FieldsEditor';
import EditPicklistModal from './components/EditPicklistModal';
import NewEntityFormModal from './components/NewEntityFormModal';
import ReferencePickerModal from './components/ReferencePickerModal';
import DeleteFieldDialog from './components/DeleteFieldDialog';
import JsonConfigEditorModal from './components/JsonConfigEditorModal';
import { parseFormJson, parsePicklistJson } from './jsonConfig';

export default function FormConfigTab() {
  const { hasPermission } = usePermissions();
  const canWrite = hasPermission('form:write');

  const schemaHook = useFormSchemas();
  // Entity types whose fields come from pinned Method Blocks have no Form
  // config, so the reference picker would offer nothing for them. Their fields
  // live on the workflow's resolved entity_schema; index the active workflows
  // by entity type so the picker can fall back to it.
  const workflowFieldsByEntityType = useWorkflowFieldsByEntityType();
  const picklistHook = usePicklists();

  const { schemaGroups, reorderingEntityType, moveSchema } = useFormOrdering(
    schemaHook.schemas,
    normalizeEntityType,
    () => schemaHook.fetchData(true),
    schemaHook.setError
  );

  const [typeIdByName, setTypeIdByName] = useState<Map<string, string>>(new Map());
  const [typeNameById, setTypeNameById] = useState<Map<string, string>>(new Map());
  const [declarations, setDeclarations] = useState<RelationDeclaration[]>([]);

  const fieldHook = useFormFields(
    schemaHook.selectedSchema,
    picklistHook.picklists,
    () => schemaHook.fetchData(true),
    schemaHook.setError,
    schemaHook.schemas,
    typeIdByName
  );

  const [picklistsExpanded, setPicklistsExpanded] = useState(true);
  const [showReferencePicker, setShowReferencePicker] = useState(false);
  const [selectedSourceEntity, setSelectedSourceEntity] = useState('');
  const [newSchemaForm, setNewSchemaForm] = useState<NewSchemaForm>({ entityType: '', name: '' });
  const [jsonEditingSchema, setJsonEditingSchema] = useState<FormSchema | null>(null);
  const [jsonEditingPicklist, setJsonEditingPicklist] = useState<Picklist | null>(null);

  useEffect(() => {
    schemaHook.fetchData();
    picklistHook.fetchPicklists();
    entityTypesApi
      .list()
      .then((res) => {
        const byName = new Map<string, string>();
        const byId = new Map<string, string>();
        for (const t of res.items ?? []) {
          const id = t.entity_type_id ?? t.id;
          byName.set(t.name.toLowerCase(), id);
          byId.set(id, t.name);
        }
        setTypeIdByName(byName);
        setTypeNameById(byId);
      })
      .catch((err) => {
        // Relations UI degrades to its empty state; forms editing still works.
        console.error('Failed to load entity types for relations:', err);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selectedEntityType = schemaHook.selectedSchema?.entity_type ?? '';
  useEffect(() => {
    const targetId = typeIdByName.get(selectedEntityType.toLowerCase());
    if (!targetId) {
      setDeclarations([]);
      return;
    }
    entityRelations
      .listDeclarations(targetId, 'to')
      .then((res) => setDeclarations(res.items ?? []))
      .catch((err) => {
        console.error('Failed to load relation declarations:', err);
        setDeclarations([]);
      });
  }, [selectedEntityType, typeIdByName]);

  const handleCloseNewSchemaModal = () => {
    schemaHook.setShowNewSchemaModal(false);
    schemaHook.setNewSchemaError(null);
    setNewSchemaForm({ entityType: '', name: '' });
  };

  const handleCreateNewForm = () => {
    schemaHook.handleCreateSchema(newSchemaForm.entityType, newSchemaForm.name);
  };

  const handleRefresh = async () => {
    await schemaHook.fetchData();
    await picklistHook.fetchPicklists();
  };

  if (schemaHook.loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-8 h-8 text-cobalt animate-spin" />
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-2">
          <FileText className="w-5 h-5 text-muted-foreground" />
          <h2 className="text-lg font-medium text-foreground">Form Configuration</h2>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            onClick={handleRefresh}
            icon={<RefreshCw className="w-4 h-4" />}
          >
            Refresh
          </Button>
          <Button
            variant="secondary"
            onClick={() => schemaHook.setShowNewSchemaModal(true)}
            icon={<Plus className="w-4 h-4" />}
            disabled={!canWrite}
          >
            New Form
          </Button>
        </div>
      </div>

      {!canWrite && (
        <div className="mb-4 flex items-center gap-2 rounded-lg border border-warning/30 bg-warning-subtle p-3 text-warning text-sm">
          <Lock className="w-4 h-4 shrink-0" />
          You have read-only access to Forms. Contact an admin to make changes.
        </div>
      )}

      {schemaHook.error && (
        <div className="mb-4 flex items-center gap-2 rounded-lg border border-destructive/20 bg-destructive/10 p-4 text-destructive">
          <AlertCircle className="w-5 h-5 shrink-0" />
          {schemaHook.error}
          <Button
            variant="primary"
            onClick={() => schemaHook.setError(null)}
            className="ml-auto"
          >
            <X className="w-4 h-4" />
          </Button>
        </div>
      )}

      {schemaHook.schemas.length === 0 ? (
        <div className="rounded-xl border border-border bg-card p-8 text-center">
          <FileText className="mx-auto mb-3 w-12 h-12 text-muted-foreground/50" />
          <p className="mb-2 text-muted-foreground">No entity schemas yet</p>
          <p className="mb-4 text-sm text-muted-foreground">
            Create a form schema to define the fields for an entity type.
          </p>
          <Button
            variant="primary"
            onClick={() => schemaHook.setShowNewSchemaModal(true)}
            className="mx-auto"
            icon={<Plus className="w-4 h-4" />}
            disabled={!canWrite}
          >
            Create First Form
          </Button>
        </div>
      ) : (
        <div className="flex flex-col gap-4 lg:grid lg:grid-cols-4 lg:gap-6">
          {/* Mobile: horizontal schema picker */}
          <div className="lg:hidden">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Forms</span>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => schemaHook.setShowNewSchemaModal(true)}
                disabled={!canWrite}
                className="text-muted-foreground hover:text-foreground"
                title="New Form"
              >
                <Plus className="w-4 h-4" />
              </Button>
            </div>
            <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-none">
              {schemaGroups.flatMap(([, group]) => group).map((schema) => (
                <button
                  key={schema.id}
                  type="button"
                  onClick={() => {
                    fieldHook.setEditingField(null);
                    schemaHook.handleSelectSchema(schema);
                  }}
                  className={`shrink-0 rounded-full border px-3 py-1.5 text-sm font-medium transition-colors ${
                    schemaHook.selectedSchema?.id === schema.id
                      ? 'border-primary/20 bg-primary/10 text-primary'
                      : 'border-border bg-card text-muted-foreground hover:bg-muted/50'
                  }`}
                >
                  {schema.name}
                </button>
              ))}
            </div>
          </div>

          {/* Desktop: left sidebar */}
          <div className="hidden lg:block lg:col-span-1 space-y-4">
            <FormSchemaList
              schemaGroups={schemaGroups}
              selectedSchema={schemaHook.selectedSchema}
              editingSchemaName={schemaHook.editingSchemaName}
              savingSchemaName={schemaHook.savingSchemaName}
              deletingSchema={schemaHook.deletingSchema}
              reorderingEntityType={reorderingEntityType}
              canWrite={canWrite}
              onSelectSchema={(schema) => {
                fieldHook.setEditingField(null);
                schemaHook.handleSelectSchema(schema);
              }}
              onNewForm={() => schemaHook.setShowNewSchemaModal(true)}
              onDeleteSchema={schemaHook.handleDeleteSchema}
              onStartRename={(schema) =>
                schemaHook.setEditingSchemaName({ schemaId: schema.id, name: schema.name })
              }
              onChangeRenameName={(name) =>
                schemaHook.setEditingSchemaName((prev) => (prev ? { ...prev, name } : prev))
              }
              onConfirmRename={schemaHook.handleRenameSchema}
              onCancelRename={() => schemaHook.setEditingSchemaName(null)}
              onMoveSchema={moveSchema}
            />
            <PicklistPanel
              picklists={picklistHook.picklists}
              expanded={picklistsExpanded}
              deletingPicklist={picklistHook.deletingPicklist}
              canWrite={canWrite}
              onToggleExpanded={() => setPicklistsExpanded((v) => !v)}
              onCreatePicklist={picklistHook.handleCreatePicklist}
              onEditPicklist={picklistHook.handleEditPicklist}
              onEditPicklistJson={setJsonEditingPicklist}
              onDeletePicklist={(id) =>
                picklistHook.handleDeletePicklist(id, schemaHook.setError)
              }
            />
          </div>

          {/* Main content */}
          <div className="lg:col-span-3">
            {schemaHook.selectedSchema ? (
              <FieldsEditor
                schema={schemaHook.selectedSchema}
                fields={fieldHook.currentFields}
                siblingFields={fieldHook.siblingFields}
                picklists={picklistHook.picklists}
                reorderingIndex={fieldHook.reorderingIndex}
                canWrite={canWrite}
                showAddFromRelated={declarations.length > 0}
                editingField={fieldHook.editingField}
                savingField={fieldHook.savingField}
                onAddField={fieldHook.handleAddField}
                onAddFromRelated={() => setShowReferencePicker(true)}
                onEditField={fieldHook.handleEditField}
                onChangeField={fieldHook.setEditingField}
                onSaveField={fieldHook.handleSaveField}
                onSaveAndAddNew={fieldHook.handleSaveAndAddNew}
                onCancelEdit={() => fieldHook.setEditingField(null)}
                onDeleteField={fieldHook.requestDeleteField}
                onReorderFields={fieldHook.reorderFields}
                onReset={schemaHook.handleResetSchema}
                onEditJson={() => setJsonEditingSchema(schemaHook.selectedSchema)}
              />
            ) : (
              <div className="bg-card rounded-xl border border-border p-8 text-center">
                <FileText className="w-12 h-12 text-muted-foreground/60 mx-auto mb-3" />
                <p className="text-muted-foreground">Select a form to edit</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Edit picklist modal */}
      {picklistHook.editingPicklist && (
        <EditPicklistModal
          editingPicklist={picklistHook.editingPicklist}
          saving={picklistHook.savingPicklist}
          canWrite={canWrite}
          onChange={(updated) => picklistHook.setEditingPicklist(updated)}
          onSave={(updated) => picklistHook.handleSavePicklist(schemaHook.setError, updated)}
          onClose={() => picklistHook.setEditingPicklist(null)}
          onAddOption={picklistHook.handleAddPicklistOption}
          onRemoveOption={picklistHook.handleRemovePicklistOption}
          onChangeOption={picklistHook.handlePicklistOptionChange}
        />
      )}

      {/* New entity form modal */}
      {schemaHook.showNewSchemaModal && (
        <NewEntityFormModal
          entityType={newSchemaForm.entityType}
          onChangeEntityType={(entityType) => setNewSchemaForm({ ...newSchemaForm, entityType })}
          fieldForm={newSchemaForm}
          onChangeFieldForm={setNewSchemaForm}
          creating={schemaHook.creatingSchema}
          error={schemaHook.newSchemaError}
          canWrite={canWrite}
          onCreate={handleCreateNewForm}
          onCreateJson={schemaHook.handleCreateSchemaJson}
          onClose={handleCloseNewSchemaModal}
        />
      )}

      {/* Reference field picker — driven by relation declarations */}
      {showReferencePicker && schemaHook.selectedSchema && (
        <ReferencePickerModal
          schemas={schemaHook.schemas}
          workflowFieldsByEntityType={workflowFieldsByEntityType}
          currentFields={fieldHook.currentFields}
          declarations={declarations}
          typeNameById={typeNameById}
          selectedDefId={selectedSourceEntity}
          onSelectDeclaration={setSelectedSourceEntity}
          onAddField={(declaration, providerName, sourceField) =>
            fieldHook.handleAddReferenceField(declaration, providerName, sourceField, () => {
              setShowReferencePicker(false);
              setSelectedSourceEntity('');
            })
          }
          onClose={() => {
            setShowReferencePicker(false);
            setSelectedSourceEntity('');
          }}
        />
      )}

      {/* Delete field confirmation */}
      {fieldHook.pendingDeleteField && (
        <DeleteFieldDialog
          field={fieldHook.pendingDeleteField}
          onConfirm={fieldHook.confirmDeleteField}
          onCancel={fieldHook.cancelDeleteField}
        />
      )}

      {jsonEditingSchema && (
        <JsonConfigEditorModal
          key={jsonEditingSchema.id}
          noun="Form"
          description={`${jsonEditingSchema.name} · includes all form fields`}
          hint="Fields use the backend form format. The form remains attached to its current entity."
          canWrite={canWrite}
          load={() => schemaHook.handleLoadSchemaJson(jsonEditingSchema)}
          parse={parseFormJson}
          onSave={(data) => schemaHook.handleUpdateSchemaJson(jsonEditingSchema, data)}
          onClose={() => setJsonEditingSchema(null)}
        />
      )}

      {jsonEditingPicklist && (
        <JsonConfigEditorModal
          key={jsonEditingPicklist.id}
          noun="Picklist"
          description={jsonEditingPicklist.name}
          canWrite={canWrite}
          load={async () => ({
            name: jsonEditingPicklist.name,
            options: jsonEditingPicklist.options,
          })}
          parse={parsePicklistJson}
          onSave={(data) => picklistHook.handleUpdatePicklistJson(jsonEditingPicklist, data)}
          onClose={() => setJsonEditingPicklist(null)}
        />
      )}
    </div>
  );
}
