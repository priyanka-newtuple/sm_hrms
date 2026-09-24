/**
 * RelationFieldMappings
 *
 * Picks which of the source entity's fields flow onto the target through one
 * relation. Writes only `relation_metadata` on the declaration — the mapping is
 * the source of truth, and the target's Form (if it even has one) is not
 * touched, so this works for entity types whose fields come from Method Blocks.
 *
 * Source fields come from `resolveEntityFormSchemas`, so a provider with Forms
 * and a provider with only a published `entity_schema` are both offered.
 */

import { useMemo, useState } from 'react';
import { Loader2, Plus, X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { resolveEntityFormSchemas } from '@/lib/state-machine/entitySchema';
import type { FormSchema, RelationDeclaration } from '@/core/types';
import type { EntityField } from '@/lib/state-machine/types';
import { toFieldId } from '../form-config/constants';

interface Props {
  declaration: RelationDeclaration;
  sourceEntityName: string;
  targetEntityName: string;
  formSchemas: FormSchema[];
  workflowFieldsByEntityType: Record<string, EntityField[]>;
  canWrite: boolean;
  onSave: (metadata: Record<string, unknown>) => Promise<void>;
}

/** `relation_metadata` mixes feature config (e.g. related_files) with field
 *  mappings; only the string-valued entries are mappings. */
function fieldMappings(declaration: RelationDeclaration): Array<[string, string]> {
  return Object.entries(declaration.relation_metadata ?? {}).filter(
    (entry): entry is [string, string] => typeof entry[1] === 'string',
  );
}

export default function RelationFieldMappings({
  declaration,
  sourceEntityName,
  targetEntityName,
  formSchemas,
  workflowFieldsByEntityType,
  canWrite,
  onSave,
}: Props) {
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState(false);
  const [picked, setPicked] = useState('');

  const mappings = fieldMappings(declaration);

  // `union`, not `state`: this maps an entity *type*, and the runtime value copy
  // reads `data[field]` regardless of the record's state.
  const sourceFields = useMemo(
    () =>
      resolveEntityFormSchemas(sourceEntityName || undefined, {
        scope: 'union',
        formSchemas,
        workflowFields: workflowFieldsByEntityType[sourceEntityName],
      })
        .flatMap((schema) => schema.schema?.fields ?? [])
        .filter((field) => field.type !== 'section' && field.type !== 'reference'),
    [sourceEntityName, formSchemas, workflowFieldsByEntityType],
  );

  const alreadyMapped = new Set(mappings.map(([key]) => key));
  const available = sourceFields.filter(
    (field) => !alreadyMapped.has(`${sourceEntityName}.${field.id}`),
  );

  const commit = async (next: Record<string, unknown>) => {
    setBusy(true);
    try {
      await onSave(next);
      setPicked('');
      setAdding(false);
    } finally {
      setBusy(false);
    }
  };

  const addMapping = async () => {
    const field = sourceFields.find((f) => f.id === picked);
    if (!field) return;
    // Flat id — the backend's `local_field_name` strips a single prefix, so a
    // dotted target id never resolves.
    const targetField = toFieldId(`${sourceEntityName}_${field.id}`);
    await commit({
      ...(declaration.relation_metadata ?? {}),
      [`${sourceEntityName}.${field.id}`]: `${targetEntityName}.${targetField}`,
    });
  };

  const removeMapping = async (key: string) => {
    const next = { ...(declaration.relation_metadata ?? {}) };
    delete next[key];
    await commit(next);
  };

  return (
    <div className="mt-2 border-t border-border pt-2">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium text-muted-foreground">Fields carried over</span>
        {canWrite && !adding && available.length > 0 && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setAdding(true)}
            icon={<Plus className="h-3.5 w-3.5" />}
          >
            Add field
          </Button>
        )}
      </div>

      {mappings.length === 0 ? (
        <p className="mt-1 text-xs text-muted-foreground">
          None yet. Linked records carry no field values across until one is added.
        </p>
      ) : (
        <ul className="mt-1 space-y-1">
          {mappings.map(([source, target]) => (
            <li
              key={source}
              className="flex items-center justify-between gap-2 rounded-md bg-muted/40 px-2 py-1"
            >
              <span className="min-w-0 truncate text-xs text-foreground">
                <code className="text-[11px]">{source}</code>
                <span className="mx-1.5 text-muted-foreground">→</span>
                <code className="text-[11px]">{target}</code>
              </span>
              {canWrite && (
                <button
                  type="button"
                  aria-label={`Remove mapping ${source}`}
                  disabled={busy}
                  onClick={() => void removeMapping(source)}
                  className="shrink-0 rounded text-muted-foreground hover:text-foreground disabled:opacity-50"
                >
                  <X className="h-3 w-3" />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      {adding && (
        <div className="mt-2 flex items-center gap-2">
          <select
            value={picked}
            onChange={(e) => setPicked(e.target.value)}
            disabled={busy}
            aria-label={`Field from ${sourceEntityName}`}
            className="h-8 min-w-0 flex-1 rounded-md border border-border bg-background px-2 text-xs text-foreground focus:border-cobalt focus:outline-none focus:ring-2 focus:ring-cobalt/20"
          >
            <option value="">Select a field from {sourceEntityName}…</option>
            {available.map((field) => (
              <option key={field.id} value={field.id}>
                {field.label || field.id}
              </option>
            ))}
          </select>
          <Button size="sm" onClick={() => void addMapping()} disabled={!picked || busy}>
            {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : 'Add'}
          </Button>
          <Button variant="ghost" size="sm" onClick={() => setAdding(false)} disabled={busy}>
            Cancel
          </Button>
        </div>
      )}

      {canWrite && available.length === 0 && sourceFields.length === 0 && (
        <p className="mt-1 text-xs text-muted-foreground">
          <code className="text-[11px]">{sourceEntityName}</code> has no fields yet — add them via a
          Form or a Method Block pinned to its published workflow.
        </p>
      )}
    </div>
  );
}
