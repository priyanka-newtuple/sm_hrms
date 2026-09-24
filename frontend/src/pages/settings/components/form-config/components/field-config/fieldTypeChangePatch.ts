import type { FieldType, FormField } from '@/core/types';

const NEW_TABLE_CONFIG: FormField['table_config'] = {
  row_mode: 'dynamic',
  display_mode: 'grid',
  allow_delete_rows: true,
  min_rows: 0,
  columns: [{ id: 'column_1', label: 'Column 1', type: 'text' }],
};

const PICKLIST_TYPES: readonly FieldType[] = ['select', 'multi_select', 'picklist_multi'];

/**
 * The patch a field type change has to apply, beyond the type itself.
 *
 * Every type-specific key is either kept (the new type still uses it) or cleared
 * (it doesn't), so switching a field's type twice cannot leave a picklist
 * binding or a table config behind for a type that ignores it. Shared by both
 * configurators because they were clearing slightly different sets — the Forms
 * tab kept a stale `unit` on a field that was no longer an integer.
 */
export function fieldTypeChangePatch(type: FieldType, draft: FormField): Partial<FormField> {
  const isPicklist = PICKLIST_TYPES.includes(type);
  return {
    type,
    picklist_id: isPicklist ? draft.picklist_id : undefined,
    enum_values: isPicklist ? draft.enum_values : undefined,
    picklist_id_2: type === 'picklist_multi' ? draft.picklist_id_2 : undefined,
    enum_values_2: type === 'picklist_multi' ? draft.enum_values_2 : undefined,
    extensions: type === 'picklist_multi' ? draft.extensions : undefined,
    table_config: type === 'table' ? draft.table_config ?? NEW_TABLE_CONFIG : undefined,
    document_config: type === 'document' ? draft.document_config : undefined,
    unit: type === 'integer' ? draft.unit : undefined,
  };
}
