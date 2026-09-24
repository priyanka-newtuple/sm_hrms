import { useMemo, useState } from 'react';
import { ArrowRight, Trash2, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import ConfirmDialog from '@/core/components/ConfirmDialog';
import type { PipelineTransitionEdge, PipelineViewModel } from '@/shared/types/pipeline';
import type { BulkActionEntity } from '../../hooks/useBulkEntityActions';

interface BulkActionBarProps {
  selected: BulkActionEntity[];
  model: PipelineViewModel;
  canDelete: boolean;
  busy: boolean;
  onClear: () => void;
  onTransition: (transition: PipelineTransitionEdge) => Promise<void>;
  onDelete: () => Promise<void>;
}

function canUseTransition(entity: BulkActionEntity, transition: PipelineTransitionEdge): boolean {
  if (entity.current_state !== transition.sourceId) return false;
  if (!entity.transition_options?.length) return true;
  const option = entity.transition_options.find(
    (item) => item.trigger === transition.trigger && item.to_state === transition.targetId,
  );
  if (!option || option.availability_known === false) return false;
  return option.allowed ?? option.all_guards_passed ?? true;
}

export default function BulkActionBar({ selected, model, canDelete, busy, onClear, onTransition, onDelete }: BulkActionBarProps) {
  const [transitionId, setTransitionId] = useState('');
  const [confirmDelete, setConfirmDelete] = useState(false);
  const commonTransitions = useMemo(
    () => model.transitions.filter((transition) => selected.every((entity) => canUseTransition(entity, transition))),
    [model.transitions, selected],
  );
  const transition = commonTransitions.find((item) => item.id === transitionId);

  if (!selected.length) return null;
  return (
    <>
      <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-cobalt/15 bg-cobalt/5 px-5 py-2.5">
        <span className="text-sm font-semibold text-cobalt">{selected.length} selected</span>
        <button type="button" onClick={onClear} disabled={busy} className="rounded-md p-1 text-muted-foreground hover:bg-card" aria-label="Clear selection">
          <X className="h-4 w-4" />
        </button>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <select
            value={transitionId}
            onChange={(event) => setTransitionId(event.target.value)}
            disabled={busy || commonTransitions.length === 0}
            aria-label="Bulk transition"
            className="h-9 min-w-48 rounded-lg border border-border bg-card px-3 text-sm outline-none focus:border-cobalt/40"
          >
            <option value="">{commonTransitions.length ? 'Choose transition…' : 'No common transitions'}</option>
            {commonTransitions.map((item) => <option key={item.id} value={item.id}>{item.label} → {item.targetLabel}</option>)}
          </select>
          <Button size="sm" disabled={!transition || busy} icon={<ArrowRight />} onClick={() => transition && void onTransition(transition)}>
            Transition
          </Button>
          {canDelete && (
            <Button variant="danger" size="sm" disabled={busy} icon={<Trash2 />} onClick={() => setConfirmDelete(true)}>
              Delete
            </Button>
          )}
        </div>
      </div>
      <ConfirmDialog
        open={confirmDelete}
        onClose={() => !busy && setConfirmDelete(false)}
        onConfirm={() => void onDelete().then(() => setConfirmDelete(false))}
        title={`Delete ${selected.length} ${selected.length === 1 ? 'entity' : 'entities'}?`}
        message="This permanently deletes the selected entities and their workflow history. This action cannot be undone."
        confirmLabel={`Delete ${selected.length}`}
        variant="danger"
        loading={busy}
      />
    </>
  );
}
