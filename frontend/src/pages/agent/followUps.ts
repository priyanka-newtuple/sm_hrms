import type { CanvasItem } from './useAgentCanvas';

export interface FollowUp {
  id: string;
  label: string;
  prompt: string;
}

/**
 * Derive contextual follow-up chips from what the agent has most recently
 * rendered on the canvas — so the user can extend the conversation in one click
 * with only actions the agent can actually perform right now (render the same
 * data a different way, drill in, or pivot to the dashboard). Falls back to a
 * small generic set when nothing renderable is on the canvas yet.
 */
export function deriveFollowUps(items: CanvasItem[]): FollowUp[] {
  const last = [...items].reverse().find((i) => i.kind === 'component');
  const out: FollowUp[] = [];
  const push = (id: string, label: string, prompt: string) => {
    if (!out.some((f) => f.id === id)) out.push({ id, label, prompt });
  };

  if (last && last.kind === 'component') {
    const props = last.props as {
      view?: string;
      summary?: { workflow_name?: string; by_state?: Record<string, number> };
      entityType?: string;
    };
    const name = props.summary?.workflow_name;

    if (last.component === 'pipeline_board' || last.component === 'pipeline_list' || last.component === 'pipeline_calendar') {
      const subject = name ? `the ${name} pipeline` : 'this pipeline';
      if (last.component !== 'pipeline_list') push('as-list', 'View as list', `Show ${subject} as a list`);
      if (last.component !== 'pipeline_calendar') push('as-calendar', 'View as calendar', `Show ${subject} as a calendar`);
      if (last.component !== 'pipeline_board') push('as-board', 'View as board', `Show ${subject} as a board`);
      // Offer to focus a busy state, if we know the distribution.
      const byState = props.summary?.by_state ?? {};
      const busiest = Object.entries(byState).sort((a, b) => b[1] - a[1])[0]?.[0];
      if (busiest) push('in-state', `Only ${busiest}`, `Show ${subject} entities in the ${busiest} stage`);
      push('overview', 'Show the dashboard', 'Show me the dashboard');
    } else if (last.component === 'dashboard' || last.component === 'dashboard_widget' || last.component === 'stat_tile') {
      push('board', 'Show a pipeline board', 'Show me the pipeline board');
      push('count', 'Total candidates', 'How many candidates do we have right now?');
      push('sla', 'SLA breaches', 'Show me the SLA breaches');
      push('workflows', 'List workflows', 'What workflows do we have?');
    } else if (last.component === 'entity_table') {
      const subject = name ? `the ${name} pipeline` : 'this pipeline';
      push('as-board', 'View as board', `Show ${subject} as a board`);
      push('overview', 'Show the dashboard', 'Show me the dashboard');
    }
  }

  if (out.length === 0) {
    push('workflows', 'List workflows', 'What workflows do we have?');
    push('board', 'Show a pipeline board', 'Show me the pipeline board');
    push('overview', 'Show the dashboard', 'Show me the dashboard');
  }

  return out.slice(0, 4);
}
