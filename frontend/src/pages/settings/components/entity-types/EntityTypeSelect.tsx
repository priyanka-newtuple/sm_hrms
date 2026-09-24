import { useEffect, useState } from 'react';
import { AlertCircle, Loader2 } from 'lucide-react';
import { entityTypes as entityTypesApi } from '../../../../core/services/api';
import type { EntityType } from '../../../../core/types';
import { Select, FormField } from '../../../../core/components/Input';

interface EntityTypeSelectProps {
  value: string;
  onChange: (value: string) => void;
  label?: string;
  required?: boolean;
  helperText?: string;
  disabled?: boolean;
  id?: string;
}

export default function EntityTypeSelect({
  value,
  onChange,
  label = 'Entity Type',
  required,
  helperText,
  disabled,
  id = 'entity-type-select',
}: EntityTypeSelectProps) {
  const [types, setTypes] = useState<EntityType[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    entityTypesApi
      .list()
      .then((res) => {
        if (cancelled) return;
        setTypes(res.items);
        setError(null);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : 'Failed to load entity types');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) {
    return (
      <FormField label={label} required={required}>
        <div className="flex items-center gap-2 px-4 py-2.5 bg-muted/50 border border-border rounded-lg text-sm text-muted-foreground">
          <Loader2 className="w-4 h-4 animate-spin" />
          Loading entity types…
        </div>
      </FormField>
    );
  }

  if (error) {
    return (
      <FormField label={label} required={required}>
        <div className="flex items-start gap-2 px-4 py-2.5 bg-destructive-subtle border border-destructive/30 rounded-lg text-sm text-destructive">
          <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
          <span>{error}</span>
        </div>
      </FormField>
    );
  }

  if (types.length === 0) {
    return (
      <FormField label={label} required={required}>
        <div className="px-4 py-3 bg-warning-subtle border border-warning/30 rounded-lg text-sm text-warning">
          No entity types defined yet. Go to{' '}
          <a href="/settings?tab=entities" className="font-medium underline">
            Settings &rsaquo; Entities
          </a>{' '}
          to create one.
        </div>
      </FormField>
    );
  }

  const options = types.map((t) => ({
    value: t.name,
    label: t.display_name ? `${t.display_name} (${t.name})` : t.name,
  }));

  // If the current value isn't in the list (legacy data), surface it so the
  // user sees what's saved rather than silently flipping to the first option.
  const valueMissing = value && !types.some((t) => t.name === value);
  const displayOptions = valueMissing
    ? [{ value, label: `${value} (unregistered)` }, ...options]
    : options;

  return (
    <Select
      id={id}
      label={label}
      required={required}
      helperText={
        valueMissing
          ? `"${value}" is not registered — pick a registered entity type or add it in Settings › Entities.`
          : helperText
      }
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder="Select an entity type"
      options={displayOptions}
      disabled={disabled}
    />
  );
}
