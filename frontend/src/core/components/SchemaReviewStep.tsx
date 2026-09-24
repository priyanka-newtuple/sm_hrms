import { Pencil } from 'lucide-react';
import type { FormField, FormSchema } from '@/core/types';
import { getFormFields, parseCurrencyValue } from '@/shared/utils/entityForm';
import { formatCurrencyValue } from '@/shared/utils/entityDisplay';

interface SchemaReviewStepProps {
  schemas: FormSchema[];
  values: Record<string, unknown>;
  onEdit: (schemaIndex: number) => void;
}

function formatFieldValue(field: FormField, value: unknown): string | null {
  if (field.type === 'section') return null;
  if (value === undefined || value === null || value === '') return null;
  if (field.type === 'boolean') return value ? 'Yes' : 'No';
  if (field.type === 'multi_select') {
    if (Array.isArray(value)) return value.filter(Boolean).join(', ') || null;
    return String(value) || null;
  }
  if (field.type === 'currency') {
    const cv = parseCurrencyValue(value);
    if (cv !== null) {
      const code = typeof cv.currency_code === 'string' ? cv.currency_code : '';
      const formatted = formatCurrencyValue(cv.amount, code);
      return formatted || null;
    }
    return String(value) || null;
  }
  return String(value) || null;
}

export default function SchemaReviewStep({ schemas, values, onEdit }: SchemaReviewStepProps) {
  return (
    <div className="space-y-6">
      <h4 className="text-xl font-medium text-foreground">Review & Confirm</h4>
      <div className="rounded-xl border border-border bg-card divide-y divide-border overflow-hidden">
        {schemas.map((schema, schemaIndex) => {
          const fields = getFormFields(schema).filter((f) => f.type !== 'section');
          const filledFields = fields.filter((f) => formatFieldValue(f, values[f.id]) !== null);

          return (
            <div key={schema.schema_key} className="px-6 py-5">
              <div className="flex items-center justify-between mb-3">
                <h5 className="text-base font-semibold text-foreground">{schema.name}</h5>
                <button
                  type="button"
                  onClick={() => onEdit(schemaIndex)}
                  className="rounded-full p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                  aria-label={`Edit ${schema.name}`}
                >
                  <Pencil className="h-4 w-4" />
                </button>
              </div>
              {filledFields.length === 0 ? (
                <p className="text-sm text-muted-foreground">No values entered.</p>
              ) : (
                <div className="space-y-1">
                  {filledFields.map((field) => (
                    <p key={field.id} className="text-sm text-muted-foreground">
                      <span className="font-medium text-foreground">{field.label}:</span>{' '}
                      {formatFieldValue(field, values[field.id])}
                    </p>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
