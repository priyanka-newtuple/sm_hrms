import { useCallback, useMemo, useState } from 'react';
import type { DragEndEvent, DragOverEvent, DragStartEvent } from '@dnd-kit/core';
import { toast } from 'sonner';

import { transitions } from '@/core/services/api';
import { getApiErrorMessage } from '@/core/services/api/client';
import type { PipelineViewModel } from '@/shared/types/pipeline';

interface UsePipelineDragControllerParams {
  model: PipelineViewModel | null;
  patchEntityState: (entityId: string, fromStateId: string, toStateId: string, workflowId?: string) => void;
  onTransitionCommitted: () => void;
}

interface PipelineDragController {
  activeEntityId: string | null;
  activeStateId: string | null;
  hoveredStateId: string | null;
  invalidStateId: string | null;
  allowedTargetIds: Set<string>;
  onDragStart: (event: DragStartEvent) => void;
  onDragOver: (event: DragOverEvent) => void;
  onDragEnd: (event: DragEndEvent) => Promise<void>;
}

const INVALID_FLASH_MS = 1200;

export function usePipelineDragController({
  model,
  patchEntityState,
  onTransitionCommitted,
}: UsePipelineDragControllerParams): PipelineDragController {
  const [activeEntityId, setActiveEntityId] = useState<string | null>(null);
  const [activeStateId, setActiveStateId] = useState<string | null>(null);
  const [hoveredStateId, setHoveredStateId] = useState<string | null>(null);
  const [invalidStateId, setInvalidStateId] = useState<string | null>(null);

  const allowedTargetIds = useMemo(() => {
    if (!activeStateId || !model) return new Set<string>();
    return new Set(
      model.transitions
        .filter((t) => t.sourceId === activeStateId)
        .map((t) => t.targetId),
    );
  }, [activeStateId, model]);

  const flashInvalid = useCallback((stateId: string) => {
    setInvalidStateId(stateId);
    window.setTimeout(
      () => setInvalidStateId((current) => (current === stateId ? null : current)),
      INVALID_FLASH_MS,
    );
  }, []);

  const onDragStart = useCallback((event: DragStartEvent) => {
    setActiveEntityId(String(event.active.data.current?.entityId ?? event.active.id));
    setActiveStateId((event.active.data.current?.stateId as string | undefined) ?? null);
    setHoveredStateId(null);
    setInvalidStateId(null);
  }, []);

  const onDragOver = useCallback((event: DragOverEvent) => {
    setHoveredStateId(event.over?.id ? String(event.over.id) : null);
  }, []);

  const onDragEnd = useCallback(
    async (event: DragEndEvent) => {
      const entityId = String(event.active.data.current?.entityId ?? event.active.id);
      const workflowId = event.active.data.current?.workflowId as string | undefined;
      const sourceStateId = (event.active.data.current?.stateId as string | undefined) ?? null;
      const targetStateId = event.over?.id ? String(event.over.id) : null;

      setActiveEntityId(null);
      setActiveStateId(null);
      setHoveredStateId(null);

      if (!sourceStateId || !targetStateId || targetStateId === sourceStateId) {
        setInvalidStateId(null);
        return;
      }

      const matching = model?.transitions.find(
        (t) => t.sourceId === sourceStateId && t.targetId === targetStateId,
      );

      if (!matching) {
        flashInvalid(targetStateId);
        return;
      }

      setInvalidStateId(null);
      patchEntityState(entityId, sourceStateId, targetStateId, workflowId);

      try {
        await transitions.execute(entityId, {
          entity_id: entityId,
          ...(workflowId ? { workflow_id: workflowId } : {}),
          trigger: matching.trigger,
          idempotency_key: `${entityId}-${workflowId ?? 'primary'}-${matching.trigger}-${Date.now()}`,
        });
        onTransitionCommitted();
      } catch (e) {
        patchEntityState(entityId, targetStateId, sourceStateId, workflowId);
        const is403 = (e as { status?: number }).status === 403;
        const description = is403
          ? `You don't have permission to move records to "${matching.targetLabel}".`
          : getApiErrorMessage(e, `Could not move record to "${matching.targetLabel}".`);
        toast.error('Transition failed', { description });
        flashInvalid(targetStateId);
      }
    },
    [flashInvalid, model, onTransitionCommitted, patchEntityState],
  );

  return {
    activeEntityId,
    activeStateId,
    hoveredStateId,
    invalidStateId,
    allowedTargetIds,
    onDragStart,
    onDragOver,
    onDragEnd,
  };
}
