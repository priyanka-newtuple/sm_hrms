import type { User } from '@/core/types';
import { linkify } from '@/shared/utils/linkify';
import { CHIP_CONFIG } from '../constants';
import type { TimelineEvent } from './useActivityTimeline';
import { relativeTime } from './utils';
import EventHeadline from './EventHeadline';
import EventSubline from './EventSubline';

interface ActivityEventRowProps {
  event: TimelineEvent;
  orgUsers: User[];
  isLast: boolean;
}

/** Renders a single row in the activity timeline feed. */
export default function ActivityEventRow({ event, orgUsers, isLast }: ActivityEventRowProps): React.ReactElement {
  const { chipBg, iconColor, Icon } = CHIP_CONFIG[event.kind];
  const absoluteDatetime = new Date(event.occurredAt).toLocaleString('en-US', {
    dateStyle: 'medium',
    timeStyle: 'short',
  });

  return (
    <div className="flex gap-3">
      <div className="flex flex-col items-center">
        <div className={`h-8 w-8 rounded-full flex items-center justify-center shrink-0 ${chipBg}`}>
          <Icon className={`h-4 w-4 ${iconColor}`} />
        </div>
        {!isLast && <div className="w-px flex-1 bg-border mt-1" />}
      </div>

      <div className="flex-1 pb-5">
        <div className="flex items-start justify-between gap-2">
          <EventHeadline event={event} />
          <span className="text-xs text-muted-foreground shrink-0 whitespace-nowrap" title={absoluteDatetime}>
            {relativeTime(event.occurredAt)}
          </span>
        </div>

        <div className="mt-0.5">
          <EventSubline event={event} orgUsers={orgUsers} />
        </div>

        {event.kind === 'transition_blocked' && (event.blockedReasons?.length ?? 0) > 0 && (
          <div className="mt-1.5 rounded-lg border border-amber/20 bg-amber/10 px-3 py-2">
            {event.blockedReasons!.map((reason: string, i: number) => (
              <p key={i} className="text-xs text-amber leading-relaxed">
                {event.blockedReasons!.length > 1 ? '· ' : ''}
                {linkify(reason, `br${i}`)}
              </p>
            ))}
          </div>
        )}

        {event.kind === 'transition_conflict' && (
          <div className="mt-1.5 rounded-lg border border-rose/20 bg-rose/10 px-3 py-2">
            <p className="text-xs text-rose">
              Another change was made to this record at the same time. The move did not go through.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
