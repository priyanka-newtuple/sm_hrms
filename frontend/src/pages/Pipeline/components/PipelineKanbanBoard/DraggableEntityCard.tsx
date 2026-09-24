import { useCallback } from 'react';
import { useDraggable } from '@dnd-kit/core';
import { User } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { DemoEntityCard } from '@/shared/types/pipeline';
import { useSkin } from '@/skins/SkinContext';
import { ComponentSlot } from '@/core/componentRegistry';
import { getEntityThumbnailUrl } from '@/core/services/api';
import { Checkbox } from '@/components/ui/checkbox';
import type { ColumnField } from '../PipelineListView/types';
import { formatRelative } from './utils';
import { KanbanCardContent } from './KanbanCardContent';

interface DraggableEntityCardProps {
  entity: DemoEntityCard;
  onEntityClick: (entityId: string, workflowId?: string) => void;
  selected?: boolean;
  onSelectedChange?: (selected: boolean) => void;
  cardFields?: ColumnField[];
}

export default function DraggableEntityCard({ entity, onEntityClick, selected = false, onSelectedChange, cardFields }: DraggableEntityCardProps) {
  const { skin } = useSkin();
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: entity.enrollmentId ?? `${entity.id}:${entity.workflowId ?? 'unenrolled'}`,
    data: {
      type: 'entity',
      entityId: entity.id,
      workflowId: entity.workflowId,
      stateId: entity.stateId,
    },
  });

  const handleClick = () => onEntityClick(entity.id, entity.workflowId);
  const inState = formatRelative(entity.stateEnteredAt);
  const kanbanCardSlot = skin.components?.['kanban-card'];
  const thumbnailDataField = skin.board.thumbnailDataField;
  const onRefreshThumbnail = useCallback(async (): Promise<string | null> => {
    if (!thumbnailDataField) return null;
    return getEntityThumbnailUrl(entity.id, thumbnailDataField);
  }, [entity.id, thumbnailDataField]);

  return (
    <div
      ref={setNodeRef}
      {...listeners}
      {...attributes}
      className={cn('group relative cursor-grab active:cursor-grabbing', isDragging && 'opacity-40')}
    >
      {onSelectedChange && (
        <div
          className={cn(
            'absolute right-2 top-2 z-10 rounded-md bg-card/95 p-1 shadow-sm transition-opacity',
            selected ? 'opacity-100' : 'opacity-0 group-hover:opacity-100 group-focus-within:opacity-100',
          )}
          onPointerDown={(event) => event.stopPropagation()}
          onClick={(event) => event.stopPropagation()}
        >
          <Checkbox
            checked={selected}
            onCheckedChange={(checked) => onSelectedChange(checked === true)}
            aria-label={`Select ${entity.title}`}
          />
        </div>
      )}
      <ComponentSlot
        slotName="kanban-card"
        component={kanbanCardSlot}
        slotProps={{ entity, onPress: handleClick, isDragging, onRefreshThumbnail }}
        fallback={
          <DefaultKanbanCard
            entity={entity}
            inState={inState}
            onPress={handleClick}
            cardFields={cardFields}
          />
        }
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Default card — rendered when the skin does not provide a 'kanban-card' slot
// ---------------------------------------------------------------------------

interface DefaultKanbanCardProps {
  entity: DemoEntityCard;
  inState: string | null;
  onPress: () => void;
  cardFields?: ColumnField[];
}

function DefaultKanbanCard({ entity, inState, onPress, cardFields }: DefaultKanbanCardProps) {
  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        onPress();
      }}
      className="w-full rounded-xl border border-border bg-card px-4 py-3 text-left transition-all hover:border-cobalt/40 hover:shadow-sm"
    >
      <KanbanCardContent entity={entity} inState={inState} cardFields={cardFields}>
        <div className="mt-2 flex items-center gap-1 text-[11px] text-muted-foreground">
          <User className="h-3 w-3 shrink-0" />
          <span className={cn('truncate', !entity.assigneeName && 'text-muted-foreground')}>
            {entity.assigneeName || 'Unassigned'}
          </span>
        </div>
      </KanbanCardContent>
    </button>
  );
}
