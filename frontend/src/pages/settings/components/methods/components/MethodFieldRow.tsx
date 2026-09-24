/**
 * MethodFieldRow
 *
 * One field inside a method. The collapsed header mirrors the Forms tab's
 * FieldRow (drag grip, type icon, label, key, badges, actions menu), but the
 * expanded half is deliberately much smaller: a method owns only its *view* of
 * a field — label, placeholder, required — while the type and settings belong
 * to the pinned Field Library version and are shown read-only.
 */

import {
  ChevronDown,
  ChevronRight,
  GripVertical,
  Loader2,
  MoreHorizontal,
  Trash2,
  Check,
  AlignLeft,
  Calendar,
  CheckSquare,
  GitBranch,
  Hash,
  Link,
  Link2,
  List,
  Mail,
  Minus,
  Phone,
  Timer,
  Type,
} from 'lucide-react';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import type { FieldType, MethodVersionField } from '@/core/types';
import { FIELD_TYPE_LABELS } from '../../form-config/constants';
import type { MethodFieldDraft } from '../hooks/useMethodFields';

const TYPE_ICONS: Record<string, React.ReactNode> = {
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
  timer_duration: <Timer className="w-3.5 h-3.5" />,
};

/** `field_type` arrives as a plain string (the catalogue's own code), so an
 *  unknown or newly-catalogued type degrades to its raw code rather than
 *  rendering blank. */
function typeLabel(fieldType: string): string {
  return FIELD_TYPE_LABELS[fieldType as FieldType] ?? fieldType;
}

interface MethodFieldRowProps {
  field: MethodVersionField;
  isExpanded: boolean;
  isReordering: boolean;
  editingDraft: MethodFieldDraft | null;
  savingField: boolean;
  canWrite: boolean;
  onToggleExpand: () => void;
  onChangeDraft: (draft: MethodFieldDraft) => void;
  onSave: () => void;
  onCancel: () => void;
  onDelete: () => void;
  /** Opens the version picker for this field. Absent (e.g. step-object lists
   *  that do not pin field versions) hides the action. */
  onRepin?: () => void;
  libraryLabel?: string;
  entityLabel?: string;
  libraryItemLabel?: string;
  libraryItemPossessive?: string;
}

export default function MethodFieldRow({
  field,
  isExpanded,
  isReordering,
  editingDraft,
  savingField,
  canWrite,
  onToggleExpand,
  onChangeDraft,
  onSave,
  onCancel,
  onDelete,
  onRepin,
  libraryLabel = 'Field Library',
  entityLabel = 'Form',
  libraryItemLabel = 'field',
  libraryItemPossessive = 'field’s',
}: MethodFieldRowProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: field.id,
    disabled: !canWrite || isExpanded,
  });

  const style = { transform: CSS.Transform.toString(transform), transition };
  // The method's own label wins; the field's library key is the fallback, so a
  // never-relabelled field still reads as something.
  const displayLabel = field.label?.trim() || field.field_key;

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
        <button
          type="button"
          onClick={canWrite ? onToggleExpand : undefined}
          disabled={!canWrite}
          className="text-muted-foreground hover:text-foreground disabled:opacity-30 shrink-0"
          title={isExpanded ? 'Close' : `Edit how this ${libraryItemLabel} appears in the ${entityLabel.toLowerCase()}`}
        >
          {isExpanded ? (
            <ChevronDown className="w-4 h-4" />
          ) : (
            <ChevronRight className="w-4 h-4" />
          )}
        </button>

        <span
          {...attributes}
          {...listeners}
          className="shrink-0 cursor-grab active:cursor-grabbing touch-none"
          aria-label="Drag to reorder"
        >
          <GripVertical className="w-4 h-4 text-muted-foreground/60 hover:text-muted-foreground transition-colors" />
        </span>

        <div className="w-7 h-7 rounded-md bg-muted flex items-center justify-center text-muted-foreground shrink-0">
          {TYPE_ICONS[field.field_type] ?? <Type className="w-3.5 h-3.5" />}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="font-semibold text-sm text-foreground">{displayLabel}</span>
            <code className="text-xs text-muted-foreground bg-muted px-1.5 py-0.5 rounded font-mono">
              {field.field_key}
            </code>
            {field.required && (
              <span className="text-xs font-medium text-info bg-info-subtle border border-info/30 px-1.5 py-0.5 rounded-full">
                Required
              </span>
            )}
            {field.ownership === 'inherited' && (
              <span
                className="inline-flex items-center gap-1 text-xs font-medium text-primary bg-primary/10 border border-primary/20 px-1.5 py-0.5 rounded-full"
                title={`Read-only on the record; filled from the linked ${field.source_entity_type ?? ''} record. Only procedures using this block carry it.`}
              >
                <Link2 className="w-3 h-3" />
                Inherited from {field.source_entity_type}.{field.source_field_key}
              </span>
            )}
          </div>
          <div className="text-xs text-muted-foreground mt-0.5">
            {typeLabel(field.field_type)}
            {field.ownership === 'inherited' && ' · value comes from the related record'}
          </div>
        </div>

        {isReordering && <Loader2 className="w-4 h-4 animate-spin text-muted-foreground shrink-0" />}

        {canWrite && (
          <DropdownMenu>
            <DropdownMenuTrigger
              render={
                <button
                  type="button"
                  className="shrink-0 rounded p-1 text-muted-foreground hover:bg-muted"
                  title="Actions"
                />
              }
            >
              <MoreHorizontal className="w-4 h-4" />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-48">
              {onRepin && (
                <>
                  <DropdownMenuItem onClick={onRepin}>
                    <GitBranch className="w-3.5 h-3.5 mr-2" />
                    Change {libraryItemLabel} version…
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                </>
              )}
              <DropdownMenuItem onClick={onDelete} className="text-destructive focus:text-destructive">
                <Trash2 className="w-3.5 h-3.5 mr-2" />
                Remove from {entityLabel.toLowerCase()}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </div>

      {/* Expanded — the method's own view of the field, nothing more */}
      {isExpanded && editingDraft && (
        <div className="border-t border-border px-4 py-4 space-y-3">
          <p className="text-xs text-muted-foreground">
            The {libraryItemPossessive} type and configuration come from {libraryLabel} and can’t be changed
            here. Edit the {libraryItemLabel} itself in {libraryLabel}.
          </p>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">
                Label <span className="font-normal">· optional</span>
              </label>
              <input
                type="text"
                value={editingDraft.label}
                onChange={(e) => onChangeDraft({ ...editingDraft, label: e.target.value })}
                autoFocus
                placeholder={field.field_key}
                className="w-full rounded-lg border border-border px-3 py-2 text-sm focus:border-cobalt focus:outline-none focus:ring-2 focus:ring-cobalt/20"
              />
              <p className="mt-1 text-xs text-muted-foreground">
                Overrides the {libraryItemPossessive} own name inside this {entityLabel.toLowerCase()}.
              </p>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">
                Placeholder text <span className="font-normal">· optional</span>
              </label>
              <input
                type="text"
                value={editingDraft.placeholder}
                onChange={(e) => onChangeDraft({ ...editingDraft, placeholder: e.target.value })}
                placeholder="e.g., Enter value..."
                className="w-full rounded-lg border border-border px-3 py-2 text-sm focus:border-cobalt focus:outline-none focus:ring-2 focus:ring-cobalt/20"
              />
            </div>
          </div>

          <div className="flex items-center justify-between py-1">
            <div>
              <span className="text-sm font-medium text-foreground">Required</span>
              <p className="mt-0.5 text-xs text-muted-foreground">
                Required in this {entityLabel.toLowerCase()}, regardless of the {libraryItemPossessive} own setting.
              </p>
            </div>
            <Switch
              checked={editingDraft.required}
              onCheckedChange={(checked) => onChangeDraft({ ...editingDraft, required: checked })}
            />
          </div>

          <div className="flex items-center justify-end gap-2 border-t border-border pt-3">
            <Button variant="secondary" onClick={onCancel} disabled={savingField}>
              Cancel
            </Button>
            <Button
              variant="ghost"
              onClick={onSave}
              disabled={savingField}
              icon={!savingField ? <Check className="w-4 h-4" /> : undefined}
            >
              {savingField ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : null}
              Save {libraryItemLabel}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
