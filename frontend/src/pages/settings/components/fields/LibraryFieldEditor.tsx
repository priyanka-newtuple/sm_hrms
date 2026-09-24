/**
 * LibraryFieldEditor
 *
 * The Fields create/edit form. Every type-specific input it offers — picklist
 * binding, Extend Field, table columns, auto-number affix, calc builder — comes
 * from the shared `FieldTypeConfig`, which the Forms tab's `FieldRow` mounts
 * too, so the two surfaces cannot drift.
 *
 * What is only here: the integer `unit` selector (the form-schema path has
 * nowhere to persist a unit, library settings are free-form) and a Description
 * input, since the Fields API has a description the Forms tab's own field model
 * doesn't. What is only in `FieldRow`: drag-to-reorder, the collapsed row
 * header and the "···" delete menu — FieldsTab supplies its own row chrome and
 * Archive action.
 */

import { Check, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import type { FormField, FieldType, Picklist } from '@/core/types';
import { FIELD_TYPES } from '../form-config/constants';
import FieldTypeConfig from '../form-config/components/field-config/FieldTypeConfig';
import ReadOnlyToggle from '../form-config/components/field-config/ReadOnlyToggle';
import IntegerUnitConfig from '../form-config/components/field-config/IntegerUnitConfig';
import { fieldTypeChangePatch } from '../form-config/components/field-config/fieldTypeChangePatch';
import { useTableJsonDialog } from '../form-config/components/field-config/TableJsonDialog';

interface LibraryFieldEditorProps {
  field: FormField;
  description: string;
  onChangeDescription: (value: string) => void;
  allFields: FormField[];
  picklists: Picklist[];
  isNew: boolean;
  savingField: boolean;
  canWrite: boolean;
  onChangeField: (field: FormField) => void;
  onSave: () => void;
  onCancel: () => void;
  entityLabel?: string;
  fieldTypeOptions?: readonly { value: string; label: string }[];
}

export default function LibraryFieldEditor({
  field: draft,
  description,
  onChangeDescription,
  allFields,
  picklists,
  isNew,
  savingField,
  canWrite,
  onChangeField,
  onSave,
  onCancel,
  entityLabel = 'Field',
  fieldTypeOptions = FIELD_TYPES,
}: LibraryFieldEditorProps) {
  const entityLower = entityLabel.toLowerCase();

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

  const update = (patch: Partial<FormField>) => {
    if (canWrite) onChangeField({ ...draft, ...patch });
  };

  const { openTableJson, dialog: tableJsonDialog } = useTableJsonDialog(
    draft.table_config,
    (tableConfig) => update({ table_config: tableConfig }),
    canWrite,
    draft.label,
    `library-table-json-title-${draft.id || 'new'}`,
  );

  return (
    <div className="space-y-3 px-4 pb-4 pt-4">
      {/* Field name + Type */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">{entityLabel} name</label>
          <input
            type="text"
            value={draft.label}
            onChange={(e) => update({ label: e.target.value })}
            disabled={!canWrite}
            autoFocus
            placeholder="e.g., Reagent name"
            className="w-full rounded-lg border border-border px-3 py-2 text-sm focus:border-cobalt focus:outline-none focus:ring-2 focus:ring-cobalt/20"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">Type</label>
          <select
            value={draft.type}
            onChange={(e) => update(fieldTypeChangePatch(e.target.value as FieldType, draft))}
            disabled={!canWrite}
            className="w-full rounded-lg border border-border px-3 py-2 text-sm focus:border-cobalt focus:outline-none focus:ring-2 focus:ring-cobalt/20 disabled:cursor-not-allowed disabled:bg-muted"
          >
            {fieldTypeOptions.map((t) => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
        </div>
      </div>

      {draft.type === 'integer' && (
        <IntegerUnitConfig field={draft} canWrite={canWrite} onChange={update} />
      )}

      <FieldTypeConfig
        field={draft}
        picklists={picklists}
        canWrite={canWrite}
        onChange={update}
        numericFields={numericFields}
        tableFields={tableFieldOptions}
        tableInstanceId={0}
      />

      {/* Placeholder */}
      <div>
        <label className="mb-1 block text-xs font-medium text-muted-foreground">
          Placeholder text <span className="font-normal text-muted-foreground">· optional</span>
        </label>
        <input
          type="text"
          value={draft.placeholder || ''}
          onChange={(e) => update({ placeholder: e.target.value || undefined })}
          disabled={!canWrite}
          placeholder="e.g., Enter value..."
          className="w-full rounded-lg border border-border px-3 py-2 text-sm focus:border-cobalt focus:outline-none focus:ring-2 focus:ring-cobalt/20"
        />
      </div>

      {/* Description, the one input FieldRow has no slot for, since the
          Forms tab's own field model has no description. */}
      <div>
        <label className="mb-1 block text-xs font-medium text-muted-foreground">
          Description <span className="font-normal text-muted-foreground">· optional</span>
        </label>
        <textarea
          value={description}
          onChange={(e) => onChangeDescription(e.target.value)}
          disabled={!canWrite}
          rows={2}
          placeholder={`What this ${entityLower} is for, and when to use it`}
          className="w-full rounded-lg border border-border px-3 py-2 text-sm focus:border-cobalt focus:outline-none focus:ring-2 focus:ring-cobalt/20"
        />
      </div>

      {/* Required toggle */}
      <div className="flex items-center justify-between py-1">
        <div>
          <span className="text-sm font-medium text-foreground">Required</span>
          <p className="mt-0.5 text-xs text-muted-foreground">Records can't be saved unless this {entityLower} has a value.</p>
        </div>
        <Switch disabled={!canWrite} checked={!!draft.required} onCheckedChange={(checked) => update({ required: checked })} />
      </div>

      {/* Full width toggle */}
      {draft.type !== 'section' && (
        <div className="flex items-center justify-between py-1">
          <div>
            <span className="text-sm font-medium text-foreground">Full width</span>
            <p className="mt-0.5 text-xs text-muted-foreground">{entityLabel} spans the full row instead of half.</p>
          </div>
          <Switch
            disabled={!canWrite}
            checked={draft.col_span !== 'half'}
            onCheckedChange={(checked) => update({ col_span: checked ? 'full' : 'half' })}
          />
        </div>
      )}

      {draft.type !== 'section' && (
        <ReadOnlyToggle
          checked={!!draft.read_only}
          disabled={!canWrite}
          onCheckedChange={(checked) => update({ read_only: checked })}
        />
      )}

      {draft.type === 'table' && (
        <div className="flex justify-end gap-2 text-xs">
          <button type="button" onClick={() => openTableJson('view')} className="text-muted-foreground hover:text-foreground hover:underline">
            View table JSON
          </button>
          <span className="text-muted-foreground">·</span>
          <button type="button" onClick={() => openTableJson('edit')} disabled={!canWrite} className="text-muted-foreground hover:text-foreground hover:underline disabled:opacity-50">
            Edit table JSON
          </button>
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center justify-end gap-2 border-t border-border pt-3">
        <Button variant="secondary" onClick={onCancel} disabled={savingField}>
          Cancel
        </Button>
        <Button
          variant="ghost"
          onClick={onSave}
          disabled={!canWrite || savingField}
          icon={!savingField ? <Check className="h-4 w-4" /> : undefined}
        >
          {savingField ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : null}
          {isNew ? `Add ${entityLower}` : `Save ${entityLower}`}
        </Button>
      </div>

      {tableJsonDialog}
    </div>
  );
}
