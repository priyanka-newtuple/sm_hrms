import { arrayMove } from '@dnd-kit/sortable';
import type { TableColumn, TableFieldConfig, TablePresetRow } from '../../../../../core/types';

export interface TableFieldConfigController {
  columns: TableColumn[];
  rows: TablePresetRow[];
  rowMode: 'dynamic' | 'fixed';
  /** Stable per-column ids for dnd-kit sorting (falls back to index when unset). */
  columnDragIds: string[];
  patchConfig: (patch: Partial<TableFieldConfig>) => void;
  updateColumn: (columnIndex: number, patch: Partial<TableColumn>) => void;
  addColumn: () => void;
  removeColumn: (columnIndex: number) => void;
  reorderColumns: (activeId: string, overId: string) => void;
  updateRow: (rowIndex: number, patch: Partial<TablePresetRow>) => void;
  addRow: () => void;
  removeRow: (rowIndex: number) => void;
  updateCell: (rowIndex: number, column: TableColumn, value: unknown) => void;
  updateCellConfig: (rowIndex: number, columnId: string, next: unknown) => void;
}

/**
 * Encapsulates every mutation of a `TableFieldConfig`. Given the current config
 * and an `onChange`, it returns derived slices plus handlers that each emit a
 * full, updated config — keeping the persisted payload identical while isolating
 * table-mutation logic from the builder's presentation.
 */
export function useTableFieldConfig(
  config: TableFieldConfig,
  onChange: (next: TableFieldConfig) => void,
): TableFieldConfigController {
  const columns = config.columns ?? [];
  const rows = config.rows ?? [];
  const rowMode = config.row_mode ?? 'dynamic';
  const columnDragIds = columns.map((c, i) => c.id || `__col_${i}`);

  const patchConfig = (patch: Partial<TableFieldConfig>) => onChange({ ...config, ...patch });

  const updateColumn = (columnIndex: number, patch: Partial<TableColumn>) =>
    patchConfig({ columns: columns.map((c, i) => (i === columnIndex ? { ...c, ...patch } : c)) });

  const addColumn = () =>
    patchConfig({
      columns: [
        ...columns,
        { id: `column_${columns.length + 1}`, label: `Column ${columns.length + 1}`, type: 'text' },
      ],
    });

  const removeColumn = (columnIndex: number) =>
    patchConfig({ columns: columns.filter((_, i) => i !== columnIndex) });

  const reorderColumns = (activeId: string, overId: string) => {
    const from = columnDragIds.indexOf(activeId);
    const to = columnDragIds.indexOf(overId);
    if (from === -1 || to === -1) return;
    patchConfig({ columns: arrayMove(columns, from, to) });
  };

  const updateRow = (rowIndex: number, patch: Partial<TablePresetRow>) =>
    patchConfig({ rows: rows.map((r, i) => (i === rowIndex ? { ...r, ...patch } : r)) });

  const addRow = () => patchConfig({ rows: [...rows, { id: `row_${rows.length + 1}`, cells: {} }] });

  const removeRow = (rowIndex: number) =>
    patchConfig({ rows: rows.filter((_, i) => i !== rowIndex) });

  const updateCell = (rowIndex: number, column: TableColumn, value: unknown) => {
    const row = rows[rowIndex];
    if (!row) return;
    updateRow(rowIndex, { cells: { ...(row.cells ?? {}), [column.id]: value } });
  };

  const updateCellConfig = (rowIndex: number, columnId: string, next: unknown) => {
    const row = rows[rowIndex];
    if (!row) return;
    const cell_config = { ...(row.cell_config ?? {}) };
    if (next === undefined) delete cell_config[columnId];
    else cell_config[columnId] = next as NonNullable<TablePresetRow['cell_config']>[string];
    updateRow(rowIndex, { cell_config });
  };

  return {
    columns,
    rows,
    rowMode,
    columnDragIds,
    patchConfig,
    updateColumn,
    addColumn,
    removeColumn,
    reorderColumns,
    updateRow,
    addRow,
    removeRow,
    updateCell,
    updateCellConfig,
  };
}
