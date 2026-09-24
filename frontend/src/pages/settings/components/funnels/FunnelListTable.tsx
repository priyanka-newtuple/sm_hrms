import type { ColumnDef } from '@tanstack/react-table';
import { Plus, MoreVertical, Copy, Download, Trash2 } from 'lucide-react';
import EmptyState from '../../../../core/components/EmptyState';
import { DataTable, DateCell, actionsColumn } from '@/core/components/DataTable';
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from '../../../../components/ui/dropdown-menu';
import { usePermissions } from '../../../../core/hooks/usePermissions';
import type { StateMachineRecord } from '../../../../core/types';
import { downloadJson } from '../../../../lib/export/download';
import { normalizeStateMachineRecord } from '../../../funnel/canvas/utils/smNormalizers';

interface FunnelListTableProps {
  records: StateMachineRecord[];
  totalRecords: number;
  onSelect: (record: StateMachineRecord) => void;
  onCreate: (mode: 'canvas' | 'wizard') => void;
  onDuplicate?: (record: StateMachineRecord) => void;
  onDelete?: (record: StateMachineRecord) => void;
}

function relativeTime(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60_000);
  const hours = Math.floor(diff / 3_600_000);
  const days = Math.floor(diff / 86_400_000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  if (hours < 24) return `${hours}h ago`;
  if (days < 30) return `${days}d ago`;
  return new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function initials(name: string): string {
  return name
    .split(/[\s_-]+/)
    .slice(0, 2)
    .map(w => w[0]?.toUpperCase() ?? '')
    .join('');
}

function workflowExportFilename(record: StateMachineRecord): string {
  const machineName = record.machine_name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '') || 'workflow';
  const version = record.version === 0 ? 'draft' : `v${record.version}`;
  return `${machineName}-${version}.json`;
}

function exportWorkflow(record: StateMachineRecord): void {
  downloadJson(normalizeStateMachineRecord(record), workflowExportFilename(record));
}

/**
 * Tabular list view for workflows (state machines).
 *
 * Renders a responsive table of workflow records with name, status,
 * version, last-edited timestamp, owner avatar, and a per-row action
 * menu (Duplicate / Export JSON / Delete). Shows a global empty state
 * when there are no workflows at all, and an inline "no matches" row
 * when filters hide every record.
 *
 * @param props - {@link FunnelListTableProps}
 * @param props.records - filtered workflow records to display.
 * @param props.totalRecords - unfiltered total; drives the global empty state.
 * @param props.onSelect - called when a row is clicked.
 * @param props.onCreate - called from the empty-state CTA to start a new workflow.
 * @param props.onDuplicate - optional handler for the row's Duplicate action.
 * @param props.onDelete - optional handler for the row's Delete action.
 */
export default function FunnelListTable({
  records,
  totalRecords,
  onSelect,
  onCreate,
  onDuplicate,
  onDelete,
}: FunnelListTableProps) {
  const { hasPermission } = usePermissions();
  const canWrite = hasPermission('workflow:write');

  if (totalRecords === 0) {
    return (
      <EmptyState
        description="No workflows yet"
        action={
          canWrite ? (
            <button
              onClick={() => onCreate('wizard')}
              className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90 transition-colors"
            >
              <Plus className="w-4 h-4" />
              Create your first workflow
            </button>
          ) : undefined
        }
      />
    );
  }

  const columns: ColumnDef<StateMachineRecord, unknown>[] = [
    {
      id: 'name',
      header: 'Name',
      accessorFn: (record) => record.name || record.machine_name,
      cell: ({ row }) => (
        <div className="min-w-0">
          <p className="font-semibold text-foreground">
            {row.original.name || row.original.machine_name}
          </p>
          {row.original.description && (
            <p className="mt-0.5 line-clamp-1 text-sm text-muted-foreground">
              {row.original.description}
            </p>
          )}
          <p className="mt-0.5 font-mono text-xs text-muted-foreground/60">
            {row.original.machine_name}
          </p>
        </div>
      ),
    },
    {
      id: 'status',
      header: 'Status',
      accessorFn: (record) => (record.is_active ? 'Active' : 'Draft'),
      cell: ({ row }) =>
        row.original.is_active ? (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-foreground px-2.5 py-1 text-xs font-semibold text-background">
            <span className="inline-block size-1.5 rounded-full bg-success" />
            Active
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5 rounded-full border border-warning/30 bg-warning/10 px-2.5 py-1 text-xs font-semibold text-warning">
            <span className="inline-block size-1.5 rounded-full bg-warning" />
            Draft
          </span>
        ),
      meta: { width: '8rem' },
    },
    {
      id: 'version',
      header: 'Ver.',
      accessorFn: (record) => record.version,
      cell: ({ row }) => (
        <span className="font-mono text-sm text-muted-foreground">v{row.original.version}</span>
      ),
      meta: { hideBelow: 'md', width: '6rem' },
    },
    {
      id: 'edited',
      header: 'Edited',
      accessorFn: (record) => record.created_at,
      cell: ({ row }) => <DateCell>{relativeTime(row.original.created_at)}</DateCell>,
      meta: { hideBelow: 'md', width: '8rem' },
    },
    {
      id: 'owner',
      header: 'Owner',
      enableSorting: false,
      cell: ({ row }) =>
        row.original.created_by_name ? (
          <div
            title={row.original.created_by_name}
            className="flex size-7 items-center justify-center rounded-full bg-primary/80 text-[10px] font-semibold text-primary-foreground"
          >
            {initials(row.original.created_by_name)}
          </div>
        ) : (
          <span className="text-sm text-muted-foreground/60">—</span>
        ),
      meta: { hideBelow: 'lg', width: '7rem' },
    },
    actionsColumn<StateMachineRecord>({
      width: '3rem',
      alwaysVisible: true,
      render: (record) => (
        <DropdownMenu>
          <DropdownMenuTrigger
            onClick={(e) => e.stopPropagation()}
            className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
          >
            <MoreVertical className="size-4" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem
              onClick={(e) => { e.stopPropagation(); onDuplicate?.(record); }}
              disabled={!canWrite}
            >
              <Copy />
              Duplicate
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={(e) => { e.stopPropagation(); exportWorkflow(record); }}
            >
              <Download />
              Export JSON
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onClick={(e) => { e.stopPropagation(); onDelete?.(record); }}
              disabled={!canWrite}
              className="text-destructive focus:bg-destructive/10 focus:text-destructive"
            >
              <Trash2 />
              Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      ),
    }),
  ];

  return (
    <DataTable
      label="Workflows"
      data={records}
      columns={columns}
      getRowId={(record) => record.id ?? `${record.machine_name}-${record.version}`}
      onRowClick={onSelect}
      emptyState={{ title: 'No workflows match your filters.' }}
    />
  );
}
