/**
 * Side panel for inserting `$entity.field` and `{{input}}` tokens into the
 * focused connector field. Shows entity fields (grouped per selected entity
 * type), inherited fields pulled from related entities, and lets the user
 * define runtime input names via a free-text entry.
 */

import { useState } from 'react';
import { AlertTriangle, Braces, Database, Link2 } from 'lucide-react';

import type { InheritedFieldGroup } from '@/shared/hooks/useInheritedFieldOptions';
import type { FocusedSlot } from '../types';
import { entityToken, inputToken } from '../utils/placeholders';

function slotLabel(slot: FocusedSlot): string {
  if (!slot) return '';
  if (slot === 'path') return 'Path';
  if (slot === 'rawBody') return 'Body';
  return slot.section === 'header' ? 'Header' : 'Query param';
}

interface EntityFieldsPanelProps {
  /** Field ids grouped per selected entity type. */
  fieldGroups: Array<{ type: string; fields: string[] }>;
  inheritedFieldGroups?: InheritedFieldGroup[];
  hasEntityType: boolean;
  /** field id → selected entity types that lack the field. */
  missingByField?: Record<string, string[]>;
  /** Set when field options failed to load for one or more types. */
  loadError?: string | null;
  focusedSlot: FocusedSlot;
  onInsert: (token: string) => void;
}

/** Small entity-type label shown above each field group when 2+ types are selected. */
function GroupLabel({ name }: { name: string }) {
  return (
    <span className="block text-[10px] font-semibold uppercase tracking-wide text-muted-foreground/70">
      {name}
    </span>
  );
}

export default function EntityFieldsPanel({
  fieldGroups,
  inheritedFieldGroups = [],
  hasEntityType,
  missingByField = {},
  loadError = null,
  focusedSlot,
  onInsert,
}: EntityFieldsPanelProps) {
  const [customName, setCustomName] = useState('');
  const grouped = fieldGroups.length > 1;
  const totalFields = fieldGroups.reduce((n, g) => n + g.fields.length, 0);

  const addCustom = () => {
    const name = customName.trim();
    if (name) {
      onInsert(inputToken(name));
      setCustomName('');
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') { e.preventDefault(); addCustom(); }
  };

  const fieldChip = (name: string) => {
    const missing = missingByField[name];
    return (
      <button
        key={name}
        type="button"
        // Keep focus on the target field so the token lands in the field
        // the user clicked (path/header/query/body), not the last one.
        onMouseDown={(e) => e.preventDefault()}
        onClick={() => onInsert(entityToken(name))}
        title={missing ? `${name} — not on: ${missing.join(', ')}` : name}
        className="max-w-full truncate rounded-full border border-border bg-background px-2 py-0.5 font-mono text-[11px] text-foreground transition-colors hover:border-primary hover:bg-primary hover:text-primary-foreground"
      >
        {name}
      </button>
    );
  };

  return (
    <div className="space-y-3 overflow-hidden rounded-xl border border-border bg-card p-3 shadow-sm @4xl:sticky @4xl:top-4 @4xl:max-h-[calc(100vh-6rem)] @4xl:overflow-y-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-foreground">Variables</span>
        {focusedSlot ? (
          <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-medium text-primary">
            → {slotLabel(focusedSlot)}
          </span>
        ) : (
          <span className="text-[10px] text-muted-foreground">click a field first</span>
        )}
      </div>

      <div className="h-px bg-border" />

      {/* Runtime inputs */}
      <div className="space-y-2">
        <div className="flex items-center gap-1.5">
          <Braces className="h-3 w-3 text-muted-foreground" />
          <span className="text-[11px] font-medium text-muted-foreground">Runtime input</span>
        </div>
        <div className="flex gap-1.5">
          <input
            value={customName}
            onChange={(e) => setCustomName(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="input name"
            className="h-7 min-w-0 flex-1 rounded-lg border border-input bg-background px-2 font-mono text-[11px] placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-primary"
          />
          <button
            type="button"
            onClick={addCustom}
            disabled={!customName.trim()}
            className="h-7 shrink-0 rounded-lg bg-primary px-2.5 text-[11px] font-semibold text-primary-foreground disabled:opacity-40"
          >
            Add
          </button>
        </div>
      </div>

      <div className="h-px bg-border" />

      {/* Entity fields — one group per selected type when multiple are selected */}
      <div className="space-y-2">
        <div className="flex items-center gap-1.5">
          <Database className="h-3 w-3 text-muted-foreground" />
          <span className="text-[11px] font-medium text-muted-foreground">Entity fields</span>
        </div>

        {!hasEntityType ? (
          <p className="text-[11px] italic text-muted-foreground/70">
            Select an entity type to see fields.
          </p>
        ) : totalFields === 0 ? (
          <p className="text-[11px] italic text-muted-foreground/70">No fields available.</p>
        ) : (
          <>
            {loadError && (
              <p className="flex items-start gap-1.5 rounded-lg bg-destructive-subtle px-2 py-1.5 text-[10px] leading-4 text-destructive">
                <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
                <span>{loadError}</span>
              </p>
            )}
            {grouped && Object.keys(missingByField).length > 0 && (
              <p className="flex items-start gap-1.5 rounded-lg bg-warning-subtle px-2 py-1.5 text-[10px] leading-4 text-warning">
                <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
                <span>
                  Fields that don't exist on a type resolve to empty for that type.
                </span>
              </p>
            )}
            {grouped ? (
              fieldGroups.map(({ type, fields }) => (
                <div key={type} className="space-y-1">
                  <GroupLabel name={type} />
                  {fields.length ? (
                    <div className="flex flex-wrap gap-1">{fields.map(fieldChip)}</div>
                  ) : (
                    <p className="text-[11px] italic text-muted-foreground/70">No fields.</p>
                  )}
                </div>
              ))
            ) : (
              <div className="flex flex-wrap gap-1">
                {fieldGroups[0]?.fields.map(fieldChip)}
              </div>
            )}
          </>
        )}
      </div>

      {/* Inherited fields — pulled from related entities via a relation declaration. */}
      {hasEntityType && inheritedFieldGroups.length > 0 && (
        <>
          <div className="h-px bg-border" />
          <div className="space-y-2">
            <div className="flex items-center gap-1.5">
              <Link2 className="h-3 w-3 text-muted-foreground" />
              <span className="text-[11px] font-medium text-muted-foreground">Inherited fields</span>
              <span className="text-[10px] text-muted-foreground/60">read-only</span>
            </div>
            {inheritedFieldGroups.map(({ type, options }) => (
              <div key={type} className="space-y-1">
                {grouped && <GroupLabel name={type} />}
                <div className="flex flex-wrap gap-1">
                  {options.map((option) => (
                    <button
                      key={`${type}:${option.id}`}
                      type="button"
                      onMouseDown={(e) => e.preventDefault()}
                      onClick={() => onInsert(entityToken(option.id))}
                      title={
                        option.sourceEntity
                          ? `Inherited from ${option.sourceEntity} (${option.relationType})`
                          : `Inherited field (${option.relationType})`
                      }
                      className="max-w-full truncate rounded-full border border-dashed border-border bg-background px-2 py-0.5 font-mono text-[11px] text-foreground transition-colors hover:border-primary hover:bg-primary hover:text-primary-foreground"
                    >
                      {option.id}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
