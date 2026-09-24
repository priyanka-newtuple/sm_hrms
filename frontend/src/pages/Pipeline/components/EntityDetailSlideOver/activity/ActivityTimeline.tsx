import { useEffect, useRef } from 'react';
import type { User } from '@/core/types';
import { useActivityTimeline } from './useActivityTimeline';
import type { TimelineEvent } from './useActivityTimeline';
import { groupByDate } from './utils';
import ActivityEventRow from './ActivityEventRow';

// ── Sub-components ────────────────────────────────────────────────────────────

function DateDivider({ label }: { label: string }): React.ReactElement {
  return (
    <div className="flex items-center gap-3 my-4">
      <div className="flex-1 h-px bg-border" />
      <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground whitespace-nowrap">
        {label}
      </span>
      <div className="flex-1 h-px bg-border" />
    </div>
  );
}

function SkeletonRows(): React.ReactElement {
  return (
    <div className="space-y-4">
      {[0, 1, 2].map((i) => (
        <div key={i} className="flex gap-3 animate-pulse">
          <div className="h-8 w-8 rounded-full bg-muted shrink-0" />
          <div className="flex-1 py-1 space-y-2">
            <div className="h-3.5 bg-muted rounded w-3/5" />
            <div className="h-3 bg-muted rounded w-2/5" />
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Props ─────────────────────────────────────────────────────────────────────

interface ActivityTimelineProps {
  entityId: string;
  orgUsers: User[];
}

// ── Component ─────────────────────────────────────────────────────────────────

/** Infinite-scrolling activity feed combining entity events and workflow transitions. */
export default function ActivityTimeline({ entityId, orgUsers }: ActivityTimelineProps): React.ReactElement {
  const { timeline, isLoading, isError, hasMore, isFetchingMore, fetchMore, refetch } =
    useActivityTimeline(entityId);

  const sentinelRef = useRef<HTMLDivElement>(null);
  const isFetchingMoreRef = useRef(isFetchingMore);
  const fetchMoreRef = useRef(fetchMore);
  isFetchingMoreRef.current = isFetchingMore;
  fetchMoreRef.current = fetchMore;

  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && !isFetchingMoreRef.current) {
          fetchMoreRef.current();
        }
      },
      { rootMargin: '200px' }
    );

    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [hasMore]);

  if (isLoading) return <SkeletonRows />;

  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center py-16 gap-2">
        <p className="text-sm text-muted-foreground">Could not load activity</p>
        <button onClick={refetch} className="text-xs text-cobalt underline">
          Try again
        </button>
      </div>
    );
  }

  if (timeline.length === 0) {
    return (
      <div className="flex items-center justify-center py-16 text-sm text-muted-foreground">
        No activity recorded yet
      </div>
    );
  }

  const groups = groupByDate(timeline);

  return (
    <div className="py-2">
      {groups.map(({ label, events: groupEvents }: { label: string; events: TimelineEvent[] }, groupIdx: number) => (
        <div key={label}>
          <DateDivider label={label} />
          {groupEvents.map((event: TimelineEvent, eventIdx: number) => (
            <ActivityEventRow
              key={event.id}
              event={event}
              orgUsers={orgUsers}
              isLast={
                groupIdx === groups.length - 1 &&
                eventIdx === groupEvents.length - 1 &&
                !hasMore
              }
            />
          ))}
        </div>
      ))}

      <div ref={sentinelRef} className="h-px" />

      {isFetchingMore && (
        <div className="flex justify-center py-4">
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-cobalt border-t-transparent" />
        </div>
      )}

      {!hasMore && (
        <div className="flex items-center justify-center py-4 text-xs text-muted-foreground">
          All activity loaded
        </div>
      )}
    </div>
  );
}
