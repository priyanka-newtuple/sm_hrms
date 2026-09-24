/**
 * One custom form's schema, rendered a section at a time.
 *
 * Loads nothing and holds no draft of its own: the schema arrived with the
 * record and the answers are ordinary data fields, so this reports changes as
 * plain `{key: value}` and the record's normal draft state owns them.
 */

import { useMemo } from 'react';

import type { CustomFormSchema } from '@/core/types';
import { cellChangeToValues, cellToField, cellValue } from '@/lib/custom-form/fields';
import EntityFormFields from '@/pages/records/detail/components/EntityFormFields';

interface CustomFormPanelProps {
  schema: CustomFormSchema;
  /** The record's draft data — where this form's answers live. */
  values: Record<string, unknown>;
  canEdit: boolean;
  activeSectionId?: string;
  onChange: (values: Record<string, unknown>) => void;
}

export default function CustomFormPanel({
  schema,
  values,
  canEdit,
  activeSectionId,
  onChange,
}: CustomFormPanelProps) {
  const activeSection = useMemo(
    () =>
      schema.sections?.find((section) => section.id === activeSectionId) ??
      schema.sections?.[0] ??
      null,
    [schema.sections, activeSectionId],
  );

  const handleCellChange = (cellId: string, value: unknown) => {
    const cell = activeSection?.cells.find((item) => item.id === cellId);
    if (!cell || !cell.editable) return;
    onChange(cellChangeToValues(cell, value));
  };

  if (!activeSection) {
    return (
      <div className="rounded-xl border border-border bg-card p-8 text-center">
        <p className="text-sm text-muted-foreground">
          This form has no sections for this record yet.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-border bg-card p-4">
        <EntityFormFields
          fields={activeSection.cells.map(cellToField)}
          values={Object.fromEntries(
            activeSection.cells.map((cell) => [cell.id, cellValue(cell, values)]),
          )}
          onChange={handleCellChange}
          mode={canEdit ? 'edit' : 'view'}
          compact
          documentPreviewEnabled
        />
      </div>
    </div>
  );
}
