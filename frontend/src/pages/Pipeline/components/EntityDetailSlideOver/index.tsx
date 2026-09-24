import { useEffect } from 'react';
import { Loader2 } from 'lucide-react';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet';
import DocumentPreviewPanel from '@/core/components/DocumentPreviewPanel';
import EntityIteratorControls from '@/core/components/EntityIteratorControls';
import {
  type EntityIteratorState,
  useEntityEditingLock,
} from '@/core/hooks/useEntityIterator';
import type { WorkflowEntityState } from '@/core/services/api';
import { useDocumentPreviewStore } from '@/core/stores/documentPreviewStore';
import type { FormSchema } from '@/core/types';
import { getEntityDisplayTitle } from '@/shared/utils/entityDisplay';
import { resolveEntityTypeLabel } from '@/shared/utils/labels';
import EntityDetailContent, { type EntityDetailTab } from './EntityDetailContent';

interface EntityDetailSlideOverProps {
  entity: WorkflowEntityState | null;
  open: boolean;
  onClose: () => void;
  onTransitionExecuted: () => void;
  schemas?: FormSchema[];
  schemasAuthoritative?: boolean;
  onSaveEntity: (
    entityId: string,
    payload: { data?: Record<string, unknown>; due_date?: string | null; schema_fields?: Array<Record<string, unknown>> },
  ) => Promise<void>;
  onEntityDataSaved?: (newData: Record<string, unknown>) => void;
  onFileUploaded?: () => void;
  onDeleted?: () => void;
  initialTab?: EntityDetailTab;
  scrollToCommentId?: string | null;
  scrollToReplyId?: string | null;
  workflowId?: string;
  iterator?: EntityIteratorState;
  loading?: boolean;
}

/** Slide-over shell around {@link EntityDetailContent} — the full-page
 *  variant lives at /pipeline/:id/entity/:entityId (EntityDetailPage). */
export default function EntityDetailSlideOver({
  entity,
  open,
  onClose,
  iterator,
  loading = false,
  ...contentProps
}: EntityDetailSlideOverProps) {
  const title = entity ? getEntityDisplayTitle(entity.data, entity.entity_id) : '';
  const resetPreview = useDocumentPreviewStore((s) => s.reset);
  const hasPreview = useDocumentPreviewStore((s) => s.docs.length > 0);
  const collapsed = useDocumentPreviewStore((s) => s.collapsed);
  const {
    editing,
    onEditingChange,
    clearEditing,
  } = useEntityEditingLock(entity?.entity_id);

  useEffect(() => {
    resetPreview();
  }, [entity?.entity_id, resetPreview]);

  // The shadcn Sheet variant hard-caps width at w-3/4 (75vw), which is too
  // narrow to seat the 34rem preview panel beside a comfortable detail column —
  // the detail collapses when the preview opens. Drive the width EXPLICITLY
  // (inline `width` beats the w-3/4 class) so the sheet = preview + detail base,
  // capped to the viewport. Open = 34rem preview + 56rem detail + gap.
  const sheetWidth = !hasPreview ? '56rem' : collapsed ? '59rem' : '84rem';

  return (
    <Sheet
      open={open}
      onOpenChange={(isOpen, eventDetails) => {
        // Don't let Esc/click-outside silently discard an in-progress edit —
        // the record iterator is already locked for the same reason.
        if (
          !isOpen &&
          editing &&
          (eventDetails?.reason === 'escape-key' || eventDetails?.reason === 'outside-press')
        ) {
          eventDetails.cancel();
          return;
        }
        if (!isOpen) {
          clearEditing();
          resetPreview();
          onClose();
        }
      }}
    >
      <SheetContent
        side="right"
        className="flex flex-row gap-0 overflow-hidden bg-card p-0 [&_[data-slot=sheet-close]]:text-[var(--modal-header-foreground)]"
        style={{ width: sheetWidth, maxWidth: '90vw' }}
      >
        {entity && <DocumentPreviewPanel className="h-full" />}

        <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
          <SheetHeader className="border-b border-border bg-[var(--modal-header-background)] px-6 py-5 pr-14 text-[var(--modal-header-foreground)]">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <SheetTitle className="truncate text-lg font-semibold text-[var(--modal-header-foreground)]">
                  {title}
                </SheetTitle>
                {entity && (
                  <SheetDescription className="text-[var(--modal-header-foreground)] opacity-70">
                    {resolveEntityTypeLabel(entity.entity_type)}
                  </SheetDescription>
                )}
              </div>
              {iterator && (
                <EntityIteratorControls
                  {...iterator}
                  disabled={iterator.disabled || editing || loading}
                  className="-my-1 shrink-0"
                />
              )}
            </div>
          </SheetHeader>

          <div className="relative flex min-h-0 flex-1 flex-col">
            {loading && (
              <div className="absolute inset-0 z-20 flex items-center justify-center bg-card/80">
                <Loader2 className="h-6 w-6 animate-spin text-cobalt" aria-label="Loading entity" />
              </div>
            )}
            {entity && (
              <EntityDetailContent
                key={entity.entity_id}
                entity={entity}
                {...contentProps}
                onEditingChange={onEditingChange}
              />
            )}
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}
