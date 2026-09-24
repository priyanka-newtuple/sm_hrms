import { useMemo } from 'react';
import { isUIResource } from '@mcp-ui/client';
import type { ToolExecution, ConversationThread } from '@/core/agent/AgentContext';

/**
 * An mcp-ui UIResource (html / externalUrl / remote-dom) as carried in a
 * tool result. Rendered by @mcp-ui/client's UIResourceRenderer.
 */
export interface CanvasResource {
  uri: string;
  mimeType?: string;
  text?: string;
  blob?: string;
}

/** One thing rendered on the agent canvas: an mcp-ui resource, or a named
 *  pre-defined app component looked up in the canvas registry. */
export type CanvasItem =
  | { id: string; kind: 'resource'; title?: string; resource: CanvasResource }
  | { id: string; kind: 'component'; title?: string; component: string; props: Record<string, unknown> };

/**
 * The canvas is a pure projection of the active conversation: it is DERIVED
 * from the thread's persisted agent messages by replaying their tool calls, so
 * it restores for free when a past session is reopened and scopes per-thread
 * automatically (no separate store, no cross-thread bleed). See STAT-334.
 */
export function useCanvasItems(thread: ConversationThread | null | undefined): CanvasItem[] {
  const messages = thread?.messages;
  return useMemo(() => {
    const out: CanvasItem[] = [];
    for (const msg of messages ?? []) {
      if (msg.role !== 'agent') continue;
      out.push(...renderablesForMessage(msg.id, msg.toolExecutions));
    }
    return out;
    // Recompute when the active thread changes or its messages grow.
  }, [thread?.id, messages]);
}

/**
 * Scan one agent message's tool executions for renderable payloads and return
 * them as canvas items with DETERMINISTIC ids (`${messageId}::${exec}::${block}`)
 * so React preserves each live component's state across re-renders and the entry
 * animation fires once per genuinely new item. Works whether the tool output is
 * the full ToolExecutionResult envelope or the bare payload.
 */
export function renderablesForMessage(
  messageId: string,
  toolExecutions: ToolExecution[] | undefined,
): CanvasItem[] {
  const out: CanvasItem[] = [];
  toolExecutions?.forEach((ex, execIdx) => {
    if (!ex.output) return;
    let parsed: unknown;
    try {
      parsed = JSON.parse(ex.output);
    } catch {
      return;
    }
    asBlocks(unwrapEnvelope(parsed)).forEach((block, blockIdx) => {
      const id = `${messageId}::${execIdx}::${blockIdx}`;
      // (a) mcp-ui UIResource: { type: 'resource', resource: { uri: 'ui://…' } }
      if (isUIResource(block as Parameters<typeof isUIResource>[0])) {
        const resource = (block as { resource: CanvasResource }).resource;
        out.push({ id, kind: 'resource', title: 'View', resource });
        return;
      }
      // (b) named pre-defined component: { __render__: { component, props } }
      const render = (block as { __render__?: { component?: string; props?: Record<string, unknown> } })?.__render__;
      if (render?.component) {
        const props = render.props ?? {};
        out.push({ id, kind: 'component', title: humanTitle(render.component, props), component: render.component, props });
      }
    });
  });
  return out;
}

/** Human-friendly canvas tile title derived from the component + its data,
 *  instead of the raw tool name ("render_ui_component"). */
function humanTitle(component: string, props: Record<string, unknown>): string {
  const p = props as {
    summary?: { workflow_name?: string };
    def?: { title?: string };
    subtitle?: string;
  };
  const workflow = p.summary?.workflow_name;
  switch (component) {
    case 'dashboard':
      return 'Dashboard';
    case 'dashboard_widget':
      return p.def?.title || 'Metric';
    case 'pipeline_board':
      return workflow ? `${workflow} · Board` : 'Pipeline board';
    case 'pipeline_list':
      return workflow ? `${workflow} · List` : 'Pipeline list';
    case 'pipeline_calendar':
      return workflow ? `${workflow} · Calendar` : 'Pipeline calendar';
    case 'entity_table':
      return workflow ? `${workflow} · Entities` : 'Entities';
    case 'stat_tile':
      return p.subtitle || 'Metric';
    default:
      return component;
  }
}

/** A tool result may be a single object or an array of content blocks. */
function asBlocks(parsed: unknown): unknown[] {
  if (Array.isArray(parsed)) return parsed;
  return [parsed];
}

/**
 * A tool call's output is always a stringified ToolExecutionResult envelope
 * (`{execution_id, success, tool_name, output, error, duration_ms}`) — the
 * tool's actual payload lives one level deeper, under `.output`. Unwrap it
 * before scanning for renderable blocks; fall back to the raw parsed value
 * if it isn't shaped like an envelope (defensive, not expected in practice).
 */
function unwrapEnvelope(parsed: unknown): unknown {
  if (parsed && typeof parsed === 'object' && !Array.isArray(parsed) && 'output' in (parsed as Record<string, unknown>)) {
    const output = (parsed as { output?: unknown }).output;
    if (output && typeof output === 'object') return output;
  }
  return parsed;
}
