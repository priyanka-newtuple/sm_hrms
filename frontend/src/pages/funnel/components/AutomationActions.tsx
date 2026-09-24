import { Loader2, Pencil, Play, Trash2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import type { EntitySchedule } from '@/core/services/api/schedules';

interface Props {
  schedule: EntitySchedule;
  busy: boolean;
  runPreviewLoadingId: string | null;
  onEdit: (schedule: EntitySchedule) => void;
  onRunNow: (schedule: EntitySchedule) => void | Promise<void>;
  onToggle: (schedule: EntitySchedule) => void | Promise<void>;
  onDelete: (schedule: EntitySchedule) => void;
}

export function AutomationActions({
  schedule,
  busy,
  runPreviewLoadingId,
  onEdit,
  onRunNow,
  onToggle,
  onDelete,
}: Props) {
  return (
    <div className="flex items-center gap-2">
      <span className="rounded-full bg-muted px-2 py-1 text-xs font-medium">
        {schedule.completed_at ? 'Completed' : schedule.is_enabled ? 'Active' : 'Paused'}
      </span>
      {!schedule.completed_at && (
        <Button variant="outline" size="sm" disabled={busy} onClick={() => onEdit(schedule)}>
          <Pencil className="mr-1 h-3.5 w-3.5" /> Edit
        </Button>
      )}
      <Button
        variant="outline"
        size="sm"
        disabled={!schedule.is_enabled || runPreviewLoadingId !== null}
        onClick={() => void onRunNow(schedule)}
      >
        {runPreviewLoadingId === schedule.schedule_id ? (
          <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
        ) : (
          <Play className="mr-1 h-3.5 w-3.5" />
        )}
        Run now
      </Button>
      {!schedule.completed_at && (
        <Button variant="outline" size="sm" onClick={() => void onToggle(schedule)}>
          {schedule.is_enabled ? 'Pause' : 'Enable'}
        </Button>
      )}
      <Button
        variant="ghost-danger"
        size="icon-sm"
        aria-label={`Delete ${schedule.name}`}
        onClick={() => onDelete(schedule)}
      >
        <Trash2 className="h-3.5 w-3.5" />
      </Button>
    </div>
  );
}
