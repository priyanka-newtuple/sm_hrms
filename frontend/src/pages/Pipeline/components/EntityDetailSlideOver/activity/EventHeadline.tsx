import { humanize, resolveStateLabel } from '@/shared/utils/labels';
import { useActionDisplayNames } from '@/shared/hooks';
import type { TimelineEvent } from './useActivityTimeline';

interface EventHeadlineProps {
  event: TimelineEvent;
}

/** ": OpenWeather (2/3)" — name plus chain position when part of a multi-action chain. */
function actionSuffix(
  event: TimelineEvent,
  resolveActionDisplayName: ReturnType<typeof useActionDisplayNames>,
): string {
  const name = event.actionKind
    ? resolveActionDisplayName({ kind: event.actionKind, actionDisplayName: event.actionDisplayName })
    : '';
  const chain =
    event.actionTotal != null && event.actionTotal > 1 && event.actionIndex != null
      ? ` (${event.actionIndex + 1}/${event.actionTotal})`
      : '';
  return `${name ? `: ${name}` : ''}${chain}`;
}

/** Renders the primary headline text for a single activity timeline event. */
export default function EventHeadline({ event }: EventHeadlineProps): React.ReactElement {
  const resolveActionDisplayName = useActionDisplayNames();
  switch (event.kind) {
    case 'transition_succeeded':
      return (
        <p className="text-sm font-medium text-foreground">
          Moved to <span className="font-semibold">{event.toState ? resolveStateLabel(event.toState) : '—'}</span>
        </p>
      );
    case 'transition_blocked':
      return (
        <p className="text-sm font-medium text-foreground">
          Move blocked: {event.fromState ? resolveStateLabel(event.fromState) : '—'} → {event.toState ? resolveStateLabel(event.toState) : '—'}
        </p>
      );
    case 'transition_conflict':
      return <p className="text-sm font-medium text-foreground">Move failed — edit conflict</p>;
    case 'task_executed':
      return (
        <p className="text-sm font-medium text-foreground">
          {event.trigger ? `Task: ${humanize(event.trigger)}` : 'Task'}
        </p>
      );
    case 'entity_created':
      return <p className="text-sm font-medium text-foreground">Record created</p>;
    case 'entity_updated': {
      const n = event.changedFieldCount ?? 0;
      const suffix = n === 0 ? '' : ` · ${n} field${n === 1 ? '' : 's'} changed`;
      return <p className="text-sm font-medium text-foreground">Record updated{suffix}</p>;
    }
    case 'assignee_changed':
      return <p className="text-sm font-medium text-foreground">Assignee changed</p>;
    case 'entity_archived':
      return <p className="text-sm font-medium text-foreground">Record archived</p>;
    case 'entity_restored':
      return <p className="text-sm font-medium text-foreground">Record restored</p>;
    case 'action_started':
      return <p className="text-sm font-medium text-foreground">Action started{actionSuffix(event, resolveActionDisplayName)}</p>;
    case 'action_completed':
      return <p className="text-sm font-medium text-foreground">Action completed{actionSuffix(event, resolveActionDisplayName)}</p>;
    case 'action_refused':
      // Worded generically: any executor can report that it changed nothing.
      // The subline carries the specific reason.
      return <p className="text-sm font-medium text-foreground">Action made no change{actionSuffix(event, resolveActionDisplayName)}</p>;
    case 'action_failed':
      return <p className="text-sm font-medium text-foreground">Action failed{actionSuffix(event, resolveActionDisplayName)}</p>;
    case 'action_retry_scheduled':
      return <p className="text-sm font-medium text-foreground">Action retry scheduled{actionSuffix(event, resolveActionDisplayName)}</p>;
    case 'action_waiting_external':
      return <p className="text-sm font-medium text-foreground">Action awaiting response{actionSuffix(event, resolveActionDisplayName)}</p>;
    case 'action_chain_skipped':
      return <p className="text-sm font-medium text-foreground">Remaining actions skipped</p>;
    case 'action_chain_stopped':
      return <p className="text-sm font-medium text-foreground">Remaining actions stopped</p>;
    default: {
      const _exhaustive: never = event.kind;
      return <p className="text-sm font-medium text-foreground">{_exhaustive}</p>;
    }
  }
}
