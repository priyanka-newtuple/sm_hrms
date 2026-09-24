import {
  DndContext,
  closestCenter,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import { SortableContext, horizontalListSortingStrategy } from '@dnd-kit/sortable';
import { Plus, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { SegmentedControl } from '@/core/components/SegmentedControl';
import CellConfigPopover from './CellConfigPopover';
import { TableColumnHeader } from './TableColumnHeader';
import { normalizeBuilderCellValue, shouldUseFixedRowTextarea, toId } from './tableFieldUtils';
import { useTableFieldConfig } from '../hooks/useTableFieldConfig';
import type { TableColumn, TableFieldConfig, TablePresetRow } from '../../../../../core/types';

export interface TableFieldBuilderProps {
  config: TableFieldConfig;
  onChange: (next: TableFieldConfig) => void;
  numericFields: { id: string; label: string }[];
  tableFields: { id: string; label: string; columns: { id: string; label: string }[] }[];
  canWrite: boolean;
  /** Disambiguates DOM ids (e.g. the delete-rows switch) across sibling builders. */
  instanceId: string | number;
}

/**
 * Unified WYSIWYG builder for a `table` form field: column config lives in the
 * grid header cells, predefined-row values are edited inline, and dynamic
 * tables show a runtime placeholder. Mutation logic lives in
 * `useTableFieldConfig`; this component is presentation only.
 */
export function TableFieldBuilder({
  config,
  onChange,
  numericFields,
  tableFields,
  canWrite,
  instanceId,
}: TableFieldBuilderProps) {
  const {
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
  } = useTableFieldConfig(config, onChange);

  const cellRows = rows.map((r) => ({ id: r.id, label: r.label || r.id }));
  const cellColumns = columns.map((c) => ({ id: c.id, label: c.label || c.id }));
  const colCount = columns.length;

  const columnSensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
  );

  const handleColumnDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    reorderColumns(String(active.id), String(over.id));
  };

  const renderCellInput = (row: TablePresetRow, rowIndex: number, column: TableColumn) => {
    const cellValue = row.cells?.[column.id];
    const commonClass = 'h-9 w-full min-w-36 rounded-md border border-border bg-card px-2 text-sm focus:border-cobalt focus:ring-2 focus:ring-cobalt';

    if (column.type === 'boolean') {
      return (
        <label className="flex h-9 min-w-28 items-center justify-center rounded-md border border-border bg-card">
          <input
            type="checkbox"
            checked={Boolean(cellValue)}
            onChange={(e) => updateCell(rowIndex, column, normalizeBuilderCellValue(column, '', e.target.checked))}
          />
        </label>
      );
    }

    if (column.type === 'select') {
      return (
        <select
          value={String(cellValue ?? '')}
          onChange={(e) => updateCell(rowIndex, column, e.target.value)}
          className={commonClass}
        >
          <option value="">Select...</option>
          {(column.enum_values ?? []).map((option) => (
            <option key={option} value={option}>{option}</option>
          ))}
        </select>
      );
    }

    const value = Array.isArray(cellValue) ? cellValue.join(', ') : String(cellValue ?? '');
    if (shouldUseFixedRowTextarea(column, value)) {
      return (
        <textarea
          value={value}
          onChange={(e) => updateCell(rowIndex, column, e.target.value)}
          rows={3}
          className="min-h-20 w-full min-w-72 resize-y whitespace-pre-wrap break-words rounded-md border border-border bg-card px-2 py-1.5 text-sm leading-5 focus:border-cobalt focus:ring-2 focus:ring-cobalt"
        />
      );
    }

    const inputType = ['integer', 'number', 'currency', 'percent'].includes(column.type) ? 'number' : column.type === 'date' ? 'date' : 'text';
    return (
      <input
        type={inputType}
        value={value}
        onChange={(e) => updateCell(rowIndex, column, normalizeBuilderCellValue(column, e.target.value))}
        placeholder={column.type === 'multi_select' ? 'Comma separated' : undefined}
        className={commonClass}
      />
    );
  };

  return (
    <div className="space-y-3 rounded-xl border border-border bg-card p-3">
      {/* Toolbar: row mode + display mode */}
      <div className="flex flex-wrap items-end gap-4">
        <div className="space-y-1">
          <span className="block text-xs font-medium text-muted-foreground">Rows</span>
          <SegmentedControl
            size="sm"
            options={[
              { value: 'fixed', label: 'Predefined rows' },
              { value: 'dynamic', label: 'Users add rows' },
            ] as const}
            value={rowMode}
            onChange={(mode) => patchConfig({ row_mode: mode, allow_delete_rows: mode === 'dynamic' })}
          />
        </div>
        <div className="space-y-1">
          <span className="block text-xs font-medium text-muted-foreground">Display as</span>
          <select
            value={config.display_mode ?? 'grid'}
            onChange={(e) => patchConfig({ display_mode: e.target.value as 'grid' | 'form' })}
            className="rounded-lg border border-border px-3 py-1.5 text-sm outline-none focus:border-cobalt focus:ring-2 focus:ring-cobalt"
          >
            <option value="grid">Table</option>
            <option value="form">Form</option>
          </select>
        </div>
      </div>

      {/* Dynamic-mode row rules */}
      {rowMode !== 'fixed' && (
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1">Minimum rows</label>
            <input
              type="number"
              min={0}
              value={config.min_rows ?? 0}
              onChange={(e) => patchConfig({ min_rows: Number(e.target.value || 0) })}
              className="w-full px-3 py-2 border border-border rounded-lg text-sm outline-none focus:ring-2 focus:ring-cobalt focus:border-cobalt"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1">Maximum rows</label>
            <input
              type="number"
              min={0}
              value={config.max_rows ?? ''}
              onChange={(e) => patchConfig({ max_rows: e.target.value ? Number(e.target.value) : undefined })}
              placeholder="No limit"
              className="w-full px-3 py-2 border border-border rounded-lg text-sm outline-none focus:ring-2 focus:ring-cobalt focus:border-cobalt"
            />
          </div>
          <label className="col-span-2 flex items-center justify-between rounded-lg border border-border bg-muted/50 px-3 py-2">
            <span className="text-sm font-medium text-foreground">Allow users to delete rows</span>
            <Switch
              id={`table-delete-rows-${instanceId}`}
              checked={config.allow_delete_rows ?? true}
              onCheckedChange={(checked) => patchConfig({ allow_delete_rows: checked })}
            />
          </label>
        </div>
      )}

      {/* Unified grid: column config lives in the header cells */}
      <div className="overflow-x-auto rounded-lg border border-border">
        <DndContext sensors={columnSensors} collisionDetection={closestCenter} onDragEnd={handleColumnDragEnd}>
          <table className="min-w-full border-collapse bg-card text-sm">
            <thead>
              <tr>
                <th className="sticky left-0 z-20 w-44 min-w-44 border-b border-r border-border bg-muted/50 px-2 py-2 text-left align-bottom text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  {rowMode === 'fixed' ? 'Row ID' : 'Columns'}
                </th>
                <SortableContext items={columnDragIds} strategy={horizontalListSortingStrategy}>
                  {columns.map((column, columnIndex) => (
                    <TableColumnHeader
                      key={columnIndex}
                      column={column}
                      columnIndex={columnIndex}
                      rowMode={rowMode}
                      canWrite={canWrite}
                      numericFields={numericFields}
                      tableFields={tableFields}
                      siblingColumns={columns
                        .filter((c) => c.id !== column.id)
                        .map((c) => ({ id: c.id, label: c.label || c.id }))}
                      onUpdate={(patch) => updateColumn(columnIndex, patch)}
                      onRemove={() => removeColumn(columnIndex)}
                    />
                  ))}
                </SortableContext>
                <th className="w-12 min-w-12 border-b border-border bg-muted/50 px-1 py-2 text-center align-bottom">
                  <button
                    type="button"
                    onClick={addColumn}
                    disabled={!canWrite}
                    className="rounded-md p-1.5 text-cobalt hover:bg-cobalt/10 disabled:opacity-40"
                    title="Add column"
                    aria-label="Add column"
                  >
                    <Plus className="h-4 w-4" />
                  </button>
                </th>
              </tr>
            </thead>
            <tbody>
              {rowMode === 'fixed' ? (
                <>
                  {rows.map((row, rowIndex) => (
                    <tr key={rowIndex} className="align-top">
                      <td className="sticky left-0 z-10 border-r border-t border-border bg-muted/50 p-2">
                        <input
                          type="text"
                          value={row.id}
                          onChange={(e) => updateRow(rowIndex, { id: toId(e.target.value) || e.target.value })}
                          placeholder="row_id"
                          className="h-9 w-full min-w-36 rounded-md border border-border bg-card px-2 font-mono text-sm focus:border-cobalt focus:ring-2 focus:ring-cobalt"
                        />
                      </td>
                      {columns.map((column, columnIndex) => (
                        <td key={columnIndex} className="border-r border-t border-border p-2 last:border-r-0">
                          <div className="flex items-center gap-1">
                            <div className="flex-1">
                              {row.cell_config?.[column.id]?.calc ? (
                                <div className="flex h-9 items-center gap-1 rounded-md border border-dashed border-cobalt/40 bg-cobalt/5 px-2 text-xs font-medium text-cobalt">
                                  <span className="font-mono">ƒ</span> Calculated
                                </div>
                              ) : (
                                renderCellInput(row, rowIndex, column)
                              )}
                            </div>
                            {/* Key by cell identity (row+column), not slot position, so the
                                popover's mount-only local mode resets when a column reorder or
                                row removal changes which cell this slot renders. */}
                            <CellConfigPopover
                              key={`${row.id || rowIndex}-${column.id || columnIndex}`}
                              column={column}
                              rowLabel={row.label || row.id}
                              value={row.cell_config?.[column.id]}
                              onChange={(next) => updateCellConfig(rowIndex, column.id, next)}
                              cellRows={cellRows}
                              cellColumns={cellColumns}
                            />
                          </div>
                        </td>
                      ))}
                      <td className="border-t border-border p-2 text-center">
                        <button
                          type="button"
                          onClick={() => removeRow(rowIndex)}
                          className="rounded-lg p-2 text-muted-foreground hover:bg-muted hover:text-destructive"
                          title="Remove row"
                          aria-label="Remove row"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </td>
                    </tr>
                  ))}
                  {rows.length === 0 && (
                    <tr>
                      <td
                        colSpan={colCount + 2}
                        className="border-t border-border px-3 py-6 text-center text-sm text-muted-foreground"
                      >
                        Add a row to start entering fixed table values.
                      </td>
                    </tr>
                  )}
                  <tr>
                    <td colSpan={colCount + 2} className="border-t border-border p-2">
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={addRow}
                        disabled={!canWrite}
                        icon={<Plus className="h-3.5 w-3.5" />}
                      >
                        Add row
                      </Button>
                    </td>
                  </tr>
                </>
              ) : (
                <tr>
                  <td colSpan={colCount + 2} className="border-t border-border p-0">
                    <div
                      className="flex flex-col items-center justify-center gap-1 px-4 py-10 text-center"
                      style={{
                        backgroundImage:
                          'repeating-linear-gradient(45deg, rgb(249 250 251), rgb(249 250 251) 10px, transparent 10px, transparent 20px)',
                      }}
                    >
                      <span className="text-sm font-medium text-muted-foreground">Rows are added by users at runtime</span>
                      <span className="text-xs text-muted-foreground">
                        Switch to “Predefined rows” to set fixed values here
                      </span>
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </DndContext>
      </div>

      {rowMode === 'fixed' && (
        <p className="text-xs text-muted-foreground">
          Mark a column read-only (lock) when users should review a value but not edit it. Use the ƒ button inside a cell for a per-cell formula.
        </p>
      )}
    </div>
  );
}
