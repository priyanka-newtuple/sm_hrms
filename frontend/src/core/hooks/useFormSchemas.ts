/**
 * Form Schemas Hook
 *
 * Loads form configurations from /forms/config. Optionally scoped to a single
 * entity type. Components consume this instead of calling the service directly.
 */

import { useState, useEffect, useCallback, useRef } from 'react';

import { formSchemas } from '../services/api';
import type { FormSchema } from '../types';

interface UseFormSchemasResult {
  schemas: FormSchema[];
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

export function useFormSchemas(entityType?: string): UseFormSchemasResult {
  const [schemas, setSchemas] = useState<FormSchema[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Guards against an out-of-order response: if `entityType` changes quickly
  // (e.g. undefined -> a real value, once a caller learns which entity type it
  // needs), an earlier, unscoped request can resolve *after* the later, scoped
  // one and silently overwrite it with every schema in the org. Only the
  // most-recently-started request is allowed to write to state.
  const latestRequestRef = useRef(0);

  const fetchSchemas = useCallback(async () => {
    const requestId = ++latestRequestRef.current;
    setLoading(true);
    setError(null);
    try {
      const resp = await formSchemas.list(entityType);
      if (requestId !== latestRequestRef.current) return;
      setSchemas(resp.items);
    } catch (e) {
      if (requestId !== latestRequestRef.current) return;
      const message = e instanceof Error ? e.message : 'Failed to load forms';
      setError(message);
      console.error('Failed to fetch form schemas:', e);
    } finally {
      if (requestId === latestRequestRef.current) setLoading(false);
    }
  }, [entityType]);

  useEffect(() => {
    fetchSchemas();
  }, [fetchSchemas]);

  return { schemas, loading, error, refetch: fetchSchemas };
}
