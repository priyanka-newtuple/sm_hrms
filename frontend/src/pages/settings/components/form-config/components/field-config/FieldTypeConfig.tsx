/**
 * Every type-specific config section of a field editor, dispatched by the
 * field's type.
 *
 * Both configurators mount this: Settings -> Forms (`FieldRow`) and Settings ->
 * Fields (`LibraryFieldEditor`), which is a fork of it. They used to carry a
 * copy each, which is how they came to disagree on control styling and on which
 * keys a type change clears. The shared bits live here; what genuinely differs
 * between the two surfaces stays in the caller — the Field Library's integer
 * `unit` (`IntegerUnitConfig`, mounted there alone because the form-schema path
 * has nowhere to persist a unit) and its Description input.
 *
 * A field has one type, so at most one section renders — except a numeric
 * field, which also gets the calc builder.
 */

import type { FormField, Picklist } from '@/core/types';
import CalcBuilder from '../CalcBuilder';
import { TableFieldBuilder, type TableFieldBuilderProps } from '../TableFieldBuilder';
import AutoNumberConfig from './AutoNumberConfig';
import DocumentConfig from './DocumentConfig';
import PicklistConfig from './PicklistConfig';
import StyleConfig from './StyleConfig';

const EMPTY_TABLE_CONFIG: TableFieldBuilderProps['config'] = {
  row_mode: 'dynamic',
  display_mode: 'grid',
  columns: [],
};

type FieldTypeConfigProps = {
  field: FormField;
  picklists: Picklist[];
  canWrite: boolean;
  onChange: (patch: Partial<FormField>) => void;
  numericFields: TableFieldBuilderProps['numericFields'];
  tableFields: TableFieldBuilderProps['tableFields'];
  /** Keeps the table builder's input ids unique when several are on one page. */
  tableInstanceId: TableFieldBuilderProps['instanceId'];
};

export default function FieldTypeConfig({
  field,
  picklists,
  canWrite,
  onChange,
  numericFields,
  tableFields,
  tableInstanceId,
}: FieldTypeConfigProps) {
  const isNumeric = field.type === 'integer' || field.type === 'number';

  return (
    <>
      <PicklistConfig field={field} picklists={picklists} canWrite={canWrite} onChange={onChange} />

      {field.type === 'document' && (
        <DocumentConfig field={field} canWrite={canWrite} onChange={onChange} />
      )}

      {field.type === 'auto_number' && (
        <AutoNumberConfig field={field} canWrite={canWrite} onChange={onChange} />
      )}

      {(field.type === 'text' || field.type === 'textarea') && (
        <StyleConfig field={field} canWrite={canWrite} onChange={onChange} />
      )}

      {field.type === 'table' && (
        <TableFieldBuilder
          config={field.table_config ?? EMPTY_TABLE_CONFIG}
          onChange={(tableConfig) => onChange({ table_config: tableConfig })}
          numericFields={numericFields}
          tableFields={tableFields}
          canWrite={canWrite}
          instanceId={tableInstanceId}
        />
      )}

      {isNumeric && (
        <CalcBuilder
          mode="field"
          value={field.calc}
          onChange={(calc) => onChange({ calc })}
          numericFields={numericFields}
          tableFields={tableFields}
        />
      )}
    </>
  );
}
