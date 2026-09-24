/**
 * Bulk Import Jobs List Hook
 *
 * Loads the organization's recent bulk import jobs, so a user who navigates
 * away mid-processing (or forgets which job they were on) can resume one
 * instead of losing access to it entirely.
 */

import { useCallback } from 'react';

import { useApi } from './useApi';
import { bulkImports } from '../services/api';
import type { BulkImportJobSummary } from '../services/api';

interface UseBulkImportJobsResult {
  jobs: BulkImportJobSummary[];
  loading: boolean;
  error: Error | null;
  refetch: () => Promise<void>;
}

export function useBulkImportJobs(): UseBulkImportJobsResult {
  // Stable fetcher avoids refetch loops — useApi's effect depends on this
  // function's identity, and an inline arrow here would be a new reference
  // (and therefore a new fetch) on every render.
  const listJobs = useCallback(() => bulkImports.list(), []);
  const { data, loading, error, refetch } = useApi(listJobs);
  return { jobs: data?.items ?? [], loading, error, refetch };
}
