/**
 * DashboardTable Component
 *
 * Presentational, responsive table for dashboard "rows" widgets. Renders a
 * sticky header, horizontal scroll on overflow, zebra striping, and readable
 * cell values (dates, numbers). No data fetching or business logic.
 */

import { useMemo } from 'react';
import { cn } from '../../lib/utils';
import { formatTableCell, isNumericValue } from '../utils';

interface DashboardTableColumn {
  key: string;
  label: string;
}

interface DashboardTableProps {
  columns: DashboardTableColumn[];
  rows: Record<string, unknown>[];
  className?: string;
}

export default function DashboardTable({ columns, rows, className }: DashboardTableProps) {
  // Right-align a column when its first non-null value is numeric.
  const numericKeys = useMemo(() => {
    const keys = new Set<string>();
    for (const col of columns) {
      const sample = rows.find((r) => r[col.key] != null);
      if (sample && isNumericValue(sample[col.key])) keys.add(col.key);
    }
    return keys;
  }, [columns, rows]);

  if (rows.length === 0) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
        No rows
      </div>
    );
  }

  return (
    <div
      className={cn(
        'widget-no-drag h-full overflow-auto rounded-lg border border-border',
        className,
      )}
    >
      <table className="w-full border-collapse text-sm">
        <thead className="sticky top-0 z-10 bg-muted/80 backdrop-blur supports-[backdrop-filter]:bg-muted/60">
          <tr>
            {columns.map((c) => (
              <th
                key={c.key}
                scope="col"
                className={cn(
                  'whitespace-nowrap border-b border-border px-4 py-2.5 font-semibold uppercase tracking-wide text-xs text-muted-foreground',
                  numericKeys.has(c.key) ? 'text-right' : 'text-left',
                )}
              >
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr
              key={i}
              className="border-b border-border/40 transition-colors odd:bg-background even:bg-muted/20 hover:bg-cobalt/5"
            >
              {columns.map((c) => {
                const display = formatTableCell(row[c.key]);
                const isEmpty = row[c.key] == null;
                return (
                  <td
                    key={c.key}
                    title={display}
                    className={cn(
                      'max-w-[24rem] truncate px-4 py-2.5',
                      numericKeys.has(c.key)
                        ? 'text-right font-mono tabular-nums'
                        : 'text-left',
                      isEmpty ? 'text-muted-foreground' : 'text-foreground',
                    )}
                  >
                    {display}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export type { DashboardTableProps, DashboardTableColumn };
