import {
  STORED_FORM_FIELD_TYPES,
  type StoredFormFieldType,
  type PortableFormConfig,
  type StoredFormField,
} from '../../../../core/types/portableForm';
import type { PicklistOption } from '../../../../core/types';

const STORED_FORM_FIELD_TYPE_SET: ReadonlySet<string> = new Set(STORED_FORM_FIELD_TYPES);

/** Validated JSON shape used when editing a backend-native form configuration. */
export type EditableFormJson = PortableFormConfig;

/** Validated JSON shape used when editing a picklist configuration. */
export interface EditablePicklistJson {
  name: string;
  options: PicklistOption[];
}

/** Parse and validate a backend-native form configuration JSON string. */
export function parseFormJson(text: string): EditableFormJson {
  const value: unknown = JSON.parse(text);
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Form JSON must be an object.');
  }

  const candidate = value as Partial<EditableFormJson>;
  if (typeof candidate.name !== 'string' || !candidate.name.trim()) {
    throw new Error("'name' must be a non-empty string.");
  }
  if (!Array.isArray(candidate.fields)) {
    throw new Error("'fields' must be an array.");
  }

  const fieldIds = new Set<string>();
  for (const [index, field] of candidate.fields.entries()) {
    if (!field || typeof field !== 'object' || Array.isArray(field)) {
      throw new Error(`Field ${index + 1} must be an object.`);
    }
    if (typeof field.field !== 'string' || !field.field.trim()) {
      throw new Error(`Field ${index + 1} needs a non-empty 'field'.`);
    }
    const normalizedFieldId = field.field.trim();
    if (fieldIds.has(normalizedFieldId)) {
      throw new Error(`Field '${normalizedFieldId}' is duplicated.`);
    }
    fieldIds.add(normalizedFieldId);
    if (
      typeof field.type !== 'string' ||
      !STORED_FORM_FIELD_TYPE_SET.has(field.type.trim().toLowerCase())
    ) {
      throw new Error(`Field '${field.field}' has an unsupported 'type'.`);
    }
  }

  return {
    name: candidate.name.trim(),
    fields: candidate.fields.map((field) => ({
      ...field,
      field: field.field.trim(),
      type: field.type.trim().toLowerCase() as StoredFormFieldType,
    })) as StoredFormField[],
  };
}

/** Parse and validate a picklist configuration JSON string. */
export function parsePicklistJson(text: string): EditablePicklistJson {
  const value: unknown = JSON.parse(text);
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Picklist JSON must be an object.');
  }

  const candidate = value as Partial<EditablePicklistJson>;
  if (typeof candidate.name !== 'string' || !candidate.name.trim()) {
    throw new Error("'name' must be a non-empty string.");
  }
  if (!Array.isArray(candidate.options) || candidate.options.length === 0) {
    throw new Error("'options' must contain at least one option.");
  }

  const options = candidate.options.map((option, index) => {
    if (!option || typeof option !== 'object' || Array.isArray(option)) {
      throw new Error(`Option ${index + 1} must be an object.`);
    }
    if (typeof option.value !== 'string' || !option.value.trim()) {
      throw new Error(`Option ${index + 1} needs a non-empty 'value'.`);
    }
    if (typeof option.label !== 'string' || !option.label.trim()) {
      throw new Error(`Option '${option.value}' needs a non-empty 'label'.`);
    }
    return { value: option.value.trim(), label: option.label.trim() };
  });

  return { name: candidate.name.trim(), options };
}
