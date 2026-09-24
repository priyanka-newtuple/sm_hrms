/**
 * Bulk Import Job Hook
 *
 * Hydrates a bulk import job by id (so a page refresh or a resumed job from
 * the recent-imports list doesn't lose it) and polls while the worker is
 * actively processing it. This is the single place that owns "how do we find
 * out the job moved on" now that analyze/commit return instantly instead of
 * blocking until the job is done — the caller no longer gets that for free
 * from the create/analyze/commit response alone.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import { BULK_IMPORT_ACTIVE_STATUSES, bulkImports, getApiErrorMessage } from '../services/api';
import type { BulkImportJob } from '../services/api';

const POLL_INTERVAL_MS = 3000;

interface UseBulkImportJobResult {
  job: BulkImportJob | null;
  /** Set the job directly — used after create/analyze/review/commit responses,
   * and for optimistic local draft edits before a review is saved. */
  setJob: (job: BulkImportJob | null) => void;
  loading: boolean;
  error: string | null;
}

export function useBulkImportJob(jobId: string | null): UseBulkImportJobResult {
  const [job, setJobState] = useState<BulkImportJob | null>(null);
  const [loading, setLoading] = useState(Boolean(jobId));
  const [error, setError] = useState<string | null>(null);
  const loadedJobIdRef = useRef<string | null>(null);

  useEffect(() => {
    if (!jobId || jobId === loadedJobIdRef.current) return;
    let cancelled = false;

    const hydrate = async () => {
      setLoading(true);
      setError(null);
      try {
        const fetched = await bulkImports.get(jobId);
        if (cancelled) return;
        loadedJobIdRef.current = jobId;
        setJobState(fetched);
      } catch (err) {
        if (!cancelled) setError(getApiErrorMessage(err, 'Bulk import job could not be loaded'));
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    hydrate();
    return () => {
      cancelled = true;
    };
  }, [jobId]);

  useEffect(() => {
    if (!job || !BULK_IMPORT_ACTIVE_STATUSES.includes(job.status)) return;
    const jobIdToPoll = job.job_id;
    const timer = window.setInterval(() => {
      bulkImports
        .get(jobIdToPoll)
        .then(setJobState)
        .catch((err) => {
          // Not user-facing — the next tick retries — but still log it so a
          // persistent failure (expired session, server error) is diagnosable.
          console.warn('Bulk import poll failed:', err);
        });
    }, POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
    // Deliberately scoped to id/status only — including the whole `job` object
    // would recreate this interval on every draft edit, not just a real status change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job?.job_id, job?.status]);

  const setJob = useCallback((next: BulkImportJob | null) => {
    loadedJobIdRef.current = next?.job_id ?? null;
    setJobState(next);
  }, []);

  return { job, setJob, loading, error };
}
