/** Non-schema column ids with dedicated sort logic in `usePipelineList`'s
 *  `sortValue` (as opposed to a schema/data field sorted via its raw value).
 *  Independent of whether the column is currently visible. */
export type FixedSortKey = 'entity' | 'state' | 'created';

/** A sortable column id: a fixed column or a schema/data field name. */
export type SortKey = FixedSortKey | string;

/** Active list sort. `key === ''` means unsorted. */
export interface ListSort {
  key: SortKey | '';
  dir: 'asc' | 'desc';
}

import type { ReactNode } from 'react';
import type { FieldTotalError, FieldTotalValue } from '@/core/services/api/workflowEntities';
import type { FieldType } from '@/core/types';
import type { PipelineListEntity } from '@/shared/types/pipeline';

/** Picker-UI grouping tag for a `ColumnField` — `STANDARD` for the fixed,
 *  always-present-by-default columns like Status/Owner/Created; `CUSTOM` for
 *  entity-type-specific form fields (also the default when `group` is
 *  omitted). Shared here so the tag isn't a repeated string literal across
 *  every file that reads or sets it. */
export const FIELD_GROUP = { STANDARD: 'standard', CUSTOM: 'custom' } as const;
export type FieldGroup = (typeof FIELD_GROUP)[keyof typeof FIELD_GROUP];

/** A configurable data column: the entity-data key and its display label.
 *  When `accessor` is set the cell/sort value comes from it instead of
 *  `entity.data[field]` — used for non-data columns (Workflow, Owner). */
export interface ColumnField {
  field: string;
  label: string;
  accessor?: (entity: PipelineListEntity) => unknown;
  /** The live form-config field type, when this column maps to a configured
   *  form field. Absent for columns discovered only from a row's `data` keys
   *  (no form declares them) and for accessor-backed synthetic columns. */
  type?: FieldType;
  enum_values?: string[];
  enum_labels?: string[];
  group?: FieldGroup;
}

/** A fully-resolved, reorderable list column. */
export interface ColumnDescriptor {
  id: string;
  label: string;
  /** sort key (defaults to id); set null to disable sorting for this column */
  sortKey?: SortKey | null;
  align?: 'left' | 'right';
  render: (entity: PipelineListEntity) => ReactNode;
}

/** Shared shape both `usePipelineList` (client-side, full-drain — Calendar
 *  and the cross-workflow aggregate widget) and `usePaginatedPipelineList`
 *  (server-paginated — the single-workflow Table tab) return, so
 *  `PipelineListView` can render either without knowing which one built it.
 *  `rows` is "this page only"; for the client-side hook that's the whole
 *  filtered set sliced locally, for the paginated hook it's the server page. */
export interface PipelineListController {
  search: string;
  setSearch: (value: string) => void;
  stateFilter: string;
  setStateFilter: (value: string) => void;
  identifierFilter: string;
  setIdentifierFilter: (value: string) => void;
  identifierOptions: string[];
  allFields: ColumnField[];
  effectiveFieldIds: string[];
  visibleColumns: ColumnField[];
  sort: ListSort;
  toggleSort: (key: SortKey) => void;
  toggleField: (field: string) => void;
  rows: PipelineListEntity[];
  totalCount: number;
  /** Per-column totals across the whole filtered set, when the server was
   *  asked for them. Null for the client-side (Calendar/aggregate) controller,
   *  which has no server aggregate behind it. */
  fieldTotals?: Record<string, FieldTotalValue | FieldTotalError> | null;
  page: number;
  setPage: (page: number | ((current: number) => number)) => void;
  pageSize: number;
}
