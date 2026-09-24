import { useMemo } from 'react';
import { Rows3 } from 'lucide-react';
import ColumnVisibilityMenu from '@/shared/components/ColumnVisibilityMenu';
import type { FormSchema } from '@/core/types';
import type { ColumnField } from '../components/PipelineListView/types';
import { useCardFieldsConfig, MAX_CARD_FIELDS } from './useCardFieldsConfig';

export interface UseKanbanCardFieldsToolbarOptions {
  /** Org-level Display setting (Settings → Display → "Card fields"). */
  enabled: boolean;
  /** Only render/wire the picker while the Kanban tab is the active view. */
  isKanbanView: boolean;
  /** Fields already shown unconditionally on the card (skin title/subtitle). */
  builtInCardFields: string[];
  /** Drops fields the viewer can't see elsewhere in this workflow. */
  canViewField?: (fieldId: string) => boolean;
  /** Gates the trigger itself — saving requires `workflow:write` server-side,
   *  so a read-only viewer should never see a control whose every toggle is
   *  a doomed request. */
  canConfigure: boolean;
}

/** Everything the board toolbar's "Card fields" button needs: the picker
 *  element itself, plus the two pieces of derived state the rest of the page
 *  needs (the Kanban-only fields request, and the selected fields' metadata
 *  for card rendering). Split out of `PipelinePage` to keep that page-level
 *  function from growing further with this feature's wiring. */
export function useKanbanCardFieldsToolbar(
  machineName: string,
  entitySchemas: FormSchema[],
  summaryFields: string[],
  options: UseKanbanCardFieldsToolbarOptions,
) {
  const cardFields = useCardFieldsConfig(machineName, entitySchemas, {
    excludeFieldIds: options.builtInCardFields,
    enabled: options.enabled,
    canViewField: options.canViewField,
  });

  const kanbanSummaryFields = useMemo(
    () => Array.from(new Set([...summaryFields, ...cardFields.selectedIds])),
    [summaryFields, cardFields.selectedIds],
  );

  // Resolved in saved-selection order, with metadata (type/enum labels) the
  // card renderer needs for compact formatting.
  const selectedCardFieldMeta = useMemo<ColumnField[]>(
    () =>
      cardFields.selectedIds
        .map((id) => cardFields.allFields.find((f) => f.field === id))
        .filter((f): f is ColumnField => Boolean(f)),
    [cardFields.selectedIds, cardFields.allFields],
  );

  const toggle =
    options.enabled && options.isKanbanView && options.canConfigure ? (
      <ColumnVisibilityMenu
        fields={cardFields.allFields}
        selectedIds={cardFields.selectedIds}
        visibleCount={cardFields.selectedIds.length}
        onToggle={cardFields.toggleField}
        triggerLabel="Card fields"
        triggerIcon={Rows3}
        maxCount={MAX_CARD_FIELDS}
        disabledReasons={cardFields.fieldDisabledReasons}
        triggerClassName="h-9 rounded-lg border-border bg-muted/70 px-3 text-sm text-foreground hover:bg-muted"
      />
    ) : null;

  return { toggle, kanbanSummaryFields, selectedCardFieldMeta };
}
