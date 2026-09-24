import type React from 'react';
import { AlertCircle, Check, X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { SchemaTabs, FieldInput } from '@/core/components';
import SourceLinkFields from '@/core/components/SourceLinkFields';
import CreateEntityDocumentUpload from '@/core/components/CreateEntityDocumentUpload';
import type { SourcePicker } from '@/core/hooks/useSourcePickers';
import type { WorkflowEntityState } from '../../../../core/services/api';
import type { FormSchema, FormField, StateMachineRecord } from '../../../../core/types';
import { IDENTIFIER_FIELD } from '../../../../shared/utils/entityForm';
import { useIdentifierConfig } from '@/shared/hooks/useIdentifierConfig';
import { displayEntityType } from '../helpers';
import EntityFormFields from './EntityFormFields';

interface CreateEntityModalProps {
  /** Record-level controls rendered above the form tabs — the timer strip.
   *  Passed in as a node because the container owns the run state. */
  timerSlot?: React.ReactNode;
  /** Disables every field while the record-level timer is paused. */
  fieldsLocked?: boolean;
  fieldsLockedHint?: string;
  routeEntityType: string;
  /** Published workflows available for enrollment on this entity type. */
  publishedWorkflows: StateMachineRecord[];
  /** True while the workflow list is being fetched. */
  workflowsLoading: boolean;
  /** Non-null if the workflow list failed to load; entity creation still works without a workflow. */
  machinesError?: string | null;
  /** The machine_name of the currently selected workflow, or null for "no workflow". */
  selectedMachineName: string | null;
  onWorkflowChange: (machineName: string | null) => void;
  /** The active form (whose fields are shown). */
  schema: FormSchema | null;
  /** All forms attached to this entity type; each renders as a tab. */
  schemas: FormSchema[];
  noWorkflowForms: boolean;
  onSelectTab: (schema: FormSchema) => void;
  formFields: FormField[];
  formData: Record<string, unknown>;
  onFieldChange: (id: string, value: unknown) => void;
  /** One picker per relation declaration targeting this entity type. */
  sourcePickers: SourcePicker[];
  sourceSelections: Record<string, string>;
  onSourceChange: (defId: string, entityId: string) => void;
  error: string | null;
  creating: boolean;
  /**
   * Accepted for compatibility but intentionally NOT used to gate submit: a
   * required/invalid field on a non-active tab must not silently disable the
   * button, otherwise `onSubmit`/`handleCreate` (which switches to the
   * offending tab and shows the error) becomes unreachable.
   */
  isFormInvalid?: boolean;
  onClose: () => void;
  onSubmit: () => void;
  /** Set once a document upload has had the agent create the entity for us. */
  uploadedEntityId: string | null;
  onEntityUploaded: (entity: WorkflowEntityState) => void;
}

export default function CreateEntityModal({
  timerSlot,
  fieldsLocked,
  fieldsLockedHint,
  routeEntityType,
  publishedWorkflows,
  workflowsLoading,
  machinesError,
  selectedMachineName,
  onWorkflowChange,
  schema,
  schemas,
  noWorkflowForms,
  onSelectTab,
  formFields,
  formData,
  onFieldChange,
  sourcePickers,
  sourceSelections,
  onSourceChange,
  error,
  creating,
  onClose,
  onSubmit,
  uploadedEntityId,
  onEntityUploaded,
}: CreateEntityModalProps) {
  const { templateMode, label: identifierLabel } = useIdentifierConfig(routeEntityType);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/45 p-4 backdrop-blur-sm">
      <div className="flex h-[75vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-border bg-card text-card-foreground shadow-2xl">
        <div className="flex flex-shrink-0 items-center justify-between border-b border-border bg-[var(--modal-header-background)] p-4 text-[var(--modal-header-foreground)]">
          <div>
            <h3 className="text-lg font-semibold">
              {routeEntityType ? `Add New ${displayEntityType(routeEntityType)}` : 'Create Entity'}
            </h3>
            {schema && (
              <p className="mt-0.5 text-sm opacity-70">{schema.name}</p>
            )}
          </div>
          <Button
            variant="ghost"
            onClick={onClose}
            className="rounded-full p-1.5 opacity-70 transition-colors hover:bg-current/10 hover:opacity-100"
          >
            <X className="w-5 h-5" />
          </Button>
        </div>

        {timerSlot}

        <div className="flex-1 overflow-y-auto p-4">
          {error && (
            <div className="mb-4 flex items-center gap-2 rounded-lg border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              {error}
            </div>
          )}

          {!templateMode && (
            <div className="mb-5">
              <label className="mb-2 block text-sm font-medium text-foreground">
                {identifierLabel}
                <span className="ml-1 text-destructive">*</span>
              </label>
              <FieldInput
                field={IDENTIFIER_FIELD}
                value={formData[IDENTIFIER_FIELD.id]}
                onChange={(val) => onFieldChange(IDENTIFIER_FIELD.id, val)}
              />
            </div>
          )}

          {(workflowsLoading || publishedWorkflows.length > 0 || machinesError) && (
            <div className="mb-4">
              <label htmlFor="workflow-select" className="mb-2 block text-sm font-medium text-foreground">
                Workflow
              </label>
              {workflowsLoading ? (
                <div className="h-9 w-full animate-pulse rounded-lg border border-border bg-muted" />
              ) : machinesError ? (
                <p className="text-sm text-warning">{machinesError}</p>
              ) : (
                <select
                  id="workflow-select"
                  value={selectedMachineName ?? ''}
                  onChange={(e) => onWorkflowChange(e.target.value || null)}
                  className="w-full px-3 py-2 border border-border rounded-lg text-sm focus:ring-2 focus:ring-cobalt focus:border-cobalt"
                >
                  <option value="">Create without workflow</option>
                  {publishedWorkflows.map((wf) => (
                    <option key={wf.machine_name} value={wf.machine_name}>
                      {wf.name || wf.machine_name}
                    </option>
                  ))}
                </select>
              )}
            </div>
          )}

          <div className="mb-4">
            <SchemaTabs schemas={schemas} activeKey={schema?.schema_key} onSelect={onSelectTab} />
          </div>

          {noWorkflowForms && (
            <p className="mb-4 text-sm text-muted-foreground">
              No forms are configured for this workflow’s initial state.
            </p>
          )}

          <SourceLinkFields
            pickers={sourcePickers}
            selections={sourceSelections}
            onChange={onSourceChange}
          />

          <div className="space-y-4">
            <EntityFormFields
              fieldsLocked={fieldsLocked}
              fieldsLockedHint={fieldsLockedHint}
              fields={formFields}
              values={formData}
              onChange={onFieldChange}
              emptyMessage='No fields to fill in. Click "Create" to continue.'
              entityType={routeEntityType}
            />
            {!schema && (
              <p className="text-sm text-muted-foreground">
                No form is configured. This record will contain only its base details.
              </p>
            )}
          </div>
        </div>

        <div className="flex flex-shrink-0 items-center justify-between border-t border-border bg-muted/30 p-4">
          <Button onClick={onClose} variant="ghost">
            Cancel
          </Button>
          <div className="flex items-center gap-3">
            {routeEntityType && (
              <CreateEntityDocumentUpload
                entityType={routeEntityType}
                disabled={!!uploadedEntityId || creating}
                onEntityCreated={onEntityUploaded}
              />
            )}
            <Button variant="ghost"
              onClick={onSubmit}
              loading={creating}
              icon={!creating ? <Check className="w-4 h-4" /> : undefined}
            >
              Create
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
