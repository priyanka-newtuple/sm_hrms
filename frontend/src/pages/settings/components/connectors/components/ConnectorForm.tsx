import { useEntityTypes } from '../../../../../core/hooks/useEntityTypes';
import MultiSelectDropdown from '../../../../../core/components/MultiSelectDropdown';
import { useEntityFieldOptionsForTypes } from '../../../../../shared/hooks/useEntityFieldOptions';
import { useInheritedFieldOptionsForTypes } from '../../../../../shared/hooks/useInheritedFieldOptions';
import type { Connector, ConnectorCreateRequest } from '../../../../../core/types';
import { AUTH_TYPES, CONTENT_TYPES, METHODS } from '../constants';
import { useConnectorForm } from '../hooks/useConnectorForm';
import { TestInputsModal } from '../../../../settings/components/connectors/ConnectorsTab';
import AuthSecretFields from './AuthSecretFields';
import ConnectorRequestSections from './ConnectorRequestSections';
import DetectedInputsPanel from './DetectedInputsPanel';
import EntityFieldsPanel from './EntityFieldsPanel';
import Field, { inputClass } from './Field';

interface ConnectorFormProps {
  initial?: Connector | null;
  onSubmit: (payload: ConnectorCreateRequest) => Promise<void>;
  onCancel: () => void;
}

/** Create/edit form for a connector — entity type is optional and only needed for entity-bound mappings. */
export default function ConnectorForm({ initial, onSubmit, onCancel }: ConnectorFormProps) {
  const { summaries } = useEntityTypes();
  const form = useConnectorForm({ initial, onSubmit });
  const {
    fields: fieldOptions,
    byType: fieldGroups,
    missingByField,
    error: fieldOptionsError,
  } = useEntityFieldOptionsForTypes(form.entityTypes);
  const inheritedFieldGroups = useInheritedFieldOptionsForTypes(form.entityTypes);

  return (
    <div className="@container space-y-4">
      <div className="flex flex-col gap-4 @4xl:flex-row @4xl:items-start">
        {/* Left — all form fields */}
        <div className="min-w-0 flex-1 space-y-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Name">
              <input value={form.name} onChange={(e) => form.setName(e.target.value)} className={inputClass} />
            </Field>
            <Field label="Entity types (optional)">
              <MultiSelectDropdown
                options={summaries.map((s) => s.name)}
                value={form.entityTypes}
                onChange={form.setEntityTypes}
                placeholder="No entity binding — select types…"
              />
            </Field>
          </div>

          <div className="grid grid-cols-[120px_1fr] gap-3">
            <Field label="Method">
              <select value={form.method} onChange={(e) => form.setMethod(e.target.value)} className={inputClass}>
                {METHODS.map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            </Field>
            <Field label="Base URL">
              <input
                value={form.baseUrl}
                onChange={(e) => form.setBaseUrl(e.target.value)}
                placeholder="https://api.example.com"
                className={inputClass}
              />
            </Field>
          </div>

          <Field label="Path">
            <input
              value={form.path}
              onChange={(e) => form.setPath(e.target.value)}
              onFocus={() => form.setFocusedSlot('path')}
              placeholder="/v1/candidates/$entity.candidate_id"
              className={`${inputClass} font-mono`}
            />
          </Field>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Auth type">
              <select value={form.authType} onChange={(e) => form.setAuthType(e.target.value)} className={inputClass}>
                {AUTH_TYPES.map((a) => (
                  <option key={a} value={a}>{a}</option>
                ))}
              </select>
            </Field>
            <Field label="Content type">
              <select value={form.contentType} onChange={(e) => form.setContentType(e.target.value)} className={inputClass}>
                {CONTENT_TYPES.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </Field>
          </div>

          <AuthSecretFields
            authType={form.authType}
            secrets={form.secrets}
            setSecret={form.setSecret}
            apiKeyHeader={form.apiKeyHeader}
            setApiKeyHeader={form.setApiKeyHeader}
            apiKeyIn={form.apiKeyIn}
            setApiKeyIn={form.setApiKeyIn}
            isEditing={form.isEditing}
          />

          <ConnectorRequestSections
            contentType={form.contentType}
            fieldOptions={fieldOptions}
            headerRows={form.headerRows}
            setHeaderRows={form.setHeaderRows}
            queryRows={form.queryRows}
            setQueryRows={form.setQueryRows}
            bodyRows={form.bodyRows}
            setBodyRows={form.setBodyRows}
            rawBody={form.rawBody}
            setRawBody={form.setRawBody}
            bodyJson={form.bodyJson}
            setBodyJson={form.setBodyJson}
            responseRows={form.responseRows}
            setResponseRows={form.setResponseRows}
            tableMappingJson={form.tableMappingJson}
            setTableMappingJson={form.setTableMappingJson}
            onHeaderValueFocus={(index) => form.setFocusedSlot({ section: 'header', index })}
            onQueryValueFocus={(index) => form.setFocusedSlot({ section: 'query', index })}
            onRawBodyFocus={() => form.setFocusedSlot('rawBody')}
            onJsonFocus={() => form.setFocusedSlot(null)}
            onTest={form.requestTest}
            testLoading={form.testLoading}
            testResponseJson={form.testResponseJson}
          />

          {form.pendingSampleInputs && (
            <TestInputsModal
              inputs={form.pendingSampleInputs}
              onConfirm={form.confirmTest}
              onClose={form.cancelTest}
            />
          )}

          <DetectedInputsPanel detected={form.detected} />
        </div>

        {/* Right — variable insert panel */}
        <div className="w-full min-w-0 @4xl:w-64 @4xl:shrink-0">
          <EntityFieldsPanel
            fieldGroups={fieldGroups}
            inheritedFieldGroups={inheritedFieldGroups}
            hasEntityType={form.entityTypes.length > 0}
            missingByField={missingByField}
            loadError={fieldOptionsError}
            focusedSlot={form.focusedSlot}
            onInsert={form.insertToken}
          />
        </div>
      </div>

      <label className="flex items-start gap-3 rounded-lg border border-border p-3">
        <input
          type="checkbox"
          checked={form.exposeAsTool}
          onChange={(e) => form.setExposeAsTool(e.target.checked)}
          className="mt-1"
        />
        <span className="space-y-1">
          <span className="block text-sm font-medium">Expose as tool</span>
          <span className="block text-sm text-muted-foreground">
            Make this connector available in MCP Tools so agents can call it directly.
          </span>
        </span>
      </label>

      <div className="flex items-center gap-2 border-t border-border pt-3">
        <button
          type="button"
          onClick={form.submit}
          disabled={form.submitting}
          className="inline-flex h-9 items-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground disabled:opacity-50"
        >
          {form.submitting ? 'Saving…' : form.isEditing ? 'Save changes' : 'Create connector'}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="inline-flex h-9 items-center rounded-md px-4 text-sm font-medium hover:bg-muted"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
