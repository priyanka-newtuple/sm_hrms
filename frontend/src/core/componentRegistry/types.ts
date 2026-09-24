import type { ComponentType } from 'react';
import type { WorkflowEntityState } from '@/core/services/api';
import type { DemoEntityCard, PipelineListEntity, PipelineStateNode, PipelineViewModel } from '@/shared/types/pipeline';

export type SlotName = 'entity-detail-view' | 'kanban-card' | 'kanban-column-header' | 'kanban-column-skeleton' | 'list-view' | 'login-page' | 'microsoft-callback' | 'pending-approval' | 'sidebar' | 'topbar';

export interface EntityDetailViewSlotProps {
  entity: WorkflowEntityState;
  open: boolean;
  onClose: () => void;
  onTransitionExecuted: () => void;
  onDeleted?: () => void;
}

/**
 * Props passed to a skin-provided kanban column header component.
 *
 * The skin component receives the state metadata and entity count needed to
 * render the column header. Colors are intentionally omitted here — the skin
 * component reads them from skin context (`useSkin`) so this interface stays
 * stable as color config evolves independently.
 */
export interface KanbanColumnHeaderSlotProps {
  /** The pipeline state this column represents */
  state: PipelineStateNode;
  /** 1-based display order of this column on the board */
  displayOrder: number;
  /** Number of entities currently in this state */
  entityCount: number;
}

/**
 * Props passed to a skin-provided kanban card component.
 *
 * `onPress` is undefined when the card is rendered as a drag overlay — skin
 * components should tolerate this and avoid attaching click handlers in that
 * context.
 *
 * `isDragging` is true only on the source card during an active drag (not on
 * the overlay). Use it to apply reduced-opacity or disabled styles.
 */
export interface KanbanCardSlotProps {
  entity: DemoEntityCard;
  onPress?: () => void;
  isDragging?: boolean;
  /**
   * Called when the card's thumbnail image fails to load. The platform
   * resolves a fresh URL from the backend and returns it, or null when the
   * entity has no configured thumbnail field or the request fails.
   */
  onRefreshThumbnail?: () => Promise<string | null>;
}

/**
 * Props passed to a skin-provided kanban column loading-skeleton component,
 * rendered in place of the real column while the entity list is still in
 * flight (the workflow/columns are already known at this point). Mirrors
 * `KanbanColumnHeaderSlotProps` minus `entityCount`, which isn't known yet.
 */
export interface KanbanColumnSkeletonSlotProps {
  state: PipelineStateNode;
  displayOrder: number;
}

// Login page slot: skin owns the full page. Component reads auth context directly.
export type LoginPageSlotProps = Record<string, never>;

// Microsoft callback visual slot: platform handles OAuth/PKCE, skin provides visuals only.
export interface MicrosoftCallbackSlotProps {
  status: 'working' | 'error';
  errorMessage: string | null;
  onRetry: () => void;
}

// Pending-approval page slot: skin owns the full page visual.
// Platform reads location.state and passes it through; skin handles the messaging.
export interface PendingApprovalSlotProps {
  email?: string;
  name?: string;
  orgName?: string;
  approvalType?: 'pending_org_admin' | 'pending_platform';
  isNewOrg?: boolean;
  onBack: () => void;
}

/**
 * The sidebar slot takes no props: a skin's sidebar reads everything it needs
 * (auth, navigation, branding, workflows) from the platform hooks directly,
 * keeping this slot fully generic and decoupled from any domain.
 */
export type SidebarSlotProps = Record<string, never>;

/**
 * The topbar slot takes no props for the same reason as the sidebar slot: a
 * skin's topbar reads auth, navigation, and branding from the platform hooks
 * directly. When a skin registers this slot the platform renders it in place
 * of the default two-row header in the 'topbar' nav layout.
 *
 * Height contract: the rendered component must fit within a single
 * `--header-height` row (the same height as the platform's own header).
 * Pages that reserve viewport space for the nav chrome (e.g. the Pipeline
 * board) size themselves against this one-row assumption — a taller custom
 * topbar will cause that content to overflow the reserved area.
 */
export type TopbarSlotProps = Record<string, never>;

/**
 * Props passed to a skin-provided list/table view — replaces the platform's
 * default `PipelineListView` (columns picker, generic filters, transition
 * actions) with a skin-owned table. The skin reads its own display config
 * (columns, status colors) via `useSkin`; entities are already filtered by
 * the board's search/filter bar above.
 */
export interface ListViewSlotProps {
  model: PipelineViewModel;
  entities: PipelineListEntity[];
  onEntityClick: (entityId: string) => void;
}

export type SlotProps = {
  'entity-detail-view': EntityDetailViewSlotProps;
  'kanban-card': KanbanCardSlotProps;
  'kanban-column-header': KanbanColumnHeaderSlotProps;
  'kanban-column-skeleton': KanbanColumnSkeletonSlotProps;
  'list-view': ListViewSlotProps;
  'login-page': LoginPageSlotProps;
  'microsoft-callback': MicrosoftCallbackSlotProps;
  'pending-approval': PendingApprovalSlotProps;
  sidebar: SidebarSlotProps;
  topbar: TopbarSlotProps;
};

/**
 * A skin component for a named slot.
 * Optionally declare `canHandle` to let ComponentSlot fall back to the
 * platform default when this component cannot render a specific entity.
 */
export type SlotComponent<S extends SlotName> = ComponentType<SlotProps[S]> & {
  canHandle?: (props: SlotProps[S]) => boolean;
};

export type SkinComponents = {
  [S in SlotName]?: SlotComponent<S>;
};
