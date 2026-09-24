/**
 * Pure (de)serialization between the connector form's editable row model and the
 * `Connector` / `ConnectorCreateRequest` API shape. Kept free of React so the form
 * component and its hook stay focused on state and rendering.
 */

import type { Connector, ConnectorCreateRequest } from '../../../../../core/types';
import { RAW } from '../constants';
import type { KeyFieldRow, KeyValueRow } from '../types';

/** A JSON request body: an object, or an array for batch endpoints. */
export type BodyTemplate = Record<string, unknown> | unknown[];

/** Build the auth_config object for the selected auth type. */
export function buildAuthConfig(
  authType: string,
  apiKeyHeader: string,
  apiKeyIn: 'header' | 'query' = 'header',
): Record<string, unknown> {
  if (authType === 'api_key') return { in: apiKeyIn, name: apiKeyHeader };
  return {};
}

/** Serialize the body editor into the API's `body_template` (raw string, key→token map, or null). */
export function buildBodyTemplate(
  contentType: string,
  rawBody: string,
  bodyRows: KeyFieldRow[],
  bodyJson?: BodyTemplate | null,
): BodyTemplate | string | null {
  if (contentType === RAW) {
    return rawBody.trim() ? rawBody : null;
  }
  // A nested body is held as JSON because the rows cannot represent it, so it
  // is the source of truth whenever it is set.
  if (bodyJson) {
    const empty = Array.isArray(bodyJson) ? bodyJson.length === 0 : Object.keys(bodyJson).length === 0;
    return empty ? null : bodyJson;
  }
  const dict = Object.fromEntries(
    bodyRows
      .filter((r) => r.key && r.field)
      .map((r) => [r.key, r.custom ? r.field : `$entity.${r.field}`]),
  );
  return Object.keys(dict).length ? dict : null;
}

/** Collapse key/value rows into a plain object, dropping rows with an empty key. */
export function objectFromRows(rows: KeyValueRow[]): Record<string, string> {
  return Object.fromEntries(rows.filter((r) => r.key).map((r) => [r.key, r.value]));
}

/** Expand an object (headers, query params) into editable key/value rows. */
export function rowsFromObject(source: Record<string, string> | undefined): KeyValueRow[] {
  return Object.entries(source ?? {}).map(([key, value]) => ({ key, value: String(value) }));
}

/** Expand a saved `body_template` into editable rows, recognising `$entity.field` tokens.
 * A template holding nested objects or arrays yields no rows: the flat row model
 * cannot represent it, and stringifying the nesting into a row would write it
 * back as a quoted string on the next save. Those are edited as JSON instead. */
export function bodyRowsFromTemplate(template: Connector['body_template'] | undefined): KeyFieldRow[] {
  if (!template || typeof template !== 'object') return [];
  if (!isRowRepresentable(template)) return [];
  return Object.entries(template).map(([key, value]) => {
    const match = typeof value === 'string' ? value.match(/^\$entity\.([a-zA-Z_][a-zA-Z0-9_]*)$/) : null;
    if (match) return { key, field: match[1], custom: false };
    return { key, field: typeof value === 'string' ? value : JSON.stringify(value), custom: true };
  });
}

/** Extract the raw body string from a saved `body_template` (empty unless it is a string). */
export function rawBodyFromTemplate(template: Connector['body_template'] | undefined): string {
  return typeof template === 'string' ? template : '';
}

/** Expand a saved `response_mapping` into editable response rows.
 * Dotted keys (`table.column`) are table-column mappings — those live in the
 * advanced JSON textarea, not the simple rows, so they're excluded here. */
export function responseRowsFromMapping(mapping: Record<string, string> | undefined): KeyFieldRow[] {
  return Object.entries(mapping ?? {})
    .filter(([field]) => !field.includes('.'))
    .map(([field, path]) => ({ key: String(path), field }));
}

/** Collapse response rows back into the API's `response_mapping` (field → path). */
export function responseMappingFromRows(rows: KeyFieldRow[]): Record<string, string> {
  return Object.fromEntries(rows.filter((r) => r.key && r.field).map((r) => [r.field, r.key]));
}

/** The dotted `table.column` entries of a saved mapping, as a pretty JSON string
 * for the advanced textarea. Empty string when there are none. */
export function tableMappingJsonFromMapping(mapping: Record<string, string> | undefined): string {
  const dotted = Object.entries(mapping ?? {}).filter(([field]) => field.includes('.'));
  return dotted.length ? JSON.stringify(Object.fromEntries(dotted), null, 2) : '';
}

/** Parse the advanced table-mapping JSON textarea into `{table.column: path}` entries.
 * Invalid/empty JSON yields no entries (the textarea is best-effort). */
export function parseTableMappingJson(json: string): Record<string, string> {
  const trimmed = json.trim();
  if (!trimmed) return {};
  try {
    const parsed: unknown = JSON.parse(trimmed);
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return Object.fromEntries(
        Object.entries(parsed as Record<string, unknown>).map(([k, v]) => [k, String(v)]),
      );
    }
  } catch {
    /* invalid JSON — ignore so it never breaks the save */
  }
  return {};
}

/* ── JSON section editors — row model ↔ JSON text conversion ── */

/** Parse text into a flat JSON object of scalars; returns an error message otherwise. */
function parseObjectOfScalars(text: string): { obj?: Record<string, string>; error?: string } {
  const trimmed = text.trim();
  if (!trimmed) return { obj: {} };
  let parsed: unknown;
  try {
    parsed = JSON.parse(trimmed);
  } catch (e) {
    return { error: e instanceof Error ? e.message : 'Invalid JSON' };
  }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    return { error: 'Must be a JSON object, e.g. {"key": "value"}' };
  }
  const obj: Record<string, string> = {};
  for (const [k, v] of Object.entries(parsed)) {
    if (v !== null && typeof v === 'object') {
      return { error: `"${k}": nested objects/arrays are not supported — values must be strings or numbers` };
    }
    obj[k] = String(v);
  }
  return { obj };
}

/**
 * Parse text into a JSON object whose values may be nested objects or arrays.
 *
 * The body editor used to reject any non-scalar value, but only because the row
 * model could not display one. The backend has always accepted nesting: the
 * column is JSONB, the contract is `dict[str, Any]`, and the placeholder
 * resolver already walks dicts and lists. Leaves of any JSON type are allowed,
 * booleans and nulls included, because the resolver passes them through
 * untouched and real payloads need them.
 *
 * The top level may be an object or an array. Batch endpoints take an array of
 * objects (inriver's entities:upsert, Elasticsearch _bulk), and the contract
 * accepts a list for exactly that reason.
 */
function parseAnyJson(text: string): { value?: BodyTemplate; error?: string } {
  const trimmed = text.trim();
  if (!trimmed) return { value: {} };
  let parsed: unknown;
  try {
    parsed = JSON.parse(trimmed);
  } catch (e) {
    return { error: e instanceof Error ? e.message : 'Invalid JSON' };
  }
  if (!parsed || typeof parsed !== 'object') {
    return { error: 'Must be a JSON object or array, e.g. {"key": "value"} or [{"key": "value"}]' };
  }
  return { value: parsed as BodyTemplate };
}

/**
 * Whether a body template can be shown in the flat key/field rows without loss.
 *
 * A row holds one key and one value, so a nested object or array has nowhere to
 * go. Templates containing one are edited as JSON only.
 */
export function isRowRepresentable(template: unknown): boolean {
  if (!template || typeof template !== 'object' || Array.isArray(template)) return false;
  return Object.values(template as Record<string, unknown>).every(
    (value) => value === null || typeof value !== 'object',
  );
}

/** Serialize key/value rows (query params) into pretty JSON for the JSON editor. */
export function keyValueJsonFromRows(rows: KeyValueRow[]): string {
  return JSON.stringify(objectFromRows(rows), null, 2);
}

/** Parse the query-params JSON editor back into rows. */
export function parseKeyValueJson(text: string): { rows?: KeyValueRow[]; error?: string } {
  const { obj, error } = parseObjectOfScalars(text);
  if (error) return { error };
  return { rows: Object.entries(obj as Record<string, string>).map(([key, value]) => ({ key, value })) };
}

/** Serialize structured body rows into pretty JSON (same shape as the saved body_template). */
export function bodyJsonFromRows(rows: KeyFieldRow[]): string {
  const template = buildBodyTemplate('application/json', '', rows);
  return JSON.stringify(template && typeof template === 'object' ? template : {}, null, 2);
}

/**
 * Parse the request-body JSON editor.
 *
 * Returns the template itself, plus rows when the flat editor can hold it. A
 * nested template comes back with no rows, and the caller keeps it as JSON
 * rather than flattening it into rows that would silently destroy the nesting.
 */
export function parseBodyJson(text: string): {
  template?: BodyTemplate;
  rows?: KeyFieldRow[];
  error?: string;
} {
  const { value, error } = parseAnyJson(text);
  if (error) return { error };
  const template = value as BodyTemplate;
  if (!isRowRepresentable(template)) return { template };
  return { template, rows: bodyRowsFromTemplate(template as Connector['body_template']) };
}

/** Serialize the full response mapping (simple rows + table-column JSON) into one JSON object. */
export function responseJsonFromForm(responseRows: KeyFieldRow[], tableMappingJson: string): string {
  const merged = {
    ...responseMappingFromRows(responseRows),
    ...parseTableMappingJson(tableMappingJson),
  };
  return JSON.stringify(merged, null, 2);
}

/** Parse the response-mapping JSON editor, splitting plain keys (rows) from dotted table keys. */
export function parseResponseJson(text: string): { rows?: KeyFieldRow[]; tableJson?: string; error?: string } {
  const { obj, error } = parseObjectOfScalars(text);
  if (error) return { error };
  const plain: Array<[string, string]> = [];
  const dotted: Array<[string, string]> = [];
  for (const [field, path] of Object.entries(obj as Record<string, string>)) {
    (field.includes('.') ? dotted : plain).push([field, path]);
  }
  return {
    rows: plain.map(([field, path]) => ({ key: path, field })),
    tableJson: dotted.length ? JSON.stringify(Object.fromEntries(dotted), null, 2) : '',
  };
}

/** Build the full create/update payload from the form's current state. */
export interface ConnectorFormState {
  name: string;
  entityTypes: string[];
  baseUrl: string;
  method: string;
  path: string;
  contentType: string;
  authType: string;
  apiKeyHeader: string;
  apiKeyIn: 'header' | 'query';
  secrets: Record<string, string>;
  headerRows: KeyValueRow[];
  queryRows: KeyValueRow[];
  bodyRows: KeyFieldRow[];
  rawBody: string;
  /** Set when the body holds nesting the rows cannot represent; wins over rows. */
  bodyJson: BodyTemplate | null;
  responseRows: KeyFieldRow[];
  tableMappingJson: string;
  exposeAsTool: boolean;
}

/** Serialize the entire form state into a `ConnectorCreateRequest`. */
export function buildConnectorPayload(state: ConnectorFormState): ConnectorCreateRequest {
  const filledSecrets = Object.fromEntries(Object.entries(state.secrets).filter(([, v]) => v));
  return {
    name: state.name.trim(),
    entity_types: state.entityTypes.map((t) => t.trim()).filter(Boolean),
    base_url: state.baseUrl.trim(),
    method: state.method,
    path: state.path.trim(),
    content_type: state.contentType,
    headers: objectFromRows(state.headerRows),
    query_params: objectFromRows(state.queryRows),
    body_template: buildBodyTemplate(
      state.contentType,
      state.rawBody,
      state.bodyRows,
      state.bodyJson,
    ),
    auth_type: state.authType,
    auth_config: buildAuthConfig(state.authType, state.apiKeyHeader, state.apiKeyIn),
    secrets: Object.keys(filledSecrets).length ? filledSecrets : undefined,
    response_mapping: {
      ...responseMappingFromRows(state.responseRows),
      ...parseTableMappingJson(state.tableMappingJson),
    },
    expose_as_tool: state.exposeAsTool,
  };
}
