import { ArrowRight } from 'lucide-react';
import type { User } from '@/core/types';
import { humanize, resolveStateLabel } from '@/shared/utils/labels';
import { linkify } from '@/shared/utils/linkify';
import type { TimelineEvent } from './useActivityTimeline';
import { resolveAssigneeName } from './utils';

interface EventSublineProps {
  event: TimelineEvent;
  orgUsers: User[];
}

/** Renders the secondary detail line (actor, state chips, assignee names) for an activity row. */
export default function EventSubline({ event, orgUsers }: EventSublineProps): React.ReactElement {
  const actor = event.actorName ?? 'System';

  switch (event.kind) {
    case 'transition_succeeded':
      return (
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-xs text-muted-foreground">{actor}</span>
          <span className="text-muted-foreground/40">·</span>
          <span className="inline-flex items-center rounded-full border border-border bg-muted px-2 py-0.5 text-[10px] font-semibold tracking-wide text-muted-foreground">
            {event.fromState ? resolveStateLabel(event.fromState) : '—'}
          </span>
          <ArrowRight className="h-3 w-3 text-muted-foreground" />
          <span className="inline-flex items-center rounded-full border border-cobalt/20 bg-cobalt/8 px-2 py-0.5 text-[10px] font-semibold tracking-wide text-cobalt">
            {event.toState ? resolveStateLabel(event.toState) : '—'}
          </span>
        </div>
      );
    case 'transition_blocked':
      return (
        <span className="text-xs text-muted-foreground">
          {actor}{event.trigger ? ` · ${humanize(event.trigger)}` : ''}
        </span>
      );
    case 'assignee_changed': {
      const prevName = resolveAssigneeName(event.previousAssigneeId, orgUsers);
      const newName = resolveAssigneeName(event.newAssigneeId, orgUsers);
      return <span className="text-xs text-muted-foreground">{prevName} → {newName}</span>;
    }
    case 'action_started': {
      // Manual re-runs carry the requesting user in metadata; name it when we can.
      if (event.triggerSource === 'manual_rerun') {
        const byName = event.triggeredById
          ? resolveAssigneeName(event.triggeredById, orgUsers)
          : actor;
        return <span className="text-xs text-muted-foreground">Re-run by {byName}</span>;
      }
      return <span className="text-xs text-muted-foreground">{actor}</span>;
    }
    case 'action_completed':
    case 'action_refused':
      // What the action reports it did. For a refusal this is the whole point
      // of the entry — the headline says nothing changed, this says why.
      return (
        <span className="text-xs text-muted-foreground">
          {actor}{event.outcomeMessage ? <>{' · '}{linkify(event.outcomeMessage, 'outcome')}</> : ''}
        </span>
      );
    case 'action_failed':
    case 'action_retry_scheduled':
      return (
        <span className="text-xs text-muted-foreground">
          {actor}{event.errorMessage ? <>{' · '}{linkify(event.errorMessage, 'err')}</> : ''}
        </span>
      );
    case 'action_chain_skipped':
    case 'action_chain_stopped':
      return (
        <span className="text-xs text-muted-foreground">
          {event.chainReason != null ? linkify(event.chainReason, 'chain') : actor}
        </span>
      );
    default:
      return <span className="text-xs text-muted-foreground">{actor}</span>;
  }
}
