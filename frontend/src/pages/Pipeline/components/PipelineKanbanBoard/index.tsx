import {
  DndContext,
  DragOverlay,
  MouseSensor,
  PointerSensor,
  TouchSensor,
  type DragEndEvent,
  type DragOverEvent,
  type DragStartEvent,
  useSensor,
  useSensors,
} from '@dnd-kit/core';
import { useMemo, useState } from 'react';
import { LayoutGrid } from 'lucide-react';
import Card from '@/core/components/Card';
import { cn } from '@/lib/utils';
import type { PipelineViewModel } from '@/shared/types/pipeline';
import { useSkin } from '@/skins';
import { useWorkflowColumnEntities, type WorkflowColumnFilters } from '../../hooks/useWorkflowColumnEntities';
import { useWorkflowStateCounts } from '../../hooks/useWorkflowStateCounts';
import { toDemoCard } from '../../hooks/usePipelineBoardData';
import EntityCardOverlay from './EntityCardOverlay';
import StateColumn from './StateColumn';
import BulkActionBar from './BulkActionBar';
import { useBulkEntityActions } from '../../hooks/useBulkEntityActions';
import type { ColumnField } from '../PipelineListView/types';

export interface PipelineKanbanBoardProps {
  machineName: string;
  filters: WorkflowColumnFilters;
  model: PipelineViewModel;
  activeEntityId: string | null;
  activeStateId: string | null;
  hoveredStateId: string | null;
  invalidStateId: string | null;
  allowedTargetIds: Set<string>;
  onDragStart: (event: DragStartEvent) => void;
  onDragOver: (event: DragOverEvent) => void;
  onDragEnd: (event: DragEndEvent) => void;
  onEntityClick: (entityId: string, workflowId?: string) => void;
  canDelete: boolean;
  onBulkMutationCommitted: () => void;
  /** Singular label for the entity type shown in the board subtitle (e.g. "candidate"). */
  entityLabel?: string;
  /** Up to 3 admin-configured extra entity fields shown on every card. */
  cardFields?: ColumnField[];
}

function ActiveEntityOverlay({
  machineName,
  filters,
  activeStateId,
  activeEntityId,
  cardFields,
}: {
  machineName: string;
  filters: WorkflowColumnFilters;
  activeStateId: string | null;
  activeEntityId: string | null;
  cardFields?: ColumnField[];
}) {
  // The active column is always already mounted (you can only drag a card
  // that's rendered), so its own hook instance's cache already holds it —
  // this second instance reads the same cache entry, no extra fetch.
  const { items } = useWorkflowColumnEntities(machineName, activeStateId ?? '', filters);
  const active = activeEntityId ? items.find((e) => e.entity_id === activeEntityId) : undefined;
  if (!active) return null;
  return <EntityCardOverlay entity={toDemoCard(active)} cardFields={cardFields} />;
}

export default function PipelineKanbanBoard({
  machineName,
  filters,
  model,
  activeEntityId,
  activeStateId,
  hoveredStateId,
  invalidStateId,
  allowedTargetIds,
  onDragStart,
  onDragOver,
  onDragEnd,
  onEntityClick,
  canDelete,
  onBulkMutationCommitted,
  entityLabel = 'entity',
  cardFields,
}: PipelineKanbanBoardProps) {
  const { skin } = useSkin();
  const [selectedStateId, setSelectedStateId] = useState<string | null>(null);
  const bulk = useBulkEntityActions({ onCommitted: onBulkMutationCommitted });
  const { counts } = useWorkflowStateCounts(machineName, filters);
  const kanbanStates = useMemo(() => {
    const allowed = skin.board.displayStates
      ? new Set(skin.board.displayStates)
      : null;
    return [...model.states]
      .filter((s) => !allowed || allowed.has(s.name))
      .sort(
        (a, b) =>
          Number(a.isTerminal) - Number(b.isTerminal) ||
          a.flowRank - b.flowRank ||
          a.order - b.order ||
          a.label.localeCompare(b.label),
      );
  }, [model.states, skin.board.displayStates]);
  const columnCount = kanbanStates.length;
  const totalEntities = kanbanStates.reduce((sum, s) => sum + (counts[s.name] ?? 0), 0);
  const sensors = useSensors(
    useSensor(MouseSensor, { activationConstraint: { distance: 8 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 200, tolerance: 8 } }),
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
  );

  const isGridLayout = skin.board.boardLayout === 'grid';
  const boardBody = (
    <>
      {!skin.board.hideBoardMeta && (
          <div className="shrink-0 border-b border-border px-5 py-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                <LayoutGrid className="h-4 w-4 text-cobalt" />
                Workflow board
                <span className="text-muted-foreground/60">·</span>
                <span className="text-xs font-normal text-muted-foreground">
                  {columnCount} columns · {totalEntities}{' '}
                  {totalEntities === 1 ? entityLabel : `${entityLabel}s`}
                </span>
              </div>
              {activeEntityId && (
                <div className="rounded-full border border-cobalt/15 bg-cobalt/5 px-3 py-1 text-[11px] font-medium text-cobalt">
                  Allowed targets highlighted. Invalid targets turn red.
                </div>
              )}
            </div>
          </div>
        )}

        <BulkActionBar
          selected={bulk.selected}
          model={model}
          canDelete={canDelete}
          busy={bulk.busy}
          onClear={bulk.clear}
          onTransition={bulk.transition}
          onDelete={bulk.remove}
        />

        <div
          className={
            isGridLayout
              ? 'min-h-0 flex-1 overflow-y-auto xl:overflow-visible'
              : 'min-h-0 flex-1 overflow-x-auto px-5 py-5'
          }
        >
          <div
            className={cn(
              isGridLayout ? 'grid h-full min-h-0' : 'flex h-full min-w-max items-stretch',
              skin.board.columnGapClassName ?? 'gap-4',
            )}
            style={isGridLayout ? { gridTemplateColumns: `repeat(${columnCount}, minmax(0, 1fr))`, gridAutoRows: '1fr' } : undefined}
          >
            {kanbanStates.map((state, index) => (
              <StateColumn
                key={state.id}
                machineName={machineName}
                filters={filters}
                state={state}
                displayOrder={index + 1}
                totalInState={counts[state.name] ?? 0}
                isStateSelected={selectedStateId === state.id}
                onSelectState={setSelectedStateId}
                activeEntityId={activeEntityId}
                hoveredStateId={hoveredStateId}
                invalidStateId={invalidStateId}
                allowedTargetIds={allowedTargetIds}
                onEntityClick={onEntityClick}
                selectedEntityIds={bulk.selectedIds}
                onEntitySelectedChange={bulk.setSelected}
                cardFields={cardFields}
              />
            ))}
          </div>
        </div>
    </>
  );

  return (
    <DndContext sensors={sensors} onDragStart={onDragStart} onDragOver={onDragOver} onDragEnd={onDragEnd}>
      {skin.board.boardChrome === 'plain' ? (
        <div className="flex h-full min-h-0 flex-1 flex-col overflow-hidden">{boardBody}</div>
      ) : (
        <Card className="flex h-full min-h-0 flex-1 flex-col overflow-hidden border border-border bg-card/90 shadow-sm" padding="none">
          {boardBody}
        </Card>
      )}
      <DragOverlay dropAnimation={null}>
        <ActiveEntityOverlay
          machineName={machineName}
          filters={filters}
          activeStateId={activeStateId}
          activeEntityId={activeEntityId}
          cardFields={cardFields}
        />
      </DragOverlay>
    </DndContext>
  );
}
