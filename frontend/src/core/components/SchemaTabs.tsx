import { cn } from '@/lib/utils';
import type { FormSchema } from '@/core/types';

interface SchemaTabsProps {
  /** Forms attached to the entity type; each renders as a tab. */
  schemas: FormSchema[];
  /** schema_key of the active form, or an extra tab's key. */
  activeKey: string | undefined;
  onSelect: (schema: FormSchema) => void;
  /** Non-form tabs rendered after the form tabs (e.g. filing forms). */
  extraTabs?: { key: string; label: string }[];
  onSelectExtra?: (key: string) => void;
}

/**
 * Tab bar for switching between the forms attached to one entity type, plus
 * any extra tabs. Used by the detail view and the add-/edit-entity dialogs.
 * Renders nothing when there is only one tab in total.
 */
export default function SchemaTabs({
  schemas,
  activeKey,
  onSelect,
  extraTabs = [],
  onSelectExtra,
}: SchemaTabsProps) {
  if (schemas.length + extraTabs.length <= 1) return null;
  return (
    <div className="flex flex-shrink-0 gap-1 overflow-x-auto border-b border-border px-2 pt-2">
      {schemas.map((s) => (
        <button
          key={s.schema_key}
          type="button"
          onClick={() => onSelect(s)}
          className={cn(
            'whitespace-nowrap rounded-t-lg px-3 py-2 text-sm font-medium transition-colors',
            s.schema_key === activeKey
              ? 'border-b-2 border-primary text-primary'
              : 'text-muted-foreground hover:text-foreground',
          )}
        >
          {s.name}
        </button>
      ))}
      {extraTabs.map((tab) => (
        <button
          key={tab.key}
          type="button"
          onClick={() => onSelectExtra?.(tab.key)}
          className={cn(
            'whitespace-nowrap rounded-t-lg px-3 py-2 text-sm font-medium transition-colors',
            tab.key === activeKey
              ? 'border-b-2 border-primary text-primary'
              : 'text-muted-foreground hover:text-foreground',
          )}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
