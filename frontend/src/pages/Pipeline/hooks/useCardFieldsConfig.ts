import { useMemo } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { boardDisplayFields, type WorkflowBoardDisplayFields } from '@/core/services/api';
import { boardDisplayFieldsKeys } from '@/core/services/api/queryKeys';
import type { FormSchema } from '@/core/types';
import { IDENTIFIER_FIELD_KEY, getFormFieldsForSchemas } from '@/shared/utils/entityForm';
import type { FieldDisabledReasons } from '@/shared/components/ColumnVisibilityMenu';
import type { ColumnField } from '../components/PipelineListView/types';
import { titleCase } from '../components/PipelineListView/utils';

export const MAX_CARD_FIELDS = 3;
const CARD_FIELDS_STALE_TIME_MS = 30_000;

/** Field types with no single-line compact form — kept visible but disabled
 *  with a tooltip, same as the max-3 cap, rather than hidden. */
const UNRENDERABLE_FIELD_TYPE_REASONS: Record<string, string> = {
  section: "Section fields are a layout placeholder, not a data value — there's nothing to show on a card.",
  table: "Table fields hold structured row data that can't be shown as a single compact value.",
  picklist_multi: "Picklist + multi-select fields don't have one single value that can be shown compactly.",
};

/** Pure — the picker's candidate list. Split out of the hook so it's
 *  unit-testable and the hook stays under the file's function-size limit.
 *  `canViewField`, when given, drops fields the viewer can't see elsewhere
 *  in this workflow (e.g. the Filters customize popover already applies the
 *  same check) — otherwise the picker would be a second, inconsistent way to
 *  discover field names a viewer has no visibility into. */
function buildCardFieldCandidates(
  entitySchemas: FormSchema[],
  excludeFieldIds: string[],
  canViewField?: (fieldId: string) => boolean,
): ColumnField[] {
  const excluded = new Set([IDENTIFIER_FIELD_KEY, 'due_date', ...excludeFieldIds]);
  const fields: ColumnField[] = [];
  const seen = new Set<string>();
  for (const f of getFormFieldsForSchemas(entitySchemas)) {
    if (excluded.has(f.id) || seen.has(f.id)) continue;
    if (canViewField && !canViewField(f.id)) continue;
    seen.add(f.id);
    fields.push({
      field: f.id,
      label: f.label || titleCase(f.id),
      type: f.type,
      ...(f.enum_values?.length ? { enum_values: f.enum_values } : {}),
      ...(f.enum_labels?.length ? { enum_labels: f.enum_labels } : {}),
    });
  }
  return fields;
}

/** Pure — why an unselected field can't be toggled on right now (an
 *  unsupported type, or the 3-field cap already being full). An
 *  already-selected field is never disabled, so it can always be removed. */
function computeFieldDisabledReasons(allFields: ColumnField[], selectedIds: string[]): FieldDisabledReasons {
  const reasons: FieldDisabledReasons = {};
  const atCap = selectedIds.length >= MAX_CARD_FIELDS;
  for (const f of allFields) {
    if (selectedIds.includes(f.field)) continue;
    const typeReason = f.type ? UNRENDERABLE_FIELD_TYPE_REASONS[f.type] : undefined;
    if (typeReason) reasons[f.field] = typeReason;
    else if (atCap) reasons[f.field] = `Up to ${MAX_CARD_FIELDS} fields can be shown on cards. Remove one to add another.`;
  }
  return reasons;
}

export interface UseCardFieldsConfigOptions {
  /** Field ids already shown unconditionally elsewhere on the default card
   *  (e.g. a skin's configured title/subtitle field for this entity type)
   *  — excluded from the picker since selecting one would just repeat what
   *  every card already displays. Purely additive to the hook's own
   *  universal exclusions (identifier, due_date); safe to omit. */
  excludeFieldIds?: string[];
  /** Org-level gate (Settings → Display → "Card fields"). Defaults to true;
   *  pass false to keep this fully inert — no fetch, no selection, no-op
   *  toggle — for orgs that haven't turned the feature on. */
  enabled?: boolean;
  /** Field-level visibility check (e.g. `usePermissions().canViewField` bound
   *  to this workflow's entity type) — a field the viewer can't view is
   *  dropped from the candidate list entirely, not just disabled. */
  canViewField?: (fieldId: string) => boolean;
}

/** Up to 3 extra entity fields configured to show on one workflow's Kanban
 *  cards (ticket: "Configurable Summary Fields on Kanban Cards"). Unlike the
 *  Table view's "Columns" picker (`useColumnPicker`, `localStorage`-backed and
 *  shared only per-browser), this is backend-persisted per workflow so the
 *  configuration is genuinely shared by everyone viewing this workflow's
 *  board — the ticket's AC2 requirement. Candidate fields are sourced the
 *  same way `useColumnPicker` does, from the entity type's live form config. */
export function useCardFieldsConfig(
  machineName: string,
  entitySchemas: FormSchema[],
  options?: UseCardFieldsConfigOptions,
) {
  const queryClient = useQueryClient();
  const excludeFieldIds = options?.excludeFieldIds;
  const enabled = options?.enabled ?? true;
  const canViewField = options?.canViewField;

  const allFields = useMemo(
    () => buildCardFieldCandidates(entitySchemas, excludeFieldIds ?? [], canViewField),
    [entitySchemas, excludeFieldIds, canViewField],
  );

  const { data, isLoading } = useQuery({
    queryKey: boardDisplayFieldsKeys.detail(machineName),
    queryFn: () => boardDisplayFields.get(machineName),
    enabled: enabled && Boolean(machineName),
    staleTime: CARD_FIELDS_STALE_TIME_MS,
  });

  // Filter out any previously-saved field id that no longer resolves to a
  // live candidate (e.g. the form field was since removed) rather than
  // showing/fetching a stale, unresolvable id.
  const selectedIds = useMemo(() => {
    const saved = data?.fields ?? [];
    if (allFields.length === 0) return saved;
    return saved.filter((id) => allFields.some((f) => f.field === id));
  }, [data?.fields, allFields]);

  const fieldDisabledReasons = useMemo(
    () => computeFieldDisabledReasons(allFields, selectedIds),
    [allFields, selectedIds],
  );

  const mutation = useMutation({
    mutationFn: (fields: string[]) => boardDisplayFields.update(machineName, fields),
    onSuccess: (updated) => {
      queryClient.setQueryData(boardDisplayFieldsKeys.detail(machineName), updated);
    },
    onError: () => {
      toast.error("Couldn't save card fields. Please try again.");
    },
  });

  const toggleField = (field: string) => {
    if (!enabled) return;
    // Read the cache directly rather than closing over `selectedIds` — two
    // toggles fired before the first PUT resolves would otherwise both build
    // `next` from the same stale array and the second request would drop the
    // first change (the endpoint replaces `fields` wholesale).
    const cached =
      queryClient.getQueryData<WorkflowBoardDisplayFields>(boardDisplayFieldsKeys.detail(machineName))?.fields ??
      selectedIds;
    const isSelected = cached.includes(field);
    if (!isSelected && fieldDisabledReasons[field]) return;
    const next = isSelected ? cached.filter((f) => f !== field) : [...cached, field];
    mutation.mutate(next);
  };

  return {
    allFields,
    selectedIds,
    fieldDisabledReasons,
    toggleField,
    isLoading,
    isSaving: mutation.isPending,
  };
}
