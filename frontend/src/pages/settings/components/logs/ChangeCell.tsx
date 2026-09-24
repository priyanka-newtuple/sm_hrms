import { ArrowRight, ChevronRight, Table2 } from 'lucide-react';

import { cn } from '@/lib/utils';

import { Badge } from '@/components/ui/badge';
import {
  diffTableField,
  formatFieldValue,
  summarizeTableChange,
  type FieldChangeRow,
} from './lib';

type Props = {
  row: FieldChangeRow;
  isExpanded: boolean;
  onToggle: () => void;
  resolveUserName: (userId: unknown) => string;
};

function ValuePair({ before, after }: { before: string; after: string }) {
  return (
    <>
      <span className="text-muted-foreground line-through">{before}</span>
      <ArrowRight className="h-3 w-3 shrink-0 text-muted-foreground" aria-hidden="true" />
      <span className="font-medium">{after}</span>
    </>
  );
}

/**
 * The Change column for one log row. Renders a masked placeholder, a lifecycle
 * event label, an expandable Table/Grid summary, or a plain before/after pair,
 * depending on which of those the row represents.
 */
export function ChangeCell({ row, isExpanded, onToggle, resolveUserName }: Props) {
  if (row.isMasked) return <span className="text-muted-foreground">Hidden</span>;

  if (row.eventLabel) {
    const isAssigneeChange = row.before !== undefined || row.after !== undefined;
    return (
      <span className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5">
        <span>{row.eventLabel}</span>
        {isAssigneeChange && (
          <ValuePair before={resolveUserName(row.before)} after={resolveUserName(row.after)} />
        )}
      </span>
    );
  }

  if (row.isTableField) {
    return (
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={isExpanded}
        className="group flex items-center gap-1.5"
      >
        <Badge variant="secondary" className="gap-1 font-normal">
          <Table2 className="h-3 w-3" aria-hidden="true" />
          {summarizeTableChange(diffTableField(row.before, row.after))}
        </Badge>
        <ChevronRight
          className={cn(
            'h-3.5 w-3.5 text-muted-foreground transition-transform duration-200 ease-out',
            isExpanded && 'rotate-90',
          )}
          aria-hidden="true"
        />
      </button>
    );
  }

  return (
    <span className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5">
      <ValuePair before={formatFieldValue(row.before)} after={formatFieldValue(row.after)} />
    </span>
  );
}

export default ChangeCell;
