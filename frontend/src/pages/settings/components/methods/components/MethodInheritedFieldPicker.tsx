/**
 * MethodInheritedFieldPicker
 *
 * The Method editor's "Add from related entity". The Forms tab's
 * ReferencePickerModal does the same job for a Form, but writes the mapping
 * into the relation's `relation_metadata`, which makes the field appear on
 * every record of the target type. This picker instead adds the field to the
 * *method block* with `ownership='inherited'`, so only the workflows that pin
 * this block carry it, and the record shows it read-only from the linked
 * source record.
 *
 * Flow: pick which of the block's entity types this is for (skipped when the
 * block is tagged with one) → pick a related entity type, from the relation
 * declarations that target it → pick the source field → the matching Field
 * Library field is reused by key, or created as a text field when none exists.
 */

import { useEffect, useMemo, useState } from 'react';
import { Link2, Loader2, Plus, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  entityRelations,
  entityTypes as entityTypesApi,
  fieldLibrary,
  formSchemas,
} from '@/core/services/api';
import { request } from '@/core/services/api/client';
import type { MethodVersionField, RelationDeclaration } from '@/core/types';
import type { EntityField } from '@/lib/state-machine/types';
import { IDENTIFIER_FIELD_KEY } from '@/shared/utils/entityForm';
import type { InheritedFieldPick } from '../hooks/useMethodFields';

/** A field offered from the related entity type. */
interface SourceFieldOption {
  key: string;
  label: string;
  /** Field Library type code to create the target field with when no field of
   *  this key exists yet. */
  libraryType: string;
  /** Where this option was seen, for the hint under it. */
  origin: 'form' | 'workflow' | 'records' | 'identifier';
}

interface Props {
  /** Entity types the block is tagged with — the field is inherited *onto* one of them. */
  blockEntityTypes: string[];
  currentFields: MethodVersionField[];
  workflowFieldsByEntityType: Record<string, EntityField[]>;
  onAdd: (pick: InheritedFieldPick) => Promise<boolean>;
  onClose: () => void;
}

const FORM_TYPE_TO_LIBRARY: Record<string, string> = {
  text: 'text',
  textarea: 'textarea',
  email: 'email',
  phone: 'phone',
  number: 'integer',
  integer: 'integer',
  date: 'datetime',
  datetime: 'datetime',
  select: 'select',
  multi_select: 'multi_select',
  boolean: 'boolean',
  url: 'url',
};

const ENGINE_TYPE_TO_LIBRARY: Record<string, string> = {
  string: 'text',
  text: 'textarea',
  email: 'email',
  phone: 'phone',
  int: 'integer',
  float: 'integer',
  datetime: 'datetime',
  enum: 'select',
  multi_select: 'multi_select',
  boolean: 'boolean',
  url: 'url',
};

function humanize(key: string): string {
  return key.replace(/[_-]+/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function MethodInheritedFieldPicker({
  blockEntityTypes,
  currentFields,
  workflowFieldsByEntityType,
  onAdd,
  onClose,
}: Props) {
  const [typeNameById, setTypeNameById] = useState<Map<string, string>>(new Map());
  const [typeIdByName, setTypeIdByName] = useState<Map<string, string>>(new Map());
  const [targetType, setTargetType] = useState<string>(blockEntityTypes[0] ?? '');
  const [declarations, setDeclarations] = useState<RelationDeclaration[]>([]);
  const [loadingDeclarations, setLoadingDeclarations] = useState(false);
  const [selectedDefId, setSelectedDefId] = useState('');
  const [sourceFields, setSourceFields] = useState<SourceFieldOption[]>([]);
  const [loadingFields, setLoadingFields] = useState(false);
  const [manualKey, setManualKey] = useState('');
  const [adding, setAdding] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // id ↔ name for every entity type: declarations reference types by id.
  useEffect(() => {
    let cancelled = false;
    void entityTypesApi
      .list({ limit: 200 })
      .then((res) => {
        if (cancelled) return;
        const byId = new Map<string, string>();
        const byName = new Map<string, string>();
        for (const t of res.items ?? []) {
          const id = t.entity_type_id ?? t.id;
          byId.set(id, t.name);
          byName.set(t.name, id);
        }
        setTypeNameById(byId);
        setTypeIdByName(byName);
      })
      .catch(() => {
        if (!cancelled) setError('Could not load entity types.');
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Relations that point AT the target type: their `from` side is what the
  // block can inherit from.
  useEffect(() => {
    const targetId = typeIdByName.get(targetType);
    setSelectedDefId('');
    if (!targetId) {
      setDeclarations([]);
      return;
    }
    let cancelled = false;
    setLoadingDeclarations(true);
    void entityRelations
      .listDeclarations(targetId, 'to')
      .then((res) => {
        if (!cancelled) setDeclarations(res.items ?? []);
      })
      .catch(() => {
        if (!cancelled) setDeclarations([]);
      })
      .finally(() => {
        if (!cancelled) setLoadingDeclarations(false);
      });
    return () => {
      cancelled = true;
    };
  }, [targetType, typeIdByName]);

  const selected = declarations.find((d) => d.relation_def_id === selectedDefId) ?? null;
  const providerName = selected ? (typeNameById.get(selected.from_entity_type_id) ?? '') : '';

  // Source fields: the provider's Forms, its workflows' entity_schema, and —
  // because types like client/site often have neither — the keys actually
  // present on its recent records.
  useEffect(() => {
    if (!selected || !providerName) {
      setSourceFields([]);
      return;
    }
    let cancelled = false;
    setLoadingFields(true);
    (async () => {
      const byKey = new Map<string, SourceFieldOption>();
      const put = (opt: SourceFieldOption) => {
        if (!byKey.has(opt.key)) byKey.set(opt.key, opt);
      };
      try {
        const forms = await formSchemas.list(providerName);
        for (const schema of forms.items) {
          for (const f of schema.schema?.fields ?? []) {
            if (f.type === 'section' || f.type === 'reference') continue;
            put({
              key: f.id,
              label: f.label || humanize(f.id),
              libraryType: FORM_TYPE_TO_LIBRARY[f.type] ?? 'text',
              origin: 'form',
            });
          }
        }
      } catch {
        // No forms is the normal case for client/site; fall through.
      }
      for (const f of workflowFieldsByEntityType[providerName] ?? []) {
        if (f.ownership === 'inherited') continue;
        put({
          key: f.field,
          label: f.description?.trim() || humanize(f.field),
          libraryType: ENGINE_TYPE_TO_LIBRARY[f.type] ?? 'text',
          origin: 'workflow',
        });
      }
      try {
        const res = await request<{ items: Array<{ data?: Record<string, unknown> }> }>(
          `/entity-records?entity_type_id=${encodeURIComponent(selected.from_entity_type_id)}&limit=50`,
        );
        for (const record of res.items ?? []) {
          for (const [key, value] of Object.entries(record.data ?? {})) {
            if (key === IDENTIFIER_FIELD_KEY) continue;
            // Keys ending in _id are relation plumbing, not something to inherit.
            if (/_id$/.test(key)) continue;
            put({
              key,
              label: humanize(key),
              libraryType:
                typeof value === 'number'
                  ? 'integer'
                  : typeof value === 'boolean'
                    ? 'boolean'
                    : 'text',
              origin: 'records',
            });
          }
        }
      } catch {
        // Records are a convenience source only.
      }
      put({
        key: IDENTIFIER_FIELD_KEY,
        label: 'Unique identifier',
        libraryType: 'text',
        origin: 'identifier',
      });
      if (!cancelled) {
        setSourceFields([...byKey.values()].sort((a, b) => a.key.localeCompare(b.key)));
        setLoadingFields(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selected, providerName, workflowFieldsByEntityType]);

  const alreadyInherited = useMemo(
    () =>
      new Set(
        currentFields
          .filter((f) => f.ownership === 'inherited' && f.source_entity_type && f.source_field_key)
          .map((f) => `${f.source_entity_type}.${f.source_field_key}`),
      ),
    [currentFields],
  );
  const listedLibraryIds = useMemo(
    () => new Set(currentFields.map((f) => f.library_field_id)),
    [currentFields],
  );

  /** Reuse the Field Library field with this key, or create a text-ish one. */
  const resolveLibraryField = async (key: string, label: string, libraryType: string) => {
    const existing = await fieldLibrary.list({ search: key, limit: 200 });
    const hit = existing.items.find((f) => f.identity.field_key === key && !f.identity.is_archived);
    if (hit) return hit.identity.library_field_id;
    const created = await fieldLibrary.create({
      name: label,
      field_key: key,
      field_type: libraryType,
      description: `Inherited from ${providerName}.${key}`,
    });
    return created.identity.library_field_id;
  };

  const handleAdd = async (key: string, label: string, libraryType: string) => {
    if (!providerName) return;
    setError(null);
    setAdding(key);
    try {
      const libraryFieldId = await resolveLibraryField(key, label, libraryType);
      if (listedLibraryIds.has(libraryFieldId)) {
        setError(
          `This block already lists the "${key}" field. Remove it first if you want it inherited instead.`,
        );
        return;
      }
      const ok = await onAdd({
        libraryFieldId,
        label,
        sourceEntityType: providerName,
        sourceFieldKey: key,
      });
      if (ok) onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not add the field.');
    } finally {
      setAdding(null);
    }
  };

  const manual = manualKey.trim();
  const manualValid = /^[a-z][a-z0-9_]*$/.test(manual);

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-card rounded-xl shadow-xl w-full max-w-lg mx-4 max-h-[90vh] overflow-hidden">
        <div className="flex items-center justify-between p-4 border-b border-border">
          <div>
            <h3 className="text-lg font-semibold text-foreground">Add field from related entity</h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              Only procedures that use this block will carry the field. It is read-only on the
              record and filled from the linked {providerName || 'source'} record.
            </p>
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground"
          >
            <X className="w-5 h-5" />
          </Button>
        </div>

        <div className="p-4 space-y-4 max-h-[60vh] overflow-y-auto">
          {blockEntityTypes.length === 0 ? (
            <div className="py-8 text-center text-sm text-muted-foreground">
              <Link2 className="w-8 h-8 mx-auto mb-2 text-muted-foreground/60" />
              <p className="font-medium text-muted-foreground">
                Tag this block with an entity type first.
              </p>
              <p className="mt-1">
                The related entity is looked up from the relations declared on that type.
              </p>
            </div>
          ) : (
            <>
              {blockEntityTypes.length > 1 && (
                <div>
                  <label className="block text-sm font-medium text-foreground mb-2">
                    Inherit onto
                  </label>
                  <div className="flex flex-wrap gap-2">
                    {blockEntityTypes.map((name) => (
                      <Button
                        key={name}
                        variant={name === targetType ? 'secondary' : 'ghost'}
                        onClick={() => setTargetType(name)}
                        className={`text-sm font-medium ${
                          name === targetType
                            ? 'border-primary/20 bg-primary/10 text-primary'
                            : 'text-muted-foreground'
                        }`}
                      >
                        {name}
                      </Button>
                    ))}
                  </div>
                </div>
              )}

              <div>
                <label className="block text-sm font-medium text-foreground mb-2">
                  Related entity
                </label>
                {loadingDeclarations ? (
                  <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
                ) : declarations.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    No relations point at <code className="bg-muted px-1 rounded">{targetType}</code>.
                    Declare one in Settings → Entities → Relations first.
                  </p>
                ) : (
                  <div className="flex flex-wrap gap-2">
                    {declarations.map((d) => {
                      const name = typeNameById.get(d.from_entity_type_id) ?? d.from_entity_type_id;
                      const isActive = d.relation_def_id === selectedDefId;
                      return (
                        <Button
                          key={d.relation_def_id}
                          variant={isActive ? 'secondary' : 'ghost'}
                          onClick={() => setSelectedDefId(d.relation_def_id)}
                          className={`text-sm font-medium ${
                            isActive
                              ? 'border-primary/20 bg-primary/10 text-primary'
                              : 'text-muted-foreground'
                          }`}
                        >
                          {name}
                          <span className="ml-1.5 text-xs opacity-70">
                            {d.relation_type === 'REFERENCE' ? 'live' : 'copy'}
                          </span>
                        </Button>
                      );
                    })}
                  </div>
                )}
              </div>

              {selected && (
                <div>
                  <label className="block text-sm font-medium text-foreground mb-2">
                    Field on {providerName}
                  </label>
                  {loadingFields ? (
                    <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
                  ) : (
                    <div className="space-y-2 max-h-64 overflow-y-auto">
                      {sourceFields.map((opt) => {
                        const taken = alreadyInherited.has(`${providerName}.${opt.key}`);
                        const busy = adding === opt.key;
                        return (
                          <Button
                            key={opt.key}
                            variant="ghost"
                            onClick={() => void handleAdd(opt.key, opt.label, opt.libraryType)}
                            disabled={taken || adding !== null}
                            className={`h-auto w-full justify-start p-3 text-left border transition-colors ${
                              taken
                                ? 'border-border bg-muted/40 opacity-50 cursor-not-allowed'
                                : 'border-border bg-background hover:border-primary/30 hover:bg-accent/40'
                            }`}
                          >
                            <div className="flex items-center justify-between w-full">
                              <div>
                                <div className="font-medium text-foreground">{opt.label}</div>
                                <div className="text-xs text-muted-foreground mt-0.5">
                                  <code className="bg-muted px-1 rounded">{opt.key}</code>
                                  <span className="ml-2">
                                    {opt.origin === 'form'
                                      ? 'from its form'
                                      : opt.origin === 'workflow'
                                        ? 'from its procedures'
                                        : opt.origin === 'records'
                                          ? 'seen on its records'
                                          : 'system'}
                                  </span>
                                </div>
                              </div>
                              {taken ? (
                                <span className="text-xs text-muted-foreground">Already added</span>
                              ) : busy ? (
                                <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
                              ) : (
                                <Plus className="w-4 h-4 text-primary" />
                              )}
                            </div>
                          </Button>
                        );
                      })}
                    </div>
                  )}

                  <div className="mt-3 rounded-lg border border-dashed border-border p-3">
                    <label className="block text-xs font-medium text-muted-foreground mb-1">
                      Or type a field key on {providerName}
                    </label>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={manualKey}
                        onChange={(e) => setManualKey(e.target.value)}
                        placeholder="e.g. client_code"
                        className="h-9 flex-1 rounded-lg border border-border px-3 text-sm font-mono focus:border-cobalt focus:outline-none focus:ring-2 focus:ring-cobalt/20"
                      />
                      <Button
                        variant="outline"
                        disabled={!manualValid || adding !== null || alreadyInherited.has(`${providerName}.${manual}`)}
                        onClick={() => void handleAdd(manual, humanize(manual), 'text')}
                      >
                        Add
                      </Button>
                    </div>
                    {manual && !manualValid && (
                      <p className="mt-1 text-xs text-destructive">
                        Lowercase letters, digits and underscores, starting with a letter.
                      </p>
                    )}
                  </div>
                </div>
              )}
            </>
          )}

          {error && (
            <p className="text-sm text-destructive border border-destructive/30 bg-destructive/5 rounded-lg px-3 py-2">
              {error}
            </p>
          )}
        </div>

        <div className="flex items-center justify-end gap-3 p-4 border-t border-border bg-muted/50">
          <Button variant="secondary" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>
    </div>
  );
}
