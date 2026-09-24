import { useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { stateMachines, workflowEntities } from '@/core/services/api';
import { events as eventsApi } from '@/core/services/api/events';
import type { StateActionRerunResponse } from '@/core/services/api/workflowEntities';
import { queryClient } from '@/core/queryClient';
import { timelineKeys, workflowEntityKeys } from '@/core/services/api/queryKeys';
import type { StateMachineRecord } from '@/core/types';

export type RunCompletionStatus = 'succeeded' | 'failed' | 'waiting' | 'timeout';

export interface ActionSummary {
  kind: string;
  config?: Record<string, unknown>;
  actionDisplayName?: string;
  connectorId?: string;
}

interface UseCurrentStateActionResult {
  /** Actions configured on the current state, in chain order; empty when none. */
  actions: ActionSummary[];
  loading: boolean;
  rerun: (entityId: string, actionIndex?: number) => Promise<StateActionRerunResponse>;
  /** Resolves when the run finishes; chain runs wait for the last link. */
  waitForRunCompletion: (
    entityId: string,
    runId: string,
    isolated: boolean,
    onBackgroundSettled?: (status: RunCompletionStatus) => void,
  ) => Promise<RunCompletionStatus>;
}

/** Terminal run events. ACTION_ALERT is a failure ("alert" policy) with no
 *  separate ACTION_FAILED, so it counts as terminal too. */
const TERMINAL_EVENT_STATUS: Record<string, RunCompletionStatus> = {
  ACTION_COMPLETED: 'succeeded',
  ACTION_FAILED: 'failed',
  ACTION_ALERT: 'failed',
  ACTION_WAITING_EXTERNAL: 'waiting',
};

/** Chain-terminating events: the rest of the chain will not run. */
const CHAIN_END_STATUS: Record<string, RunCompletionStatus> = {
  ACTION_CHAIN_STOPPED: 'failed',
  ACTION_CHAIN_SKIPPED: 'succeeded',
};

const POLL_INTERVAL_MS = 2_500;
/** How long the button stays disabled/spinning before we hand control back. */
const ACTIVE_POLL_TIMEOUT_MS = 20_000;
/** How long we keep quietly checking after that, for slow actions (agent runs, etc.). */
const BACKGROUND_POLL_TIMEOUT_MS = 2 * 60_000;

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/** Reads the state's actions (list shape, legacy singular fallback). */
function findStateActions(record: StateMachineRecord, stateName: string): ActionSummary[] {
  const states = (record.definition as { states?: unknown }).states;
  if (!Array.isArray(states)) return [];
  for (const state of states) {
    if (!state || typeof state !== 'object') continue;
    const s = state as { name?: unknown; on_state_actions?: unknown; on_state_action?: unknown };
    if (s.name !== stateName) continue;
    const actions = Array.isArray(s.on_state_actions)
      ? s.on_state_actions
      : s.on_state_action && typeof s.on_state_action === 'object'
        ? [s.on_state_action]
        : [];
    return actions.flatMap((a): ActionSummary[] => {
      if (!a || typeof a !== 'object') return [];
      const { kind, config } = a as { kind?: unknown; config?: unknown };
      if (typeof kind !== 'string' || !kind) return [];
      const actionConfig =
        config && typeof config === 'object' && !Array.isArray(config)
          ? (config as Record<string, unknown>)
          : {};
      const connectorId = actionConfig.connector_id;
      const actionDisplayName =
        typeof actionConfig.action_display_name === 'string'
          ? actionConfig.action_display_name
          : undefined;
      return [{
        kind,
        config: actionConfig,
        actionDisplayName,
        connectorId: typeof connectorId === 'string' ? connectorId : undefined,
      }];
    });
  }
  return [];
}

/** Current state's actions + a `rerun` mutation; `workflowId` falls back for `machineName`. */
export function useCurrentStateAction(
  machineName: string | undefined,
  workflowId: string | undefined,
  currentState: string | undefined,
): UseCurrentStateActionResult {
  const enabled = Boolean(currentState && (machineName || workflowId));

  const query = useQuery({
    queryKey: ['activeWorkflowDefinition', machineName ?? null, workflowId ?? null],
    enabled,
    // Always re-check on mount so a workflow edit shows/hides the button immediately.
    staleTime: 0,
    retry: false,
    queryFn: (): Promise<StateMachineRecord> =>
      workflowId
        ? stateMachines.getById(workflowId)
        : stateMachines.getActive(machineName as string),
  });

  // Fetch failure = "no action" so the caller just hides the control.
  const actions =
    enabled && currentState && query.data ? findStateActions(query.data, currentState) : [];

  const rerun = useCallback(async (entityId: string, actionIndex?: number) => {
    const result = await workflowEntities.rerunStateAction(entityId, actionIndex, workflowId);
    void queryClient.invalidateQueries({ queryKey: timelineKeys.all(entityId) });
    return result;
  }, [workflowId]);

  /** Polls until the run finishes or `deadline` passes. */
  const pollUntil = useCallback(
    async (
      entityId: string,
      runId: string,
      deadline: number,
      isolated: boolean,
    ): Promise<RunCompletionStatus> => {
      while (Date.now() < deadline) {
        await sleep(POLL_INTERVAL_MS);
        try {
          const page = await eventsApi.listActivity(entityId, { limit: 25, offset: 0 });
          for (const item of page.items ?? []) {
            const md = (item.metadata as Record<string, unknown> | null) ?? {};
            const matchesChain = md.chain_id === runId;
            const matchesRun = item.correlation_id === runId || md.run_id === runId;
            if (item.event_type in CHAIN_END_STATUS && matchesChain) {
              return CHAIN_END_STATUS[item.event_type];
            }
            if (!(item.event_type in TERMINAL_EVENT_STATUS)) continue;
            if (!(matchesChain || matchesRun)) continue;
            if (isolated) return TERMINAL_EVENT_STATUS[item.event_type];
            const index = typeof md.action_index === 'number' ? md.action_index : 0;
            const total = typeof md.action_total === 'number' ? md.action_total : 1;
            if (index + 1 >= total) return TERMINAL_EVENT_STATUS[item.event_type];
          }
        } catch (err) {
          // Transient fetch error — keep polling until the deadline.
          console.error('[pollUntil] transient error, retrying', runId, err);
        }
      }
      return 'timeout';
    },
    [],
  );

  const waitForRunCompletion = useCallback(
    async (
      entityId: string,
      runId: string,
      isolated: boolean,
      onBackgroundSettled?: (status: RunCompletionStatus) => void,
    ): Promise<RunCompletionStatus> => {
      const status = await pollUntil(entityId, runId, Date.now() + ACTIVE_POLL_TIMEOUT_MS, isolated);
      if (status !== 'timeout') {
        void queryClient.invalidateQueries({ queryKey: timelineKeys.all(entityId) });
        void queryClient.invalidateQueries({ queryKey: workflowEntityKeys.all() });
        return status;
      }
      // Still running: hand control back now, keep polling quietly.
      void (async () => {
        const bgStatus = await pollUntil(
          entityId, runId, Date.now() + BACKGROUND_POLL_TIMEOUT_MS, isolated,
        );
        if (bgStatus === 'timeout') return;
        void queryClient.invalidateQueries({ queryKey: timelineKeys.all(entityId) });
        void queryClient.invalidateQueries({ queryKey: workflowEntityKeys.all() });
        onBackgroundSettled?.(bgStatus);
      })();
      return status;
    },
    [pollUntil],
  );

  return { actions, loading: enabled && query.isPending, rerun, waitForRunCompletion };
}
