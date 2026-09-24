import { GripVertical, Lock, MoreHorizontal, Trash2 } from 'lucide-react';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { cn } from '@/lib/utils';
import ColorSwatchPicker, {
  DEFAULT_BACKGROUND_COLOR,
  DEFAULT_TEXT_COLOR,
} from '@/core/components/ColorSwatchPicker';
import CalcBuilder from './CalcBuilder';
import { TABLE_COLUMN_TYPES, toId, splitOptions } from './tableFieldUtils';
import type { TableColumn, TableColumnType } from '../../../../../core/types';

export interface TableColumnHeaderProps {
  column: TableColumn;
  columnIndex: number;
  rowMode: 'dynamic' | 'fixed';
  canWrite: boolean;
  numericFields: { id: string; label: string }[];
  tableFields: { id: string; label: string; columns: { id: string; label: string }[] }[];
  siblingColumns: { id: string; label: string }[];
  onUpdate: (patch: Partial<TableColumn>) => void;
  onRemove: () => void;
}

/**
 * One column header cell in the unified table builder. Holds the column's
 * full config (label, type, required/read-only, advanced options popover) and
 * is drag-sortable to reorder columns. All edits flow through `onUpdate` /
 * `onRemove` so the persisted `table_config.columns[]` payload is unchanged.
 */
export function TableColumnHeader({
  column,
  columnIndex,
  rowMode,
  canWrite,
  numericFields,
  tableFields,
  siblingColumns,
  onUpdate,
  onRemove,
}: TableColumnHeaderProps) {
  const sortableId = column.id || `__col_${columnIndex}`;
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: sortableId,
    disabled: !canWrite,
  });
  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    zIndex: isDragging ? 30 : undefined,
  };
  const isSelect = column.type === 'select' || column.type === 'multi_select';

  return (
    <th
      ref={setNodeRef}
      style={style}
      className="min-w-52 border-b border-r border-border bg-muted/50 p-2 align-bottom last:border-r-0"
    >
      <div className="flex items-center gap-1">
        <span
          {...attributes}
          {...listeners}
          className="shrink-0 cursor-grab touch-none text-muted-foreground/60 hover:text-muted-foreground active:cursor-grabbing"
          aria-label="Drag to reorder column"
        >
          <GripVertical className="h-4 w-4" />
        </span>
        <input
          type="text"
          value={column.label}
          onChange={(e) => onUpdate({ label: e.target.value, id: column.id || toId(e.target.value) })}
          placeholder="Column label"
          className="min-w-0 flex-1 rounded-md border border-transparent bg-transparent px-1.5 py-1 text-sm font-medium text-foreground outline-none hover:border-border focus:border-cobalt focus:bg-card focus:ring-2 focus:ring-cobalt"
        />
        <button
          type="button"
          onClick={onRemove}
          disabled={!canWrite}
          className="shrink-0 rounded p-1 text-muted-foreground hover:bg-muted hover:text-destructive disabled:opacity-40"
          title="Remove column"
          aria-label="Remove column"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>
      <div className="mt-1.5 flex items-center gap-1.5">
        <select
          value={column.type}
          onChange={(e) => onUpdate({ type: e.target.value as TableColumnType })}
          className="min-w-0 flex-1 rounded-md border border-border bg-card px-1.5 py-1 text-xs outline-none focus:border-cobalt focus:ring-2 focus:ring-cobalt"
        >
          {TABLE_COLUMN_TYPES.map((type) => (
            <option key={type.value} value={type.value}>{type.label}</option>
          ))}
        </select>
        <button
          type="button"
          onClick={() => onUpdate({ required: !column.required })}
          aria-pressed={Boolean(column.required)}
          aria-label="Toggle required"
          title={column.required ? 'Required' : 'Not required'}
          className={cn(
            'flex h-6 min-w-[24px] items-center justify-center rounded-md border px-1 text-[11px] font-semibold transition-colors',
            column.required
              ? 'border-destructive/30 bg-destructive-subtle text-destructive'
              : 'border-border bg-card text-muted-foreground hover:text-muted-foreground',
          )}
        >
          R
        </button>
        <button
          type="button"
          onClick={() => onUpdate({ readonly: !column.readonly })}
          aria-pressed={Boolean(column.readonly)}
          aria-label="Toggle read-only"
          title={column.readonly ? 'Read-only' : 'Editable'}
          className={cn(
            'flex h-6 min-w-[24px] items-center justify-center rounded-md border transition-colors',
            column.readonly
              ? 'border-cobalt/30 bg-cobalt/10 text-cobalt'
              : 'border-border bg-card text-muted-foreground hover:text-muted-foreground',
          )}
        >
          <Lock className="h-3 w-3" />
        </button>
        <Popover>
          <PopoverTrigger
            title="Column options"
            aria-label="Column options"
            className="flex h-6 min-w-[24px] items-center justify-center rounded-md border border-border bg-card text-muted-foreground transition-colors hover:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cobalt"
          >
            <MoreHorizontal className="h-3.5 w-3.5" />
          </PopoverTrigger>
          <PopoverContent align="end" className="w-96 space-y-3">
            <div className="text-xs font-semibold text-foreground">
              Column options · {column.label || column.id}
            </div>
            <div className="space-y-1">
              <span className="block text-xs font-medium text-muted-foreground">Field ID</span>
              <input
                type="text"
                value={column.id}
                onChange={(e) => onUpdate({ id: toId(e.target.value) || e.target.value })}
                placeholder="column_id"
                className="w-full rounded-lg border border-border px-2 py-1.5 font-mono text-sm outline-none focus:border-cobalt focus:ring-2 focus:ring-cobalt"
              />
            </div>
            {isSelect && (
              <div className="space-y-1">
                <span className="block text-xs font-medium text-muted-foreground">Options</span>
                <input
                  type="text"
                  value={(column.enum_values ?? []).join(', ')}
                  onChange={(e) => onUpdate({ enum_values: splitOptions(e.target.value) })}
                  placeholder="Options, comma separated"
                  className="w-full rounded-lg border border-border px-2 py-1.5 text-sm outline-none focus:border-cobalt focus:ring-2 focus:ring-cobalt"
                />
              </div>
            )}
            {(column.type === 'text' || column.type === 'textarea') && (
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1">
                  <span className="block text-xs font-medium text-muted-foreground">Background color</span>
                  <ColorSwatchPicker
                    value={column.style_config?.background_color ?? DEFAULT_BACKGROUND_COLOR}
                    onChange={(hex) =>
                      onUpdate({ style_config: { ...column.style_config, background_color: hex } })
                    }
                    size={22}
                  />
                </div>
                <div className="space-y-1">
                  <span className="block text-xs font-medium text-muted-foreground">Text color</span>
                  <ColorSwatchPicker
                    value={column.style_config?.text_color ?? DEFAULT_TEXT_COLOR}
                    onChange={(hex) =>
                      onUpdate({ style_config: { ...column.style_config, text_color: hex } })
                    }
                    size={22}
                  />
                </div>
              </div>
            )}
            {rowMode !== 'fixed' && (
              <div className="space-y-1">
                <span className="block text-xs font-medium text-muted-foreground">Formula</span>
                <CalcBuilder
                  mode="column"
                  value={column.calc}
                  onChange={(calc) => onUpdate({ calc })}
                  numericFields={numericFields}
                  tableFields={tableFields}
                  siblingColumns={siblingColumns}
                />
              </div>
            )}
          </PopoverContent>
        </Popover>
      </div>
    </th>
  );
}
