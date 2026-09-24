import { pickWizardCopy } from '@/core/types/wizardCopy';
import type { FieldType, FormField, FormSchema } from "@/core/types";
import type {
  EntityField,
  Guard,
  ResolvedMethodSchema,
  Transition,
} from "@/lib/state-machine/types";

/**
 * What the workflow must record for a form field so the publish-time drift
 * check agrees with it.
 *
 * That check compares against the *persisted* form field type
 * (`mapFormFieldToEntityField` in core/services/api/formSchemas.ts) after the
 * backend runs it through `_normalize_form_field_type`
 * (backend/workflow/services/entity_schema.py) — which is not a one-to-one
 * mapping: `textarea` persists as `text` and normalizes to `string`, `select`
 * is only `enum` once it has options, and both `multi_select` and
 * `picklist_multi` persist as `multi_select`. Anything that disagrees here is
 * reported as permanent schema drift on every publish.
 */
function mapFormFieldTypeToEntityType(field: FormField): EntityField["type"] {
  const hasOptions = (field.enum_values?.length ?? 0) > 0;
  switch (field.type) {
    case "text":
    case "textarea":
      return "string";
    case "email":
      return "email";
    case "phone":
      return "phone";
    case "url":
      return "url";
    case "integer":
    case "number":
      return "int";
    case "select":
      return hasOptions ? "enum" : "string";
    case "multi_select":
    case "picklist_multi":
      // EntityField refuses a `multi_select` that declares no options, so a
      // picklist with nothing in it still has to travel as free-form json.
      return hasOptions ? "multi_select" : "json";
    case "table":
      return "json";
    case "currency":
      return "currency";
    case "auto_number":
      return "auto_number";
    case "timer_duration":
      return "timer_duration";
    case "date":
    case "datetime":
      return "datetime";
    case "boolean":
      return "boolean";
    case "document":
      return "document";
    default:
      return "string";
  }
}

export function buildEntityFieldsFromFormSchema(schema: FormSchema): EntityField[] {
  return schema.schema.fields
    .filter((field) => field.type !== "section")
    .map((field) => {
      const entityType = mapFormFieldTypeToEntityType(field);
      return {
        field: field.id,
        type: entityType,
        required: field.required,
        nullable: !field.required,
        default:
          field.type === "document"
            ? null
            : field.type === "boolean"
            ? false
            : field.type === "number" || field.type === "integer"
              ? 0
              : field.type === "select" ||
                field.type === "multi_select" ||
                field.type === "picklist_multi"
                ? null
              : field.type === "date" || field.type === "datetime"
                ? null
              : "",
        // Backend rejects enum_values on any type other than 'enum' and
        // 'multi_select', so a picklist attached to anything else (e.g. a
        // string field) must not leak its options into the workflow schema.
        enum_values:
          entityType === "enum" || entityType === "multi_select"
            ? field.enum_values ?? []
            : [],
        picklist_id: null,
        description: field.label,
      };
    });
}

export function buildEntityFieldsFromFormSchemas(schemas: FormSchema[]): EntityField[] {
  // TODO: Filter inactive form schemas here once form schema callers stop relying
  // on API-side filtering guarantees.
  const seen = new Set<string>();
  const fields: EntityField[] = [];
  for (const schema of schemas) {
    for (const field of buildEntityFieldsFromFormSchema(schema)) {
      if (seen.has(field.field)) continue;
      seen.add(field.field);
      fields.push(field);
    }
  }
  return fields;
}

/**
 * Field keys a workflow's pinned Method Blocks contribute.
 *
 * Two sources, unioned:
 *  - `method_schemas`, written into the definition at publish time. This is the
 *    authoritative list, resolved from the exact pinned version, and it carries
 *    the real `ownership`/`source`/type.
 *  - `liveMethodFields`, the caller's view of the methods currently referenced
 *    by `method_refs`. Covers a method pinned since the last publish, which
 *    `method_schemas` cannot know about yet.
 *
 * Unioned rather than preferring one, because the failure modes are not
 * symmetric: over-protecting a key merely leaves a field as it already is,
 * while under-protecting lets the Form-derived rewrite clobber a method's
 * definition of it and makes the workflow unpublishable.
 */
export function pinnedMethodFieldKeys(
  definition: { method_schemas?: ResolvedMethodSchema[] } | undefined,
  liveMethodFields: EntityField[][] = [],
): Set<string> {
  const keys = new Set<string>();
  for (const schema of definition?.method_schemas ?? []) {
    for (const field of schema.fields ?? []) {
      if (field?.field) keys.add(field.field);
    }
  }
  for (const fields of liveMethodFields) {
    for (const field of fields ?? []) {
      if (field?.field) keys.add(field.field);
    }
  }
  return keys;
}

/**
 * The Form-owned half of a workflow's `entity_schema`: its fields, minus every
 * key a pinned Method Block provides.
 *
 * A key a pinned Method Block provides must have exactly one source, and that
 * source is the method: `_prepare_publishable_definition` seeds the merge from
 * the workflow's own fields and then refuses any pinned field that differs,
 * with PINNED_METHOD_FIELD_CONFLICT. The Forms-to-Method-Blocks migration
 * established the same rule from the other end, stripping those keys out of
 * `entity_schema` so "the merge sees one source for each key".
 *
 * The Form-sync broke that by replacing `entity_schema.fields` wholesale:
 * `buildEntityFieldsFromFormSchema` has no `ownership`, no `source` and only a
 * generic type guess, so it put a second, disagreeing copy of every pinned key
 * back. Dropping the key instead of writing either copy restores the rule, and
 * clears a workflow that is already carrying the bad copy.
 *
 * Every other key follows the Form as before, including disappearing when the
 * Form drops it.
 */
export function formFieldsExcludingPinned(
  formDerivedFields: EntityField[],
  protectedKeys: Set<string>,
): EntityField[] {
  const merged: EntityField[] = [];
  const taken = new Set<string>();
  // Nothing from `currentFields` is carried over for a pinned key. The copy a
  // previous publish wrote there goes stale the moment the method changes, and
  // a stale copy is exactly what publish refuses; the backend rewrites the key
  // from the method on the next publish anyway.
  for (const field of formDerivedFields) {
    if (taken.has(field.field) || protectedKeys.has(field.field)) continue;
    merged.push(field);
    taken.add(field.field);
  }
  return merged;
}

/**
 * Order-insensitive identity for a field list.
 *
 * `JSON.stringify` compares key order and element order, and both move here:
 * the Form's builder decides key order, and the merge drops pinned keys, which
 * shifts positions. Comparing raw JSON therefore reports "changed" for a list
 * that is the same set of identical fields, which commits a reorder and marks
 * an untouched document dirty the moment it is opened.
 */
function fieldsFingerprint(fields: EntityField[]): string {
  return JSON.stringify(
    [...fields]
      .sort((a, b) => a.field.localeCompare(b.field))
      .map((field) =>
        Object.fromEntries(
          Object.entries(field as unknown as Record<string, unknown>).sort(([a], [b]) =>
            a.localeCompare(b),
          ),
        ),
      ),
  );
}

/**
 * The Form-sync both funnel editors run when an entity type's Forms load.
 *
 * Extracted because the wizard and the canvas each carried their own copy, and
 * the bug this fixes had to be found and fixed twice as a result: a Method
 * Block field rebuilt from the Form loses its ownership/source/type, and
 * publish then refuses the workflow with PINNED_METHOD_FIELD_CONFLICT.
 *
 * `liveMethodFields` is the caller's view of the methods its states currently
 * reference; see `pinnedMethodFieldKeys` for why it is unioned with the
 * definition's own `method_schemas`.
 */
export function resyncEntitySchemaFields(
  definition: {
    entity_schema: { fields: EntityField[] };
    transitions: Transition[];
    method_schemas?: ResolvedMethodSchema[];
  },
  formItems: FormSchema[],
  liveMethodFields: EntityField[][],
): { fields: EntityField[]; transitions: Transition[]; unchanged: boolean } {
  const current = definition.entity_schema.fields;
  // A pinned Method Block owns its fields, and must remain their only source.
  const protectedKeys = pinnedMethodFieldKeys(definition, liveMethodFields);
  const fields = formFieldsExcludingPinned(
    buildEntityFieldsFromFormSchemas(formItems),
    protectedKeys,
  );
  // Guards may reference a pinned field, which no longer lives in
  // entity_schema. Prune against both sources or every such guard is lost.
  const knownFieldNames = new Set([...fields.map((f) => f.field), ...protectedKeys]);
  const transitions = pruneTransitionsForFieldNames(definition.transitions, knownFieldNames);
  const unchanged =
    fieldsFingerprint(fields) === fieldsFingerprint(current) &&
    JSON.stringify(transitions) === JSON.stringify(definition.transitions);
  return { fields, transitions, unchanged };
}

function guardReferencesOnlyKnownFields(guard: Guard, validFields: Set<string>): boolean {
  if (guard.field && !validFields.has(guard.field)) return false;
  if (guard.type === "compare_dates") {
    // TODO: Replace these hardcoded config keys with typed guard config shapes.
    const config = guard.config ?? {};
    const extraFields = [
      config.left,
      config.right,
      config.other_field,
    ].filter((value): value is string => typeof value === "string" && value.trim().length > 0);
    return extraFields.every((field) => validFields.has(field));
  }
  return true;
}

export function pruneTransitionsForEntityFields(
  transitions: Transition[],
  fields: EntityField[],
): Transition[] {
  return pruneTransitionsForFieldNames(transitions, new Set(fields.map((f) => f.field)));
}

/**
 * The same pruning, given field names directly.
 *
 * A guard may reference a field a pinned Method Block provides, which is
 * deliberately absent from `entity_schema`. Callers that know about both
 * sources pass the union here, so such a guard is not pruned as unknown.
 */
export function pruneTransitionsForFieldNames(
  transitions: Transition[],
  validFields: Set<string>,
): Transition[] {
  return transitions.map((transition) => ({
    ...transition,
    required_fields: transition.required_fields.filter((field) =>
      validFields.has(field.field),
    ),
    guards: transition.guards.filter((guard) =>
      guardReferencesOnlyKnownFields(guard, validFields),
    ),
  }));
}


/** Inverse of `mapFormFieldTypeToEntityType`, for the fallback below. */
function mapEntityTypeToFormFieldType(type: string): FieldType {
  switch (type) {
    case "text":
      return "textarea";
    case "email":
      return "email";
    case "phone":
      return "phone";
    case "url":
      return "url";
    case "int":
    case "integer":
      return "integer";
    case "number":
    case "float":
      return "number";
    case "enum":
      return "select";
    case "multi_select":
      return "multi_select";
    case "boolean":
      return "boolean";
    case "date":
      return "date";
    case "datetime":
      return "datetime";
    case "currency":
      return "currency";
    case "auto_number":
      return "auto_number";
    case "timer_duration":
      return "timer_duration";
    case "document":
      // Without this a Method-contributed document field fell to the default
      // text input in fallback-rendered forms, losing the upload control.
      return "document";
    case "table":
      return "table";
    // string, json and anything the form layer has no control for fall back to
    // a plain text input rather than rendering nothing.
    default:
      return "text";
  }
}

/** The synthetic form's schema_key, so callers can tell it apart from a real one. */
export const WORKFLOW_SCHEMA_FALLBACK_KEY = "__workflow_entity_schema__";

/**
 * Build a read-only stand-in form from a workflow's own resolved entity schema.
 *
 * A workflow's `entity_schema` is where fields contributed by a state's pinned
 * Method Blocks end up (merged at publish). Nothing propagates those onto the
 * Forms module, so an entity type configured purely through Methods has no form
 * config at all, and every form-driven surface renders "No form is configured"
 * despite the workflow knowing the fields perfectly well.
 *
 * This is a display fallback, used only when the entity type genuinely has no
 * active form: a real form always wins, so this can never mask or override one
 * somebody built by hand. `identifier` is dropped because the create dialog
 * renders it separately, outside the schema fields.
 */
export function buildFallbackFormSchemaFromEntitySchema(
  entityType: string,
  fields: EntityField[],
  options: {
    stateName?: string;
    requireState?: boolean;
    scope?: EntityFieldScope;
    schemaKey?: string;
    name?: string;
    version?: number;
    displayOrder?: number;
    allowEmpty?: boolean;
  } = {},
): FormSchema | null {
  const {
    stateName,
    requireState = false,
    scope,
    schemaKey = WORKFLOW_SCHEMA_FALLBACK_KEY,
    name = "Workflow fields",
    version = 1,
    displayOrder = 0,
    allowEmpty = false,
  } = options;
  const usable = (fields ?? [])
    .filter((field) => field.field && field.field !== "identifier")
    // A field with no source_states is the workflow's own and belongs to every
    // state. One carrying them came from a Method pinned to those states, so it
    // renders only while the record sits in one of them — once the record moves
    // on, the field stops rendering. Its value is untouched either way; this is
    // a display filter, not a data operation.
    .filter((field) => {
      const states = field.source_states ?? [];
      if (states.length === 0) return true;
      // Explicit union: every field the type can ever hold, regardless of
      // state. Stated by the caller rather than inferred from a missing
      // `stateName`, so "deliberately unscoped" can never be confused with
      // "state not loaded yet" — that conflation was a real bug once.
      if (scope === 'union') return true;
      // `requireState` is what a detail view passes: it is showing one record,
      // so until its state is known no state-scoped field may render. Without
      // it an unknown state falls back to "show everything", and the fields
      // flash in while the record loads — or stay in for good if it never does.
      // Callers with legitimately no state (board-wide column pickers, filter
      // builders) leave it off and still get the full list.
      if (!stateName) return !requireState;
      return states.includes(stateName);
    });
  if (usable.length === 0 && !allowEmpty) return null;
  const formFields: FormField[] = usable.map((field) => {
    // A Method block field pinned with ownership='inherited' is read-only on
    // this record: its value comes from the linked source record, so it renders
    // as a `reference` field exactly like a relation_metadata target, and
    // `pickEnterableData` keeps it out of the save payload (the backend 403s
    // any write to it).
    if (field.ownership === "inherited") {
      const sourceField = field.source?.context_field ?? field.field;
      const sourceEntity = field.source?.context_entity_type ?? "";
      return {
        id: field.field,
        label: sourceEntity
          ? `${sourceField.replace(/_/g, " ")} (${sourceEntity})`
          : field.description?.trim() || field.field,
        type: "reference",
        required: false,
        system: false,
        editable: false,
        ...(sourceEntity ? { source_entity: sourceEntity, source_field: sourceField } : {}),
      };
    }
    return {
      id: field.field,
      label: field.description?.trim() || field.field,
      // Table fields are stored by the engine as JSON; table_config is the
      // discriminator that restores the table editor on synthetic schemas. A
      // picklist_multi field is stored as `multi_select`, and its second
      // picklist is the discriminator that restores its wizard the same way.
      type: field.table_config
        ? "table"
        : field.picklist_id_2 || field.extensions
          ? "picklist_multi"
          : mapEntityTypeToFormFieldType(field.type),
      required: Boolean(field.required),
      system: false,
      ...(field.editable != null ? { editable: field.editable } : {}),
      ...(field.placeholder ? { placeholder: field.placeholder } : {}),
      ...(field.col_span ? { col_span: field.col_span } : {}),
      ...(field.enum_values?.length ? { enum_values: field.enum_values } : {}),
      ...(field.picklist_id ? { picklist_id: field.picklist_id } : {}),
      ...(field.picklist_id_2 ? { picklist_id_2: field.picklist_id_2 } : {}),
      ...(field.enum_values_2?.length ? { enum_values_2: field.enum_values_2 } : {}),
      ...(field.enum_labels_2?.length ? { enum_labels_2: field.enum_labels_2 } : {}),
      ...(field.extensions ? { extensions: field.extensions } : {}),
      ...(field.extension_label ? { extension_label: field.extension_label } : {}),
      ...pickWizardCopy(field as unknown as Record<string, unknown>),
      ...(field.auto_number_config ? { auto_number_config: field.auto_number_config } : {}),
      ...(field.currency_config ? { currency_config: field.currency_config } : {}),
      ...(field.document_config ? { document_config: field.document_config } : {}),
      ...(field.table_config ? { table_config: field.table_config } : {}),
      ...(field.calc ? { calc: field.calc } : {}),
      ...(field.style_config ? { style_config: field.style_config } : {}),
      ...(field.read_only ? { read_only: true } : {}),
    };
  });
  return {
    id: schemaKey,
    schema_key: schemaKey,
    name,
    entity_type: entityType,
    version,
    is_active: true,
    display_order: displayOrder,
    schema: { fields: formFields },
    created_at: "",
    updated_at: "",
  };
}

/**
 * Reconstruct the form boundaries captured for pinned Methods at publish time.
 * Legacy workflow responses without snapshots keep the original single-schema
 * fallback, so mixed-version deployments remain backwards compatible.
 */
export function buildFallbackFormSchemasFromEntitySchema(
  entityType: string,
  fields: EntityField[],
  methodSchemas: ResolvedMethodSchema[] | undefined,
  options: { stateName?: string; requireState?: boolean; scope?: EntityFieldScope } = {},
): FormSchema[] {
  if (!methodSchemas?.length) {
    const fallback = buildFallbackFormSchemaFromEntitySchema(entityType, fields, options);
    return fallback ? [fallback] : [];
  }

  const { stateName, requireState = false, scope } = options;
  const visibleMethods = methodSchemas
    .filter((schema) => {
      if (scope === 'union') return true;
      if (stateName) return schema.state_name === stateName;
      return !requireState;
    })
    .sort((left, right) => {
      const stateOrder = (left.state_order ?? Number.MAX_SAFE_INTEGER)
        - (right.state_order ?? Number.MAX_SAFE_INTEGER);
      if (stateOrder !== 0) return stateOrder;
      if (left.state_name !== right.state_name) {
        return left.state_name.localeCompare(right.state_name);
      }
      if (left.method_order !== right.method_order) {
        return left.method_order - right.method_order;
      }
      return left.method_id.localeCompare(right.method_id);
    });

  const seenMethodVersions = new Set<string>();
  const distinctMethods = scope === 'union'
    ? visibleMethods.filter((method) => {
        const key = `${method.method_id}:${method.version_id}`;
        if (seenMethodVersions.has(key)) return false;
        seenMethodVersions.add(key);
        return true;
      })
    : visibleMethods;

  // Fields with no Method provenance are still part of the workflow contract.
  // Keep them in their own leading schema instead of dropping them as soon as
  // Method-specific tabs are available.
  const workflowFields = fields.filter((field) => (field.source_states ?? []).length === 0);
  const workflowSchema = buildFallbackFormSchemaFromEntitySchema(entityType, workflowFields, {
    ...options,
    schemaKey: WORKFLOW_SCHEMA_FALLBACK_KEY,
    name: 'Workflow fields',
    displayOrder: 0,
  });

  const offset = workflowSchema ? 1 : 0;
  const resolved = distinctMethods
    .map((method, index) =>
      buildFallbackFormSchemaFromEntitySchema(entityType, method.fields, {
        ...options,
        schemaKey: scope === 'union'
          ? `method:${method.method_id}:${method.version_id}`
          : `method:${method.method_id}:${method.version_id}:${method.state_name}`,
        name: method.method_name,
        version: method.version,
        displayOrder: offset + index,
        allowEmpty: true,
      }),
    )
    .filter((schema): schema is FormSchema => schema !== null);

  return workflowSchema ? [workflowSchema, ...resolved] : resolved;
}

export type EntityFieldScope = 'state' | 'union';

/**
 * The one place that answers "what fields does this entity type have?".
 *
 * Active Form configs win when they exist — unchanged priority. Only when the
 * type has none does the workflow's resolved `entity_schema` stand in, which is
 * where fields contributed by pinned Method Blocks live.
 *
 * `scope` is required and always explicit:
 *  - `'state'`  one record in one state: a field shows only while that state is
 *               among its `source_states`. An unknown `currentState` yields
 *               only unscoped fields, never the full set.
 *  - `'union'`  the entity *type* rather than a record — every field it can
 *               ever hold. Relation mapping needs this: the runtime value copy
 *               reads `data[field]` with no regard for state, so restricting
 *               the picker to one state would hide mappable fields.
 */
export function resolveEntityFormSchemas(
  entityType: string | undefined,
  options: {
    scope: EntityFieldScope;
    formSchemas: FormSchema[];
    currentState?: string;
    workflowFields?: EntityField[] | null;
  },
): FormSchema[] {
  const { scope, formSchemas, currentState, workflowFields } = options;
  if (!entityType) return [];
  const normalize = (value: string) => value.trim().toLowerCase().replace(/^ats\./, '');
  const target = normalize(entityType);
  const active = formSchemas.filter(
    (schema) => normalize(schema.entity_type ?? '') === target && schema.is_active,
  );
  if (active.length > 0) return active;
  if (!workflowFields?.length) return [];
  const fallback = buildFallbackFormSchemaFromEntitySchema(entityType, workflowFields, {
    scope,
    stateName: scope === 'state' ? currentState : undefined,
    requireState: scope === 'state',
  });
  return fallback ? [fallback] : [];
}

/**
 * Every field surface an entity type has, as schemas: active Forms UNIONED with
 * the Method-Block-composed fields on its published workflow `entity_schema`.
 *
 * Unlike `resolveEntityFormSchemas` (Forms-first, for display surfaces where a
 * Form deliberately wins), this is for authoring surfaces that must offer both
 * sources at once — role field permissions, the Field Filteration picker —
 * because a hybrid type (old Form still present alongside new Method-Block
 * fields, the deliberate mid-migration state) stores values from both in the
 * same `entities.data` that permissions and conditions are evaluated against.
 *
 * Method-Block fields already declared by a Form are dropped (the Form's
 * definition wins a name collision), so nothing is ever offered twice.
 */
export function unionEntityFormSchemas(
  entityType: string | undefined,
  options: {
    formSchemas: FormSchema[];
    workflowFields?: EntityField[] | null;
  },
): FormSchema[] {
  const { formSchemas, workflowFields } = options;
  const resolved = resolveEntityFormSchemas(entityType, {
    scope: 'union',
    formSchemas,
    workflowFields,
  });
  if (!entityType) return resolved;
  const fallback = buildFallbackFormSchemaFromEntitySchema(entityType, workflowFields ?? [], {
    scope: 'union',
  });
  if (!fallback) return resolved;
  if (resolved.length === 0) return [fallback];
  // Form-less type: the resolver already returned this very fallback.
  if (resolved.some((schema) => schema.schema_key === WORKFLOW_SCHEMA_FALLBACK_KEY)) {
    return resolved;
  }
  const declared = new Set(
    resolved.flatMap((schema) => (schema.schema?.fields ?? []).map((field) => field.id)),
  );
  const extras = fallback.schema.fields.filter((field) => !declared.has(field.id));
  if (extras.length === 0) return resolved;
  return [...resolved, { ...fallback, schema: { fields: extras } }];
}

/** The synthetic form holding relation-inherited fields when the type has no Form. */
export const INHERITED_SCHEMA_KEY = '__relation_inherited_fields__';

/** One `relation_metadata` mapping, already split into its parts. */
interface InheritedMapping {
  sourceEntity: string;
  sourceField: string;
  targetField: string;
}

/** Strip a single `<entity>.` prefix, matching the backend's `local_field_name`. */
function localName(value: string): string {
  const dot = value.indexOf('.');
  return dot === -1 ? value : value.slice(dot + 1);
}

/**
 * Mappings on declarations that target `entityType`, read off `relation_metadata`.
 *
 * `relation_metadata` mixes feature config (e.g. `related_files`) with field
 * mappings, so only string-valued entries count.
 */
export function inheritedMappingsForEntityType(
  entityType: string | undefined,
  declarations: Array<{
    to_entity_type_id: string;
    from_entity_type_id: string;
    relation_metadata?: Record<string, unknown> | null;
  }>,
  typeNameById: Map<string, string>,
): InheritedMapping[] {
  if (!entityType) return [];
  const normalize = (value: string) => value.trim().toLowerCase().replace(/^ats\./, '');
  const target = normalize(entityType);
  const out: InheritedMapping[] = [];
  for (const declaration of declarations) {
    if (normalize(typeNameById.get(declaration.to_entity_type_id) ?? '') !== target) continue;
    const provider = typeNameById.get(declaration.from_entity_type_id) ?? '';
    for (const [source, mapped] of Object.entries(declaration.relation_metadata ?? {})) {
      if (typeof mapped !== 'string') continue;
      out.push({
        sourceEntity: provider || localName(source).split('.')[0],
        sourceField: localName(source),
        targetField: localName(mapped),
      });
    }
  }
  return out;
}

/**
 * Append relation-inherited fields to resolved schemas as read-only reference fields.
 *
 * `relation_metadata` on the declaration is the source of truth for what a
 * relation carries over — the matching `type: 'reference'` entry in a target's
 * Form is only a display artifact, and a Method-Block-driven type has no Form to
 * hold one. Synthesising here means both kinds of entity type render inherited
 * values, and an existing Form entry is left to win so nothing renders twice.
 */
export function withInheritedReferenceFields(
  schemas: FormSchema[],
  options: {
    entityType: string | undefined;
    mappings: InheritedMapping[];
  },
): FormSchema[] {
  const { entityType, mappings } = options;
  if (!entityType || mappings.length === 0) return schemas;
  const existing = new Set(
    schemas.flatMap((schema) => (schema.schema?.fields ?? []).map((field) => field.id)),
  );
  const fields: FormField[] = [];
  for (const mapping of mappings) {
    // Dotted ids never resolve at runtime, and a field the Form already
    // declares must not be duplicated.
    if (!mapping.targetField || mapping.targetField.includes('.')) continue;
    if (existing.has(mapping.targetField)) continue;
    existing.add(mapping.targetField);
    fields.push({
      id: mapping.targetField,
      label: `${mapping.sourceField.replace(/_/g, ' ')} (${mapping.sourceEntity})`,
      type: 'reference',
      required: false,
      system: false,
      source_entity: mapping.sourceEntity,
      source_field: mapping.sourceField,
    });
  }
  if (fields.length === 0) return schemas;
  if (schemas.length > 0) {
    const [first, ...rest] = schemas;
    return [
      { ...first, schema: { ...first.schema, fields: [...(first.schema?.fields ?? []), ...fields] } },
      ...rest,
    ];
  }
  // Inherited fields can be the only ones the type has.
  return [
    {
      id: INHERITED_SCHEMA_KEY,
      schema_key: INHERITED_SCHEMA_KEY,
      name: 'Linked fields',
      entity_type: entityType,
      version: 1,
      is_active: true,
      display_order: 0,
      schema: { fields },
      created_at: '',
      updated_at: '',
    },
  ];
}
