import { Loader2 } from 'lucide-react';

import type { BulkImportJobSummary } from '@/core/services/api';

const STATUS_STYLES: Record<string, string> = {
  QUEUED: 'bg-amber-500/10 text-amber-700',
  PROCESSING: 'bg-amber-500/10 text-amber-700',
  COMMITTING: 'bg-amber-500/10 text-amber-700',
  CANCELLING: 'bg-amber-500/10 text-amber-700',
  READY_FOR_REVIEW: 'bg-blue-500/10 text-blue-700',
  COMPLETED_WITH_ERRORS: 'bg-blue-500/10 text-blue-700',
  COMPLETED: 'bg-emerald-500/10 text-emerald-700',
  FAILED: 'bg-destructive/10 text-destructive',
  CANCELLED: 'bg-muted text-muted-foreground',
};

const STATUS_LABELS: Record<string, string> = {
  QUEUED: 'Queued',
  PROCESSING: 'Processing',
  COMMITTING: 'Creating records',
  CANCELLING: 'Stopping',
  READY_FOR_REVIEW: 'Ready for review',
  COMPLETED_WITH_ERRORS: 'Needs attention',
  COMPLETED: 'Completed',
  FAILED: 'Failed',
  CANCELLED: 'Stopped',
};

interface RecentImportsListProps {
  jobs: BulkImportJobSummary[];
  loading: boolean;
  onSelect: (jobId: string) => void;
}

/** Lets a user resume any in-progress or awaiting-review import instead of
 * losing access to it after navigating away — the backend has no other way
 * to look this up without already knowing the job id. */
export default function RecentImportsList({ jobs, loading, onSelect }: RecentImportsListProps) {
  if (loading) {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-border bg-card p-4 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading recent imports…
      </div>
    );
  }
  if (jobs.length === 0) return null;

  return (
    <section className="rounded-2xl border border-border bg-card">
      <div className="border-b border-border px-5 py-4">
        <h2 className="font-medium text-foreground">Recent imports</h2>
        <p className="text-xs text-muted-foreground">
          Resume a job that's still processing or awaiting review.
        </p>
      </div>
      <div className="divide-y divide-border">
        {jobs.map((job) => (
          <button
            key={job.job_id}
            type="button"
            onClick={() => onSelect(job.job_id)}
            className="flex w-full items-center justify-between gap-3 px-5 py-3 text-left text-sm hover:bg-muted/50"
          >
            <div>
              <div className="font-medium text-foreground">
                {job.entity_type_name || 'Unknown entity type'}
              </div>
              <div className="text-xs text-muted-foreground">
                {job.file_count} file{job.file_count === 1 ? '' : 's'}
                {job.draft_count > 0
                  && ` · ${job.draft_count} draft${job.draft_count === 1 ? '' : 's'}`}
              </div>
            </div>
            <span
              className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-medium ${
                STATUS_STYLES[job.status] || 'bg-muted text-muted-foreground'
              }`}
            >
              {STATUS_LABELS[job.status] || job.status}
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}
