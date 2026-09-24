import { useMemo, useState } from 'react';
import { CalendarClock, Info, Loader2 } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';

import SchedulesPanel from '@/pages/funnel/components/SchedulesPanel';
import { Button } from '@/components/ui/button';
import Modal from '@/core/components/Modal';
import { useWorkflows } from '@/shared/hooks/useWorkflows';

const selectClass =
  'h-10 min-w-64 rounded-lg border border-border bg-background px-3 text-sm';

export default function AutomationsTab() {
  const [showInfo, setShowInfo] = useState(false);
  const { workflows, loading, error } = useWorkflows();
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedMachine = searchParams.get('workflow');
  const selected = useMemo(
    () => workflows.find((workflow) => workflow.slug === requestedMachine),
    [requestedMachine, workflows],
  );
  const workflowLabels = useMemo(
    () => Object.fromEntries(workflows.map((workflow) => [workflow.slug, workflow.label])),
    [workflows],
  );

  const selectWorkflow = (machineName: string) => {
    const next = new URLSearchParams(searchParams);
    if (machineName) next.set('workflow', machineName);
    else next.delete('workflow');
    setSearchParams(next);
  };

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <CalendarClock className="h-6 w-6 text-cobalt" />
            <h1 className="text-3xl font-semibold tracking-tight">Automations</h1>
            <Button
              variant="ghost"
              size="icon"
              aria-label="About automations"
              title="About automations"
              onClick={() => setShowInfo(true)}
            >
              <Info className="h-4 w-4" />
            </Button>
          </div>
          <p className="mt-2 text-sm text-muted-foreground">
            Reusable platform automations. Currently supports scheduled entity creation.
          </p>
        </div>
        {workflows.length > 0 && (
          <label className="text-sm font-medium">
            Workflow
            <select
              className={`${selectClass} ml-3`}
              value={selected?.slug ?? ''}
              onChange={(event) => selectWorkflow(event.target.value)}
            >
              <option value="">All workflows</option>
              {workflows.map((workflow) => (
                <option key={workflow.slug} value={workflow.slug}>
                  {workflow.label}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      {loading ? (
        <Loader2 className="mx-auto mt-16 h-6 w-6 animate-spin text-cobalt" />
      ) : error ? (
        <div className="rounded-xl border border-destructive/30 bg-destructive-subtle p-4 text-sm text-destructive">
          {error}
        </div>
      ) : workflows.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border p-10 text-center">
          Publish a workflow before creating an automation.
        </div>
      ) : (
        <SchedulesPanel
          embedded
          machineName={selected?.slug}
          workflowEntityType={selected?.entityType}
          workflowLabels={workflowLabels}
        />
      )}

      <Modal open={showInfo} onClose={() => setShowInfo(false)} title="About automations" size="md">
        <div className="space-y-5 text-sm leading-6 text-muted-foreground">
          <div>
            <p className="font-medium text-foreground">What this tab does</p>
            <p className="mt-1">
              Automations create and enrol related records on a one-time or recurring schedule.
              You can view all workflows, run an automation now, pause it, edit its timing, or
              delete it.
            </p>
          </div>
          <div>
            <p className="font-medium text-foreground">Quick setup</p>
            <ol className="mt-1 list-decimal space-y-1 pl-5">
              <li>Create the target workflow and its entity type.</li>
              <li>Define a relationship from the source entity to that target entity.</li>
              <li>Select the workflow here, then choose New automation.</li>
              <li>Set timing, scope, optional conditions, timezone, and save.</li>
            </ol>
          </div>
          <p className="rounded-lg bg-muted/50 p-3 text-xs">
            With no records selected, an automation applies to all active related records. Run now
            uses the same scope and conditions as the schedule.
          </p>
        </div>
      </Modal>
    </div>
  );
}
