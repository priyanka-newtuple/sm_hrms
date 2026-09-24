/** Field types accepted by the backend's EntityField contract. */
export const STORED_FORM_FIELD_TYPES = [
  'string',
  'text',
  'email',
  'phone',
  'url',
  'number',
  'int',
  'integer',
  'float',
  'boolean',
  'date',
  'datetime',
  'enum',
  'json',
  'multi_select',
  'auto_number',
  'currency',
] as const;

/** One backend-supported stored form field type. */
export type StoredFormFieldType = (typeof STORED_FORM_FIELD_TYPES)[number];

/** Backend-native form field used by the portable JSON editor. */
export interface StoredFormField {
  field: string;
  type: StoredFormFieldType;
  [key: string]: unknown;
}

/** Entity-neutral backend form configuration; entity attachment stays outside the JSON. */
export interface PortableFormConfig {
  name: string;
  fields: StoredFormField[];
}
