import type { DemoEntityCard } from '@/shared/types/pipeline';
import { useSkin } from '@/skins/SkinContext';
import { ComponentSlot } from '@/core/componentRegistry';
import type { ColumnField } from '../PipelineListView/types';
import { formatRelative } from './utils';
import { KanbanCardContent } from './KanbanCardContent';

interface EntityCardOverlayProps {
  entity: DemoEntityCard;
  cardFields?: ColumnField[];
}

export default function EntityCardOverlay({ entity, cardFields }: EntityCardOverlayProps) {
  const { skin } = useSkin();
  const inState = formatRelative(entity.stateEnteredAt);
  const kanbanCardSlot = skin.components?.['kanban-card'];

  return (
    // Overlay wrapper: fixed width, drag cursor, elevated shadow + cobalt ring
    <div className="w-[296px] cursor-grabbing rounded-xl shadow-xl ring-2 ring-cobalt/20">
      <ComponentSlot
        slotName="kanban-card"
        component={kanbanCardSlot}
        slotProps={{ entity, onPress: undefined, isDragging: false }}
        fallback={<DefaultOverlayCard entity={entity} inState={inState} cardFields={cardFields} />}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Default overlay card — rendered when the skin does not provide a slot
// ---------------------------------------------------------------------------

interface DefaultOverlayCardProps {
  entity: DemoEntityCard;
  inState: string | null;
  cardFields?: ColumnField[];
}

function DefaultOverlayCard({ entity, inState, cardFields }: DefaultOverlayCardProps) {
  return (
    <div className="rounded-xl border border-cobalt/40 bg-card px-4 py-3 text-left">
      <KanbanCardContent entity={entity} inState={inState} cardFields={cardFields} />
    </div>
  );
}
