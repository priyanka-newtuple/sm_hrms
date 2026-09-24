import type { ReactNode } from 'react';
import {
  closestCenter,
  DndContext,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import type { Table } from '@tanstack/react-table';

import { currentColumnOrder } from './utils';

/**
 * Drag-and-drop context for column reordering.
 *
 * This must wrap the `<table>` element rather than live inside it: `DndContext`
 * renders its own accessibility nodes, and a `<div>` inside `<table>` is invalid
 * HTML that React refuses to nest.
 */
export function ColumnReorderProvider<T>({
  table,
  children,
}: {
  table: Table<T>;
  children: ReactNode;
}) {
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }));

  const handleDragEnd = ({ active, over }: DragEndEvent) => {
    if (!over || active.id === over.id) return;

    const current = currentColumnOrder(table);

    const from = current.indexOf(String(active.id));
    const to = current.indexOf(String(over.id));
    if (from < 0 || to < 0) return;

    const next = [...current];
    next.splice(to, 0, next.splice(from, 1)[0]);
    table.setColumnOrder(next);
  };

  return (
    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
      {children}
    </DndContext>
  );
}
