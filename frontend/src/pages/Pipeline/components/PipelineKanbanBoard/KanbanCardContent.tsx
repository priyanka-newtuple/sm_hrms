import type { ReactNode } from 'react';
import { Clock } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { DemoEntityCard } from '@/shared/types/pipeline';
import type { ColumnField } from '../PipelineListView/types';
import { formatCardFieldValue } from '../../utils/cardFieldValue';
import EntityThumbnail from './EntityThumbnail';
import DueDateBadge from '../DueDateBadge';

interface KanbanCardContentProps {
  entity: DemoEntityCard;
  inState: string | null;
  /** Slot rendered between the header and time-in-state footer (e.g. assignee row). */
  children?: ReactNode;
  /** Up to 3 admin-configured extra entity fields to show on this card
   *  (see useCardFieldsConfig). A field with an empty value is skipped
   *  entirely rather than rendered as a blank chip. */
  cardFields?: ColumnField[];
}

/** Shared thumbnail → title/subtitle header and time-in-state footer used by both
 *  DefaultKanbanCard and DefaultOverlayCard. */
export function KanbanCardContent({ entity, inState, children, cardFields }: KanbanCardContentProps) {
  return (
    <>
      <div className="flex items-center gap-3">
        {entity.thumbnailUrl && <EntityThumbnail url={entity.thumbnailUrl} />}
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-foreground">{entity.title}</p>
          <p className="mt-0.5 truncate text-xs text-muted-foreground">{entity.subtitle}</p>
        </div>
      </div>
      {children}
      {cardFields && cardFields.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          {cardFields.map((field) => {
            const rendered = formatCardFieldValue(field, entity.data?.[field.field]);
            if (rendered === null) return null;
            const Icon = rendered.icon;
            return (
              <span
                key={field.field}
                title={`${field.label}: ${rendered.text}`}
                className="inline-flex max-w-[8rem] items-center gap-1 truncate rounded-full border border-border/70 bg-muted/50 px-2 py-0.5 text-[11px] font-medium text-foreground"
              >
                {rendered.dotClassName && (
                  <span aria-hidden="true" className={cn('size-1.5 shrink-0 rounded-full', rendered.dotClassName)} />
                )}
                {Icon && <Icon className="h-3 w-3 shrink-0 text-muted-foreground" />}
                <span className="truncate">{rendered.text}</span>
              </span>
            );
          })}
        </div>
      )}
      {entity.dueDate && <div className="mt-2"><DueDateBadge value={entity.dueDate} /></div>}
      {inState && (
        <div className="mt-3 flex items-center border-t border-border pt-2">
          <span className="inline-flex items-center gap-1 text-[11px] font-medium text-muted-foreground">
            <Clock className="h-3 w-3" />
            {inState} in state
          </span>
        </div>
      )}
    </>
  );
}
