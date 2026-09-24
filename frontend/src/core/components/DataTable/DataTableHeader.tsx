import { horizontalListSortingStrategy, SortableContext, useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { flexRender, type Header, type Table } from '@tanstack/react-table';

import { cn } from '@/lib/utils';
import { TableHead, TableHeader, TableRow } from '@/components/ui/table';

import { SortableHeaderLabel } from './SortableHeaderLabel';
import { columnClasses, reorderableIds, type DataTableColumnMeta } from './utils';

/**
 * Header content. A plain string header on a sortable column is wrapped in
 * {@link SortableHeaderLabel} automatically, so consumers only reach for it
 * when they need custom header markup.
 */
function HeaderContent<T>({ header }: { header: Header<T, unknown> }) {
  if (header.isPlaceholder) return null;

  const { columnDef } = header.column;
  const meta = columnDef.meta as DataTableColumnMeta | undefined;

  if (typeof columnDef.header === 'string') {
    return (
      <SortableHeaderLabel
        column={header.column}
        icon={meta?.headerIcon}
        enrichable={meta?.enrichable}
      >
        {columnDef.header}
      </SortableHeaderLabel>
    );
  }

  return <>{flexRender(columnDef.header, header.getContext())}</>;
}

function headCellClass(meta: DataTableColumnMeta | undefined, stickyHeader?: boolean): string {
  return cn(
    columnClasses(meta, 'head'),
    // `border-collapse` drops a sticky cell's own border once it detaches, so the
    // header rule is drawn as an inset shadow that travels with the cell.
    stickyHeader && 'sticky top-0 z-10 bg-background shadow-[inset_0_-1px_0_var(--border)]',
    meta?.sticky && stickyHeader && 'z-20',
  );
}

function PlainHeadCell<T>({
  header,
  stickyHeader,
}: {
  header: Header<T, unknown>;
  stickyHeader?: boolean;
}) {
  const meta = header.column.columnDef.meta as DataTableColumnMeta | undefined;
  return (
    <TableHead style={{ width: meta?.width }} className={headCellClass(meta, stickyHeader)}>
      <HeaderContent header={header} />
    </TableHead>
  );
}

/** Head cell that can be dragged to reorder its column. */
function DraggableHeadCell<T>({
  header,
  stickyHeader,
}: {
  header: Header<T, unknown>;
  stickyHeader?: boolean;
}) {
  const meta = header.column.columnDef.meta as DataTableColumnMeta | undefined;
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: header.column.id,
  });

  return (
    <TableHead
      ref={setNodeRef}
      style={{ width: meta?.width, transform: CSS.Translate.toString(transform), transition }}
      className={cn(
        headCellClass(meta, stickyHeader),
        'cursor-grab select-none active:cursor-grabbing',
        isDragging && 'relative z-30 bg-primary/10 opacity-80',
      )}
      {...attributes}
      {...listeners}
    >
      <HeaderContent header={header} />
    </TableHead>
  );
}

export function DataTableHeader<T>({
  table,
  stickyHeader,
  enableColumnReorder,
}: {
  table: Table<T>;
  stickyHeader?: boolean;
  enableColumnReorder?: boolean;
}) {
  const sortableIds = enableColumnReorder ? reorderableIds(table) : [];

  const rows = table.getHeaderGroups().map((group) => (
    <TableRow key={group.id}>
      {group.headers.map((header) =>
        sortableIds.includes(header.column.id) ? (
          <DraggableHeadCell key={header.id} header={header} stickyHeader={stickyHeader} />
        ) : (
          <PlainHeadCell key={header.id} header={header} stickyHeader={stickyHeader} />
        ),
      )}
    </TableRow>
  ));

  if (!enableColumnReorder) return <TableHeader>{rows}</TableHeader>;

  // `SortableContext` renders no DOM of its own, so it is safe inside <table>.
  // The surrounding `DndContext` lives outside it (see ColumnReorderProvider).
  return (
    <SortableContext items={sortableIds} strategy={horizontalListSortingStrategy}>
      <TableHeader>{rows}</TableHeader>
    </SortableContext>
  );
}
