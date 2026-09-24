import type { ExportField } from '@/lib/export/types';
import { Checkbox } from '@/components/ui/checkbox';
import { cn } from '@/lib/utils';

interface FieldGroupProps {
  title: string;
  fields: ExportField[];
  isSelected: (key: string) => boolean;
  onToggle: (key: string) => void;
  onSelectAll: () => void;
  onClear: () => void;
}

function fillHint(field: ExportField): string | null {
  if (field.totalCount === 0) return null;
  if (field.fillCount === 0) return 'empty';
  if (field.fillCount < field.totalCount) {
    return `${field.totalCount - field.fillCount} blank`;
  }
  return null;
}

/** One labelled group of checkbox field rows with select-all / clear. */
export default function FieldGroup({
  title,
  fields,
  isSelected,
  onToggle,
  onSelectAll,
  onClear,
}: FieldGroupProps) {
  if (fields.length === 0) return null;

  const selectedCount = fields.reduce((n, f) => (isSelected(f.key) ? n + 1 : n), 0);
  const allSelected = selectedCount === fields.length;
  const noneSelected = selectedCount === 0;

  return (
    <section className="mb-5">
      <div className="mb-2 flex items-center justify-between px-1">
        <div className="flex items-center gap-2">
          <h3 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            {title}
          </h3>
          <span className="rounded-full bg-muted px-1.5 py-0.5 text-[10px] font-medium tabular-nums text-muted-foreground">
            {selectedCount}/{fields.length}
          </span>
        </div>
        <div className="flex items-center gap-1 text-xs">
          <button
            type="button"
            disabled={allSelected}
            onClick={onSelectAll}
            className="rounded px-1.5 py-0.5 font-medium text-primary transition-colors hover:bg-primary/10 disabled:opacity-40 disabled:hover:bg-transparent"
          >
            Select all
          </button>
          <button
            type="button"
            disabled={noneSelected}
            onClick={onClear}
            className="rounded px-1.5 py-0.5 font-medium text-muted-foreground transition-colors hover:bg-muted disabled:opacity-40 disabled:hover:bg-transparent"
          >
            Clear
          </button>
        </div>
      </div>
      <ul className="space-y-0.5">
        {fields.map((field) => {
          const checked = isSelected(field.key);
          const hint = fillHint(field);
          const empty = field.fillCount === 0 && field.totalCount > 0;
          return (
            <li key={field.key}>
              <label
                className={cn(
                  'flex cursor-pointer items-center gap-3 rounded-lg px-2.5 py-2 transition-colors',
                  checked ? 'bg-primary/5' : 'hover:bg-muted',
                )}
              >
                <Checkbox checked={checked} onCheckedChange={() => onToggle(field.key)} />
                <span
                  className={cn(
                    'flex-1 truncate text-sm',
                    empty ? 'text-muted-foreground' : 'text-foreground',
                  )}
                >
                  {field.label}
                </span>
                {hint && (
                  <span className="shrink-0 rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
                    {hint}
                  </span>
                )}
              </label>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
