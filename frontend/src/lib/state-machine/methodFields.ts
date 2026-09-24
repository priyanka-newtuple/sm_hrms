/**
 * Pure logic for resolving a workflow's Method Blocks into Entity Fields,
 * scoped per state.
 *
 * Framework-agnostic on purpose: every function here takes plain data in
 * (states, already-fetched method fields, the field-type catalogue) and
 * returns plain data out — no React, no API-client dependency. This is the
 * shared surface a skin's own UI (e.g. a custom designer built outside this
 * app) can call directly to get the exact same state-scoped field
 * resolution, instead of re-deriving it independently — the same way a skin
 * already imports shared types from this folder (see
 * `packages/pe-skin/lib/designer/procedureOps.ts`'s
 * `import type { ... } from '@/lib/state-machine/types'`).
 *
 * `useMethodFieldsByState` (in the Wizard) is the React-hook wrapper around
 * this module: it owns the data fetching (fieldLibrary.listFieldTypes(),
 * methodLibrary.get() per method) and calls these functions to turn the
 * fetched data into per-state field lists. Any other caller — including one
 * with its own API client — only needs to fetch the same two shapes
 * (field-type catalogue items, and each method's fields) and can call these
 * functions the same way.
 */

import type { FieldTypeOption, MethodVersionField } from '@/core/types';
import { pickWizardCopy } from '@/core/types/wizardCopy';
import type { EntityField, StateNode } from './types';

/** code -> (engine_type, config_kind), the same catalogue
 * backend/workflow/manager.py's _entity_field_from_method_field converts
 * through at publish time. */
export type FieldTypeCatalogue = Map<string, { engineType: string | null; configKind: string }>;

/** Build the field-type catalogue lookup from a field-library
 * listFieldTypes() response's `items`. Pure — safe to call with any source
 * of the same shape (the Wizard's API client, a skin's own, a test
 * fixture). */
export function buildFieldTypeCatalogue(
  items: Pick<FieldTypeOption, 'code' | 'engine_type' | 'config_kind'>[],
): FieldTypeCatalogue {
  return new Map(
    items.map((item) => [item.code, { engineType: item.engine_type, configKind: item.config_kind }]),
  );
}

/** Convert one Method Library field into the EntityField shape a workflow's
 * entity_schema (and Guards field pickers) understand. */
export function toEntityField(field: MethodVersionField, catalogue: FieldTypeCatalogue): EntityField {
  const entry = catalogue.get(field.field_type);
  const engineType = entry?.engineType ?? field.field_type;
  const settings = (field.settings ?? {}) as Record<string, unknown>;
  const enumValues =
    entry?.configKind === 'enum_values' || entry?.configKind === 'picklist'
      ? ((settings.enum_values as string[] | undefined) ?? [])
      : [];
  const picklistId =
    entry?.configKind === 'picklist' ? (settings.picklist_id as string | undefined) ?? null : null;
  // A picklist_multi field's second picklist and its "Extend Field" config ride
  // along, matching what the backend's `_entity_field_from_method_field` copies
  // — without them a pinned field renders as a flat multi-select of the first
  // picklist alone.
  const isPicklist = entry?.configKind === 'picklist';
  const picklistId2 = isPicklist ? (settings.picklist_id_2 as string | undefined) : undefined;
  const enumValues2 = isPicklist ? (settings.enum_values_2 as string[] | undefined) : undefined;
  const enumLabels2 = isPicklist ? (settings.enum_labels_2 as string[] | undefined) : undefined;
  const extensions = isPicklist
    ? (settings.extensions as EntityField['extensions'] | undefined)
    : undefined;
  const extensionLabel = isPicklist
    ? (settings.extension_label as string | undefined)
    : undefined;
  const wizardCopy = isPicklist ? pickWizardCopy(settings) : {};
  // Type-agnostic presentation settings, copied for every type — the same two
  // keys `_entity_field_from_method_field` copies outside its config_kind
  // branches.
  const styleConfig = settings.style_config as EntityField['style_config'] | undefined;
  const readOnly = Boolean(settings.read_only);
  return {
    field: field.field_key,
    type: engineType as EntityField['type'],
    required: field.required,
    nullable: true,
    default: null,
    enum_values: enumValues,
    picklist_id: picklistId,
    ...(picklistId2 ? { picklist_id_2: picklistId2 } : {}),
    ...(enumValues2?.length ? { enum_values_2: enumValues2 } : {}),
    ...(enumLabels2?.length ? { enum_labels_2: enumLabels2 } : {}),
    ...(extensions && Object.keys(extensions).length > 0 ? { extensions } : {}),
    ...(extensionLabel ? { extension_label: extensionLabel } : {}),
    ...wizardCopy,
    ...(styleConfig && Object.keys(styleConfig).length > 0 ? { style_config: styleConfig } : {}),
    ...(readOnly ? { read_only: true } : {}),
    description: field.label || field.field_key,
  };
}

/** Convert every field on one already-fetched method version into
 * EntityFields. */
export function fieldsForMethod(
  fields: MethodVersionField[],
  catalogue: FieldTypeCatalogue,
): EntityField[] {
  return fields.map((f) => toEntityField(f, catalogue));
}

/**
 * Resolves each state's OWN field list from its attached Method Block(s) —
 * scoped per state, unlike a workflow's flat entity_schema.fields (which
 * merges every state's method fields into one list with no attribution back
 * to the state that contributed each one).
 *
 * `fieldsByMethod` is keyed by method_id, already resolved to EntityFields
 * (e.g. via `fieldsForMethod` above) for every method_id referenced by any
 * state's `method_refs`. This function does only the per-state scoping —
 * no fetching — so it has no opinion on how the caller got fieldsByMethod.
 */
export function resolveFieldsByState(
  states: StateNode[],
  fieldsByMethod: Record<string, EntityField[]>,
): Record<string, EntityField[]> {
  const result: Record<string, EntityField[]> = {};
  for (const state of states) {
    const seen = new Set<string>();
    const fields: EntityField[] = [];
    for (const ref of state.method_refs ?? []) {
      for (const field of fieldsByMethod[ref.method_id] ?? []) {
        if (seen.has(field.field)) continue;
        seen.add(field.field);
        fields.push(field);
      }
    }
    result[state.name] = fields;
  }
  return result;
}

/** Every distinct method_id referenced by any state's method_refs, sorted
 * for a stable fetch/dependency key. */
export function methodIdsFromStates(states: StateNode[]): string[] {
  return Array.from(
    new Set(states.flatMap((s) => (s.method_refs ?? []).map((r) => r.method_id))),
  ).sort();
}
