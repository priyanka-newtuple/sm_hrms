import type { ColumnDef } from '@tanstack/react-table';
import { Calendar, Eye, GitBranch, Loader2, Pencil, Tag, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { DataTable, DataTableToolbar, DateCell, actionsColumn } from '@/core/components/DataTable';
import ColumnVisibilityMenu from '@/shared/components/ColumnVisibilityMenu';
import type { WorkflowEntityState } from '../../../../core/services/api';
import type { FormSchema } from '../../../../core/types';
import { deriveEntityDisplayName, displayEntityType, formatDate } from '../helpers';
import { resolveStateLabel } from '../../../../shared/utils/labels';
import { useEntityColumns } from '../useEntityColumns';
import { formatDetailValue } from './entityFieldUtils';

interface EntityTableProps {
  entities: WorkflowEntityState[];
  schemaForEntity: (entity: WorkflowEntityState) => FormSchema | null;
  deletingEntityId: string | null;
  onEdit: (entity: WorkflowEntityState) => void;
  onDelete: (entity: WorkflowEntityState) => void;
  canEdit?: boolean;
  canDelete?: boolean;
  canView?: boolean;
  /** Scopes the persisted column choice, so each entity type keeps its own. */
  columnScope: string;
}

export default function EntityTable({
  entities,
  schemaForEntity,
  deletingEntityId,
  onEdit,
  onDelete,
  canEdit = true,
  canDelete = true,
  canView = true,
  columnScope,
}: EntityTableProps) {
  const { allFields, effectiveIds, visibleCustomFields, toggleField, formFieldFor } =
    useEntityColumns(entities, schemaForEntity, columnScope);

  const standardColumns: Record<string, ColumnDef<WorkflowEntityState, unknown>> = {
    'std:name': {
      id: 'std:name',
      header: 'Name',
      enableSorting: false,
      cell: ({ row }) => (
        <div className="flex flex-col leading-tight">
          <span className="font-medium text-foreground">
            {deriveEntityDisplayName(row.original, schemaForEntity(row.original))}
          </span>
          <span className="font-mono text-xs text-muted-foreground">
            {row.original.entity_id.slice(0, 8)}
          </span>
        </div>
      ),
      meta: { width: '13rem' },
    },
    'std:type': {
      id: 'std:type',
      header: 'Type',
      enableSorting: false,
      cell: ({ row }) => (
        <span className="inline-flex items-center gap-1.5 rounded-full bg-cobalt/8 px-2 py-0.5 text-xs font-medium text-cobalt">
          <Tag className="size-3" />
          {displayEntityType(row.original.entity_type)}
        </span>
      ),
      meta: { width: '10rem' },
    },
    'std:state': {
      id: 'std:state',
      header: 'State',
      enableSorting: false,
      cell: ({ row }) => (
        <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
          <GitBranch className="size-3" />
          {resolveStateLabel(row.original.current_state)}
        </span>
      ),
      meta: { width: '8rem' },
    },
    'std:created': {
      id: 'std:created',
      header: 'Created',
      enableSorting: false,
      cell: ({ row }) => (
        <DateCell>
          <span className="inline-flex items-center gap-1">
            <Calendar className="size-3" />
            {formatDate(row.original.created_at)}
          </span>
        </DateCell>
      ),
      meta: { width: '9rem' },
    },
  };

  const columns: ColumnDef<WorkflowEntityState, unknown>[] = [
    ...effectiveIds.flatMap((id) => (standardColumns[id] ? [standardColumns[id]] : [])),
    ...visibleCustomFields.map<ColumnDef<WorkflowEntityState, unknown>>((field) => ({
      id: field.field,
      header: field.label,
      enableSorting: false,
      cell: ({ row }) => (
        <span className="block truncate text-[13px] text-foreground/80">
          {formatDetailValue(
            formFieldFor(row.original, field.field),
            row.original.data[field.field],
          )}
        </span>
      ),
      meta: { width: '12rem' },
    })),
    actionsColumn<WorkflowEntityState>({
      width: '7rem',
      // Edit/delete are this screen's primary affordances — keep them visible.
      alwaysVisible: true,
      render: (entity) => (
        <>
          {canEdit ? (
            <Button
              variant="ghost-action"
              size="icon"
              onClick={() => onEdit(entity)}
              title="Edit entity"
            >
              <Pencil className="size-4" />
            </Button>
          ) : canView ? (
            <Button
              variant="ghost-action"
              size="icon"
              onClick={() => onEdit(entity)}
              title="View entity"
            >
              <Eye className="size-4" />
            </Button>
          ) : null}
          {canDelete && (
            <Button
              variant="ghost-danger"
              size="icon"
              onClick={() => onDelete(entity)}
              disabled={deletingEntityId === entity.entity_id}
              title="Delete entity"
            >
              {deletingEntityId === entity.entity_id ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Trash2 className="size-4" />
              )}
            </Button>
          )}
        </>
      ),
    }),
  ];

  return (
    <DataTable
      label="Records"
      data={entities}
      columns={columns}
      getRowId={(entity) => entity.entity_id}
      enableSorting={false}
      toolbar={
        <DataTableToolbar
          right={
            <ColumnVisibilityMenu
              fields={allFields}
              selectedIds={effectiveIds}
              visibleCount={effectiveIds.length}
              onToggle={toggleField}
            />
          }
        />
      }
      emptyState={{ title: 'No records yet' }}
    />
  );
}
