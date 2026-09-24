import { Braces, FileText, Plus } from 'lucide-react';
import {
  DndContext,
  closestCenter,
  PointerSensor,
  useSensor,
  useSensors,
} from '@dnd-kit/core';
import type { DragEndEvent } from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { Button } from '@/components/ui/button';
import type { FormField, FormSchema, Picklist } from '../../../../../core/types';
import type { EditingField } from '../types';
import FieldRow from './FieldRow';

interface FieldsEditorProps {
  schema: FormSchema;
  fields: FormField[];
  /** Fields from other forms attached to the same entity type — offered to the
   * calc builder as extra operand/aggregate-source options (entity data is
   * shared across all its forms). */
  siblingFields?: FormField[];
  picklists: Picklist[];
  reorderingIndex: number | null;
  canWrite: boolean;
  showAddFromRelated: boolean;
  editingField: EditingField | null;
  savingField: boolean;
  onAddField: () => void;
  onAddFromRelated: () => void;
  onEditField: (index: number) => void;
  onChangeField: (updated: EditingField) => void;
  onSaveField: () => void;
  onSaveAndAddNew: () => void;
  onCancelEdit: () => void;
  onDeleteField: (index: number) => void;
  onReorderFields: (fromIndex: number, toIndex: number) => void;
  onReset: () => void;
  onEditJson: () => void;
}

export default function FieldsEditor({
  schema,
  fields,
  siblingFields = [],
  picklists,
  reorderingIndex,
  canWrite,
  showAddFromRelated,
  editingField,
  savingField,
  onAddField,
  onAddFromRelated,
  onEditField,
  onChangeField,
  onSaveField,
  onSaveAndAddNew,
  onCancelEdit,
  onDeleteField,
  onReorderFields,
  onReset,
  onEditJson,
}: FieldsEditorProps) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } })
  );

  const handleToggleExpand = (index: number) => {
    if (editingField && editingField.index === index && !editingField.isNew) {
      onCancelEdit();
    } else {
      onEditField(index);
    }
  };

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const fromIndex = fields.findIndex((f) => f.id === active.id);
    const toIndex = fields.findIndex((f) => f.id === over.id);
    if (fromIndex !== -1 && toIndex !== -1) {
      onReorderFields(fromIndex, toIndex);
    }
  };

  const sortableIds = fields.map((f) => f.id);
  // Already deduped against `fields` upstream (useFormFields' siblingFields).
  const allFieldsForBuilder = [...fields, ...siblingFields];

  return (
    <div className="bg-card rounded-xl border border-border">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-border">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-muted flex items-center justify-center shrink-0">
            <FileText className="w-[18px] h-[18px] text-muted-foreground" />
          </div>
          <div>
            <h3 className="font-semibold text-foreground leading-tight">{schema.name}</h3>
            <p className="text-sm text-muted-foreground mt-0.5">
              Define the shape of records in this entity. Fields control what data can be
              captured.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 ml-4 shrink-0">
          <Button
            variant="outline"
            onClick={onEditJson}
            icon={<Braces className="w-4 h-4" />}
          >
            {canWrite ? 'Edit JSON' : 'View JSON'}
          </Button>
          {showAddFromRelated && (
            <Button variant="secondary" onClick={onAddFromRelated} disabled={!canWrite}>
              Add from related entity
            </Button>
          )}
          <Button
            variant="outline"
            onClick={onAddField}
            icon={<Plus className="w-4 h-4" />}
            disabled={!canWrite}
          >
            Add field
          </Button>
        </div>
      </div>

      {/* Fields count row */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-border">
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Fields
        </span>
        <span className="text-xs text-muted-foreground">
          {fields.length} {fields.length === 1 ? 'field' : 'fields'}
        </span>
      </div>

      {/* Field list */}
      <div className="p-4 space-y-2">
        {fields.length === 0 && !editingField?.isNew ? (
          <div className="text-center py-10 text-muted-foreground">
            <FileText className="w-10 h-10 mx-auto mb-3 text-muted-foreground/60" />
            <p className="text-sm">No fields configured yet</p>
            <Button
              variant="outline"
              onClick={onAddField}
              className="mt-3"
              disabled={!canWrite}
              icon={<Plus className="w-4 h-4" />}
            >
              Add your first field
            </Button>
          </div>
        ) : (
          <>
            <DndContext
              sensors={sensors}
              collisionDetection={closestCenter}
              onDragEnd={handleDragEnd}
            >
              <SortableContext items={sortableIds} strategy={verticalListSortingStrategy}>
                {fields.map((field, index) => (
                  <FieldRow
                    key={field.id || index}
                    field={field}
                    index={index}
                    totalFields={fields.length}
                    allFields={allFieldsForBuilder}
                    picklists={picklists}
                    isReordering={reorderingIndex === index}
                    isExpanded={
                      editingField !== null &&
                      editingField.index === index &&
                      !editingField.isNew
                    }
                    editingDraft={
                      editingField?.index === index && !editingField.isNew
                        ? editingField
                        : null
                    }
                    savingField={savingField}
                    canWrite={canWrite}
                    onToggleExpand={() => handleToggleExpand(index)}
                    onChangeField={onChangeField}
                    onSave={onSaveField}
                    onCancel={onCancelEdit}
                    onDelete={() => onDeleteField(index)}
                  />
                ))}
              </SortableContext>
            </DndContext>

            {/* New field row — appended below existing, not sortable */}
            {editingField?.isNew && (
              <FieldRow
                field={editingField.field}
                index={fields.length}
                totalFields={fields.length + 1}
                allFields={allFieldsForBuilder}
                picklists={picklists}
                isReordering={false}
                isExpanded={true}
                editingDraft={editingField}
                savingField={savingField}
                canWrite={canWrite}
                sortable={false}
                onToggleExpand={onCancelEdit}
                onChangeField={onChangeField}
                onSave={onSaveField}
                onSaveAndAddNew={onSaveAndAddNew}
                onCancel={onCancelEdit}
                onDelete={onCancelEdit}
              />
            )}
          </>
        )}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-end px-5 py-3 border-t border-border">
        <button
          type="button"
          onClick={onReset}
          disabled={!canWrite}
          className="text-xs text-muted-foreground hover:text-muted-foreground disabled:opacity-40 transition-colors"
        >
          Reset to default
        </button>
      </div>
    </div>
  );
}
