import { Loader2 } from "lucide-react";

import type { EntitySchedule } from "@/core/services/api";

interface ScheduleActivationActionFieldsProps {
  schedules: EntitySchedule[];
  loading: boolean;
  selectedIds: string[];
  onSelectedIdsChange: (ids: string[]) => void;
  policy: string;
  onPolicyChange: (policy: string) => void;
  runOnce?: boolean;
}

export function ScheduleActivationActionFields({
  schedules,
  loading,
  selectedIds,
  onSelectedIdsChange,
  policy,
  onPolicyChange,
  runOnce = false,
}: ScheduleActivationActionFieldsProps) {
  const toggle = (scheduleId: string) => {
    onSelectedIdsChange(
      selectedIds.includes(scheduleId)
        ? selectedIds.filter((id) => id !== scheduleId)
        : [...selectedIds, scheduleId],
    );
  };

  return (
    <div className="space-y-4 rounded-lg border border-border bg-background p-3">
      <div>
        <p className="text-xs font-medium">
          {runOnce ? "Automations to run once" : "Recurring automations"}
        </p>
        <p className="mt-1 text-[11px] text-muted-foreground">
          {runOnce
            ? "When an entity enters this state, immediately create one configured batch without subscribing it to future batches."
            : "When an entity enters this state, subscribe only that entity to the selected automations."}
        </p>
      </div>
      {loading ? (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 className="h-3 w-3 animate-spin" /> Loading schedules…
        </div>
      ) : schedules.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          No automations are configured. Create one on the Automations page first.
        </p>
      ) : (
        <div className="max-h-44 space-y-2 overflow-y-auto">
          {schedules.map((schedule) => (
            <label key={schedule.schedule_id} className="flex cursor-pointer items-start gap-2 rounded-md border p-2">
              <input
                type="checkbox"
                checked={selectedIds.includes(schedule.schedule_id)}
                onChange={() => toggle(schedule.schedule_id)}
                className="mt-0.5"
              />
              <span className="min-w-0">
                <span className="block truncate text-xs font-medium">{schedule.name}</span>
                <span className="block text-[11px] text-muted-foreground">
                  {schedule.machine_name} · {schedule.recurrence.frequency}
                  {runOnce ? ` · ${schedule.occurrences_per_batch} per run` : ""}
                  {!schedule.is_enabled ? " · paused" : ""}
                </span>
              </span>
            </label>
          ))}
        </div>
      )}
      <label className="block space-y-1.5">
        <span className="text-xs font-medium">
          {runOnce ? "First period in the batch" : "First filing period"}
        </span>
        <select
          value={policy}
          onChange={(event) => onPolicyChange(event.target.value)}
          className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
        >
          <option value="current_period">Current month / quarter / year</option>
          <option value="next_occurrence">Next due date only</option>
        </select>
        <span className="block text-[11px] text-muted-foreground">
          {runOnce
            ? "Entities per run controls the batch size. Paused automations can be invoked here; pausing only disables automatic runs."
            : "Current period does not backfill earlier periods. If its filing date has passed, work appears immediately."}
        </span>
      </label>
    </div>
  );
}
