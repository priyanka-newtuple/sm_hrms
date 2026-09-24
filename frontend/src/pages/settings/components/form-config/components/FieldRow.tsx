import { useState } from 'react';
import {
  ChevronRight,
  ChevronDown,
  GripVertical,
  MoreHorizontal,
  Lock,
  Loader2,
  Check,
  Hash,
  Type,
  Mail,
  Calendar,
  List,
  CheckSquare,
  Link,
  Link2,
  Minus,
  AlignLeft,
  Phone,
  Paperclip,
} from 'lucide-react';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import ReadOnlyToggle from './field-config/ReadOnlyToggle';
import type { FormField, FieldType, Picklist } from '../../../../../core/types';
import type { EditingField } from '../types';
import { FIELD_TYPE_LABELS, FIELD_TYPES } from '../constants';
import FieldTypeConfig from './field-config/FieldTypeConfig';
import { fieldTypeChangePatch } from './field-config/fieldTypeChangePatch';
import { useTableJsonDialog } from './field-config/TableJsonDialog';

function FieldTypeIcon({ type }: { type: FieldType }) {
  const icons: Partial<Record<FieldType, React.ReactNode>> = {
    text: <Type className="w-3.5 h-3.5" />,
    textarea: <AlignLeft className="w-3.5 h-3.5" />,
    email: <Mail className="w-3.5 h-3.5" />,
    phone: <Phone className="w-3.5 h-3.5" />,
    number: <Hash className="w-3.5 h-3.5" />,
    integer: <Hash className="w-3.5 h-3.5" />,
    date: <Calendar className="w-3.5 h-3.5" />,
    datetime: <Calendar className="w-3.5 h-3.5" />,
    select: <ChevronDown className="w-3.5 h-3.5" />,
    multi_select: <List className="w-3.5 h-3.5" />,
    picklist_multi: <List className="w-3.5 h-3.5" />,
    boolean: <CheckSquare className="w-3.5 h-3.5" />,
    url: <Link className="w-3.5 h-3.5" />,
    table: <List className="w-3.5 h-3.5" />,
    auto_number: <Hash className="w-3.5 h-3.5" />,
    section: <Minus className="w-3.5 h-3.5" />,
    reference: <Link2 className="w-3.5 h-3.5" />,
    document: <Paperclip className="w-3.5 h-3.5" />,
  };
  return (
    <div className="w-7 h-7 rounded-md bg-muted flex items-center justify-center text-muted-foreground shrink-0">
      {icons[type] ?? <Type className="w-3.5 h-3.5" />}
    </div>
  );
}

interface FieldRowProps {
  field: FormField;
  index: number;
  totalFields: number;
  allFields: FormField[];
  picklists: Picklist[];
  isReordering: boolean;
  isExpanded: boolean;
  editingDraft: EditingField | null;
  savingField: boolean;
  canWrite: boolean;
  sortable?: boolean;
  onToggleExpand: () => void;
  onChangeField: (updated: EditingField) => void;
  onSave: () => void;
  onSaveAndAddNew?: () => void;
  onCancel: () => void;
  onDelete: () => void;
}

export default function FieldRow({
  field,
  index,
  allFields,
  picklists,
  isReordering,
  isExpanded,
  editingDraft,
  savingField,
  canWrite,
  sortable = true,
  onToggleExpand,
  onChangeField,
  onSave,
  onSaveAndAddNew,
  onCancel,
  onDelete,
}: FieldRowProps) {
  const [showMenu, setShowMenu] = useState(false);
  const draft = editingDraft?.field ?? field;
  const numericFields = allFields
    .filter((f) => (f.type === 'integer' || f.type === 'number') && f.id !== draft.id)
    .map((f) => ({ id: f.id, label: f.label || f.id }));
  const tableFieldOptions = allFields
    .filter((f) => f.type === 'table')
    .map((f) => ({
      id: f.id,
      label: f.label || f.id,
      columns: (f.table_config?.columns ?? []).map((c) => ({ id: c.id, label: c.label || c.id })),
    }));
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: field.id || String(index), disabled: !sortable || !canWrite || isExpanded });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  const update = (patch: Partial<typeof draft>) => {
    if (!editingDraft) return;
    onChangeField({ ...editingDraft, field: { ...draft, ...patch } });
  };

  const { openTableJson, dialog: tableJsonDialog } = useTableJsonDialog(
    draft.table_config,
    (tableConfig) => update({ table_config: tableConfig }),
    canWrite,
    draft.label,
    `table-json-title-${field.id || index}`,
  );

  const canExpand = field.editable !== false && canWrite;

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`border rounded-xl overflow-visible transition-colors ${
        isExpanded ? 'border-primary/30 shadow-sm' : 'border-border bg-card'
      } ${isDragging ? 'opacity-50 shadow-xl z-50' : ''}`}
    >
      {/* Row header — always visible */}
      <div className="flex items-center gap-2 px-4 py-3">
        {/* Expand toggle */}
        <button
          type="button"
          onClick={canExpand ? onToggleExpand : undefined}
          disabled={!canExpand}
          className="text-muted-foreground hover:text-muted-foreground disabled:opacity-30 shrink-0"
        >
          {isExpanded ? (
            <ChevronDown className="w-4 h-4" />
          ) : (
            <ChevronRight className="w-4 h-4" />
          )}
        </button>

        {/* Drag grip handle */}
        <span
          {...attributes}
          {...listeners}
          className="shrink-0 cursor-grab active:cursor-grabbing touch-none"
          aria-label="Drag to reorder"
        >
          <GripVertical className="w-4 h-4 text-muted-foreground/60 hover:text-muted-foreground transition-colors" />
        </span>

        {/* Type icon */}
        <FieldTypeIcon type={field.type} />

        {/* Field info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="font-semibold text-sm text-foreground">{field.label}</span>
            <code className="text-xs text-muted-foreground bg-muted px-1.5 py-0.5 rounded font-mono">
              {field.id}
            </code>
            {field.required && (
              <span className="text-xs font-medium text-info bg-info-subtle border border-info/30 px-1.5 py-0.5 rounded-full">
                Required
              </span>
            )}
            {field.system && (
              <span title="System field">
                <Lock className="w-3 h-3 text-muted-foreground shrink-0" />
              </span>
            )}
            {field.type === 'reference' && field.id.includes('.') && (
              <span
                className="text-xs font-medium text-warning bg-warning-subtle border border-warning/30 px-1.5 py-0.5 rounded-full"
                title="Added before relations existed. Delete and re-add via 'Add from related' after defining a relation in Entity Types."
              >
                no relation
              </span>
            )}
          </div>
          <div className="text-xs text-muted-foreground mt-0.5">
            {FIELD_TYPE_LABELS[field.type] || field.type}
          </div>
        </div>

        {isReordering && (
          <Loader2 className="w-4 h-4 animate-spin text-muted-foreground shrink-0" />
        )}

        {/* ··· menu */}
        <div className="relative shrink-0">
          <button
            type="button"
            onClick={() => setShowMenu((v) => !v)}
            className="p-1.5 rounded text-muted-foreground hover:text-muted-foreground hover:bg-muted"
          >
            <MoreHorizontal className="w-4 h-4" />
          </button>
          {showMenu && (
            <>
              <div className="fixed inset-0 z-10" onClick={() => setShowMenu(false)} />
              <div className="absolute right-0 top-full mt-1 z-20 bg-card border border-border rounded-lg shadow-lg py-1 min-w-[130px]">
                {field.system ? (
                  <div className="px-3 py-2 text-xs text-muted-foreground">System field</div>
                ) : (
                  <>
                    {draft.type === 'table' && (
                      <>
                        <button
                          type="button"
                          onClick={() => {
                            setShowMenu(false);
                            openTableJson('view');
                          }}
                          className="w-full text-left px-3 py-2 text-sm text-foreground hover:bg-muted/50"
                        >
                          View JSON
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setShowMenu(false);
                            openTableJson('edit');
                          }}
                          disabled={!canWrite}
                          className="w-full text-left px-3 py-2 text-sm text-foreground hover:bg-muted/50 disabled:opacity-50"
                        >
                          Edit JSON
                        </button>
                        <div className="my-1 border-t border-border" />
                      </>
                    )}
                    <button
                      type="button"
                      onClick={() => {
                        setShowMenu(false);
                        onDelete();
                      }}
                      disabled={!canWrite}
                      className="w-full text-left px-3 py-2 text-sm text-destructive hover:bg-destructive-subtle disabled:opacity-50"
                    >
                      Delete field
                    </button>
                  </>
                )}
              </div>
            </>
          )}
        </div>
      </div>

      {/* Inline form — shown when expanded */}
      {isExpanded && editingDraft && (
        <div className="px-4 pb-4 pt-1 border-t border-border space-y-3">
          {/* Field name + Type */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1">
                Field name
              </label>
              <input
                type="text"
                value={draft.label}
                onChange={(e) => update({ label: e.target.value })}
                disabled={field.system}
                autoFocus
                placeholder="e.g., Custom Field"
                className="w-full px-3 py-2 border border-border rounded-lg text-sm focus:ring-2 focus:ring-cobalt focus:border-cobalt disabled:bg-muted"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1">Type</label>
              <select
                value={draft.type}
                onChange={(e) => update(fieldTypeChangePatch(e.target.value as FieldType, draft))}
                disabled={field.system}
                className="w-full px-3 py-2 border border-border rounded-lg text-sm focus:ring-2 focus:ring-cobalt focus:border-cobalt disabled:bg-muted"
              >
                {FIELD_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <FieldTypeConfig
            field={draft}
            picklists={picklists}
            canWrite={canWrite}
            onChange={update}
            numericFields={numericFields}
            tableFields={tableFieldOptions}
            tableInstanceId={index}
          />

          {/* Placeholder */}
          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1">
              Placeholder text{' '}
              <span className="font-normal text-muted-foreground">· optional</span>
            </label>
            <input
              type="text"
              value={draft.placeholder || ''}
              onChange={(e) => update({ placeholder: e.target.value || undefined })}
              placeholder="e.g., Enter value..."
              className="w-full px-3 py-2 border border-border rounded-lg text-sm focus:ring-2 focus:ring-cobalt focus:border-cobalt"
            />
          </div>

          {/* Required toggle */}
          <div className="flex items-center justify-between py-1">
            <div>
              <span className="text-sm font-medium text-foreground">Required</span>
              <p className="text-xs text-muted-foreground mt-0.5">
                Records can't be saved unless this field has a value.
              </p>
            </div>
            <Switch
              id={`required-${index}`}
              checked={!!draft.required}
              onCheckedChange={(checked) => update({ required: checked })}
            />
          </div>

          {/* Full width toggle */}
          {draft.type !== 'section' && (
            <div className="flex items-center justify-between py-1">
              <div>
                <span className="text-sm font-medium text-foreground">Full width</span>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Field spans the full row instead of half.
                </p>
              </div>
              <Switch
                id={`col-span-${index}`}
                checked={draft.col_span !== 'half'}
                onCheckedChange={(checked) =>
                  update({ col_span: checked ? 'full' : 'half' })
                }
              />
            </div>
          )}

          {draft.type !== 'section' && (
            <ReadOnlyToggle
              id={`read-only-${index}`}
              checked={!!draft.read_only}
              onCheckedChange={(checked) => update({ read_only: checked })}
            />
          )}

          {/* Actions */}
          <div className="flex items-center justify-end gap-2 pt-1 border-t border-border">
            <Button variant="secondary" onClick={onCancel} disabled={savingField}>
              Cancel
            </Button>
            {editingDraft.isNew && onSaveAndAddNew && (
              <Button
                variant="outline"
                onClick={onSaveAndAddNew}
                disabled={!canWrite || savingField}
              >
                {savingField ? (
                  <Loader2 className="w-4 h-4 animate-spin mr-1" />
                ) : null}
                Save & add another
              </Button>
            )}
            <Button
              variant="ghost"
              onClick={onSave}
              disabled={!canWrite || savingField}
              icon={!savingField ? <Check className="w-4 h-4" /> : undefined}
            >
              {savingField ? (
                <Loader2 className="w-4 h-4 animate-spin mr-1" />
              ) : null}
              {editingDraft.isNew ? 'Add field' : 'Save field'}
            </Button>
          </div>
        </div>
      )}
      {tableJsonDialog}
    </div>
  );
}
