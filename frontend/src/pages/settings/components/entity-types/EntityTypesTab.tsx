import { useState } from 'react';
import { AlertCircle, Boxes, Loader2, Lock, Plus, RefreshCw } from 'lucide-react';
import { usePermissions } from '../../../../core/hooks/usePermissions';
import { useEntityTypeAdmin } from '../../../../core/hooks/useEntityTypeAdmin';
import type { EntityType } from '../../../../core/types';
import { Button } from '@/components/ui/button';
import RelationsModal from './RelationsModal';
import EntityTypesTable from './EntityTypesTable';
import EntityTypeEditorModal from './EntityTypeEditorModal';
import DeleteEntityTypeDialog from './DeleteEntityTypeDialog';

export default function EntityTypesTab() {
  const { types, schemas, loading, error, refresh, createType, updateType, deleteType } =
    useEntityTypeAdmin();

  // `{ entityType: null }` opens the editor in create mode; `null` closes it.
  const [editor, setEditor] = useState<{ entityType: EntityType | null } | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<EntityType | null>(null);
  const [relationsTarget, setRelationsTarget] = useState<EntityType | null>(null);

  const { hasPermission } = usePermissions();
  const canWrite = hasPermission('entity_record:write');

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Boxes className="w-5 h-5 text-muted-foreground" aria-hidden="true" />
            <h2 className="text-lg font-medium text-foreground">Entity Types</h2>
          </div>
          <p className="text-sm text-muted-foreground">
            Define the domain entities used across funnels and forms.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            onClick={() => void refresh()}
            disabled={loading}
            icon={<RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} aria-hidden="true" />}
          >
            Refresh
          </Button>

          <Button
            variant="ghost"
            onClick={() => setEditor({ entityType: null })}
            icon={<Plus className="w-4 h-4" aria-hidden="true" />}
            disabled={!canWrite}
          >
            New Entity Type
          </Button>
        </div>
      </div>

      {!canWrite && (
        <div className="mb-4 flex items-center gap-2 rounded-lg border border-warning/30 bg-warning-subtle p-3 text-warning text-sm">
          <Lock className="w-4 h-4 flex-shrink-0" />
          You have read-only access to Entity Types. Contact an admin to make changes.
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-12" aria-live="polite">
          <Loader2 className="w-8 h-8 text-primary animate-spin" aria-hidden="true" />
          <span className="sr-only">Loading entity types</span>
        </div>
      ) : error ? (
        <div className="flex flex-col items-center justify-center rounded-2xl border border-destructive/20 bg-card py-12 text-center">
          <AlertCircle className="mb-2 h-6 w-6 text-destructive" aria-hidden="true" />
          <p className="mb-4 text-destructive">{error}</p>
          <Button variant="primary" onClick={() => void refresh()}>
            Retry
          </Button>
        </div>
      ) : types.length === 0 ? (
        <div className="rounded-xl border border-border bg-card p-8 text-center">
          <Boxes className="mx-auto mb-3 w-12 h-12 text-muted-foreground/50" aria-hidden="true" />
          <p className="mb-1 text-muted-foreground">No entity types defined yet.</p>
          <p className="text-sm text-muted-foreground">
            Create one to use it in funnels and form schemas.
          </p>
        </div>
      ) : (
        <EntityTypesTable
          types={types}
          schemas={schemas}
          canWrite={canWrite}
          onEdit={(entityType) => setEditor({ entityType })}
          onDelete={(entityType) => setDeleteTarget(entityType)}
          onRelations={(entityType) => setRelationsTarget(entityType)}
        />
      )}

      {editor && (
        <EntityTypeEditorModal
          key={editor.entityType?.id ?? editor.entityType?.name ?? 'new'}
          entityType={editor.entityType}
          types={types}
          schemas={schemas}
          canWrite={canWrite}
          onClose={() => setEditor(null)}
          createType={createType}
          updateType={updateType}
        />
      )}

      {relationsTarget && (
        <RelationsModal
          entityType={relationsTarget}
          allTypes={types}
          canWrite={canWrite}
          onClose={() => setRelationsTarget(null)}
        />
      )}

      <DeleteEntityTypeDialog
        target={deleteTarget}
        canWrite={canWrite}
        onClose={() => setDeleteTarget(null)}
        deleteType={deleteType}
      />
    </div>
  );
}
