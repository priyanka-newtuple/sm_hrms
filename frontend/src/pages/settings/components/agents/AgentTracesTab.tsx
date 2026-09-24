import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ChevronDown, Loader2, RefreshCw, Search, Sparkles, Wrench } from 'lucide-react';
import { agentTraces } from '../../../../core/services/api';
import type { AgentTraceRunDetail, AgentTraceRunListItem, AgentTraceSessionListItem } from '../../../../core/types';
import { Button } from '@/components/ui/button';

function formatDuration(ms?: number | null) {
  if (!ms && ms !== 0) return '—';
  if (ms < 1000) return `${ms} ms`;
  const s = (ms / 1000).toFixed(2);
  return `${s} s`;
}

function formatDate(value?: string | null) {
  if (!value) return '—';
  return new Date(value).toLocaleString();
}

function formatPayload(payload: unknown) {
  if (payload === null || payload === undefined) return '';
  if (typeof payload === 'string') return payload;
  try {
    return JSON.stringify(payload, null, 2);
  } catch {
    return String(payload);
  }
}

function truncateText(value: string, max = 140) {
  const normalized = value.replace(/\s+/g, ' ').trim();
  if (normalized.length <= max) return normalized;
  return `${normalized.slice(0, max - 1)}...`;
}

function statusBadgeClass(status?: string | null): string {
  if (status === 'success') return 'bg-success-subtle text-success';
  if (status === 'partial') return 'bg-warning-subtle text-warning';
  return 'bg-destructive-subtle text-destructive';
}

function getKindMeta(kind: string) {
  const normalized = kind.toLowerCase();
  if (normalized === 'system_prompt') {
    return { label: 'System Prompt', chip: 'bg-violet-100 text-violet-700', dot: 'bg-violet-500', border: 'border-violet-200' };
  }
  if (normalized === 'user_message') {
    return { label: 'User Message', chip: 'bg-cyan-100 text-cyan-700', dot: 'bg-cyan-500', border: 'border-cyan-200' };
  }
  if (normalized === 'assistant_message') {
    return { label: 'Assistant', chip: 'bg-indigo-100 text-indigo-700', dot: 'bg-indigo-500', border: 'border-indigo-200' };
  }
  if (normalized === 'tool_call') {
    return { label: 'Tool Call', chip: 'bg-warning-subtle text-warning', dot: 'bg-warning', border: 'border-warning/30' };
  }
  if (normalized === 'llm_request') {
    return { label: 'LLM Request', chip: 'bg-cyan-100 text-cyan-700', dot: 'bg-cyan-500', border: 'border-cyan-200' };
  }
  if (normalized === 'tool_result') {
    return { label: 'Tool Result', chip: 'bg-success-subtle text-success', dot: 'bg-success', border: 'border-success/30' };
  }
  if (normalized === 'pending_action') {
    return { label: 'Pending Action', chip: 'bg-warning-subtle text-warning', dot: 'bg-warning', border: 'border-warning/30' };
  }
  if (normalized === 'error') {
    return { label: 'Error', chip: 'bg-destructive-subtle text-destructive', dot: 'bg-destructive', border: 'border-destructive/30' };
  }
  if (normalized === 'context') {
    return { label: 'Context', chip: 'bg-muted text-foreground', dot: 'bg-muted-foreground', border: 'border-border' };
  }
  if (normalized === 'run_summary') {
    return { label: 'Summary', chip: 'bg-info-subtle text-info', dot: 'bg-info', border: 'border-info/30' };
  }
  return { label: kind.replace('_', ' '), chip: 'bg-muted text-foreground', dot: 'bg-muted-foreground', border: 'border-border' };
}

function getFlowMeta(kind: string) {
  const normalized = kind.toLowerCase();
  if (normalized === 'llm_request') {
    return {
      label: 'Sent to LLM',
      className: 'bg-cyan-50 text-cyan-700 border-cyan-200',
      panelClass: 'bg-cyan-50/35',
    };
  }
  if (normalized === 'user_message') {
    return {
      label: 'User Input',
      className: 'bg-info-subtle text-info border-info/30',
      panelClass: 'bg-info-subtle/35',
    };
  }
  if (normalized === 'assistant_message') {
    return {
      label: 'Received from LLM',
      className: 'bg-indigo-50 text-indigo-700 border-indigo-200',
      panelClass: 'bg-indigo-50/35',
    };
  }
  if (normalized === 'tool_call' || normalized === 'tool_result' || normalized === 'pending_action') {
    return {
      label: 'Tool/System',
      className: 'bg-warning-subtle text-warning border-warning/30',
      panelClass: 'bg-warning-subtle/35',
    };
  }
  if (normalized === 'error') {
    return {
      label: 'Runtime Error',
      className: 'bg-destructive-subtle text-destructive border-destructive/30',
      panelClass: 'bg-destructive-subtle/40',
    };
  }
  return {
    label: 'Run Metadata',
    className: 'bg-muted/50 text-foreground border-border',
    panelClass: 'bg-muted/40',
  };
}

type TraceEvent = AgentTraceRunDetail['events'][number];
type JsonRecord = Record<string, unknown>;

function asRecord(value: unknown): JsonRecord {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as JsonRecord : {};
}

function asString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null;
}

function getNestedRecord(source: JsonRecord, key: string): JsonRecord {
  return asRecord(source[key]);
}

function getToolNames(payload: JsonRecord): string[] {
  const toolSummary = getNestedRecord(payload, 'tool_summary');
  const tools = Array.isArray(toolSummary.tools) ? toolSummary.tools : [];
  return tools
    .map((tool) => {
      const row = asRecord(tool);
      return asString(row.tool_id) || asString(row.capability_key);
    })
    .filter((tool): tool is string => Boolean(tool));
}

function TraceContextSummary({ payload }: { payload: unknown }) {
  const data = asRecord(payload);
  const agent = getNestedRecord(data, 'agent');
  const runtimeSpec = getNestedRecord(data, 'runtime_spec');
  const executionContext = getNestedRecord(data, 'execution_context');
  const runtime = getNestedRecord(executionContext, 'runtime');
  const session = getNestedRecord(executionContext, 'session');
  const toolSummary = getNestedRecord(data, 'tool_summary');
  const toolNames = getToolNames(data);
  const toolCount = typeof toolSummary.count === 'number'
    ? toolSummary.count
    : Array.isArray(runtimeSpec.tool_ids)
      ? runtimeSpec.tool_ids.length
      : 0;

  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="rounded-lg border border-border bg-muted/50 p-3">
          <div className="text-[11px] font-semibold uppercase text-muted-foreground">Agent</div>
          <div className="mt-1 text-sm font-medium text-foreground">
            {asString(agent.name) || asString(runtimeSpec.name) || 'Unknown agent'}
          </div>
          <div className="mt-1 text-xs text-muted-foreground">
            {asString(agent.model) || asString(runtimeSpec.model) || 'Model unavailable'}
          </div>
        </div>
        <div className="rounded-lg border border-border bg-muted/50 p-3">
          <div className="text-[11px] font-semibold uppercase text-muted-foreground">Session</div>
          <div className="mt-1 text-sm font-medium text-foreground break-all">
            {asString(data.session_id) || asString(session.session_id) || 'No session'}
          </div>
          <div className="mt-1 text-xs text-muted-foreground">
            User {asString(runtime.user_id)?.slice(0, 8) || 'unknown'}
          </div>
        </div>
      </div>

      <div className="rounded-lg border border-border bg-card p-3">
        <div className="flex items-center justify-between gap-3">
          <div className="text-[11px] font-semibold uppercase text-muted-foreground">Enabled Tools</div>
          <span className="rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">
            {toolCount} configured
          </span>
        </div>
        {toolNames.length > 0 ? (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {toolNames.map((tool) => (
              <span key={tool} className="rounded-full bg-warning-subtle px-2 py-1 text-xs text-warning">
                {tool}
              </span>
            ))}
          </div>
        ) : (
          <div className="mt-2 text-xs text-muted-foreground">
            Tool names are unavailable for this trace; raw capability IDs are in the payload below.
          </div>
        )}
      </div>
    </div>
  );
}

function TraceEventBody({ event }: { event: TraceEvent }) {
  const payload = asRecord(event.payload);
  if (event.kind === 'context') {
    return <TraceContextSummary payload={event.payload} />;
  }
  if (event.kind === 'user_message' || event.kind === 'assistant_message') {
    return (
      <div className="rounded-lg bg-muted/50 p-3 text-sm leading-6 text-foreground whitespace-pre-wrap">
        {asString(payload.content) || formatPayload(event.payload)}
      </div>
    );
  }
  if (event.kind === 'llm_request') {
    const body = getNestedRecord(payload, 'body');
    const tools = Array.isArray(body.tools) ? body.tools : [];
    const messages = Array.isArray(body.input)
      ? body.input
      : Array.isArray(body.messages)
        ? body.messages
        : body.input
          ? [body.input]
          : [];
    return (
      <div className="space-y-3">
        <div className="grid gap-2 sm:grid-cols-3">
          <div className="rounded-lg border border-cyan-100 bg-card p-3">
            <div className="text-[11px] uppercase text-muted-foreground">API</div>
            <div className="mt-1 text-sm font-medium text-foreground">{asString(payload.api) || 'unknown'}</div>
          </div>
          <div className="rounded-lg border border-cyan-100 bg-card p-3">
            <div className="text-[11px] uppercase text-muted-foreground">Messages</div>
            <div className="mt-1 text-sm font-medium text-foreground">{messages.length}</div>
          </div>
          <div className="rounded-lg border border-cyan-100 bg-card p-3">
            <div className="text-[11px] uppercase text-muted-foreground">Tools</div>
            <div className="mt-1 text-sm font-medium text-foreground">{tools.length}</div>
          </div>
        </div>

        {tools.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {tools.map((tool, index) => {
              const row = asRecord(tool);
              const fn = getNestedRecord(row, 'function');
              const name = asString(fn.name) || `tool_${index + 1}`;
              return (
                <span key={name} className="inline-flex items-center gap-1 rounded-full bg-cyan-100 px-2 py-1 text-xs text-cyan-800">
                  <Wrench className="h-3 w-3" />
                  {name}
                </span>
              );
            })}
          </div>
        )}

        <div>
          <div className="mb-1 text-xs font-medium text-muted-foreground">Translated request body</div>
          <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-lg border border-cyan-100 bg-card p-3 text-xs">
            {formatPayload(body)}
          </pre>
        </div>
      </div>
    );
  }
  if (event.kind === 'error') {
    return (
      <div className="rounded-lg border border-destructive/30 bg-destructive-subtle p-3 text-sm leading-6 text-destructive whitespace-pre-wrap">
        {asString(payload.message) || formatPayload(event.payload)}
      </div>
    );
  }
  if (event.kind === 'run_summary') {
    return (
      <div className="grid gap-2 sm:grid-cols-3">
        <div className="rounded-lg bg-muted/50 p-3">
          <div className="text-[11px] uppercase text-muted-foreground">Status</div>
          <div className="mt-1 text-sm font-medium text-foreground">{asString(payload.status) || 'unknown'}</div>
        </div>
        <div className="rounded-lg bg-muted/50 p-3">
          <div className="text-[11px] uppercase text-muted-foreground">Tokens</div>
          <div className="mt-1 text-sm font-medium text-foreground">{String(payload.tokens_used ?? 0)}</div>
        </div>
        <div className="rounded-lg bg-muted/50 p-3">
          <div className="text-[11px] uppercase text-muted-foreground">Duration</div>
          <div className="mt-1 text-sm font-medium text-foreground">
            {formatDuration(typeof payload.duration_ms === 'number' ? payload.duration_ms : null)}
          </div>
        </div>
      </div>
    );
  }
  return (
    <pre className="text-xs bg-muted/50 border border-border rounded-lg p-3 overflow-auto max-h-72 whitespace-pre-wrap">
      {formatPayload(event.payload)}
    </pre>
  );
}

function getTraceEventSummary(event: TraceEvent) {
  const payload = asRecord(event.payload);
  if (event.kind === 'llm_request') {
    const body = getNestedRecord(payload, 'body');
    const messages = Array.isArray(body.messages) ? body.messages : [];
    const tools = Array.isArray(body.tools) ? body.tools : [];
    const toolNames = tools
      .map((tool) => asString(getNestedRecord(asRecord(tool), 'function').name))
      .filter((tool): tool is string => Boolean(tool));
    return [
      `${messages.length} messages`,
      `${tools.length} tools`,
      toolNames.length ? toolNames.join(', ') : null,
    ].filter(Boolean).join(' · ');
  }
  if (event.kind === 'context') {
    const agent = getNestedRecord(payload, 'agent');
    const toolSummary = getNestedRecord(payload, 'tool_summary');
    const toolCount = typeof toolSummary.count === 'number' ? toolSummary.count : 0;
    return [
      asString(agent.name) || 'Unknown agent',
      asString(agent.model),
      `${toolCount} configured tools`,
    ].filter(Boolean).join(' · ');
  }
  if (event.kind === 'user_message' || event.kind === 'assistant_message') {
    return truncateText(asString(payload.content) || formatPayload(event.payload));
  }
  if (event.kind === 'tool_call') {
    const result = payload.result;
    const resultRecord = asRecord(result);
    const output = resultRecord.output;
    const count = asRecord(output).count;
    return [
      asString(payload.tool) || asString(payload.name) || 'Tool call',
      payload.success === false ? 'failed' : 'completed',
      typeof count === 'number' ? `${count} results` : null,
    ].filter(Boolean).join(' · ');
  }
  if (event.kind === 'pending_action') {
    return asString(payload.description) || asString(payload.tool) || 'Pending approval';
  }
  if (event.kind === 'error') {
    return truncateText(asString(payload.message) || formatPayload(event.payload));
  }
  if (event.kind === 'run_summary') {
    return [
      asString(payload.status) || 'unknown',
      `${String(payload.tokens_used ?? 0)} tokens`,
      formatDuration(typeof payload.duration_ms === 'number' ? payload.duration_ms : null),
    ].join(' · ');
  }
  return truncateText(formatPayload(event.payload));
}

function TraceEventsTable({ events }: { events: TraceEvent[] }) {
  const [expandedEventIds, setExpandedEventIds] = useState<Set<string>>(() => new Set());

  useEffect(() => {
    setExpandedEventIds(new Set());
  }, [events]);

  const toggleEvent = (eventId: string) => {
    setExpandedEventIds((current) => {
      const next = new Set(current);
      if (next.has(eventId)) {
        next.delete(eventId);
      } else {
        next.add(eventId);
      }
      return next;
    });
  };

  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card">
      <div className="overflow-x-auto">
        <table className="w-full table-fixed border-collapse text-sm">
          <colgroup>
            <col className="w-14" />
            <col className="w-44" />
            <col />
          </colgroup>
          <thead className="sticky top-0 z-10 bg-muted/50 text-left text-[11px] font-semibold uppercase text-muted-foreground">
            <tr>
              <th className="border-b border-border px-2 py-2"></th>
              <th className="border-b border-border px-3 py-2">Event</th>
              <th className="border-b border-border px-3 py-2">Summary</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {events.map((event) => {
              const meta = getKindMeta(event.kind);
              const flow = getFlowMeta(event.kind);
              const isExpanded = expandedEventIds.has(event.id);
              return (
                <Fragment key={event.id}>
                  <tr className={`${flow.panelClass} align-top hover:bg-card`}>
                    <td className="px-2 py-2">
                      <button
                        type="button"
                        onClick={() => toggleEvent(event.id)}
                        className="inline-flex h-8 w-9 items-center justify-center rounded-lg border border-border bg-card text-xs font-medium text-muted-foreground hover:border-cobalt/40 hover:text-cobalt"
                        aria-expanded={isExpanded}
                        title={isExpanded ? 'Hide raw payload' : 'View raw payload'}
                      >
                        <ChevronDown className={`h-3.5 w-3.5 transition-transform ${isExpanded ? 'rotate-180' : ''}`} />
                      </button>
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex min-w-0 flex-col gap-1">
                        <div className="flex min-w-0 items-center gap-2">
                          <span className="font-mono text-xs text-muted-foreground">#{event.seq}</span>
                          <span className={`inline-flex rounded-full px-2 py-0.5 text-[10px] uppercase tracking-wide ${meta.chip}`}>
                            {meta.label}
                          </span>
                        </div>
                        <span className={`inline-flex w-fit rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${flow.className}`}>
                          {flow.label}
                        </span>
                        <span className="truncate font-mono text-[11px] text-muted-foreground">{event.kind}</span>
                      </div>
                    </td>
                    <td className="px-3 py-2 text-foreground">
                      <div className="line-clamp-2">{getTraceEventSummary(event)}</div>
                    </td>
                  </tr>
                  {isExpanded && (
                    <tr className="bg-card">
                      <td className="border-t border-border px-3 py-3" colSpan={3}>
                        <div className="space-y-3">
                          <div className="min-w-0">
                            <div className="mb-1 text-xs font-semibold uppercase text-muted-foreground">Rendered payload</div>
                            <TraceEventBody event={event} />
                          </div>
                          <div className="min-w-0">
                            <div className="mb-1 text-xs font-semibold uppercase text-muted-foreground">Raw payload</div>
                            <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-lg border border-border bg-muted/50 p-3 text-xs">
                              {formatPayload(event.payload)}
                            </pre>
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function AgentTracesTab() {
  const [sessions, setSessions] = useState<AgentTraceSessionListItem[]>([]);
  const [sessionRuns, setSessionRuns] = useState<AgentTraceRunListItem[]>([]);
  const [selectedSession, setSelectedSession] = useState<AgentTraceSessionListItem | null>(null);
  const [selectedRun, setSelectedRun] = useState<AgentTraceRunDetail | null>(null);
  const selectedRunIdRef = useRef<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [runsLoading, setRunsLoading] = useState(false);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'success' | 'partial' | 'error'>('all');

  const filteredSessions = useMemo(() => {
    return sessions.filter((session) => {
      if (statusFilter !== 'all' && session.latest_status !== statusFilter) return false;
      if (!query) return true;
      const q = query.toLowerCase();
      return (
        session.agent_name.toLowerCase().includes(q) ||
        (session.latest_input_message || '').toLowerCase().includes(q)
      );
    });
  }, [sessions, query, statusFilter]);

  const fetchRunDetails = useCallback(async (runId: string) => {
    setDetailsLoading(true);
    try {
      const response = await agentTraces.getRun(runId);
      setSelectedRun(response);
      selectedRunIdRef.current = response.id;
    } finally {
      setDetailsLoading(false);
    }
  }, []);

  const fetchSessionRuns = useCallback(async (sessionId: string, autoSelectRun = true) => {
    try {
      setRunsLoading(true);
      const response = await agentTraces.listRuns({ limit: 100, session_id: sessionId });
      setSessionRuns(response.items);
      if (autoSelectRun && response.items.length > 0) {
        await fetchRunDetails(response.items[0].id);
      }
    } finally {
      setRunsLoading(false);
    }
  }, [fetchRunDetails]);

  const fetchSessions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await agentTraces.listSessions({ limit: 100 });
      setSessions(response.items);
      if (response.items.length > 0) {
        const first = response.items[0];
        setSelectedSession(first);
        await fetchSessionRuns(first.session_id, true);
      } else {
        setSelectedSession(null);
        setSessionRuns([]);
        setSelectedRun(null);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load agent traces');
    } finally {
      setLoading(false);
    }
  }, [fetchSessionRuns]);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-border bg-gradient-to-br from-muted/60 via-card to-cyan/10 p-6 shadow-sm">
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2">
              <div className="h-9 w-9 rounded-xl bg-cobalt/10 flex items-center justify-center">
                <Sparkles className="w-4 h-4 text-cobalt" />
              </div>
              <h2 className="text-lg font-semibold text-foreground">Agent Traces</h2>
            </div>
            <p className="text-sm text-muted-foreground mt-2">Inspect agent runs, tool calls, and model responses.</p>
          </div>
          <Button
            variant="ghost"
            onClick={() => fetchSessions()}
            className="flex items-center gap-2 px-3 py-2 text-muted-foreground hover:text-cobalt hover:bg-card/80 rounded-lg transition-all duration-200 shadow-sm border border-transparent hover:border-cobalt/20"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <div className="relative flex-1">
          <Search className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search agent name, prompt, or error..."
            className="w-full pl-9 pr-3 py-2 border border-border rounded-xl text-sm bg-card/90 focus:bg-card focus:ring-2 focus:ring-cobalt/20 transition-all"
          />
        </div>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as 'all' | 'success' | 'partial' | 'error')}
          className="px-3 py-2 border border-border rounded-xl text-sm bg-card focus:ring-2 focus:ring-cobalt/20 transition-all"
        >
          <option value="all">All statuses</option>
          <option value="success">Success</option>
          <option value="partial">Partial</option>
          <option value="error">Error</option>
        </select>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-6 h-6 text-cobalt animate-spin" />
        </div>
      ) : error ? (
        <div className="bg-destructive-subtle border border-destructive/30 rounded-xl p-4 text-destructive text-sm">
          {error}
        </div>
      ) : (
        <div className="grid min-h-[560px] grid-cols-12 gap-5 lg:h-[calc(100vh-280px)]">
          <div className="col-span-12 min-h-0 lg:col-span-4 xl:col-span-3">
            <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-sm">
              <div className="px-4 py-3 border-b border-border text-sm font-medium text-foreground flex items-center justify-between">
                <span>Conversations</span>
                <span className="text-xs px-2 py-0.5 rounded-full bg-muted text-muted-foreground">{filteredSessions.length}</span>
              </div>
              <div className="min-h-0 flex-1 divide-y divide-border overflow-y-auto">
                {filteredSessions.length === 0 && (
                  <div className="px-4 py-6 text-sm text-muted-foreground text-center">
                    No agent traces found.
                  </div>
                )}
                {filteredSessions.map((session) => (
                  <button
                    type="button"
                    key={session.session_id}
                    onClick={async () => {
                      setSelectedSession(session);
                      await fetchSessionRuns(session.session_id, true);
                    }}
                    className={`block w-full px-3 py-3 text-left transition-all duration-200 hover:bg-muted/50 ${
                      selectedSession?.session_id === session.session_id ? 'bg-cobalt/5 ring-1 ring-cobalt/20' : 'bg-card'
                    }`}
                  >
                    <div className="flex min-w-0 items-start justify-between gap-3">
                      <div className="min-w-0 flex-1 truncate text-sm font-medium text-foreground">
                        {session.agent_name}
                      </div>
                      <span
                        className={`shrink-0 text-[11px] px-2 py-0.5 rounded-full ${statusBadgeClass(session.latest_status)}`}
                      >
                        {session.latest_status}
                      </span>
                    </div>
                    <div className="mt-1 flex min-w-0 flex-wrap items-center gap-x-1.5 gap-y-1 text-xs text-muted-foreground">
                      <span>Session {session.session_id.slice(0, 8)}</span>
                      <span aria-hidden="true">·</span>
                      <span>{session.run_count} turns</span>
                      <span aria-hidden="true">·</span>
                      <span>{session.total_tokens} tokens</span>
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      {formatDate(session.last_started_at)}
                    </div>
                    {session.latest_input_message && (
                      <div className="mt-2 text-xs text-muted-foreground line-clamp-2">
                        {session.latest_input_message}
                      </div>
                    )}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="col-span-12 min-h-0 lg:col-span-8 xl:col-span-9">
            <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-sm">
              {!selectedRun ? (
                <div className="p-4 text-sm text-muted-foreground">Select a run to view details.</div>
              ) : detailsLoading ? (
                <div className="flex items-center justify-center py-12">
                  <Loader2 className="w-6 h-6 text-cobalt animate-spin" />
                </div>
              ) : (
                <>
                  <div className="border-b border-border bg-card px-4 py-3">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
                          <h3 className="truncate text-base font-semibold text-foreground">{selectedRun.agent_name}</h3>
                          <span
                            className={`shrink-0 rounded-full px-2 py-0.5 text-xs ${statusBadgeClass(selectedRun.status)}`}
                          >
                            {selectedRun.status}
                          </span>
                        </div>
                        <div className="mt-1 flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
                          <span>{formatDate(selectedRun.started_at)}</span>
                          <span aria-hidden="true">·</span>
                          <span>{formatDuration(selectedRun.duration_ms)}</span>
                          <span aria-hidden="true">·</span>
                          <span>{selectedRun.tokens_used} tokens</span>
                          {selectedSession && (
                            <>
                              <span aria-hidden="true">·</span>
                              <span className="truncate">Session {selectedSession.session_id.slice(0, 8)}</span>
                              <span aria-hidden="true">·</span>
                              <span>{selectedSession.run_count} turns</span>
                            </>
                          )}
                        </div>
                      </div>
                      {runsLoading && <Loader2 className="h-4 w-4 animate-spin text-cobalt" />}
                    </div>

                    <div className="mt-3 flex gap-1.5 overflow-x-auto pb-1">
                      {!selectedSession ? (
                        <div className="text-sm text-muted-foreground">Select a conversation.</div>
                      ) : sessionRuns.length === 0 ? (
                        <div className="text-sm text-muted-foreground">No turns found.</div>
                      ) : (
                        sessionRuns.map((run, index) => (
                          <button
                            type="button"
                            key={run.id}
                            onClick={() => fetchRunDetails(run.id)}
                            className={`flex max-w-64 shrink-0 items-center gap-2 rounded-full border px-3 py-1.5 text-left text-xs transition ${
                              selectedRun?.id === run.id
                                ? 'border-cobalt bg-cobalt/5 text-cobalt shadow-sm'
                                : 'border-border bg-muted/50 text-muted-foreground hover:bg-card'
                            }`}
                          >
                            <span className="font-semibold">Turn {index + 1}</span>
                            <span className="text-muted-foreground">·</span>
                            <span>{formatDuration(run.duration_ms)}</span>
                            {run.input_message && (
                              <>
                                <span className="text-muted-foreground">·</span>
                                <span className="truncate">{run.input_message}</span>
                              </>
                            )}
                          </button>
                        ))
                      )}
                    </div>
                  </div>

                  <div className="min-h-0 flex-1 overflow-y-auto p-3">
                    {selectedRun.error && (
                      <div className="mb-4 rounded-lg border border-destructive/30 bg-destructive-subtle p-3 text-sm text-destructive">
                        {selectedRun.error}
                      </div>
                    )}

                    <div className="mb-2 flex flex-wrap gap-1.5">
                      {[
                        ['Sent to LLM', 'bg-cyan-50 text-cyan-700 border-cyan-200'],
                        ['User Input', 'bg-info-subtle text-info border-info/30'],
                        ['Received from LLM', 'bg-indigo-50 text-indigo-700 border-indigo-200'],
                        ['Tool/System', 'bg-warning-subtle text-warning border-warning/30'],
                        ['Run Metadata', 'bg-muted/50 text-foreground border-border'],
                      ].map(([label, className]) => (
                        <div key={label} className={`rounded-full border px-2.5 py-0.5 text-xs font-medium ${className}`}>
                          {label}
                        </div>
                      ))}
                    </div>

                    <TraceEventsTable events={selectedRun.events} />
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
