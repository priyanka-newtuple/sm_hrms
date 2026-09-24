import { useEffect, useState } from 'react';
import { AlertCircle, Loader2 } from 'lucide-react';
import { stateMachines } from '../../../core/services/api';
import type { WorkflowService } from '../../../core/types';
import { Select, FormField } from '../../../core/components/Input';

const NO_SERVICE_VALUE = '';

interface ServiceSelectProps {
  value: string | null | undefined;
  onChange: (value: string | null) => void;
  label?: string;
  helperText?: string;
  disabled?: boolean;
  id?: string;
}

/**
 * Picker for the optional Service a workflow is filed under.
 *
 * Mirrors EntityTypeSelect, with two differences: Service is never required
 * (a "No service" option is always first and always valid), and an empty
 * catalog is a normal starting state rather than a warning, since an
 * organization simply hasn't created any services yet.
 */
export default function ServiceSelect({
  value,
  onChange,
  label = 'Service',
  helperText = 'Optional grouping used to file this workflow under a service. Manage the list from Workflows.',
  disabled,
  id = 'workflow-service-select',
}: ServiceSelectProps) {
  const [services, setServices] = useState<WorkflowService[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    stateMachines.services
      .list()
      .then((res) => {
        if (cancelled) return;
        setServices(res.items);
        setError(null);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : 'Failed to load services');
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
      <FormField label={label}>
        <div className="flex items-center gap-2 px-4 py-2.5 bg-muted/50 border border-border rounded-lg text-sm text-muted-foreground">
          <Loader2 className="w-4 h-4 animate-spin" />
          Loading services…
        </div>
      </FormField>
    );
  }

  if (error) {
    return (
      <FormField label={label}>
        <div className="flex items-start gap-2 px-4 py-2.5 bg-destructive-subtle border border-destructive/30 rounded-lg text-sm text-destructive">
          <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
          <span>{error}</span>
        </div>
      </FormField>
    );
  }

  const currentValue = value ?? NO_SERVICE_VALUE;
  const options = [
    { value: NO_SERVICE_VALUE, label: 'No service' },
    ...services.map((s) => ({ value: s.service_id, label: s.name })),
  ];

  // If the current value isn't in the list (deleted service, legacy data),
  // surface it so the user sees what's saved rather than silently flipping to
  // "No service".
  const valueMissing = currentValue !== NO_SERVICE_VALUE && !services.some((s) => s.service_id === currentValue);
  const displayOptions = valueMissing
    ? [{ value: currentValue, label: `${currentValue} (unregistered)` }, ...options]
    : options;

  return (
    <Select
      id={id}
      label={label}
      helperText={
        valueMissing
          ? `This workflow's saved service is no longer in the list. Pick a registered service, or "No service" to clear it.`
          : helperText
      }
      value={currentValue}
      onChange={(e) => onChange(e.target.value === NO_SERVICE_VALUE ? null : e.target.value)}
      options={displayOptions}
      disabled={disabled}
    />
  );
}
