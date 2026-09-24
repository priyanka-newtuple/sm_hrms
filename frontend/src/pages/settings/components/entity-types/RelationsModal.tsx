import { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertCircle, ArrowRight, Link2, Loader2, Plus, Trash2, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useWorkflowFieldsByEntityType } from '@/shared/hooks';
import { entityRelations, formSchemas as formSchemasApi } from '../../../../core/services/api';
import type {
  EntityType,
  FormSchema,
  RelationDeclaration,
  RelationMode,
} from '../../../../core/types';
import RelationFieldMappings from './RelationFieldMappings';

type Props = {
  entityType: EntityType;
  allTypes: EntityType[];
  canWrite: boolean;
  onClose: () => void;
};

const typeId = (t: EntityType) => t.entity_type_id ?? t.id;

const MODE_OPTIONS: Array<{ value: RelationMode; label: string; description: string }> = [
  {
    value: 'REFERENCE',
    label: 'Live link',
    description:
      'Target records must link a source record at creation. Linked fields stay in sync and are read-only on the target.',
  },
  {
    value: 'SNAPSHOT',
    label: 'Copy at creation',
    description:
      "Linking is optional. Field values are copied when linked and don't change afterward.",
  },
];

export default function RelationsModal({ entityType, allTypes, canWrite, onClose }: Props) {
  const [declarations, setDeclarations] = useState<RelationDeclaration[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [showCreate, setShowCreate] = useState(false);
  const [otherTypeId, setOtherTypeId] = useState('');
  const [currentIsProvider, setCurrentIsProvider] = useState(true);
  const [mode, setMode] = useState<RelationMode>('REFERENCE');
  const [includeRelatedFiles, setIncludeRelatedFiles] = useState(false);
  const [saving, setSaving] = useState(false);

  // Source-field options for the mapping editor: Forms plus the Method-Block
  // fields on each type's published workflow.
  const [allFormSchemas, setAllFormSchemas] = useState<FormSchema[]>([]);
  const workflowFieldsByEntityType = useWorkflowFieldsByEntityType();

  const [deleteTarget, setDeleteTarget] = useState<RelationDeclaration | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [updatingRelatedFilesId, setUpdatingRelatedFilesId] = useState<string | null>(null);

  const selfId = typeId(entityType);
  const nameById = useMemo(() => {
    const map = new Map<string, string>();
    for (const t of allTypes) map.set(typeId(t), t.name);
    return map;
  }, [allTypes]);
  const otherTypes = useMemo(
    () => allTypes.filter((t) => typeId(t) !== selfId && t.is_active),
    [allTypes, selfId],
  );

  useEffect(() => {
    let cancelled = false;
    void formSchemasApi
      .list()
      .then((res) => {
        if (!cancelled) setAllFormSchemas((res.items ?? []).filter((schema) => schema.is_active));
      })
      .catch(() => {
        // The mapping editor degrades to workflow fields only.
        if (!cancelled) setAllFormSchemas([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const fetchDeclarations = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await entityRelations.listDeclarations(selfId, 'both');
      setDeclarations(res.items ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load relations');
    } finally {
      setLoading(false);
    }
  }, [selfId]);

  const saveMetadata = useCallback(
    async (declaration: RelationDeclaration, metadata: Record<string, unknown>) => {
      setError(null);
      try {
        await entityRelations.updateMapping(declaration.relation_def_id, metadata);
        await fetchDeclarations();
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to update field mappings');
        throw e;
      }
    },
    [fetchDeclarations],
  );

  useEffect(() => {
    void fetchDeclarations();
  }, [fetchDeclarations]);

  const handleCreate = async () => {
    if (!otherTypeId || saving) return;
    setSaving(true);
    setError(null);
    try {
      const fromId = currentIsProvider ? selfId : otherTypeId;
      const toId = currentIsProvider ? otherTypeId : selfId;
      await entityRelations.createDeclaration(fromId, {
        to_entity_type_id: toId,
        relation_type: mode,
        relation_metadata: includeRelatedFiles
          ? {
              related_files: {
                enabled: true,
                include_file_type_ids: [],
                group_by: 'source_entity',
              },
            }
          : {},
      });
      setShowCreate(false);
      setOtherTypeId('');
      setMode('REFERENCE');
      setIncludeRelatedFiles(false);
      await fetchDeclarations();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create relation');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget || deleting) return;
    setDeleting(true);
    setError(null);
    try {
      // Legacy named relations exist as forward+reverse row pairs; the legacy
      // endpoint removes both. Declarations (no relation_name) are single
      // directed rows and soft-delete individually.
      if (deleteTarget.relation_name) {
        await entityRelations.deleteLegacyRelation(
          deleteTarget.from_entity_type_id,
          deleteTarget.relation_def_id,
        );
      } else {
        await entityRelations.deleteDeclaration(deleteTarget.relation_def_id);
      }
      setDeleteTarget(null);
      await fetchDeclarations();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete relation');
    } finally {
      setDeleting(false);
    }
  };

  const relatedFilesEnabled = (declaration: RelationDeclaration) => {
    const config = declaration.relation_metadata?.related_files;
    return Boolean(config && typeof config === 'object' && (config as Record<string, unknown>).enabled);
  };

  const stringFieldMappingCount = (declaration: RelationDeclaration) =>
    Object.values(declaration.relation_metadata ?? {}).filter((value) => typeof value === 'string').length;

  const toggleRelatedFiles = async (declaration: RelationDeclaration, enabled: boolean) => {
    if (!canWrite || updatingRelatedFilesId) return;
    setUpdatingRelatedFilesId(declaration.relation_def_id);
    setError(null);
    try {
      const metadata = { ...(declaration.relation_metadata ?? {}) };
      if (enabled) {
        metadata.related_files = {
          enabled: true,
          include_file_type_ids: [],
          group_by: 'source_entity',
        };
      } else {
        delete metadata.related_files;
      }
      await entityRelations.updateMapping(declaration.relation_def_id, metadata);
      await fetchDeclarations();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to update related files');
    } finally {
      setUpdatingRelatedFilesId(null);
    }
  };

  return (
    <div
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      role="dialog"
      aria-modal="true"
      aria-labelledby="relations-modal-title"
    >
      <div className="bg-card rounded-xl shadow-xl w-full max-w-2xl mx-4 max-h-[85vh] flex flex-col">
        <div className="flex items-center justify-between p-4 border-b border-border">
          <div className="flex items-center gap-2">
            <Link2 className="w-5 h-5 text-muted-foreground" aria-hidden="true" />
            <h3 id="relations-modal-title" className="text-lg font-semibold text-foreground">
              Relations for{' '}
              <code className="bg-muted px-1.5 py-0.5 rounded text-sm">{entityType.name}</code>
            </h3>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close">
            <X className="w-5 h-5" aria-hidden="true" />
          </Button>
        </div>

        <div className="p-4 space-y-4 overflow-y-auto">
          {error && (
            <div
              className="flex items-start gap-2 px-3 py-2 bg-destructive-subtle border border-destructive/30 rounded-lg text-sm text-destructive"
              role="alert"
            >
              <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" aria-hidden="true" />
              <span>{error}</span>
            </div>
          )}

          {loading ? (
            <div className="flex items-center justify-center py-8" aria-live="polite">
              <Loader2 className="w-6 h-6 text-primary animate-spin" aria-hidden="true" />
              <span className="sr-only">Loading relations</span>
            </div>
          ) : declarations.length === 0 && !showCreate ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              No relations defined. Fields can flow between two entity types once a relation exists.
            </p>
          ) : (
            <ul className="space-y-2">
              {declarations.map((d) => {
                const fieldCount = stringFieldMappingCount(d);
                const relatedEnabled = relatedFilesEnabled(d);
                return (
                  <li
                    key={d.relation_def_id}
                    className="rounded-lg border border-border px-3 py-2"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex min-w-0 flex-wrap items-center gap-2 text-sm text-foreground">
                          <code className="bg-muted px-1.5 py-0.5 rounded text-xs">
                            {nameById.get(d.from_entity_type_id) ?? d.from_entity_type_id}
                          </code>
                          <ArrowRight className="w-4 h-4 text-muted-foreground flex-shrink-0" aria-hidden="true" />
                          <code className="bg-muted px-1.5 py-0.5 rounded text-xs">
                            {nameById.get(d.to_entity_type_id) ?? d.to_entity_type_id}
                          </code>
                          <span
                            className={`ml-2 inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                              d.relation_type === 'REFERENCE'
                                ? 'bg-info-subtle text-info'
                                : 'bg-warning-subtle text-warning'
                            }`}
                          >
                            {d.relation_type === 'REFERENCE' ? 'Live link' : 'Copy at creation'}
                          </span>
                          {relatedEnabled && (
                            <span className="inline-flex items-center rounded-full bg-success-subtle px-2 py-0.5 text-xs font-medium text-success">
                              related files
                            </span>
                          )}
                          {d.relation_name && (
                            <span
                              className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-muted text-muted-foreground"
                              title={`Legacy named relation “${d.relation_name}” — created with the older API as a two-directional pair`}
                            >
                              legacy
                            </span>
                          )}
                          <span className="text-xs text-muted-foreground">
                            {fieldCount} {fieldCount === 1 ? 'field' : 'fields'}
                          </span>
                        </div>
                        {!d.relation_name && (
                          <label className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
                            <input
                              type="checkbox"
                              checked={relatedEnabled}
                              disabled={!canWrite || updatingRelatedFilesId === d.relation_def_id}
                              onChange={(e) => void toggleRelatedFiles(d, e.target.checked)}
                            />
                            <span>Show files from the source entity in a read-only Related files section</span>
                          </label>
                        )}
                        <RelationFieldMappings
                          declaration={d}
                          sourceEntityName={nameById.get(d.from_entity_type_id) ?? ''}
                          targetEntityName={nameById.get(d.to_entity_type_id) ?? ''}
                          formSchemas={allFormSchemas}
                          workflowFieldsByEntityType={workflowFieldsByEntityType}
                          canWrite={canWrite}
                          onSave={(metadata) => saveMetadata(d, metadata)}
                        />
                      </div>
                      <Button
                        variant="ghost-danger"
                        size="icon"
                        onClick={() => setDeleteTarget(d)}
                        disabled={!canWrite}
                        aria-label="Delete relation"
                        title="Delete"
                      >
                        <Trash2 className="w-4 h-4" aria-hidden="true" />
                      </Button>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}

          {showCreate && (
            <div className="rounded-lg border border-border p-3 space-y-3">
              <div>
                <label
                  htmlFor="relation-other-type"
                  className="block text-sm font-medium text-foreground mb-1"
                >
                  Related entity type
                </label>
                <select
                  id="relation-other-type"
                  value={otherTypeId}
                  onChange={(e) => setOtherTypeId(e.target.value)}
                  className="w-full px-3 py-2 border border-border rounded-lg text-sm"
                >
                  <option value="">Select a type…</option>
                  {otherTypes.map((t) => (
                    <option key={typeId(t)} value={typeId(t)}>
                      {t.name}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <span className="block text-sm font-medium text-foreground mb-1">Direction</span>
                <label className="flex items-center gap-2 text-sm text-foreground">
                  <input
                    type="radio"
                    name="relation-direction"
                    checked={currentIsProvider}
                    onChange={() => setCurrentIsProvider(true)}
                  />
                  <span>
                    <code className="bg-muted px-1 rounded text-xs">{entityType.name}</code>{' '}
                    provides fields to the related type
                  </span>
                </label>
                <label className="flex items-center gap-2 text-sm text-foreground mt-1">
                  <input
                    type="radio"
                    name="relation-direction"
                    checked={!currentIsProvider}
                    onChange={() => setCurrentIsProvider(false)}
                  />
                  <span>
                    <code className="bg-muted px-1 rounded text-xs">{entityType.name}</code>{' '}
                    receives fields from the related type
                  </span>
                </label>
              </div>

              <div>
                <span className="block text-sm font-medium text-foreground mb-1">Mode</span>
                {MODE_OPTIONS.map((opt) => (
                  <label key={opt.value} className="flex items-start gap-2 text-sm text-foreground mt-1">
                    <input
                      type="radio"
                      name="relation-mode"
                      checked={mode === opt.value}
                      onChange={() => setMode(opt.value)}
                      className="mt-0.5"
                    />
                    <span>
                      <span className="font-medium">{opt.label}</span>
                      <span className="block text-xs text-muted-foreground">{opt.description}</span>
                    </span>
                  </label>
                ))}
              </div>

              <label className="flex items-start gap-2 rounded-lg border border-border p-3 text-sm text-foreground">
                <input
                  type="checkbox"
                  checked={includeRelatedFiles}
                  onChange={(e) => setIncludeRelatedFiles(e.target.checked)}
                  className="mt-0.5"
                />
                <span>
                  <span className="font-medium">Include files in this relationship</span>
                  <span className="block text-xs text-muted-foreground">
                    Show source entity files in a read-only Related files section on the target entity.
                  </span>
                </span>
              </label>

              <div className="flex justify-end gap-2">
                <Button
                  variant="ghost"
                  onClick={() => {
                    setShowCreate(false);
                    setIncludeRelatedFiles(false);
                  }}
                  disabled={saving}
                >
                  Cancel
                </Button>
                <Button
                  variant="primary"
                  onClick={() => void handleCreate()}
                  disabled={!otherTypeId || saving}
                  loading={saving}
                >
                  Create relation
                </Button>
              </div>
            </div>
          )}

          {deleteTarget && (
            <div className="rounded-lg border border-destructive/30 bg-destructive-subtle p-3 space-y-2">
              <p className="text-sm text-destructive">
                {deleteTarget.relation_name
                  ? 'Delete this legacy relation? Both directions of the pair will be removed permanently.'
                  : 'Delete this relation? Reference fields already added to forms will stop resolving values.'}
              </p>
              <div className="flex justify-end gap-2">
                <Button variant="ghost" onClick={() => setDeleteTarget(null)} disabled={deleting}>
                  Cancel
                </Button>
                <Button variant="primary" onClick={() => void handleDelete()} loading={deleting}>
                  Delete
                </Button>
              </div>
            </div>
          )}
        </div>

        <div className="flex items-center justify-between p-4 border-t border-border bg-muted/50 rounded-b-xl">
          <span className="text-xs text-muted-foreground">
            Fields carried over are set per relation above.
          </span>
          <Button
            variant="ghost"
            onClick={() => setShowCreate(true)}
            icon={<Plus className="w-4 h-4" aria-hidden="true" />}
            disabled={!canWrite || showCreate}
          >
            New Relation
          </Button>
        </div>
      </div>
    </div>
  );
}
