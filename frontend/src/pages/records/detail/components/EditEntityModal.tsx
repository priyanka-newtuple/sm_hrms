import type React from 'react';
import { AlertCircle, Check, Loader2, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { FieldInput, SchemaTabs } from '@/core/components';
import EntityIteratorControls from '@/core/components/EntityIteratorControls';
import type { EntityIteratorState } from '@/core/hooks/useEntityIterator';
import type { WorkflowEntityState } from '../../../../core/services/api';
import type { FormField, FormSchema } from '../../../../core/types';
import { displayEntityType } from '../helpers';
import EntityFormFields from './EntityFormFields';
import { IDENTIFIER_FIELD, IDENTIFIER_FIELD_KEY } from '@/shared/utils/entityForm';

interface EditEntityModalProps {
  /** Record-level controls rendered above the form tabs — the timer strip. */
  timerSlot?: React.ReactNode;
  /** Disables every field while the record-level timer is paused. */
  fieldsLocked?: boolean;
  fieldsLockedHint?: string;
  entity: WorkflowEntityState;
  /** The active form (whose fields are shown). */
  schema: FormSchema | null;
  /** All forms attached to this entity type; each renders as a tab. */
  schemas: FormSchema[];
  onSelectTab: (schema: FormSchema) => void;
  fields: FormField[];
  values: Record<string, unknown>;
  onFieldChange: (id: string, value: unknown) => void;
  error: string | null;
  saving: boolean;
  onClose: () => void;
  onSubmit: () => void;
  readOnly?: boolean;
  identifierLabel: string;
  identifierReadOnly: boolean;
  iterator?: EntityIteratorState;
  loading?: boolean;
}

export default function EditEntityModal({
  timerSlot,
  fieldsLocked,
  fieldsLockedHint,
  entity,
  schema,
  schemas,
  onSelectTab,
  fields,
  values,
  onFieldChange,
  error,
  saving,
  onClose,
  onSubmit,
  readOnly = false,
  identifierLabel,
  identifierReadOnly,
  iterator,
  loading = false,
}: EditEntityModalProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/45 p-4 backdrop-blur-sm">
      <div className="flex h-[75vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-border bg-card text-card-foreground shadow-2xl">
        <div className="flex items-center justify-between border-b border-border bg-[var(--modal-header-background)] p-4 text-[var(--modal-header-foreground)]">
          <div>
            <h3 className="text-lg font-semibold">
              {readOnly ? 'View' : 'Edit'} {displayEntityType(entity.entity_type)}
            </h3>
            {schema && <p className="mt-0.5 text-sm opacity-70">{schema.name}</p>}
          </div>
          <div className="flex items-center gap-2">
            {iterator && (
              <EntityIteratorControls
                {...iterator}
                disabled={iterator.disabled || loading || saving}
              />
            )}
            <Button
              variant="ghost"
              onClick={onClose}
              className="rounded-full p-1.5 opacity-70 transition-colors hover:bg-current/10 hover:opacity-100"
            >
              <X className="w-5 h-5" />
            </Button>
          </div>
        </div>

        {timerSlot}
        <SchemaTabs schemas={schemas} activeKey={schema?.schema_key} onSelect={onSelectTab} />

        <div className="relative flex-1 overflow-y-auto p-4 space-y-4">
          {loading && (
            <div className="absolute inset-0 z-10 flex items-center justify-center bg-card/80">
              <Loader2 className="h-6 w-6 animate-spin text-cobalt" aria-label="Loading entity" />
            </div>
          )}
          {error && !readOnly && (
            <div className="flex items-center gap-2 rounded-lg border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              {error}
            </div>
          )}
          {schema?.schema_key === schemas[0]?.schema_key && (
            <div>
              <label className="mb-2 block text-sm font-medium text-foreground">
                {identifierLabel}
                {!identifierReadOnly && !readOnly && (
                  <span className="ml-1 text-destructive">*</span>
                )}
              </label>
              {identifierReadOnly || readOnly ? (
                <div className="rounded-md border border-border bg-muted/50 px-3 py-2 text-sm text-foreground">
                  {String(values[IDENTIFIER_FIELD_KEY] ?? '—')}
                </div>
              ) : (
                <FieldInput
                  field={{ ...IDENTIFIER_FIELD, label: identifierLabel }}
                  value={values[IDENTIFIER_FIELD_KEY]}
                  onChange={(value) => onFieldChange(IDENTIFIER_FIELD_KEY, value)}
                />
              )}
            </div>
          )}
          <EntityFormFields
            fieldsLocked={fieldsLocked}
            fieldsLockedHint={fieldsLockedHint}
            fields={fields}
            values={values}
            onChange={onFieldChange}
            entityType={entity.entity_type}
            entityId={entity.entity_id}
            mode={readOnly ? 'view' : 'edit'}
          />
        </div>
        <div className="flex items-center justify-between border-t border-border bg-muted/30 p-4">
          <Button onClick={onClose} variant="ghost">
            {readOnly ? 'Close' : 'Cancel'}
          </Button>
          {!readOnly && (
            <Button variant="ghost"
              onClick={onSubmit}
              loading={saving}
              icon={!saving ? <Check className="w-4 h-4" /> : undefined}
            >
              Save Changes
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
