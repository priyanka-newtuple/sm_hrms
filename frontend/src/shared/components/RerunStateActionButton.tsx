import { useEffect, useRef, useState } from 'react';
import { ChevronDown, Loader2, RotateCw } from 'lucide-react';
import { toast } from 'sonner';

import { getApiErrorMessage } from '@/core/services/api/client';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useActionDisplayNames, useCurrentStateAction, type RunCompletionStatus } from '@/shared/hooks';
import { useFeatureFlags } from '@/core/hooks/useFeatureFlags';
import { cn } from '@/lib/utils';

const HTTP_FORBIDDEN = 403;
const HTTP_CONFLICT = 409;

interface RerunStateActionButtonProps {
  entityId: string;
  currentState: string;
  /** Workflow the entity is enrolled in; either identifier resolves the active definition. */
  machineName?: string;
  workflowId?: string;
  /** Called when the run reaches a terminal state so the parent can refetch entity data. */
  onCompleted?: () => void;
}

/** "Re-run action" control for the entity detail badge row. Renders nothing
 *  when the entity's current state has no on-state action configured. */
export default function RerunStateActionButton({
  entityId,
  currentState,
  machineName,
  workflowId,
  onCompleted,
}: RerunStateActionButtonProps) {
  const { actions, loading, rerun, waitForRunCompletion } = useCurrentStateAction(
    machineName || undefined,
    workflowId,
    currentState,
  );
  const resolveActionDisplayName = useActionDisplayNames();
  const { hideRerunAction } = useFeatureFlags();
  const [running, setRunning] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const mountedRef = useRef(true);
  useEffect(() => () => { mountedRef.current = false; }, []);

  if (loading || actions.length === 0 || hideRerunAction) return null;

  const isChain = actions.length > 1;
  const actionName = (index: number) => {
    const a = actions[index];
    return resolveActionDisplayName(a);
  };

  const notifyOutcome = (label: string, status: RunCompletionStatus) => {
    if (status === 'succeeded') {
      toast.success('Action completed', {
        description: `"${label}" finished and the record has been refreshed.`,
      });
    } else if (status === 'failed') {
      toast.error('Action failed', {
        description: `"${label}" did not complete — check the Activity tab for details.`,
      });
    } else if (status === 'waiting') {
      toast('Awaiting external response', {
        description: `"${label}" is waiting on an external system.`,
      });
    } else {
      toast('Still running', {
        description: `"${label}" is taking a while — it'll refresh automatically when done.`,
      });
    }
  };

  // actionIndex omitted = whole chain from action 0; set = just that one action, isolated.
  const run = async (actionIndex: number | undefined, label: string) => {
    setRunning(true);
    setMenuOpen(false);
    try {
      const { run_id } = await rerun(entityId, actionIndex);
      const isolated = actionIndex != null;
      const status = await waitForRunCompletion(entityId, run_id, isolated, (bgStatus) => {
        if (mountedRef.current) onCompleted?.();
        notifyOutcome(label, bgStatus);
      });
      if (status !== 'timeout' && mountedRef.current) onCompleted?.();
      notifyOutcome(label, status);
    } catch (e) {
      const status = (e as { status?: number }).status;
      toast.error('Could not re-run action', {
        description:
          status === HTTP_FORBIDDEN
            ? `You don't have permission to re-run "${label}".`
            : status === HTTP_CONFLICT
              ? `"${label}" is already pending or running for this record.`
              : getApiErrorMessage(e, `"${label}" could not be re-run.`),
      });
    } finally {
      setRunning(false);
    }
  };

  const wholeChainLabel = isChain ? `${actions.length} actions` : actionName(0);

  return (
    <div className="inline-flex" onClick={(e) => e.stopPropagation()}>
      <button
        type="button"
        onClick={() => void run(undefined, wholeChainLabel)}
        disabled={running}
        title={isChain ? `Re-run all ${actions.length} actions` : `Re-run "${wholeChainLabel}"`}
        className={cn(
          'inline-flex h-8 items-center gap-1.5 border-y border-l border-primary/20 bg-primary/5 px-3 text-xs font-medium text-primary transition-colors hover:bg-primary/10 disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring/30',
          isChain ? 'rounded-l-lg' : 'rounded-lg border-r',
        )}
      >
        {running ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        ) : (
          <RotateCw className="h-3.5 w-3.5" />
        )}
        <span className="truncate">{isChain ? 'Re-run actions' : 'Re-run action'}</span>
      </button>

      {isChain && (
        <DropdownMenu open={menuOpen} onOpenChange={setMenuOpen}>
          <DropdownMenuTrigger
            disabled={running}
            className="inline-flex h-8 items-center rounded-r-lg border border-primary/20 bg-primary/5 px-1.5 text-primary transition-colors hover:bg-primary/10 disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring/30"
            aria-label="Re-run a specific action"
          >
            <ChevronDown className="h-3.5 w-3.5" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-64">
            {actions.map((_, index) => (
              <DropdownMenuItem
                key={index}
                onClick={() => void run(index, actionName(index))}
              >
                <span className="text-muted-foreground">{index + 1}.</span>{' '}
                {actionName(index)}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      )}
    </div>
  );
}
