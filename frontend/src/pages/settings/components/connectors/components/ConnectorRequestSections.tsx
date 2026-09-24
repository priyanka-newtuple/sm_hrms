import { useState } from 'react';
import { Braces, Loader2, Zap } from 'lucide-react';

import { RAW } from '../constants';
import type { KeyFieldRow, KeyValueRow } from '../types';
import {
  bodyJsonFromRows,
  type BodyTemplate,
  keyValueJsonFromRows,
  parseBodyJson,
  parseKeyValueJson,
  parseResponseJson,
  responseJsonFromForm,
} from '../utils/mappers';
import Field from './Field';
import JsonEditor from './JsonEditor';
import KeyValueRows from './KeyValueRows';
import MappingRows from './MappingRows';
import ResponseJsonPicker from './ResponseJsonPicker';
import SectionModeToggle, { type SectionEditMode } from './SectionModeToggle';

interface ConnectorRequestSectionsProps {
  contentType: string;
  fieldOptions: string[];
  headerRows: KeyValueRow[];
  setHeaderRows: (rows: KeyValueRow[]) => void;
  queryRows: KeyValueRow[];
  setQueryRows: (rows: KeyValueRow[]) => void;
  bodyRows: KeyFieldRow[];
  setBodyRows: (rows: KeyFieldRow[]) => void;
  rawBody: string;
  setRawBody: (value: string) => void;
  /** Set while the body holds nesting the rows cannot represent. */
  bodyJson: BodyTemplate | null;
  setBodyJson: (value: BodyTemplate | null) => void;
  responseRows: KeyFieldRow[];
  setResponseRows: (rows: KeyFieldRow[]) => void;
  tableMappingJson: string;
  setTableMappingJson: (value: string) => void;
  onHeaderValueFocus?: (index: number) => void;
  onQueryValueFocus?: (index: number) => void;
  onRawBodyFocus?: () => void;
  onJsonFocus?: () => void;
  /** When set, enables the inline test button so the user can pick paths from the live response. */
  onTest?: () => void | Promise<unknown>;
  testLoading?: boolean;
  testResponseJson?: unknown;
}

/** Section title row with the Form/JSON segmented toggle on the right. */
function SectionHeader({
  label,
  mode,
  onModeChange,
  disabledModes,
}: {
  label: string;
  mode: SectionEditMode;
  onModeChange: (mode: SectionEditMode) => void;
  disabledModes?: Partial<Record<SectionEditMode, string>>;
}) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-xs font-medium">{label}</span>
      <SectionModeToggle mode={mode} onChange={onModeChange} disabled={disabledModes} />
    </div>
  );
}

/** Headers, query params, request body, and response mapping editors for a connector. */
export default function ConnectorRequestSections({
  contentType,
  fieldOptions,
  headerRows,
  setHeaderRows,
  queryRows,
  setQueryRows,
  bodyRows,
  setBodyRows,
  rawBody,
  setRawBody,
  bodyJson,
  setBodyJson,
  responseRows,
  setResponseRows,
  tableMappingJson,
  setTableMappingJson,
  onHeaderValueFocus,
  onQueryValueFocus,
  onRawBodyFocus,
  onJsonFocus,
  onTest,
  testLoading,
  testResponseJson,
}: ConnectorRequestSectionsProps) {
  // Rows are the source of truth; valid JSON edits sync into rows immediately.
  const [queryMode, setQueryMode] = useState<SectionEditMode>('rows');
  const [queryDraft, setQueryDraft] = useState('');
  const [queryError, setQueryError] = useState<string | null>(null);

  // A body the rows cannot represent opens in JSON, otherwise editing an
  // existing nested connector would show an empty form.
  const [bodyMode, setBodyMode] = useState<SectionEditMode>(bodyJson ? 'json' : 'rows');
  const [bodyDraft, setBodyDraft] = useState(() =>
    bodyJson ? JSON.stringify(bodyJson, null, 2) : '',
  );
  const [bodyError, setBodyError] = useState<string | null>(null);

  const [responseMode, setResponseMode] = useState<SectionEditMode>('rows');
  const [responseDraft, setResponseDraft] = useState('');
  const [responseError, setResponseError] = useState<string | null>(null);

  const switchQueryMode = (mode: SectionEditMode) => {
    if (mode === 'json') {
      setQueryDraft(keyValueJsonFromRows(queryRows));
      setQueryError(null);
    }
    setQueryMode(mode);
  };
  const onQueryDraftChange = (text: string) => {
    setQueryDraft(text);
    const { rows, error } = parseKeyValueJson(text);
    if (error) setQueryError(error);
    else {
      setQueryError(null);
      setQueryRows(rows as KeyValueRow[]);
    }
  };

  const switchBodyMode = (mode: SectionEditMode) => {
    if (mode === 'json') {
      // A nested body is already the source of truth; only rebuild the draft
      // from rows when the rows are what is being edited.
      setBodyDraft(bodyJson ? JSON.stringify(bodyJson, null, 2) : bodyJsonFromRows(bodyRows));
      setBodyError(null);
    }
    setBodyMode(mode);
  };
  const onBodyDraftChange = (text: string) => {
    setBodyDraft(text);
    const { template, rows, error } = parseBodyJson(text);
    if (error) {
      setBodyError(error);
      return;
    }
    setBodyError(null);
    if (rows) {
      // Flat enough for the row editor, so the rows stay the source of truth.
      setBodyRows(rows);
      setBodyJson(null);
      return;
    }
    // Nested: keep the JSON itself, because collapsing it into rows would write
    // the nesting back as a quoted string on save.
    setBodyJson(template ?? null);
  };

  const switchResponseMode = (mode: SectionEditMode) => {
    if (mode === 'json') {
      setResponseDraft(responseJsonFromForm(responseRows, tableMappingJson));
      setResponseError(null);
    }
    setResponseMode(mode);
  };
  const onResponseDraftChange = (text: string) => {
    setResponseDraft(text);
    const { rows, tableJson, error } = parseResponseJson(text);
    if (error) setResponseError(error);
    else {
      setResponseError(null);
      setResponseRows(rows as KeyFieldRow[]);
      setTableMappingJson(tableJson ?? '');
    }
  };

  const addPathAsRow = (path: string) => {
    const alreadyMapped = responseRows.some((r) => r.key === path);
    if (alreadyMapped) return;
    const next = [...responseRows, { key: path, field: '' }];
    setResponseRows(next);
    if (responseMode === 'json') {
      setResponseDraft(responseJsonFromForm(next, tableMappingJson));
      setResponseError(null);
    }
  };

  return (
    <>
      <Field label="Headers">
        <KeyValueRows
          rows={headerRows}
          onChange={setHeaderRows}
          keyPlaceholder="Header name (e.g. X-Api-Version)"
          valuePlaceholder="Value"
          onValueFocus={onHeaderValueFocus}
        />
      </Field>

      {/* Query params */}
      <div className="space-y-1.5">
        <SectionHeader label="Query params" mode={queryMode} onModeChange={switchQueryMode} />
        {queryMode === 'rows' ? (
          <KeyValueRows
            rows={queryRows}
            onChange={setQueryRows}
            keyPlaceholder="Param name (e.g. source)"
            valuePlaceholder="Value"
            onValueFocus={onQueryValueFocus}
          />
        ) : (
          <JsonEditor
            value={queryDraft}
            onChange={onQueryDraftChange}
            error={queryError}
            rows={5}
            placeholder={'{\n  "entity_id": "$entity.client_id",\n  "aggregated": "true"\n}'}
            onFocus={onJsonFocus}
          />
        )}
      </div>

      {/* Test & pick — shown once, above body so the tree is usable for both body and response */}
      {onTest && (
        <div className="flex items-center justify-between rounded-lg border border-border bg-muted/30 px-3 py-2">
          <span className="text-xs text-muted-foreground">
            Fire a test call to pick response paths for the body or mapping below.
          </span>
          <button
            type="button"
            onClick={onTest}
            disabled={testLoading}
            className="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium text-primary hover:bg-muted disabled:opacity-50"
          >
            {testLoading ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Zap className="h-3.5 w-3.5" />
            )}
            Test & pick paths
          </button>
        </div>
      )}

      {/* JSON picker — shown once; clicking adds to whichever section the user scrolls to use */}
      {testResponseJson !== undefined && testResponseJson !== null && (
        <ResponseJsonPicker data={testResponseJson} onPickPath={addPathAsRow} />
      )}

      {/* Request body */}
      {contentType === RAW ? (
        <Field label="Request body (raw — supports {{field}} / $entity.field)">
          <textarea
            value={rawBody}
            onChange={(e) => setRawBody(e.target.value)}
            onFocus={onRawBodyFocus}
            rows={4}
            placeholder="<xml>…</xml> or any raw payload"
            className="w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-sm"
          />
        </Field>
      ) : (
        <div className="space-y-1.5">
          <SectionHeader
            label="Request body — request key ← entity field"
            mode={bodyMode}
            onModeChange={switchBodyMode}
            disabledModes={
              bodyJson
                ? { rows: 'This body uses nested JSON, which the form rows cannot show. Edit it here.' }
                : undefined
            }
          />
          {bodyMode === 'rows' ? (
            <MappingRows
              rows={bodyRows}
              onChange={setBodyRows}
              keyLabel="Request key"
              keyPlaceholder="e.g. job_id"
              fieldLabel="Entity field"
              fieldOptions={fieldOptions}
            />
          ) : (
            <JsonEditor
              value={bodyDraft}
              onChange={onBodyDraftChange}
              error={bodyError}
              rows={6}
              placeholder={'{\n  "job_id": "$entity.job_id",\n  "source": "regpro"\n}'}
              onFocus={onJsonFocus}
            />
          )}
        </div>
      )}

      {/* Response mapping */}
      <div className="space-y-1.5">
        <SectionHeader
          label="Response mapping — response path → entity field"
          mode={responseMode}
          onModeChange={switchResponseMode}
        />
        {responseMode === 'rows' ? (
          <>
            <MappingRows
              rows={responseRows}
              onChange={setResponseRows}
              keyLabel="Response path"
              keyPlaceholder="e.g. data.status or items[].id"
              fieldLabel="Entity field"
              fieldOptions={fieldOptions}
            />
            {tableMappingJson.trim() && (
              <button
                type="button"
                onClick={() => switchResponseMode('json')}
                className="flex w-full items-center gap-1.5 rounded-lg border border-dashed border-border bg-muted/30 px-3 py-2 text-left text-xs text-muted-foreground transition-colors hover:border-primary hover:text-foreground"
              >
                <Braces className="h-3.5 w-3.5 shrink-0" />
                This connector also has table column mappings — switch to the JSON view to edit
                them.
              </button>
            )}
          </>
        ) : (
          <>
            <JsonEditor
              value={responseDraft}
              onChange={onResponseDraftChange}
              error={responseError}
              rows={8}
              placeholder={'{\n  "filing_id": "results[0].id",\n  "block_4.line": "results[column_indicator=a].fcc_line",\n  "block_4.__match__": "line"\n}'}
              onFocus={onJsonFocus}
            />
            <p className="text-xs text-muted-foreground">
              One object for the whole mapping — plain keys map an entity field to a response path;
              dotted keys (<code>table.column</code>) fill table columns. This is exactly the shape
              the connector stores.
            </p>
          </>
        )}
      </div>
    </>
  );
}
