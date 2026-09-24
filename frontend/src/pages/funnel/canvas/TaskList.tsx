import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Trash2 } from "lucide-react";
import type { TransitionTask } from "@/lib/state-machine/types";
import { DDSelect } from "./DDSelect";

interface TaskListProps {
  tasks: TransitionTask[];
  onChange: (next: TransitionTask[]) => void;
}

function EmptyHint({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-md border border-dashed border-border p-3 text-center text-xs text-muted-foreground">
      {children}
    </div>
  );
}

export function TaskList({ tasks, onChange }: TaskListProps) {
  if (tasks.length === 0) {
    return <EmptyHint>No tasks.</EmptyHint>;
  }

  const update = (i: number, patch: Partial<TransitionTask>) =>
    onChange(tasks.map((t, j) => (j === i ? { ...t, ...patch } : t)));

  return (
    <div className="space-y-2">
      {tasks.map((tk, i) => (
        <div key={i} className="rounded-md border border-border bg-background p-3">
          <div className="grid gap-2 sm:grid-cols-12">
            <div className="space-y-1 sm:col-span-5">
              <Label className="text-xs">Task identifier</Label>
              <Input
                value={tk.task}
                onChange={(e) => update(i, { task: e.target.value })}
                placeholder="task_record_transition"
                className="font-mono text-xs"
              />
            </div>
            <div className="space-y-1 sm:col-span-5">
              <Label className="text-xs">Label</Label>
              <Input value={tk.label} onChange={(e) => update(i, { label: e.target.value })} />
            </div>
            <div className="space-y-1 sm:col-span-2">
              <Label className="text-xs">Order</Label>
              <Input
                type="number"
                value={tk.order}
                onChange={(e) => update(i, { order: Number(e.target.value) || 1 })}
              />
            </div>
            <div className="flex items-end gap-4 sm:col-span-6">
              <label className="flex items-center gap-2 text-xs">
                <Checkbox
                  checked={tk.required}
                  onCheckedChange={(v) => update(i, { required: !!v })}
                />
                Required
              </label>
              <div className="flex items-center gap-2 text-xs">
                <span>On failure</span>
                <div className="w-28">
                  <DDSelect
                    value={tk.on_failure}
                    options={[
                      { value: "stop", label: "Stop" },
                      { value: "continue", label: "Continue" },
                    ]}
                    onSelect={(v) => update(i, { on_failure: v as "stop" | "continue" })}
                  />
                </div>
              </div>
            </div>
            <div className="flex justify-end sm:col-span-6">
              <Button
                variant="ghost"
                size="icon"
                onClick={() => onChange(tasks.filter((_, j) => j !== i))}
              >
                <Trash2 className="h-4 w-4 text-muted-foreground" />
              </Button>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
