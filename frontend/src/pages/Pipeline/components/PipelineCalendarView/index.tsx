import { useMemo, useState } from 'react';
import {
  addDays,
  addMonths,
  format,
  isSameDay,
  isSameMonth,
  startOfMonth,
  startOfWeek,
  subMonths,
} from 'date-fns';
import { CalendarDays, ChevronLeft, ChevronRight, X } from 'lucide-react';
import { getEntityPrimaryValue } from '@/shared/utils/entityDisplay';
import type { FormSchema } from '@/core/types';
import type { PipelineListEntity, PipelineViewModel } from '@/shared/types/pipeline';
import { cn } from '@/lib/utils';
import { bucketEntitiesByDueDate } from '../../utils/dueDate';
import PipelineListToolbar from '../PipelineListView/PipelineListToolbar';
import { usePipelineList } from '../PipelineListView/usePipelineList';

// ponytail: fixed v1 density cap; make responsive if compact calendars need more room.
const MAX_VISIBLE_PER_DAY = 3;
const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

interface PipelineCalendarViewProps {
  model: PipelineViewModel;
  entities: PipelineListEntity[];
  /** The entity type's live form config, same source the Table view uses. */
  entitySchemas?: FormSchema[];
  onEntityClick?: (entityId: string) => void;
}

export default function PipelineCalendarView({
  model,
  entities,
  entitySchemas,
  onEntityClick,
}: PipelineCalendarViewProps) {
  const [month, setMonth] = useState(() => startOfMonth(new Date()));
  const [expandedDay, setExpandedDay] = useState<string | null>(null);
  const {
    search,
    setSearch,
    stateFilter,
    setStateFilter,
    identifierFilter,
    setIdentifierFilter,
    identifierOptions,
    filtered,
  } = usePipelineList(model, entities, {
    entitySchemas,
    // This view shows no columns — it must never rewrite the Table's selection.
    ownsColumnSelection: false,
  });

  const days = useMemo(() => {
    const first = startOfWeek(startOfMonth(month), { weekStartsOn: 0 });
    return Array.from({ length: 42 }, (_, index) => addDays(first, index));
  }, [month]);

  const { byDay, unscheduled } = useMemo(
    () => bucketEntitiesByDueDate(filtered),
    [filtered],
  );

  return (
    <div className="min-w-[850px] overflow-hidden rounded-xl border border-border/80 bg-card shadow-crisp">
      <PipelineListToolbar
        title="Calendar"
        icon={<CalendarDays className="h-4 w-4" />}
        filteredCount={filtered.length}
        totalCount={entities.length}
        entityType={model.entityType}
        search={search}
        onSearchChange={setSearch}
        stateFilter={stateFilter}
        onStateFilterChange={setStateFilter}
        states={model.states}
        identifierFilter={identifierFilter}
        onIdentifierFilterChange={setIdentifierFilter}
        identifierOptions={identifierOptions}
      />
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setMonth(startOfMonth(new Date()))}
            className="rounded-md border border-border bg-background px-3 py-1.5 text-sm font-medium hover:bg-muted"
          >
            Today
          </button>
          <div className="flex items-center">
            <button
              type="button"
              aria-label="Previous month"
              onClick={() => setMonth((current) => subMonths(current, 1))}
              className="rounded-md p-2 text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <button
              type="button"
              aria-label="Next month"
              onClick={() => setMonth((current) => addMonths(current, 1))}
              className="rounded-md p-2 text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
          <h2 className="min-w-40 text-base font-semibold text-foreground">{format(month, 'MMMM yyyy')}</h2>
        </div>

        <div className="flex items-center gap-2">
          <span className="rounded-full bg-muted px-2.5 py-1 text-xs font-medium text-muted-foreground">
            {unscheduled} unscheduled
          </span>
          <span className="inline-flex h-9 items-center gap-2 rounded-md border border-border bg-background px-3 text-sm font-medium text-foreground">
            <CalendarDays className="h-4 w-4 text-muted-foreground" />
            Due date
          </span>
        </div>
      </div>

      <div className="grid grid-cols-7 border-b border-border bg-muted/35">
        {WEEKDAYS.map((weekday) => (
          <div key={weekday} className="px-2 py-2 text-center text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            {weekday}
          </div>
        ))}
      </div>

      <div className="grid grid-cols-7">
        {days.map((day, index) => {
          const key = format(day, 'yyyy-MM-dd');
          const scheduled = byDay.get(key) ?? [];
          const visible = scheduled.slice(0, MAX_VISIBLE_PER_DAY);
          const overflow = scheduled.length - visible.length;
          const isToday = isSameDay(day, new Date());

          return (
            <div
              key={key}
              className={cn(
                'relative min-h-32 border-b border-r border-border p-1.5',
                index % 7 === 6 && 'border-r-0',
                !isSameMonth(day, month) && 'bg-muted/25',
              )}
            >
              <div className="mb-1 flex h-7 items-center">
                <span
                  className={cn(
                    'flex h-7 w-7 items-center justify-center rounded-full text-xs font-medium',
                    isToday && 'bg-primary text-primary-foreground',
                    !isToday && isSameMonth(day, month) && 'text-foreground',
                    !isToday && !isSameMonth(day, month) && 'text-muted-foreground/50',
                  )}
                >
                  {format(day, 'd')}
                </span>
              </div>

              <div className="space-y-1">
                {visible.map(({ entity }) => {
                  const state = model.stateById.get(entity.current_state);
                  return (
                    <button
                      key={entity.entity_id}
                      type="button"
                      title={getEntityPrimaryValue(entity.data, entity.entity_id)}
                      onClick={() => onEntityClick?.(entity.entity_id)}
                      className={cn(
                        'flex w-full items-center gap-1.5 rounded-md border px-1.5 py-1 text-left text-[11px] font-medium hover:brightness-95',
                        state?.accent.soft ?? 'bg-muted/60',
                        state?.accent.border ?? 'border-border',
                        state?.accent.text ?? 'text-foreground',
                      )}
                    >
                      <span className={cn('h-1.5 w-1.5 shrink-0 rounded-full', state?.accent.dot ?? 'bg-muted-foreground')} />
                      <span className="truncate">{getEntityPrimaryValue(entity.data, entity.entity_id)}</span>
                    </button>
                  );
                })}

                {overflow > 0 && (
                  <button
                    type="button"
                    onClick={() => setExpandedDay(key)}
                    className="px-1 text-xs font-medium text-muted-foreground hover:text-foreground"
                  >
                    +{overflow} more
                  </button>
                )}
              </div>

              {expandedDay === key && (
                <div className="absolute left-1 right-1 top-9 z-20 rounded-lg border border-border bg-popover p-2 shadow-lg">
                  <div className="mb-2 flex items-center justify-between">
                    <span className="text-xs font-semibold text-foreground">{format(day, 'EEEE, MMMM d')}</span>
                    <button type="button" aria-label="Close day events" onClick={() => setExpandedDay(null)} className="rounded p-0.5 hover:bg-muted">
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </div>
                  <div className="max-h-48 space-y-1 overflow-y-auto">
                    {scheduled.map(({ entity }) => (
                      <button
                        key={entity.entity_id}
                        type="button"
                        onClick={() => {
                          setExpandedDay(null);
                          onEntityClick?.(entity.entity_id);
                        }}
                        className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs hover:bg-muted"
                      >
                        <span className="truncate font-medium text-foreground">{getEntityPrimaryValue(entity.data, entity.entity_id)}</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
