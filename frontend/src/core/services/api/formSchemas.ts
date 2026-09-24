/**
 * Form schemas backed by /forms/config. Includes entity-field ↔ form-field mapping.
 */

import type {
  ExtensionField,
  FormField,
  FormSchema,
  FormSchemaCreateRequest,
  PublicFormSchemaResponse,
  PublicFormSubmitRequest,
  PublicFormSubmitResponse,
  FormSchemaUpdateRequest,
} from '../../types';
import type { PortableFormConfig } from '../../types/portableForm';
import { pickWizardCopy, type WizardCopy } from '../../types/wizardCopy';
import { request } from './client';

function mapEntityFieldTypeToFrontend(type: string): FormField['type'] {
  switch (type) {
    case 'email': return 'email';
    case 'phone': return 'phone';
    case 'url': return 'url';
    case 'text': return 'textarea';
    case 'int':
    case 'float': return 'integer';
    case 'boolean': return 'boolean';
    case 'date':
    case 'datetime': return 'datetime';
    case 'enum': return 'select';
    case 'multi_select': return 'multi_select';
    case 'picklist_multi': return 'picklist_multi';
    case 'auto_number': return 'auto_number';
    case 'timer_duration': return 'timer_duration';
    case 'currency': return 'currency';
    case 'document': return 'document';
    case 'json': return 'textarea';
    default: return 'text';
  }
}

function mapFrontendFieldTypeToEntity(type: FormField['type']): string {
  switch (type) {
    case 'email': return 'email';
    case 'phone': return 'phone';
    case 'url': return 'url';
    case 'textarea': return 'text';
    case 'integer': return 'int';
    case 'number': return 'int';
    case 'boolean': return 'boolean';
    case 'date':
    case 'datetime': return 'datetime';
    case 'multi_select': return 'multi_select';
    case 'picklist_multi': return 'picklist_multi';
    case 'auto_number': return 'auto_number';
    case 'timer_duration': return 'timer_duration';
    case 'currency': return 'currency';
    case 'document': return 'document';
    default: return 'string';
  }
}

const REF_DESC_PREFIX = '__ref__:';
// picklist_multi is a frontend-only type the backend doesn't know about, and the
// backend's EntityField model strips unknown keys (picklist_id_2 / enum_values_2).
// So we persist the field as a plain multi_select and stash the second picklist's
// data + the real label inside the description, behind this marker prefix.
const PLM_DESC_PREFIX = '__plm__:';
// Stashes enum_labels + field label so they survive the backend round-trip.
const ENL_DESC_PREFIX = '__enl__:';

/** Everything a picklist_multi field carries that the backend's EntityField
 *  would otherwise drop, as stashed behind `PLM_DESC_PREFIX`. */
type PicklistMultiMeta = {
  label?: string;
  picklist_id_2?: string;
  enum_values_2?: string[];
  enum_labels_2?: string[];
  extensions?: unknown;
  extension_label?: string;
} & WizardCopy;

/**
 * Re-inflate the "Extend Field" configuration from a stashed blob.
 *
 * Defensive because the blob is free text as far as the backend is concerned:
 * anything that is not an option keyed to a list of snapshotted fields is
 * dropped rather than handed to the renderer. Returns `undefined` when the
 * field has no configuration at all, which is what keeps Extend Field OFF.
 */
function parseExtensions(raw: unknown): FormField['extensions'] | undefined {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return undefined;
  const extensions: NonNullable<FormField['extensions']> = {};
  for (const [option, entry] of Object.entries(raw as Record<string, unknown>)) {
    const fields = (entry as { fields?: unknown })?.fields;
    if (!Array.isArray(fields)) continue;
    const parsed = fields.filter(
      (candidate): candidate is ExtensionField =>
        Boolean(candidate) &&
        typeof candidate === 'object' &&
        typeof (candidate as ExtensionField).id === 'string' &&
        typeof (candidate as ExtensionField).type === 'string',
    );
    if (parsed.length > 0) extensions[option] = { fields: parsed };
  }
  return Object.keys(extensions).length > 0 ? extensions : undefined;
}

/** "job_title" -> "Job Title", for a field the backend stored without a label. */
function labelFromFieldName(fieldName: string): string {
  return fieldName.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

/** A relation, stashed as `__ref__:<entity>:<field>:<label>`. */
function mapReferenceField(fieldName: string, blob: string): FormField {
  const [source_entity, source_field, ...labelParts] = blob.slice(REF_DESC_PREFIX.length).split(':');
  return {
    id: fieldName,
    label: labelParts.join(':') || labelFromFieldName(fieldName),
    type: 'reference',
    required: false,
    system: false,
    editable: true,
    source_entity,
    source_field,
  };
}

/** Everything a picklist_multi carries, from whichever era wrote it. */
type PicklistMultiSource = {
  label: string | undefined;
  required: boolean;
  picklistId?: string;
  picklistId2?: string;
  enumValues?: string[];
  enumValues2?: string[];
  enumLabels2?: string[];
  extensions?: FormField['extensions'];
  extensionLabel?: string;
  wizardCopy?: WizardCopy;
  currentValue?: unknown;
  /** Only the native shape reads these; the blob era never looked at them. */
  placeholder?: string;
  colSpan?: 'half';
};

/**
 * The one place a picklist_multi `FormField` is assembled, so the two
 * persistence eras below cannot drift: a key added here reaches both.
 */
function picklistMultiFormField(fieldName: string, src: PicklistMultiSource): FormField {
  return {
    id: fieldName,
    label: src.label || labelFromFieldName(fieldName),
    type: 'picklist_multi',
    required: src.required,
    system: false,
    editable: true,
    ...(src.picklistId ? { picklist_id: src.picklistId } : {}),
    ...(src.picklistId2 ? { picklist_id_2: src.picklistId2 } : {}),
    ...(src.enumValues && src.enumValues.length > 0 ? { enum_values: src.enumValues } : {}),
    ...(src.enumValues2 && src.enumValues2.length > 0 ? { enum_values_2: src.enumValues2 } : {}),
    ...(src.enumLabels2 && src.enumLabels2.length > 0 ? { enum_labels_2: src.enumLabels2 } : {}),
    ...(src.extensions ? { extensions: src.extensions } : {}),
    ...(src.extensionLabel ? { extension_label: src.extensionLabel } : {}),
    ...src.wizardCopy,
    ...(src.placeholder ? { placeholder: src.placeholder } : {}),
    ...(src.currentValue !== undefined && src.currentValue !== null
      ? { current_value: src.currentValue }
      : {}),
    ...(src.colSpan === 'half' ? { col_span: 'half' as const } : {}),
  };
}

/**
 * A picklist_multi written before the engine carried its keys natively, when
 * everything `EntityField` would have dropped was stashed behind
 * `PLM_DESC_PREFIX`. Read-only path: nothing writes this shape any more.
 *
 * `placeholder` and `col_span` are deliberately not read here: this era never
 * did, and starting to would change how already-stored fields render.
 */
function mapLegacyPicklistMultiMeta(
  fieldName: string,
  raw: Record<string, unknown>,
  blob: string,
  enumValues: string[] | undefined,
): FormField {
  let meta: PicklistMultiMeta = {};
  try {
    meta = JSON.parse(blob.slice(PLM_DESC_PREFIX.length));
  } catch {
    // Malformed blob: the field still renders, as a labelled multi-select.
    meta = {};
  }
  return picklistMultiFormField(fieldName, {
    label: meta.label,
    required: Boolean(raw.required ?? false),
    picklistId: raw.picklist_id ? String(raw.picklist_id) : undefined,
    picklistId2: meta.picklist_id_2 ? String(meta.picklist_id_2) : undefined,
    enumValues,
    enumValues2: Array.isArray(meta.enum_values_2)
      ? meta.enum_values_2.map(String).filter(Boolean)
      : undefined,
    enumLabels2: Array.isArray(meta.enum_labels_2) ? meta.enum_labels_2.map(String) : undefined,
    extensions: parseExtensions(meta.extensions),
    extensionLabel: meta.extension_label ? String(meta.extension_label) : undefined,
    wizardCopy: pickWizardCopy(meta as Record<string, unknown>),
    currentValue: raw.current_value,
  });
}

/**
 * A picklist_multi whose second picklist and "Extend Field" config arrive as
 * ordinary keys — what the engine stores today, and what a pinned Method Block
 * produces. `picklistId2` and `extensions` are passed in because the caller
 * already parsed them to decide this branch applies.
 */
function mapNativePicklistMulti(
  fieldName: string,
  raw: Record<string, unknown>,
  description: string | undefined,
  enumValues: string[] | undefined,
  picklistId2: string | undefined,
  extensions: FormField['extensions'],
): FormField {
  return picklistMultiFormField(fieldName, {
    label: description,
    required: Boolean(raw.required ?? false),
    picklistId: raw.picklist_id ? String(raw.picklist_id) : undefined,
    picklistId2,
    enumValues,
    enumValues2: Array.isArray(raw.enum_values_2)
      ? (raw.enum_values_2 as unknown[]).map(String).filter(Boolean)
      : undefined,
    enumLabels2: Array.isArray(raw.enum_labels_2)
      ? (raw.enum_labels_2 as unknown[]).map(String)
      : undefined,
    extensions,
    extensionLabel: raw.extension_label ? String(raw.extension_label) : undefined,
    wizardCopy: pickWizardCopy(raw),
    placeholder: raw.placeholder ? String(raw.placeholder) : undefined,
    currentValue: raw.current_value,
    colSpan: raw.col_span === 'half' ? 'half' : undefined,
  });
}

/** A select/multi_select whose option labels and field label were stashed
 *  behind `ENL_DESC_PREFIX` to survive the backend round-trip. */
function mapEnumLabelsField(
  fieldName: string,
  raw: Record<string, unknown>,
  blob: string,
  enumValues: string[] | undefined,
): FormField {
  let meta: { label?: string; enum_labels?: string[] } = {};
  try {
    meta = JSON.parse(blob.slice(ENL_DESC_PREFIX.length));
  } catch {
    // Malformed payload: fall back to deriving the label from the field id.
    meta = {};
  }
  const enumLabels = Array.isArray(meta.enum_labels) ? meta.enum_labels.map(String) : undefined;
  return {
    id: fieldName,
    label: meta.label || labelFromFieldName(fieldName),
    type: mapEntityFieldTypeToFrontend(String(raw.type || 'string')),
    required: Boolean(raw.required ?? false),
    system: false,
    editable: true,
    ...(raw.placeholder ? { placeholder: String(raw.placeholder) } : {}),
    ...(raw.picklist_id ? { picklist_id: String(raw.picklist_id) } : {}),
    ...(enumValues && enumValues.length > 0 ? { enum_values: enumValues } : {}),
    ...(enumLabels && enumLabels.length > 0 ? { enum_labels: enumLabels } : {}),
    ...(raw.current_value !== undefined && raw.current_value !== null ? { current_value: raw.current_value } : {}),
    ...(raw.col_span === 'half' ? { col_span: 'half' as const } : {}),
  };
}

function mapTableField(
  fieldName: string,
  raw: Record<string, unknown>,
  description: string | undefined,
): FormField {
  return {
    id: fieldName,
    label: description || labelFromFieldName(fieldName),
    type: 'table',
    required: Boolean(raw.required ?? false),
    system: false,
    editable: true,
    table_config: raw.table_config as FormField['table_config'],
    ...(raw.placeholder ? { placeholder: String(raw.placeholder) } : {}),
    ...(raw.current_value !== undefined && raw.current_value !== null ? { current_value: raw.current_value } : {}),
    ...(raw.col_span === 'half' ? { col_span: 'half' as const } : {}),
  };
}

/** Every other field: the description is just a label, and the type-specific
 *  config blocks travel as their own keys. */
function mapPlainField(
  fieldName: string,
  raw: Record<string, unknown>,
  description: string | undefined,
  enumValues: string[] | undefined,
): FormField {
  return {
    id: fieldName,
    label: description || labelFromFieldName(fieldName),
    type: mapEntityFieldTypeToFrontend(String(raw.type || 'string')),
    required: Boolean(raw.required ?? false),
    system: false,
    editable: true,
    ...(raw.placeholder ? { placeholder: String(raw.placeholder) } : {}),
    ...(raw.picklist_id ? { picklist_id: String(raw.picklist_id) } : {}),
    ...(enumValues && enumValues.length > 0 ? { enum_values: enumValues } : {}),
    ...(raw.current_value !== undefined && raw.current_value !== null ? { current_value: raw.current_value } : {}),
    ...(raw.col_span === 'half' ? { col_span: 'half' as const } : {}),
    ...(raw.auto_number_config && typeof raw.auto_number_config === 'object'
      ? { auto_number_config: raw.auto_number_config as FormField['auto_number_config'] }
      : {}),
    ...(raw.currency_config && typeof raw.currency_config === 'object'
      ? { currency_config: raw.currency_config as FormField['currency_config'] }
      : {}),
    ...(raw.calc && typeof raw.calc === 'object' ? { calc: raw.calc as FormField['calc'] } : {}),
    ...(raw.document_config && typeof raw.document_config === 'object'
      ? { document_config: raw.document_config as FormField['document_config'] }
      : {}),
  };
}

/**
 * One persisted `EntityField` back into the `FormField` the editors and
 * `FieldInput` speak. Dispatch only — each shape has its own mapper above, in
 * the order they are recognised: the marker-prefixed descriptions first (a
 * prefix is unambiguous), then the shapes recognised by their keys.
 */
export function mapEntityFieldToFormField(raw: Record<string, unknown>): FormField {
  // Mirror of `commonFieldAttributes`: restored for every persisted shape, not
  // only the plain one, since the dispatch below returns early per type.
  return {
    ...mapEntityFieldToFormFieldByShape(raw),
    ...(raw.style_config && typeof raw.style_config === 'object'
      ? { style_config: raw.style_config as FormField['style_config'] }
      : {}),
    ...(raw.read_only ? { read_only: true } : {}),
  };
}

function mapEntityFieldToFormFieldByShape(raw: Record<string, unknown>): FormField {
  const fieldName = String(raw.field || '');
  const description = raw.description ? String(raw.description) : undefined;
  const enumValues = Array.isArray(raw.enum_values)
    ? (raw.enum_values as unknown[]).map(String).filter(Boolean)
    : undefined;

  if (description?.startsWith(REF_DESC_PREFIX)) return mapReferenceField(fieldName, description);

  if (description?.startsWith(PLM_DESC_PREFIX)) {
    return mapLegacyPicklistMultiMeta(fieldName, raw, description, enumValues);
  }

  const picklistId2 = raw.picklist_id_2 ? String(raw.picklist_id_2) : undefined;
  const extensions = parseExtensions(raw.extensions);
  if (picklistId2 || extensions) {
    return mapNativePicklistMulti(fieldName, raw, description, enumValues, picklistId2, extensions);
  }

  if (description?.startsWith(ENL_DESC_PREFIX)) {
    return mapEnumLabelsField(fieldName, raw, description, enumValues);
  }

  if (raw.table_config && typeof raw.table_config === 'object') {
    return mapTableField(fieldName, raw, description);
  }

  return mapPlainField(fieldName, raw, description, enumValues);
}

export function mapRawFormSchemaToFrontend(raw: Record<string, unknown>): FormSchema {
  const fields = (Array.isArray(raw.fields) ? raw.fields : []) as Record<string, unknown>[];
  const schemaKey = String(raw.schema_key || raw.id || '');
  return {
    id: schemaKey,
    schema_key: schemaKey,
    name: String(raw.name || schemaKey || ''),
    entity_type: String(raw.entity_type || ''),
    version: 1,
    is_active: Boolean(raw.is_active ?? true),
    display_order: Number(raw.display_order ?? 0),
    schema: { fields: fields.map(mapEntityFieldToFormField) },
    created_at: String(raw.created_at || new Date().toISOString()),
    updated_at: String(raw.updated_at || new Date().toISOString()),
  };
}

function normalizeEntityTypeForMatch(value: string): string {
  return value.replace(/^ATS\./, '').trim().toLowerCase();
}

function formSchemaKey(entityType: string, name: string): string {
  const normalizedEntityType = entityType.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');
  const normalizedName = name.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');
  return normalizedName ? `${normalizedEntityType}__${normalizedName}` : normalizedEntityType;
}

function rawSchemaToPortable(raw: Record<string, unknown>): PortableFormConfig {
  return {
    name: String(raw.name || ''),
    fields: Array.isArray(raw.fields)
      ? raw.fields.map((field) => ({ ...(field as Record<string, unknown>) })) as PortableFormConfig['fields']
      : [],
  };
}

/**
 * Settings that belong to no single field type. They are merged onto whatever
 * the type-specific mapping produced, because those mappings return early per
 * type and would otherwise keep these for plain fields alone.
 */
function commonFieldAttributes(field: FormField): Record<string, unknown> {
  return {
    ...(field.style_config ? { style_config: field.style_config } : {}),
    ...(field.read_only ? { read_only: true } : {}),
  };
}

function mapFormFieldToEntityField(field: FormField): Record<string, unknown> {
  return { ...mapFormFieldToEntityFieldByType(field), ...commonFieldAttributes(field) };
}

function mapFormFieldToEntityFieldByType(field: FormField): Record<string, unknown> {
  if (field.type === 'reference') {
    return {
      field: field.id,
      type: 'string',
      required: false,
      nullable: true,
      description: `${REF_DESC_PREFIX}${field.source_entity ?? ''}:${field.source_field ?? ''}:${field.label}`,
      ...(field.col_span === 'half' ? { col_span: 'half' } : {}),
    };
  }
  if (field.type === 'picklist_multi') {
    // Stored as multi_select — the type the engine has for it — with both
    // picklists and the "Extend Field" config as ordinary `EntityField` keys.
    // The label goes in `description` like every other field's does; the old
    // `__plm__:` blob is only still read (see mapEntityFieldToFormField).
    return {
      field: field.id,
      type: 'multi_select',
      required: field.required,
      nullable: !field.required,
      description: field.label || null,
      ...(field.picklist_id ? { picklist_id: field.picklist_id } : {}),
      ...(field.enum_values && field.enum_values.length > 0 ? { enum_values: field.enum_values } : {}),
      ...(field.picklist_id_2 ? { picklist_id_2: field.picklist_id_2 } : {}),
      ...(field.enum_values_2?.length ? { enum_values_2: field.enum_values_2 } : {}),
      ...(field.enum_labels_2?.length ? { enum_labels_2: field.enum_labels_2 } : {}),
      // Only written when options are actually configured, so a field with
      // Extend Field off round-trips to `extensions: undefined`.
      ...(field.extensions && Object.keys(field.extensions).length > 0
        ? { extensions: field.extensions }
        : {}),
      ...(field.extension_label ? { extension_label: field.extension_label } : {}),
      ...pickWizardCopy(field as unknown as Record<string, unknown>),
      ...(field.placeholder ? { placeholder: field.placeholder } : {}),
      ...(field.col_span === 'half' ? { col_span: 'half' } : {}),
    };
  }
  if (field.type === 'auto_number') {
    return {
      field: field.id,
      type: 'auto_number',
      required: false,
      nullable: false,
      description: field.label || null,
      auto_number_config: {
        affix_mode: field.auto_number_config?.affix_mode ?? 'none',
        affix: field.auto_number_config?.affix ?? '',
      },
      ...(field.col_span === 'half' ? { col_span: 'half' } : {}),
    };
  }
  if (field.type === 'currency') {
    return {
      field: field.id,
      type: 'currency',
      required: field.required,
      nullable: !field.required,
      description: field.label || null,
      currency_config: {
        currency_code: field.currency_config?.currency_code ?? 'USD',
      },
      ...(field.col_span === 'half' ? { col_span: 'half' } : {}),
      ...(field.placeholder ? { placeholder: field.placeholder } : {}),
    };
  }
  if (field.type === 'table') {
    return {
      field: field.id,
      type: 'json',
      required: field.required,
      nullable: !field.required,
      description: field.label || null,
      table_config: field.table_config ?? { row_mode: 'dynamic', display_mode: 'grid', columns: [] },
      ...(field.col_span === 'half' ? { col_span: 'half' } : {}),
      ...(field.placeholder ? { placeholder: field.placeholder } : {}),
    };
  }
  const isEnum = field.type === 'select' && field.enum_values && field.enum_values.length > 0;
  const isMultiSelect = field.type === 'multi_select' && field.enum_values && field.enum_values.length > 0;
  const hasLabels = (isEnum || isMultiSelect) && field.enum_labels && field.enum_labels.length > 0;
  return {
    field: field.id,
    type: isMultiSelect ? 'multi_select' : isEnum ? 'enum' : mapFrontendFieldTypeToEntity(field.type),
    required: field.required,
    nullable: !field.required,
    description: hasLabels
      ? `${ENL_DESC_PREFIX}${JSON.stringify({ label: field.label, enum_labels: field.enum_labels })}`
      : field.label || null,
    ...(field.picklist_id ? { picklist_id: field.picklist_id } : {}),
    ...((isEnum || isMultiSelect) ? { enum_values: field.enum_values } : {}),
    ...(field.col_span === 'half' ? { col_span: 'half' } : {}),
    ...(field.placeholder ? { placeholder: field.placeholder } : {}),
    ...(field.calc ? { calc: field.calc } : {}),
    ...(field.type === 'document' && field.document_config
      ? { document_config: field.document_config }
      : {}),
  };
}

export const formSchemas = {
  list: (entityType?: string) => {
    return request<{ items: Record<string, unknown>[]; total: number }>(
      entityType
        ? `/forms/config?entity_type=${encodeURIComponent(entityType.replace(/^ATS\./, '').trim())}`
        : '/forms/config'
    ).then((resp) => ({
      items: (resp.items || [])
        .map(mapRawFormSchemaToFrontend)
        .filter((schema) =>
          !entityType ||
          normalizeEntityTypeForMatch(schema.entity_type) === normalizeEntityTypeForMatch(entityType)
        ),
      total: entityType
        ? (resp.items || [])
            .map(mapRawFormSchemaToFrontend)
            .filter((schema) =>
              normalizeEntityTypeForMatch(schema.entity_type) === normalizeEntityTypeForMatch(entityType)
            ).length
        : resp.total ?? 0,
    }));
  },

  get: (schemaKey: string) =>
    request<Record<string, unknown>>(
      `/forms/config/${encodeURIComponent(schemaKey)}`
    ).then(mapRawFormSchemaToFrontend),

  getPortable: (schemaKey: string) =>
    request<Record<string, unknown>>(
      `/forms/config/${encodeURIComponent(schemaKey)}`
    ).then(rawSchemaToPortable),

  create: (data: FormSchemaCreateRequest) => {
    const cleanedEntityType = data.entity_type.replace(/^ATS\./, '').trim();
    const schemaKey = formSchemaKey(cleanedEntityType, data.name);
    const entityFields = (data.schema.fields || [])
      .filter((f) => f.type !== 'section')
      .map(mapFormFieldToEntityField);
    return request<Record<string, unknown>>('/forms/config', {
      method: 'POST',
      body: JSON.stringify({
        schema_key: schemaKey,
        name: data.name,
        entity_type: cleanedEntityType,
        fields: entityFields,
        is_active: data.activate ?? true,
      }),
    }).then(mapRawFormSchemaToFrontend);
  },

  createPortable: (entityType: string, data: PortableFormConfig) => {
    const cleanedEntityType = entityType.replace(/^ATS\./, '').trim();
    return request<Record<string, unknown>>('/forms/config', {
      method: 'POST',
      body: JSON.stringify({
        schema_key: formSchemaKey(cleanedEntityType, data.name),
        name: data.name,
        entity_type: cleanedEntityType,
        fields: data.fields,
        is_active: true,
      }),
    }).then(mapRawFormSchemaToFrontend);
  },

  update: (schemaKey: string, data: FormSchemaUpdateRequest) => {
    const entityFields = data.schema?.fields
      ? data.schema.fields
          .filter((f) => f.type !== 'section')
          .map(mapFormFieldToEntityField)
      : undefined;
    return request<Record<string, unknown>>(
      `/forms/config/${encodeURIComponent(schemaKey)}`,
      {
        method: 'PUT',
        body: JSON.stringify({
          ...(data.name !== undefined ? { name: data.name } : {}),
          ...(entityFields
            ? { fields: entityFields }
            : {}),
          ...(data.activate !== undefined ? { is_active: data.activate } : {}),
        }),
      }
    ).then(mapRawFormSchemaToFrontend);
  },

  updatePortable: (schemaKey: string, data: PortableFormConfig) =>
    request<Record<string, unknown>>(
      `/forms/config/${encodeURIComponent(schemaKey)}`,
      {
        method: 'PUT',
        body: JSON.stringify({ name: data.name, fields: data.fields }),
      }
    ).then(mapRawFormSchemaToFrontend),

  /** Persist a form's sort position among the forms sharing its entity type. */
  reorder: (schemaKey: string, displayOrder: number) =>
    request<Record<string, unknown>>(
      `/forms/config/${encodeURIComponent(schemaKey)}`,
      {
        method: 'PUT',
        body: JSON.stringify({ display_order: displayOrder }),
      }
    ).then(mapRawFormSchemaToFrontend),

  reset: (schemaKey: string) =>
    request<Record<string, unknown>>(
      `/forms/config/${encodeURIComponent(schemaKey)}`
    ).then(mapRawFormSchemaToFrontend),

  delete: (schemaKey: string) =>
    request<void>(
      `/forms/config/${encodeURIComponent(schemaKey)}`,
      { method: 'DELETE' }
    ),

  seed: (): Promise<{ picklists_seeded: number; schemas_seeded: number; message: string }> =>
    Promise.resolve({ picklists_seeded: 0, schemas_seeded: 0, message: 'Use the New Form button to create schemas' }),

  getPublic: (token: string): Promise<PublicFormSchemaResponse> =>
    request<PublicFormSchemaResponse>(`/forms/public/${encodeURIComponent(token)}`),

  submitPublic: (data: PublicFormSubmitRequest): Promise<PublicFormSubmitResponse> =>
    request<PublicFormSubmitResponse>('/forms/public/submit', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  getPublicByEntity: (entityId: string): Promise<PublicFormSchemaResponse> =>
    request<PublicFormSchemaResponse>(`/forms/public/entity/${encodeURIComponent(entityId)}`),

  submitPublicByEntity: (entityId: string, fields: Record<string, unknown>): Promise<PublicFormSubmitResponse> =>
    request<PublicFormSubmitResponse>(`/forms/public/entity/${encodeURIComponent(entityId)}/submit`, {
      method: 'POST',
      body: JSON.stringify({ fields }),
    }),
};
