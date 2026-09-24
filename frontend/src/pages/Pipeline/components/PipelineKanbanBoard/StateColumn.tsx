import { useDroppable } from '@dnd-kit/core';
import { useEffect, useRef } from 'react';
import { cn } from '@/lib/utils';
import type { PipelineStateNode } from '@/shared/types/pipeline';
import { useSkin, getStateTokens } from '@/skins';
import { ComponentSlot } from '@/core/componentRegistry';
import { toDemoCard } from '../../hooks/usePipelineBoardData';
import { useWorkflowColumnEntities, type WorkflowColumnFilters } from '../../hooks/useWorkflowColumnEntities';
import DraggableEntityCard from './DraggableEntityCard';
import type { WorkflowEntityState } from '@/core/services/api';
import type { ColumnField } from '../PipelineListView/types';

interface StateColumnProps {
  machineName: string;
  filters: WorkflowColumnFilters;
  state: PipelineStateNode;
  displayOrder: number;
  totalInState: number;
  isStateSelected: boolean;
  onSelectState: (stateId: string) => void;
  activeEntityId: string | null;
  hoveredStateId: string | null;
  invalidStateId: string | null;
  allowedTargetIds: Set<string>;
  onEntityClick: (entityId: string, workflowId?: string) => void;
  selectedEntityIds: Set<string>;
  onEntitySelectedChange: (entity: WorkflowEntityState, selected: boolean) => void;
  cardFields?: ColumnField[];
}

export default function StateColumn({
  machineName,
  filters,
  state,
  displayOrder,
  totalInState,
  isStateSelected,
  onSelectState,
  activeEntityId,
  hoveredStateId,
  invalidStateId,
  allowedTargetIds,
  onEntityClick,
  selectedEntityIds,
  onEntitySelectedChange,
  cardFields,
}: StateColumnProps) {
  const { skin } = useSkin();
  const { items, hasNextPage, isFetchingNextPage, fetchNextPage } = useWorkflowColumnEntities(
    machineName,
    state.name,
    filters,
  );
  const sentinelRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const target = sentinelRef.current;
    if (!target || !hasNextPage) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting && hasNextPage && !isFetchingNextPage) {
          void fetchNextPage();
        }
      },
      { rootMargin: '200px' },
    );
    observer.observe(target);
    return () => observer.disconnect();
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  const dragging = activeEntityId !== null;
  const isAllowedTarget = dragging && allowedTargetIds.has(state.id);
  const isInvalidTarget = dragging && hoveredStateId === state.id && !isAllowedTarget;
  const showNeutralDragTarget = dragging && hoveredStateId === state.id && isAllowedTarget;
  const showInvalidDrop = invalidStateId === state.id;

  // Skin color takes precedence over the Tailwind accent fallback.
  const skinColor = skin.board.stateColors[state.name];
  const tokens = skinColor ? getStateTokens(skinColor) : null;
  // columnBackground overrides per-state tinting when the skin wants a uniform column color.
  const columnBg = skin.board.columnBackground ?? tokens?.background ?? undefined;

  const { setNodeRef, isOver } = useDroppable({
    id: state.id,
    data: { type: 'state-column', stateId: state.id },
  });

  const emptyText =
    skin.board.emptyLaneText ?? `No ${state.label.toLowerCase()} entities yet.`;

  return (
    <div
      ref={setNodeRef}
      role="button"
      tabIndex={0}
      onClick={() => onSelectState(state.id)}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          onSelectState(state.id);
        }
      }}
      style={
        // A skin-supplied columnBackground means the skin wants a uniform
        // column color and has opted out of the per-state tinted look —
        // that includes the tinted border, which would otherwise silently
        // win over any border color the skin's own columnClassName sets
        // (inline styles always beat classes).
        skin.board.columnBackground
          ? { backgroundColor: skin.board.columnBackground }
          : tokens
            ? { borderColor: tokens.border, backgroundColor: columnBg }
            : undefined
      }
      className={cn(
        skin.board.columnClassName ?? 'flex h-full min-h-[360px] w-[320px] flex-col rounded-2xl border p-3 text-left transition-all',
        !tokens && !skin.board.columnClassName && 'bg-muted/70',
        !tokens && !skin.board.columnClassName && state.accent.border,
        isStateSelected ? 'ring-2 ring-cobalt/20 shadow-lg' : 'hover:shadow-md',
        dragging && isAllowedTarget && 'border-success/30 bg-success-subtle/60',
        showNeutralDragTarget && 'ring-2 ring-success/30',
        isOver && isAllowedTarget && 'shadow-lg shadow-emerald-100',
        isInvalidTarget && 'border-destructive/30 bg-destructive-subtle/70 ring-2 ring-destructive/30',
        showInvalidDrop && 'border-destructive/30 bg-destructive-subtle/70 ring-2 ring-destructive/30',
      )}
    >
      <ComponentSlot
        slotName="kanban-column-header"
        component={skin.components?.['kanban-column-header']}
        slotProps={{ state, displayOrder, entityCount: totalInState }}
        fallback={
          <div className="flex items-center justify-between gap-2 px-1">
            <div className="flex min-w-0 items-center gap-2">
              <span className="rounded-md border border-border bg-card px-1.5 py-0.5 text-[10px] font-semibold text-muted-foreground">
                #{displayOrder}
              </span>
              {tokens && (
                <span
                  aria-hidden="true"
                  className="size-2 rounded-full flex-shrink-0"
                  style={{ backgroundColor: tokens.dot }}
                />
              )}
              {!tokens && (
                <span
                  aria-hidden="true"
                  className={cn('size-2 rounded-full flex-shrink-0', state.accent.dot)}
                />
              )}
              <h3
                className="truncate text-xs font-semibold tracking-wider"
                style={tokens ? { color: tokens.text } : undefined}
              >
                {state.label}
              </h3>
              <span className="rounded-md bg-accent/70 px-1.5 py-0.5 text-[10px] font-semibold text-muted-foreground">
                {totalInState}
              </span>
              {!skin.board.hideTerminalBadge && state.isInitial && (
                <span className={cn('rounded-md border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider', state.accent.badge)}>
                  Initial
                </span>
              )}
              {!skin.board.hideTerminalBadge && state.isTerminal && (
                <span className={cn('rounded-md border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider', state.accent.badge)}>
                  Terminal
                </span>
              )}
            </div>
          </div>
        }
      />

      {!skin.board.hideTransitionMeta && (
        <div className="mt-2 flex items-center gap-3 border-b border-border/80 px-1 pb-2 text-[11px] text-muted-foreground">
          <span className="inline-flex items-center gap-1">
            <span className="text-muted-foreground">↳ Out</span>
            <span className="font-semibold text-foreground">{state.outgoingCount}</span>
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="text-muted-foreground">→ In</span>
            <span className="font-semibold text-foreground">{state.incomingCount}</span>
          </span>
        </div>
      )}

      <div className={skin.board.columnContentClassName ?? 'mt-2 min-h-0 flex-1 space-y-2 overflow-y-auto pr-1'}>
        {items.length > 0 ? (
          items.map((workflowEntity) => {
            const entity = toDemoCard(workflowEntity);
            return (
            <div
              key={entity.id}
              onClick={(e) => e.stopPropagation()}
              onKeyDown={(e) => e.stopPropagation()}
            >
              <DraggableEntityCard
                entity={entity}
                onEntityClick={onEntityClick}
                selected={selectedEntityIds.has(entity.id)}
                onSelectedChange={(selected) => onEntitySelectedChange(workflowEntity, selected)}
                cardFields={cardFields}
              />
            </div>
            );
          })
        ) : (
          <div
            className={
              skin.board.columnEmptyClassName ??
              'rounded-xl border border-dashed border-border bg-card/60 px-3 py-4 text-center text-[11px] text-muted-foreground'
            }
          >
            {emptyText}
          </div>
        )}
        {hasNextPage && (
          <div ref={sentinelRef} className="py-2 text-center text-[11px] text-muted-foreground">
            {isFetchingNextPage ? 'Loading more…' : ''}
          </div>
        )}
      </div>
    </div>
  );
}
