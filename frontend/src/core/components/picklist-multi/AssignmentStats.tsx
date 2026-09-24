/** Step 3's footer: how many rows have items, and how many assignments total. */

import { Layers, Map as MapIcon } from 'lucide-react';
import { assignmentCount, type Row } from './rows';

export default function AssignmentStats({ rows }: { rows: Row[] }) {
  const configuredCount = rows.filter((row) => row.toggles.length > 0).length;
  const totalAssignments = assignmentCount(rows);

  return (
    <div className="mt-2.5 flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
      <span className="flex items-center gap-1.5">
        <MapIcon size={14} className="text-cobalt" />
        <b className="font-semibold text-foreground">{configuredCount}</b> of {rows.length} configured
      </span>
      <span className="flex items-center gap-1.5">
        <Layers size={14} className="text-cobalt" />
        <b className="font-semibold text-foreground">{totalAssignments}</b> item assignments
      </span>
    </div>
  );
}
