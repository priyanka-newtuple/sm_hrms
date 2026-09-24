import { DataTable } from '@/core/components/DataTable';
import TableChangeDetail from './TableChangeDetail';
import { useFieldChangeColumns } from './columns';
import { diffTableField, type FieldChangeRow } from './lib';

type Props = {
  /** Flattened rows from `toFieldChangeRows` — one per changed field, or one per
   *  lifecycle event (created, archived, assignee changed). */
  rows: FieldChangeRow[];
  isLoading: boolean;
  onOpenRecord: (row: FieldChangeRow) => void;
  isRecordLinkable: (row: FieldChangeRow) => boolean;
  resolveUserName: (userId: unknown) => string;
  pagination: { total: number; limit: number; offset: number; onChange: (offset: number) => void };
};

/** Logs table: one row per changed field, on the platform's shared DataTable. */
export function FieldChangeTable({
  rows,
  isLoading,
  onOpenRecord,
  isRecordLinkable,
  resolveUserName,
  pagination,
}: Props) {
  const columns = useFieldChangeColumns({ onOpenRecord, isRecordLinkable, resolveUserName });

  return (
    <DataTable
      label="Field changes"
      data={rows}
      columns={columns}
      getRowId={(row) => row.id}
      isLoading={isLoading}
      enableSorting={false}
      renderExpanded={(row) => <TableChangeDetail change={diffTableField(row.before, row.after)} />}
      getRowCanExpand={(row) => row.isTableField}
      serverPagination={pagination}
      emptyState={{
        title: 'No changes found',
        description: 'No field changes match these filters.',
      }}
    />
  );
}

export default FieldChangeTable;
