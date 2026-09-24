/**
 * ColumnOrderPicker Component
 *
 * Presentational control for choosing which columns show and in what order.
 * Rows reorder by drag-and-drop (@dnd-kit, matching the form-config FieldsEditor
 * pattern). The parent owns the ordered selection; this component only renders
 * and emits the next ordered array. No data fetching or business logic.
 *
 * Convention: an empty `value` means "all columns, default order". The first
 * mutation materializes the full ordered list so order is preserved.
 */

import { GripVertical, Plus, X } from 'lucide-react';
import {
  DndContext,
  closestCenter,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import {
  SortableContext,
  arrayMove,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';

interface ColumnOption {
  key: string;
  label: string;
}

interface ColumnOrderPickerProps {
  columns: ColumnOption[];
  value: string[];
  onChange: (next: string[]) => void;
  label?: string;
}

interface SortableRowProps {
  id: string;
  index: number;
  label: string;
  onRemove: () => void;
}

function SortableRow({ id, index, label, onRemove }: SortableRowProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id,
  });
  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    zIndex: isDragging ? 1 : undefined,
  };
  return (
    <li
      ref={setNodeRef}
      style={style}
      className={
        isDragging
          ? 'flex items-center gap-2 rounded-lg border border-cobalt bg-background px-2 py-1.5 shadow-sm'
          : 'flex items-center gap-2 rounded-lg border border-border bg-background px-2 py-1.5'
      }
    >
      <button
        type="button"
        aria-label="Drag to reorder"
        className="cursor-grab touch-none rounded p-1 text-muted-foreground hover:bg-muted active:cursor-grabbing"
        {...attributes}
        {...listeners}
      >
        <GripVertical className="h-4 w-4" strokeWidth={1.5} />
      </button>
      <span className="w-5 text-center text-xs tabular-nums text-muted-foreground">{index + 1}</span>
      <span className="flex-1 truncate text-sm text-foreground">{label}</span>
      <button
        type="button"
        aria-label="Remove column"
        onClick={onRemove}
        className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-destructive"
      >
        <X className="h-4 w-4" strokeWidth={1.5} />
      </button>
    </li>
  );
}

export default function ColumnOrderPicker({
  columns,
  value,
  onChange,
  label = 'Columns',
}: ColumnOrderPickerProps) {
  const allKeys = columns.map((c) => c.key);
  // Empty selection means "all, default order" — materialize for display.
  const selectedKeys = value.length > 0 ? value.filter((k) => allKeys.includes(k)) : allKeys;
  const available = columns.filter((c) => !selectedKeys.includes(c.key));
  const labelFor = (key: string) => columns.find((c) => c.key === key)?.label ?? key;

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const from = selectedKeys.indexOf(String(active.id));
    const to = selectedKeys.indexOf(String(over.id));
    if (from === -1 || to === -1) return;
    // Reordering materializes the full ordered list (arrayMove on selectedKeys).
    onChange(arrayMove(selectedKeys, from, to));
  };

  const remove = (key: string) => onChange(selectedKeys.filter((k) => k !== key));
  const add = (key: string) => onChange([...selectedKeys, key]);

  return (
    <div className="space-y-2">
      <span className="text-sm font-medium text-foreground">{label}</span>

      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext items={selectedKeys} strategy={verticalListSortingStrategy}>
          <ul className="space-y-1">
            {selectedKeys.map((key, index) => (
              <SortableRow
                key={key}
                id={key}
                index={index}
                label={labelFor(key)}
                onRemove={() => remove(key)}
              />
            ))}
          </ul>
        </SortableContext>
      </DndContext>

      {available.length > 0 && (
        <div className="space-y-1.5">
          <span className="text-xs text-muted-foreground">Add a column</span>
          <div className="flex flex-wrap gap-1.5">
            {available.map((c) => (
              <button
                key={c.key}
                type="button"
                onClick={() => add(c.key)}
                className="inline-flex items-center gap-1 rounded-full border border-border px-2.5 py-1 text-xs text-muted-foreground hover:bg-muted"
              >
                <Plus className="h-3 w-3" strokeWidth={1.5} />
                {c.label}
              </button>
            ))}
          </div>
        </div>
      )}

      <p className="text-xs text-muted-foreground">
        Drag to reorder. Remove all to show every column in the default order.
      </p>
    </div>
  );
}

export type { ColumnOrderPickerProps, ColumnOption };
