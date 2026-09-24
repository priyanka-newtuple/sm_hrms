import { Plus } from 'lucide-react';
import type { ReactNode } from 'react';
import { Button } from '@/components/ui/button';
import { useSkin } from '@/skins';
import { resolveEntityTypeLabel } from '@/shared/utils/labels';
import type { StateMachineRecord } from '@/core/types';

interface PipelinePageHeaderProps {
  workflow: StateMachineRecord;
  onAddEntity: () => void;
  canCreate?: boolean;
  /** Export control rendered beside the Add button — shown only when skin.board.showExportCsv is true. */
  exportSlot?: ReactNode;
  /** Put the title above a compact controls row when the full toolbar is supplied. */
  stackControls?: boolean;
  /**
   * Optional control (e.g. the Kanban/List view tabs) rendered top-right,
   * before the Add button. Used by skins with `board.toolbarLayout: 'unified'`
   * to move the view toggle into the title row.
   */
  viewToggle?: ReactNode;
  bulkImportSlot?: ReactNode;
}

export default function PipelinePageHeader({
  workflow,
  onAddEntity,
  canCreate = true,
  exportSlot,
  viewToggle,
  stackControls = false,
  bulkImportSlot,
}: PipelinePageHeaderProps) {
  const { skin } = useSkin();
  const displayEntityType = resolveEntityTypeLabel(workflow.entity_type);
  const heading = skin.board.pageTitle ?? workflow.name ?? displayEntityType;
  const showExport = skin.board.showExportCsv !== false;
  const showAddEntity = skin.board.showAddEntity !== false;
  const addAction = canCreate && showAddEntity ? (
    <Button
      variant="primary"
      size="md"
      onClick={onAddEntity}
      rounded="lg"
      icon={<Plus className="h-4 w-4" />}
      className="font-semibold shadow-crisp hover:shadow-card"
    >
      Add {displayEntityType}
    </Button>
  ) : null;

  // Grouped together (rather than three loose siblings after viewToggle) so
  // they wrap and align as one unit — never split across a line break.
  const actionButtons = (addAction || bulkImportSlot || (showExport && exportSlot)) && (
    <div className="flex shrink-0 flex-wrap items-center gap-2">
      {addAction}
      {bulkImportSlot}
      {showExport && exportSlot}
    </div>
  );

  if (stackControls) {
    return (
      <div className="flex shrink-0 flex-col gap-2">
        <h1 className={skin.board.titleClassName ?? 'truncate text-lg font-semibold tracking-tight text-foreground'}>{heading}</h1>
        {/* Grid, not flex-wrap, for the outer split: a wrapped flex group's
            "natural" width (used to decide whether the next item still fits
            on the line) is its unconstrained max-content size, not its
            final rendered width — so actionButtons kept getting pushed to
            its own line even when the filters row visibly had room left.
            minmax(0,1fr) gives the filters column exactly the leftover
            width and lets ITS OWN flex-wrap react to that real, resolved
            width; auto sizes actionButtons to its content and never
            competes for space it doesn't need.
            Single column below sm: side-by-side columns don't wrap to a new
            row the way flex items do — squeezed narrow enough (e.g. mobile),
            the 1fr column's content (like the non-wrapping view-tabs pill)
            just overflows its track and renders on top of the actionButtons
            column instead. Stacking avoids the two ever competing for the
            same horizontal space at all. */}
        <div className="grid min-w-0 grid-cols-1 gap-2 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start">
          {viewToggle}
          {actionButtons}
        </div>
      </div>
    );
  }

  return (
    <div className="flex shrink-0 flex-wrap items-center gap-2">
      <div className="mr-auto min-w-0 max-w-[min(20rem,40vw)]">
        <h1 className={skin.board.titleClassName ?? 'truncate text-lg font-semibold tracking-tight text-foreground'}>{heading}</h1>
      </div>
      {viewToggle}
      {addAction}
      {bulkImportSlot}
      {showExport && exportSlot}
    </div>
  );
}
