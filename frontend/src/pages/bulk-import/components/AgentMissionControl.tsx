import {
  Check,
  Circle,
  Clock3,
  FileStack,
  Loader2,
  RefreshCw,
  Route,
  CircleStop,
  Sparkles,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import type { BulkImportJob } from '@/core/services/api';

type MissionStepState = 'complete' | 'active' | 'pending';

interface MissionStep {
  label: string;
  detail: string;
  state: MissionStepState;
}

function missionSteps(job: BulkImportJob): MissionStep[] {
  const isCommit = job.operation === 'commit' || job.status === 'COMMITTING';

  return [
    {
      label: 'Sources received',
      detail: `${job.files.length} file${job.files.length === 1 ? '' : 's'} secured`,
      state: 'complete',
    },
    {
      label: 'AI analysis',
      detail: 'Read, structure and map source evidence',
      state: isCommit ? 'complete' : 'active',
    },
    {
      label: 'Human review',
      detail: 'Confirm mappings and proposed records',
      state: isCommit ? 'complete' : 'pending',
    },
    {
      label: 'Apply changes',
      detail: 'Create or update records and attach files',
      state: isCommit ? 'active' : 'pending',
    },
  ];
}

function StepIcon({ state }: { state: MissionStepState }) {
  if (state === 'complete') {
    return (
      <span className="flex h-7 w-7 items-center justify-center rounded-full bg-emerald-500 text-white shadow-sm">
        <Check className="h-4 w-4" strokeWidth={2.5} />
      </span>
    );
  }
  if (state === 'active') {
    return (
      <span className="relative flex h-7 w-7 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-sm shadow-primary/25">
        <span className="absolute inset-0 animate-ping rounded-full bg-primary/25" />
        <Loader2 className="relative h-4 w-4 animate-spin" />
      </span>
    );
  }
  return (
    <span className="flex h-7 w-7 items-center justify-center rounded-full border border-border bg-background text-muted-foreground">
      <Circle className="h-2.5 w-2.5" fill="currentColor" />
    </span>
  );
}

interface AgentMissionControlProps {
  job: BulkImportJob;
  stopping: boolean;
  onStop: () => void;
}

export default function AgentMissionControl({ job, stopping, onStop }: AgentMissionControlProps) {
  const steps = missionSteps(job);
  const isQueued = job.status === 'QUEUED';
  const isCommit = job.operation === 'commit' || job.status === 'COMMITTING';
  const isCancelling = job.status === 'CANCELLING' || job.cancel_requested;
  const title = isQueued
    ? 'Mission queued and ready'
    : isCancelling
      ? 'Stopping bulk upload'
    : isCommit
      ? 'Applying approved changes'
      : 'Understanding your source files';
  const description = isQueued
    ? 'The bulk upload agent is waiting for an available worker.'
    : isCancelling
      ? 'Finishing the current safe unit of work. Records already created will be preserved.'
    : isCommit
      ? 'The agent is creating or updating records and preserving their source evidence.'
      : 'The agent is inspecting content, finding record boundaries and proposing field mappings.';
  const commitTotal = job.commit_total_count
    || job.drafts.filter((draft) => draft.selected).length;
  const commitProcessed = Math.min(job.commit_processed_count, commitTotal);
  const commitProgress = commitTotal > 0
    ? Math.round((commitProcessed / commitTotal) * 100)
    : 0;

  return (
    <section className="rounded-2xl border border-border bg-card shadow-sm">
      <div className="p-5 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex min-w-0 items-start gap-3.5">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-border/80 bg-background/80 text-primary shadow-sm backdrop-blur-sm">
              <Sparkles className="h-[18px] w-[18px]" strokeWidth={1.75} />
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">
                  Bulk upload agent
                </span>
                <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-700 dark:text-emerald-400">
                  <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-500" />
                  Live status
                </span>
              </div>
              <h2 className="mt-1 text-lg font-semibold text-foreground">{title}</h2>
              <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{description}</p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="inline-flex items-center gap-1.5 rounded-full border border-border/80 bg-background/70 px-3 py-1.5 text-xs text-muted-foreground backdrop-blur-sm">
              <RefreshCw className="h-3.5 w-3.5" />
              Updates every 3 seconds
            </div>
            <Button
              variant="outline"
              size="sm"
              loading={stopping || isCancelling}
              disabled={stopping || isCancelling}
              onClick={onStop}
              icon={<CircleStop />}
            >
              {isCancelling ? 'Stopping' : 'Stop upload'}
            </Button>
          </div>
        </div>

        {isCommit && (
          <div className="mt-5 rounded-xl border border-border/80 bg-background/70 p-4">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <div className="text-sm font-semibold text-foreground">
                  {commitProcessed} of {commitTotal} records processed
                </div>
                <div className="mt-1 text-xs text-muted-foreground">
                  {job.created_count} created
                  {job.existing_count > 0 && ` · ${job.existing_count} updated`}
                </div>
              </div>
              <span className="text-sm font-semibold tabular-nums text-primary">
                {commitProgress}%
              </span>
            </div>
            <div
              className="mt-3 h-2 overflow-hidden rounded-full bg-muted"
              role="progressbar"
              aria-label="Bulk upload commit progress"
              aria-valuemin={0}
              aria-valuemax={commitTotal}
              aria-valuenow={commitProcessed}
            >
              <div
                className="h-full rounded-full bg-primary transition-[width] duration-500 ease-out"
                style={{ width: `${commitProgress}%` }}
              />
            </div>
          </div>
        )}

        <div className="mt-6 grid gap-2 md:grid-cols-4">
          {steps.map((step, index) => (
            <div
              key={step.label}
              className={`relative rounded-xl border p-3.5 transition-colors ${
                step.state === 'active'
                  ? 'border-primary/35 bg-background/90 shadow-sm'
                  : 'border-border/70 bg-background/55'
              }`}
            >
              {index < steps.length - 1 && (
                <span className="absolute left-[calc(100%+1px)] top-7 hidden h-px w-2 bg-border md:block" />
              )}
              <div className="flex items-center gap-2.5">
                <StepIcon state={step.state} />
                <span className={`text-sm font-medium ${step.state === 'pending' ? 'text-muted-foreground' : 'text-foreground'}`}>
                  {step.label}
                </span>
              </div>
              <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{step.detail}</p>
            </div>
          ))}
        </div>

        <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 border-t border-border/70 pt-4 text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            <FileStack className="h-3.5 w-3.5 text-primary" />
            {job.files.length} source file{job.files.length === 1 ? '' : 's'}
          </span>
          <span className="inline-flex items-center gap-1.5">
            <Route className="h-3.5 w-3.5 text-primary" />
            Target: {job.entity_type_name}
          </span>
          <span className="inline-flex items-center gap-1.5">
            <Clock3 className="h-3.5 w-3.5 text-primary" />
            Safe to leave this page. The mission continues in the background.
          </span>
        </div>
      </div>
    </section>
  );
}
