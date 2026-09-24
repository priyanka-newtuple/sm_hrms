import { useMemo } from 'react';
import type { ColumnDef } from '@tanstack/react-table';

import { DateCell } from '@/core/components/DataTable';
import ChangeCell from './ChangeCell';
import { formatFieldLabel, type FieldChangeRow } from './lib';

type Options = {
  onOpenRecord: (row: FieldChangeRow) => void;
  isRecordLinkable: (row: FieldChangeRow) => boolean;
  resolveUserName: (userId: unknown) => string;
};

function RecordCell({
  row,
  isLinkable,
  onOpen,
}: {
  row: FieldChangeRow;
  isLinkable: boolean;
  onOpen: () => void;
}) {
  const label = row.entityIdentifier ?? row.entityId ?? '—';
  return (
    <span className="flex flex-wrap items-baseline gap-x-2">
      {isLinkable ? (
        <button type="button" onClick={onOpen} className="text-left text-cobalt hover:underline">
          {label}
        </button>
      ) : (
        <span>{label}</span>
      )}
      {row.entityType && <span className="text-xs text-muted-foreground">{row.entityType}</span>}
    </span>
  );
}

/** Column definitions for the Logs table. */
export function useFieldChangeColumns({
  onOpenRecord,
  isRecordLinkable,
  resolveUserName,
}: Options): ColumnDef<FieldChangeRow, unknown>[] {
  return useMemo(
    () => [
      {
        id: 'when',
        header: 'When',
        size: 180,
        cell: ({ row }) => (
          <DateCell>
            {row.original.occurredAt ? new Date(row.original.occurredAt).toLocaleString() : ''}
          </DateCell>
        ),
      },
      {
        id: 'who',
        header: 'Who',
        size: 180,
        cell: ({ row }) => row.original.actorName ?? '—',
      },
      {
        id: 'record',
        header: 'Record',
        size: 220,
        cell: ({ row }) => (
          <RecordCell
            row={row.original}
            isLinkable={isRecordLinkable(row.original)}
            onOpen={() => onOpenRecord(row.original)}
          />
        ),
      },
      {
        id: 'field',
        header: 'Field',
        size: 160,
        cell: ({ row }) => (row.original.fieldKey ? formatFieldLabel(row.original.fieldKey) : '—'),
      },
      {
        id: 'change',
        header: 'Change',
        cell: ({ row }) => (
          <ChangeCell
            row={row.original}
            isExpanded={row.getIsExpanded()}
            onToggle={() => row.toggleExpanded()}
            resolveUserName={resolveUserName}
          />
        ),
      },
    ],
    [isRecordLinkable, onOpenRecord, resolveUserName],
  );
}
