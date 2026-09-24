import { useCallback, useEffect, useMemo, useState } from 'react';
import { Loader2, Play, RefreshCcw, Sparkles, AlertCircle } from 'lucide-react';

import { agent } from '../../../../core/services/api';
import type {
  AgentDefinitionListItem,
  AgentRun,
} from '../../../../core/types';
import Badge from '../../../../core/components/Badge';
import { resolveEnumLabel } from '../../../../shared/utils/labels';

const STATUS_TONE: Record<string, 'success' | 'warning' | 'error' | 'default'> = {
  completed: 'success',
  running: 'warning',
  queued: 'default',
  waiting_for_approval: 'warning',
  failed: 'error',
  cancelled: 'default',
};

function StatusBadge({ status }: { status: string }) {
  const tone = STATUS_TONE[status] ?? 'default';
  return <Badge variant={tone}>{resolveEnumLabel(status)}</Badge>;
}

/**
 * Minimal console for the phase-1 agent runtime: pick a definition, send one
 * prompt, see the response. Drives only the run endpoints
 * (POST/GET /agent/runs) and the existing definitions list. Multi-turn chat,
 * tools, approvals and traces are not part of the phase-1 runtime.
 */
export default function AgentRunConsole() {
  const [definitions, setDefinitions] = useState<AgentDefinitionListItem[]>([]);
  const [selectedId, setSelectedId] = useState<string>('');
  const [input, setInput] = useState<string>('');
  const [isRunning, setIsRunning] = useState(false);
  const [result, setResult] = useState<AgentRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [recentRuns, setRecentRuns] = useState<AgentRun[]>([]);

  const loadDefinitions = useCallback(async () => {
    try {
      const items = await agent.listDefinitions(true);
      setDefinitions(items);
      setSelectedId((current) => current || items[0]?.definition_id || '');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load agent definitions');
    }
  }, []);

  const loadRecentRuns = useCallback(async () => {
    try {
      const response = await agent.listRuns({ limit: 10 });
      setRecentRuns(response.items);
    } catch {
      // Recent runs are a convenience; ignore load failures.
    }
  }, []);

  useEffect(() => {
    void loadDefinitions();
    void loadRecentRuns();
  }, [loadDefinitions, loadRecentRuns]);

  const handleRun = useCallback(async () => {
    if (!selectedId || !input.trim() || isRunning) return;
    setIsRunning(true);
    setError(null);
    setResult(null);
    try {
      const run = await agent.createRun({ definition_id: selectedId, input: input.trim() });
      setResult(run);
      void loadRecentRuns();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Agent run failed');
    } finally {
      setIsRunning(false);
    }
  }, [selectedId, input, isRunning, loadRecentRuns]);

  const canRun = useMemo(
    () => Boolean(selectedId) && input.trim().length > 0 && !isRunning,
    [selectedId, input, isRunning],
  );

  return (
    <div className="space-y-6">
      <header className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-cobalt/10 text-cobalt">
          <Sparkles className="h-5 w-5" />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-foreground">Agent Run Console</h2>
          <p className="text-sm text-muted-foreground">
            Phase-1 runtime: select an agent, send a single prompt, get one response.
          </p>
        </div>
      </header>

      <div className="rounded-xl border border-border bg-card p-5 space-y-4">
        <div className="space-y-1.5">
          <label className="text-sm font-medium text-foreground" htmlFor="agent-run-definition">
            Agent
          </label>
          <select
            id="agent-run-definition"
            value={selectedId}
            onChange={(e) => setSelectedId(e.target.value)}
            className="w-full rounded-lg border border-border px-3 py-2 text-sm focus:border-cobalt focus:outline-none focus:ring-1 focus:ring-cobalt"
          >
            {definitions.length === 0 && <option value="">No agents available</option>}
            {definitions.map((def) => (
              <option key={def.definition_id} value={def.definition_id}>
                {def.display_name}
                {def.is_system ? ' (built-in)' : ''}
                {def.is_active ? '' : ' — disabled'}
              </option>
            ))}
          </select>
        </div>

        <div className="space-y-1.5">
          <label className="text-sm font-medium text-foreground" htmlFor="agent-run-input">
            Prompt
          </label>
          <textarea
            id="agent-run-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            rows={4}
            placeholder="Ask the agent something…"
            className="w-full resize-y rounded-lg border border-border px-3 py-2 text-sm focus:border-cobalt focus:outline-none focus:ring-1 focus:ring-cobalt"
          />
        </div>

        <div className="flex items-center justify-between">
          <button
            type="button"
            onClick={() => void loadDefinitions()}
            className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
          >
            <RefreshCcw className="h-3.5 w-3.5" />
            Reload agents
          </button>
          <button
            type="button"
            onClick={() => void handleRun()}
            disabled={!canRun}
            className="inline-flex items-center gap-2 rounded-full bg-cobalt px-5 py-2 text-sm font-medium text-white transition hover:bg-cobalt/90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isRunning ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Play className="h-4 w-4" />
            )}
            {isRunning ? 'Running…' : 'Run agent'}
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-start gap-2 rounded-xl border border-destructive/30 bg-destructive-subtle p-4 text-sm text-destructive">
          <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {result && (
        <div className="rounded-xl border border-border bg-card p-5 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-foreground">Result</span>
            <StatusBadge status={result.status} />
          </div>
          {result.output && (
            <p className="whitespace-pre-wrap text-sm text-foreground">{result.output}</p>
          )}
          {result.error && (
            <p className="whitespace-pre-wrap text-sm text-destructive">{result.error}</p>
          )}
          <p className="text-xs text-muted-foreground">Run ID: {result.run_id}</p>
        </div>
      )}

      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-foreground">Recent runs</h3>
          <button
            type="button"
            onClick={() => void loadRecentRuns()}
            className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
          >
            <RefreshCcw className="h-3 w-3" />
            Refresh
          </button>
        </div>
        {recentRuns.length === 0 ? (
          <p className="text-sm text-muted-foreground">No runs yet.</p>
        ) : (
          <ul className="divide-y divide-border rounded-xl border border-border bg-card">
            {recentRuns.map((run) => (
              <li key={run.run_id} className="flex items-center justify-between gap-4 px-4 py-3">
                <div className="min-w-0">
                  <p className="truncate text-sm text-foreground">{run.input}</p>
                  {run.output && (
                    <p className="truncate text-xs text-muted-foreground">{run.output}</p>
                  )}
                </div>
                <StatusBadge status={run.status} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
