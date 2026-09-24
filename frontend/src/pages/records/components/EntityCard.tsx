import { ArrowRight, Database } from 'lucide-react';
import type { EntityType, FormSchema } from '../../../core/types';
import { resolveEntityTypeLabel } from '../../../shared/utils/labels';
import { formatCount, formatUpdatedAt, iconClassFor } from './utils';

interface EntityCardProps {
  entityType: EntityType;
  schema?: FormSchema;
  count: number;
  onOpen: () => void;
}

export default function EntityCard({ entityType, schema, count, onOpen }: EntityCardProps) {
  const iconClass = iconClassFor(entityType.name);
  const fieldCount = schema?.schema?.fields?.length ?? 0;
  const label = resolveEntityTypeLabel(entityType.name, entityType);
  const description = entityType.description || 'Workspace entity';

  return (
    <button
      type="button"
      onClick={onOpen}
      className="group flex flex-col rounded-xl border border-border bg-card p-5 text-left transition-all hover:border-primary/40 hover:shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
    >
      <div className="flex items-start gap-3">
        <div className={`flex h-10 w-10 items-center justify-center rounded-xl ${iconClass}`}>
          <Database className="h-5 w-5" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-foreground truncate">{label}</span>
            <span className="rounded-md border border-border bg-muted px-1.5 py-0.5 text-[11px] font-medium text-muted-foreground">
              {formatCount(count)}
            </span>
          </div>
          <p className="mt-0.5 text-sm text-muted-foreground truncate">{description}</p>
        </div>
        <ArrowRight className="h-4 w-4 text-muted-foreground/50 group-hover:text-primary transition-colors mt-1" />
      </div>
      <div className="mt-4 border-t border-dashed border-border pt-3 text-xs text-muted-foreground">
        <span className="font-medium text-foreground">{fieldCount}</span> fields · updated{' '}
        {formatUpdatedAt(entityType.updated_at)}
      </div>
    </button>
  );
}
