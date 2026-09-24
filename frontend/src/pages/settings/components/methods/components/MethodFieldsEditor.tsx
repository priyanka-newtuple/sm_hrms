/**
 * MethodFieldsEditor
 *
 * The Methods tab's detail panel: header, field count, the drag-sortable field
 * list, and the metadata footer. Mirrors the Forms tab's FieldsEditor, with
 * "Add field" replaced by "Add from Field Library" — a method composes existing
 * fields rather than defining new ones.
 */

import {
  Copy,
  ExternalLink,
  FileText,
  Link2,
  Loader2,
  Plug,
  Rows3,
  History,
} from 'lucide-react';
import { useState } from 'react';
import type { ReactNode } from 'react';
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
import type {
  Connector,
  MethodCategory,
  MethodVersion,
  MethodVersionField,
  MethodWithFields,
} from '@/core/types';
import MethodFieldRow from './MethodFieldRow';
import FieldLibraryPanel from './FieldLibraryPanel';
import MethodVersionHistory from './MethodVersionHistory';
import EntityTypeTagPicker from './EntityTypeTagPicker';
import MethodFieldVersionDialog from './MethodFieldVersionDialog';
import MethodInheritedFieldPicker from './MethodInheritedFieldPicker';
import type { EntityField } from '@/lib/state-machine/types';
import type { InheritedFieldPick, MethodFieldDraft } from '../hooks/useMethodFields';

interface MethodFieldsEditorProps {
  method: MethodWithFields;
  categories: MethodCategory[];
  editingField: MethodFieldDraft | null;
  savingField: boolean;
  reorderingIndex: number | null;
  canWrite: boolean;
  loadingDetail: boolean;
  existingFieldIds: string[];
  addingFields: boolean;
  onAddFromLibrary: (libraryFieldIds: string[]) => void;
  /** "Add from related entity": list a field that reads its value from a
   *  record linked to this one. Undefined hides the button (step-object lists). */
  onAddInheritedField?: (pick: InheritedFieldPick) => Promise<boolean>;
  /** Active workflows' entity_schema fields per entity type, for the picker's
   *  source-field list. */
  workflowFieldsByEntityType?: Record<string, EntityField[]>;
  onGoToFieldLibrary: () => void;
  onEditField: (index: number) => void;
  onChangeDraft: (draft: MethodFieldDraft) => void;
  onSaveField: () => void;
  onCancelEdit: () => void;
  onDeleteField: (index: number) => void;
  onReorderFields: (fromIndex: number, toIndex: number) => void;
  /** Repin one field to a different version of that field. Resolves true on
   *  success so the dialog closes only when the repin actually landed. */
  onRepinField: (linkId: string, versionId: string) => Promise<boolean>;
  repinningLinkId: string | null;
  /** The version picker reads the Field Library, so the repin action is only
   *  offered when the actor can read it — otherwise the picker would 403. */
  canReadFieldLibrary: boolean;
  onChangeCategory: (categoryId: string | null) => void;
  onChangeDescription: (description: string) => void;
  /** Connectors this form may fetch from. Empty hides the data-source control. */
  connectors?: Connector[];
  /** Attach a connector, making this a custom form, or pass null to clear it. */
  onChangeConnector?: (connectorId: string | null) => void;
  /** Entity types available to tag against, and the commit for a change. */
  availableEntityTypes: string[];
  onChangeEntityTypes: (entityTypes: string[]) => void;
  onClone: () => void;
  onCloneVersion: (version: MethodVersion) => void;
  libraryLabel?: string;
  entityLabel?: string;
  libraryItemTitle?: string;
  libraryItemLabel?: string;
  libraryItemLabelPlural?: string;
  selectedItemsLabel?: string;
  libraryItemPossessive?: string;
  libraryEntity?: 'field' | 'step-object';
  codePrefix?: string;
  /** Skin-owned content rendered in the detail panel, after the metadata
   *  section and before the field list. Undefined renders nothing. */
  renderExtra?: (method: MethodWithFields) => ReactNode;
}

export default function MethodFieldsEditor({
  method,
  categories,
  editingField,
  savingField,
  reorderingIndex,
  canWrite,
  loadingDetail,
  existingFieldIds,
  addingFields,
  onAddFromLibrary,
  onAddInheritedField,
  workflowFieldsByEntityType = {},
  onGoToFieldLibrary,
  onEditField,
  onChangeDraft,
  onSaveField,
  onCancelEdit,
  onDeleteField,
  onReorderFields,
  onRepinField,
  repinningLinkId,
  canReadFieldLibrary,
  onChangeCategory,
  onChangeDescription,
  connectors = [],
  onChangeConnector,
  availableEntityTypes,
  onChangeEntityTypes,
  onClone,
  onCloneVersion,
  libraryLabel = 'Field Library',
  entityLabel = 'Form',
  libraryItemTitle = 'Field',
  libraryItemLabel = 'field',
  libraryItemLabelPlural = 'fields',
  selectedItemsLabel = 'form fields',
  libraryItemPossessive = 'field’s',
  libraryEntity = 'field',
  codePrefix = 'FR',
  renderExtra,
}: MethodFieldsEditorProps) {
  const [libraryCollapsed, setLibraryCollapsed] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  // The field whose version picker is open. Field version pins only apply to
  // real Field Library fields, so the action is offered for the 'field' entity
  // and left off step-object lists.
  const [repinField, setRepinField] = useState<MethodVersionField | null>(null);
  const [inheritedPickerOpen, setInheritedPickerOpen] = useState(false);
  const canRepin = libraryEntity === 'field' && canReadFieldLibrary;
  const connectorId = method.version.connector_id ?? null;
  const attachedConnector = connectors.find((c) => c.id === connectorId) ?? null;
  const isCustomForm = Boolean(connectorId);
  const showDataSource = Boolean(onChangeConnector) && libraryEntity === 'field';
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
  );

  const fields = method.fields;

  const handleToggleExpand = (index: number) => {
    if (editingField && editingField.index === index) onCancelEdit();
    else onEditField(index);
  };

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const fromIndex = fields.findIndex((f) => f.id === active.id);
    const toIndex = fields.findIndex((f) => f.id === over.id);
    if (fromIndex !== -1 && toIndex !== -1) onReorderFields(fromIndex, toIndex);
  };

  return (
    <div className="bg-card rounded-xl border border-border">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-border">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-9 h-9 rounded-lg bg-muted flex items-center justify-center shrink-0">
            <FileText className="w-[18px] h-[18px] text-muted-foreground" />
          </div>
          <div className="min-w-0">
            <h3 className="font-semibold text-foreground leading-tight flex items-center gap-2">
              <span className="truncate">{method.identity.name}</span>
              <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-xs font-mono text-muted-foreground">
                {codePrefix}-{String(method.identity.method_code).padStart(2, '0')}
              </span>
              <span className="shrink-0 rounded-full border border-border px-1.5 py-0.5 text-xs text-muted-foreground">
                v{method.version.version}
              </span>
            </h3>
            <p className="text-sm text-muted-foreground mt-0.5">
              An ordered list of {libraryItemLabelPlural}. Editing the list creates a new version.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 ml-4 shrink-0">
          {loadingDetail && <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />}
          <Button variant="outline" onClick={onClone} disabled={!canWrite} icon={<Copy className="w-4 h-4" />}>
            Clone
          </Button>
          <Button
            variant="outline"
            onClick={() => setHistoryOpen(true)}
            icon={<History className="w-4 h-4" />}
          >
            History
          </Button>
        </div>
      </div>

      {/* Metadata: category + description, both edited in place, no version */}
      <div
        className={`grid grid-cols-1 gap-3 border-b border-border px-5 py-4 ${
          showDataSource ? 'md:grid-cols-5' : 'md:grid-cols-4'
        }`}
      >
        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">Category</label>
          <select
            value={method.identity.category_id ?? ''}
            onChange={(e) => onChangeCategory(e.target.value || null)}
            disabled={!canWrite}
            className="h-9 w-full rounded-lg border border-border px-3 text-sm focus:border-cobalt focus:outline-none focus:ring-2 focus:ring-cobalt/20 disabled:opacity-60"
          >
            <option value="">Uncategorised</option>
            {categories.map((category) => (
              <option key={category.category_id} value={category.category_id}>
                {category.name}
              </option>
            ))}
          </select>
        </div>
        {showDataSource && (
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">
              Data source
            </label>
            <select
              value={connectorId ?? ''}
              onChange={(e) => onChangeConnector?.(e.target.value || null)}
              disabled={!canWrite}
              className="h-9 w-full rounded-lg border border-border px-3 text-sm focus:border-cobalt focus:outline-none focus:ring-2 focus:ring-cobalt/20 disabled:opacity-60"
            >
              <option value="">{libraryLabel} fields</option>
              {connectors.length > 0 && (
                <optgroup label="Fetch from a connector">
                  {connectors.map((connector) => (
                    <option key={connector.id} value={connector.id}>
                      {connector.name}
                    </option>
                  ))}
                </optgroup>
              )}
            </select>
          </div>
        )}
        <div className="md:col-span-2">
          <label className="mb-1 block text-xs font-medium text-muted-foreground">
            Description <span className="font-normal">· optional</span>
          </label>
          <input
            type="text"
            defaultValue={method.identity.description ?? ''}
            // Committed on blur rather than per-keystroke: this is a live PATCH,
            // and one request per character would be absurd.
            onBlur={(e) => {
              const next = e.target.value.trim();
              if (next !== (method.identity.description ?? '').trim()) onChangeDescription(next);
            }}
            disabled={!canWrite}
            placeholder={`What this ${entityLabel.toLowerCase()} is for`}
            className="h-9 w-full rounded-lg border border-border px-3 text-sm focus:border-cobalt focus:outline-none focus:ring-2 focus:ring-cobalt/20 disabled:opacity-60"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">
            {libraryEntity === 'field' ? 'Entity type' : 'Entity types'}
          </label>
          {/* Untagged is allowed on purpose, and means this block is offered on
              no workflow state until an entity type is picked. */}
          <EntityTypeTagPicker
            available={availableEntityTypes}
            selected={method.identity.entity_types ?? []}
            disabled={!canWrite}
            onChange={onChangeEntityTypes}
            // Forms don't support multiple linked entity types yet.
            singleSelect={libraryEntity === 'field'}
          />
        </div>
      </div>

      {renderExtra && (
        <div className="border-b border-border px-5 py-4">{renderExtra(method)}</div>
      )}

      {isCustomForm ? (
        <div className="p-4">
          <div className="rounded-xl border border-border bg-background p-4">
            <div className="flex items-start gap-3">
              <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-muted">
                <Plug className="h-4 w-4 text-muted-foreground" />
              </div>
              <div className="min-w-0">
                <p className="text-sm font-medium text-foreground">
                  {attachedConnector?.name ?? 'Fetched from a connector'}
                </p>
                {attachedConnector ? (
                  <p className="mt-0.5 truncate font-mono text-xs text-muted-foreground">
                    {attachedConnector.method} {attachedConnector.base_url}
                    {attachedConnector.path}
                  </p>
                ) : (
                  <p className="mt-0.5 text-xs text-amber-600">
                    This connector is missing or no longer readable.
                  </p>
                )}
                <p className="mt-2 text-xs text-muted-foreground">
                  Its sections and {libraryItemLabelPlural} come from the response, per record.
                  Set the data source back to {libraryLabel} fields to list{' '}
                  {libraryItemLabelPlural} here instead.
                </p>
              </div>
            </div>
          </div>
        </div>
      ) : (
      /* Library on the left; the composite's ordered item list on the right. */
      <div className={`grid items-start p-4 lg:gap-5 ${libraryCollapsed ? 'gap-0 lg:grid-cols-[minmax(0,1fr)_0px]' : 'gap-4 lg:grid-cols-[minmax(0,1.65fr)_minmax(260px,0.85fr)]'}`}>
        {!libraryCollapsed && (
          <div className="min-w-0 lg:order-2">
            <FieldLibraryPanel
              existingFieldIds={existingFieldIds}
              adding={addingFields}
              canWrite={canWrite}
              collapsed={false}
              onToggleCollapsed={() => setLibraryCollapsed(true)}
              onAdd={onAddFromLibrary}
              onGoToFieldLibrary={onGoToFieldLibrary}
              entity={libraryEntity}
              parentLabel={entityLabel}
            />
          </div>
        )}

        <section className="min-w-0 overflow-hidden rounded-xl border border-border bg-background lg:order-1">
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <div>
              <h3 className="text-sm font-semibold text-foreground">Selected {selectedItemsLabel}</h3>
              <p className="mt-0.5 text-xs text-muted-foreground">Drag to reorder · click an item to customize it</p>
            </div>
            <div className="flex items-center gap-2">
              <span className="rounded-full bg-muted px-2.5 py-1 text-xs font-medium text-muted-foreground">
                {fields.length} {fields.length === 1 ? libraryItemLabel : libraryItemLabelPlural}
              </span>
              {onAddInheritedField && (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setInheritedPickerOpen(true)}
                  disabled={!canWrite}
                  icon={<Link2 className="w-3.5 h-3.5" />}
                >
                  Add from related entity
                </Button>
              )}
              {libraryCollapsed && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setLibraryCollapsed(false)}
                  disabled={!canWrite}
                >
                  Add
                </Button>
              )}
            </div>
          </div>
          <div className="space-y-2 p-4">
            {fields.length === 0 ? (
              <div className="rounded-lg border border-dashed border-border py-14 text-center text-muted-foreground">
                <Rows3 className="mx-auto mb-3 h-10 w-10 text-muted-foreground/50" />
                <p className="text-sm font-medium text-foreground">No {libraryItemLabelPlural} selected yet</p>
                <p className="mx-auto mt-1 max-w-xs text-xs text-muted-foreground">
                  Choose {libraryItemLabelPlural} from the {libraryLabel} on the left to build this {entityLabel.toLowerCase()}.
                </p>
              </div>
            ) : (
              <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
                <SortableContext items={fields.map((f) => f.id)} strategy={verticalListSortingStrategy}>
                  {fields.map((field, index) => (
                    <MethodFieldRow
                      key={field.id}
                      field={field}
                      isExpanded={editingField?.index === index}
                      isReordering={reorderingIndex === index}
                      editingDraft={editingField?.index === index ? editingField : null}
                      savingField={savingField}
                      canWrite={canWrite}
                      onToggleExpand={() => handleToggleExpand(index)}
                      onChangeDraft={onChangeDraft}
                      onSave={onSaveField}
                      onCancel={onCancelEdit}
                      onDelete={() => onDeleteField(index)}
                      onRepin={canRepin && canWrite ? () => setRepinField(field) : undefined}
                      libraryLabel={libraryLabel}
                      entityLabel={entityLabel}
                      libraryItemLabel={libraryItemLabel}
                      libraryItemPossessive={libraryItemPossessive}
                    />
                  ))}
                </SortableContext>
              </DndContext>
            )}
          </div>
        </section>
      </div>
      )}

      {/* Footer */}
      <div className="flex items-center justify-between px-5 py-3 border-t border-border">
        <span className="text-xs text-muted-foreground">
          {libraryItemTitle} types and settings are owned by the {libraryLabel}.
        </span>
        <button
          type="button"
          onClick={onGoToFieldLibrary}
          className="flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
        >
          <ExternalLink className="w-3 h-3" />
          Manage {libraryLabel.toLowerCase()}
        </button>
      </div>

      <MethodVersionHistory
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        method={method.identity}
        canWrite={canWrite}
        onCloneVersion={(version) => {
          setHistoryOpen(false);
          onCloneVersion(version);
        }}
        entityLabel={entityLabel}
        codePrefix={codePrefix}
      />

      {inheritedPickerOpen && onAddInheritedField && (
        <MethodInheritedFieldPicker
          blockEntityTypes={method.identity.entity_types ?? []}
          currentFields={fields}
          workflowFieldsByEntityType={workflowFieldsByEntityType}
          onAdd={onAddInheritedField}
          onClose={() => setInheritedPickerOpen(false)}
        />
      )}

      {repinField && (
        <MethodFieldVersionDialog
          field={repinField}
          busy={repinningLinkId === repinField.id}
          entityLabel={entityLabel}
          libraryItemTitle={libraryItemTitle}
          onClose={() => setRepinField(null)}
          onRepin={(versionId) => {
            void onRepinField(repinField.id, versionId).then((ok) => {
              if (ok) setRepinField(null);
            });
          }}
        />
      )}
    </div>
  );
}
