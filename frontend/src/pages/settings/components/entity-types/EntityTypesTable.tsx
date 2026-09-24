import type { ColumnDef } from '@tanstack/react-table';
import { AlertCircle, Link2, Pencil, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { DataTable, actionsColumn } from '@/core/components/DataTable';
import { hasIdentifierTemplate } from '@/shared/utils/entityForm';
import type { EntityType, FormSchema } from '../../../../core/types';
import { fieldsForEntityType, missingIdentifierTokens } from './entityTypeFields';

interface EntityTypesTableProps {
  types: EntityType[];
  schemas: FormSchema[];
  canWrite: boolean;
  onEdit: (entityType: EntityType) => void;
  onDelete: (entityType: EntityType) => void;
  onRelations: (entityType: EntityType) => void;
}

export default function EntityTypesTable({
  types,
  schemas,
  canWrite,
  onEdit,
  onDelete,
  onRelations,
}: EntityTypesTableProps) {
  const typeNames = new Set(types.map((t) => t.name.toLowerCase()));

  /** Identifier-template tokens that don't resolve against the type's known fields. */
  const missingTokensFor = (entityType: EntityType): string[] => {
    const knownFields = new Set(
      fieldsForEntityType(schemas, entityType.name).map((field) => field.id.toLowerCase()),
    );
    // ponytail: lenient badge — any `<existing_type>_identifier` token
    // counts as resolvable without fetching per-type declarations.
    return missingIdentifierTokens(
      String(entityType.schema_definition?.identifier_template ?? ''),
      knownFields,
      typeNames,
    );
  };

  const columns: ColumnDef<EntityType, unknown>[] = [
    {
      id: 'name',
      header: 'Name',
      accessorFn: (entityType) => entityType.name,
      cell: ({ row }) => {
        const missing = missingTokensFor(row.original);
        return (
          <div className="flex items-center gap-2">
            <code className="rounded bg-muted px-2 py-1 font-mono text-xs text-foreground/85">
              {row.original.name}
            </code>
            {hasIdentifierTemplate(row.original.schema_definition) && missing.length > 0 && (
              <span
                className="inline-flex items-center gap-1 rounded-full bg-warning-subtle px-2 py-0.5 text-xs font-medium text-warning"
                title={`Identifier template references missing fields: ${missing.join(', ')}`}
              >
                <AlertCircle className="size-3" /> template
              </span>
            )}
          </div>
        );
      },
    },
    {
      id: 'description',
      header: 'Description',
      accessorFn: (entityType) => entityType.description ?? '',
      cell: ({ row }) => (
        <span className="text-muted-foreground">{row.original.description || '—'}</span>
      ),
    },
    {
      id: 'status',
      header: 'Status',
      accessorFn: (entityType) => (entityType.is_active ? 'Active' : 'Archived'),
      cell: ({ row }) => (
        <span
          className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
            row.original.is_active
              ? 'bg-success-subtle text-success'
              : 'bg-muted text-muted-foreground'
          }`}
        >
          {row.original.is_active ? 'Active' : 'Archived'}
        </span>
      ),
      meta: { width: '8rem' },
    },
    actionsColumn<EntityType>({
      width: '9rem',
      alwaysVisible: true,
      render: (entityType) => (
        <>
          <Button
            variant="ghost"
            size="icon"
            type="button"
            onClick={() => onRelations(entityType)}
            aria-label={`Relations for ${entityType.name}`}
            title="Relations"
          >
            <Link2 className="size-4" aria-hidden="true" />
          </Button>

          <Button
            variant="ghost-danger"
            size="icon"
            type="button"
            onClick={() => onDelete(entityType)}
            disabled={!canWrite}
            aria-label={`Delete ${entityType.name}`}
            title="Delete"
          >
            <Trash2 className="size-4" aria-hidden="true" />
          </Button>

          <Button
            variant="primary"
            type="button"
            onClick={() => onEdit(entityType)}
            className="rounded bg-secondary p-2 text-muted-foreground transition-colors hover:bg-primary/5 hover:text-primary"
            aria-label={`Edit ${entityType.name}`}
            title="Edit"
            disabled={!canWrite}
          >
            <Pencil className="size-4" aria-hidden="true" />
          </Button>
        </>
      ),
    }),
  ];

  return (
    <DataTable
      label="Entity types"
      data={types}
      columns={columns}
      getRowId={(entityType) => entityType.id ?? entityType.name}
      emptyState={{ title: 'No entity types yet' }}
    />
  );
}
