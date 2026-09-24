/**
 * Form-state hook for the connector create/edit form.
 *
 * Owns every editable field, the derived placeholder summary, and payload
 * serialization — keeping `ConnectorForm` a thin presentational orchestrator.
 * Test logic is delegated to `useConnectorTest`; token insertion to
 * `useTokenInsertion`. Service access goes through `useConnectorActions`
 * (Component → Hook → Service), never a direct import.
 */

import { useMemo, useState } from 'react';
import { toast } from 'sonner';

import type { Connector, ConnectorCreateRequest } from '../../../../../core/types';
import { RAW } from '../constants';
import type { KeyFieldRow, KeyValueRow } from '../types';
import {
  bodyRowsFromTemplate,
  isRowRepresentable,
  type BodyTemplate,
  buildConnectorPayload,
  rawBodyFromTemplate,
  responseRowsFromMapping,
  rowsFromObject,
  tableMappingJsonFromMapping,
} from '../utils/mappers';
import { detectPlaceholders, entityToken, stringsFromJson } from '../utils/placeholders';
import { useConnectorTest } from './useConnectorTest';
import { useTokenInsertion } from './useTokenInsertion';

interface UseConnectorFormArgs {
  initial?: Connector | null;
  onSubmit: (payload: ConnectorCreateRequest) => Promise<void>;
}

export function useConnectorForm({ initial, onSubmit }: UseConnectorFormArgs) {
  const isEditing = Boolean(initial);

  const [name, setName] = useState(initial?.name ?? '');
  const [entityTypes, setEntityTypes] = useState<string[]>(initial?.entity_types ?? []);
  const [baseUrl, setBaseUrl] = useState(initial?.base_url ?? '');
  const [method, setMethod] = useState(initial?.method ?? 'POST');
  const [path, setPath] = useState(initial?.path ?? '');
  const [contentType, setContentType] = useState(initial?.content_type ?? 'application/json');
  const [authType, setAuthType] = useState(initial?.auth_type ?? 'none');
  const [secrets, setSecrets] = useState<Record<string, string>>({});
  const [apiKeyHeader, setApiKeyHeader] = useState(String(initial?.auth_config?.name ?? 'X-API-Key'));
  const [apiKeyIn, setApiKeyIn] = useState<'header' | 'query'>(
    initial?.auth_config?.in === 'query' ? 'query' : 'header',
  );
  const [headerRows, setHeaderRows] = useState<KeyValueRow[]>(() => rowsFromObject(initial?.headers));
  const [queryRows, setQueryRows] = useState<KeyValueRow[]>(() => rowsFromObject(initial?.query_params));
  const [bodyRows, setBodyRows] = useState<KeyFieldRow[]>(() => bodyRowsFromTemplate(initial?.body_template));
  const [rawBody, setRawBody] = useState(() => rawBodyFromTemplate(initial?.body_template));
  // Set only while the body holds nesting the rows cannot represent. Null means
  // the rows are the source of truth.
  const [bodyJson, setBodyJson] = useState<BodyTemplate | null>(() => {
    const template = initial?.body_template;
    if (!template || typeof template !== 'object' || isRowRepresentable(template)) return null;
    return template as BodyTemplate;
  });
  const [responseRows, setResponseRows] = useState<KeyFieldRow[]>(
    () => responseRowsFromMapping(initial?.response_mapping),
  );
  const [tableMappingJson, setTableMappingJson] = useState(
    () => tableMappingJsonFromMapping(initial?.response_mapping),
  );
  const [exposeAsTool, setExposeAsTool] = useState(initial?.expose_as_tool ?? false);
  const [submitting, setSubmitting] = useState(false);

  const setSecret = (key: string, value: string) =>
    setSecrets((prev) => ({ ...prev, [key]: value }));

  const detected = useMemo(() => {
    const texts = [path, ...headerRows.map((r) => r.value), ...queryRows.map((r) => r.value)];
    if (contentType === RAW) texts.push(rawBody);
    else if (bodyJson) texts.push(...stringsFromJson(bodyJson));
    else bodyRows.forEach((r) => texts.push(r.custom ? r.field : entityToken(r.field)));
    return detectPlaceholders(texts);
  }, [path, headerRows, queryRows, bodyRows, rawBody, bodyJson, contentType]);

  const buildPayload = (): ConnectorCreateRequest =>
    buildConnectorPayload({
      name,
      entityTypes,
      baseUrl,
      method,
      path,
      contentType,
      authType,
      apiKeyHeader,
      apiKeyIn,
      secrets,
      headerRows,
      queryRows,
      bodyRows,
      rawBody,
      bodyJson,
      responseRows,
      tableMappingJson,
      exposeAsTool,
    });

  const { focusedSlot, setFocusedSlot, insertToken } = useTokenInsertion({
    setPath,
    setRawBody,
    setHeaderRows,
    setQueryRows,
  });

  const { testLoading, testResponseJson, requestTest, pendingSampleInputs, confirmTest, cancelTest } = useConnectorTest({
    buildPayload,
    connectorId: initial?.id,
  });

  const submit = async () => {
    if (!name.trim() || !baseUrl.trim()) {
      toast.error('Name and base URL are required.');
      return;
    }
    setSubmitting(true);
    try {
      await onSubmit(buildPayload());
    } finally {
      setSubmitting(false);
    }
  };

  return {
    isEditing,
    // field values + setters
    name, setName,
    entityTypes, setEntityTypes,
    baseUrl, setBaseUrl,
    method, setMethod,
    path, setPath,
    contentType, setContentType,
    authType, setAuthType,
    secrets, setSecret,
    apiKeyHeader, setApiKeyHeader,
    apiKeyIn, setApiKeyIn,
    headerRows, setHeaderRows,
    queryRows, setQueryRows,
    bodyRows, setBodyRows,
    rawBody, setRawBody,
    bodyJson, setBodyJson,
    responseRows, setResponseRows,
    tableMappingJson, setTableMappingJson,
    exposeAsTool, setExposeAsTool,
    // interaction state
    focusedSlot, setFocusedSlot,
    detected,
    // async state + actions
    submitting,
    testLoading,
    testResponseJson,
    insertToken,
    requestTest,
    pendingSampleInputs,
    confirmTest,
    cancelTest,
    submit,
  };
}
