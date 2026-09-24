import { ArrowRight } from 'lucide-react';

import { cn } from '@/lib/utils';
import { formatFieldLabel, formatFieldValue, type TableChange, type TableRowDetail } from './lib';

type Props = { change: TableChange };
type Tone = 'added' | 'removed';

/**
 * A row that was added to or removed from a Table/Grid field, listing every
 * column it held. `tone` selects the chip and whether values are struck
 * through: 'added' for rows that appeared, 'removed' for rows that went.
 */
function RowDetailCard({ row, tone }: { row: TableRowDetail; tone: Tone }) {
  const isAdded = tone === 'added';
  return (
    <div className="rounded-md border border-border bg-background px-3 py-2">
      <span
        className={cn(
          'rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide',
          isAdded ? 'bg-success-subtle text-success' : 'bg-muted text-muted-foreground',
        )}
      >
        {isAdded ? 'Added' : 'Removed'}
      </span>
      {row.cells.length > 0 && (
        <dl className="mt-1.5 flex flex-wrap gap-x-5 gap-y-1">
          {row.cells.map((cell) => (
            <div key={cell.column} className="flex items-baseline gap-1.5">
              <dt className="text-[10px] uppercase tracking-wide text-muted-foreground">
                {formatFieldLabel(cell.column)}
              </dt>
              <dd className={cn('text-xs', !isAdded && 'line-through')}>
                {formatFieldValue(cell.value)}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}

export function TableChangeDetail({ change }: Props) {
  const { addedRows, removedRows, cellChanges } = change;

  if (!addedRows.length && !removedRows.length && !cellChanges.length) {
    return (
      <p className="text-xs text-muted-foreground">
        No cell-level detail available for this change.
      </p>
    );
  }

  return (
    <div className="animate-in fade-in-0 slide-in-from-top-1 space-y-2 pl-1 duration-200 ease-out">
      {addedRows.map((row, index) => (
        <RowDetailCard key={`added:${index}`} row={row} tone="added" />
      ))}
      {removedRows.map((row, index) => (
        <RowDetailCard key={`removed:${index}`} row={row} tone="removed" />
      ))}
      {cellChanges.length > 0 && (
        <div className="rounded-md border border-border bg-background px-3 py-2">
          <dl className="space-y-1.5">
            {cellChanges.map((cell) => (
              <div
                key={`${cell.rowLabel}:${cell.column}`}
                className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5"
              >
                <dt className="text-[10px] uppercase tracking-wide text-muted-foreground">
                  {cell.rowLabel} · {formatFieldLabel(cell.column)}
                </dt>
                <dd className="flex flex-wrap items-center gap-1.5 text-xs">
                  <span className="text-muted-foreground line-through">
                    {formatFieldValue(cell.before)}
                  </span>
                  <ArrowRight className="h-3 w-3 shrink-0 text-muted-foreground" aria-hidden="true" />
                  <span className="font-medium">{formatFieldValue(cell.after)}</span>
                </dd>
              </div>
            ))}
          </dl>
        </div>
      )}
    </div>
  );
}

export default TableChangeDetail;
