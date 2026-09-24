/**
 * Manages inline connector test execution — loading flag, response JSON,
 * and the async `runTest` action. Encapsulates all test-related state so
 * `useConnectorForm` stays focused on field management.
 */

import { useState } from 'react';
import { toast } from 'sonner';

import { useConnectorActions } from '../../../../../core/hooks/useConnectors';
import type { ConnectorCreateRequest } from '../../../../../core/types';

interface UseConnectorTestArgs {
  buildPayload: () => ConnectorCreateRequest;
  connectorId?: string;
}

function detectPayloadInputs(payload: ConnectorCreateRequest): string[] {
  const sources = [
    payload.base_url ?? '',
    payload.path ?? '',
    ...Object.values(payload.headers ?? {}),
    ...Object.values(payload.query_params ?? {}),
    typeof payload.body_template === 'string'
      ? payload.body_template
      : JSON.stringify(payload.body_template ?? ''),
  ].filter((s): s is string => typeof s === 'string');

  const found = new Set<string>();
  for (const s of sources) {
    for (const m of s.matchAll(/\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}/g)) found.add(m[1]);
    for (const m of s.matchAll(/\$entity\.([a-zA-Z_][a-zA-Z0-9_]*)/g)) found.add(m[1]);
  }
  return [...found];
}

export function useConnectorTest({ buildPayload, connectorId }: UseConnectorTestArgs) {
  const { testInline } = useConnectorActions();
  const [testLoading, setTestLoading] = useState(false);
  const [testResponseJson, setTestResponseJson] = useState<unknown>(undefined);
  const [pendingSampleInputs, setPendingSampleInputs] = useState<string[] | null>(null);

  const runTest = async (sampleFields: Record<string, string> = {}) => {
    setTestLoading(true);
    try {
      const result = await testInline(buildPayload(), sampleFields, connectorId);
      if (result.success) toast.success(`Test OK (HTTP ${result.status_code ?? '—'}).`);
      else toast.error(`Test failed: ${result.message}`);
      setTestResponseJson(result.response_json ?? null);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to test connector.');
    } finally {
      setTestLoading(false);
    }
  };

  const requestTest = () => {
    const inputs = detectPayloadInputs(buildPayload());
    if (inputs.length > 0) {
      setPendingSampleInputs(inputs);
    } else {
      runTest({});
    }
  };

  const confirmTest = (values: Record<string, string>) => {
    setPendingSampleInputs(null);
    runTest(values);
  };

  const cancelTest = () => setPendingSampleInputs(null);

  return { testLoading, testResponseJson, requestTest, pendingSampleInputs, confirmTest, cancelTest };
}
