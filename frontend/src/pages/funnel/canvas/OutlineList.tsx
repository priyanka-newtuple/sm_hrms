import { Badge } from "@/components/ui/badge";
import { ArrowRight, CircleDot, ListChecks, Plus, Shield, Trash2 } from "lucide-react";
import type { StateMachineDocument } from "@/lib/state-machine/types";
import { Button } from '@/components/ui/button';

interface OutlineListProps {
  doc: StateMachineDocument;
  onSelectState: (name: string) => void;
  onSelectTransition: (key: string) => void;
  onDeleteState?: (name: string) => void;
  onDeleteTransition?: (key: string) => void;
  onCreateTransition?: (from: string, to: string) => void;
}

export function OutlineList({
  doc,
  onSelectState,
  onSelectTransition,
  onDeleteState,
  onDeleteTransition,
  onCreateTransition,
}: OutlineListProps) {
  const def = doc.definition;

  return (
    <div className="space-y-6 p-4">
      <section>
        <div className="mb-2 flex items-center justify-between">
          <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            States ({def.states.length})
          </div>
        </div>
        {def.states.length === 0 ? (
          <div className="rounded-md border border-dashed border-border p-3 text-center text-xs text-muted-foreground">
            No states yet.
          </div>
        ) : (
          <ul className="divide-y divide-border rounded-md border border-border">
            {def.states.map((s) => {
              const isInitial = s.tags?.includes("initial");
              const isTerminal = s.tags?.includes("terminal");
              return (
                <li
                  key={s.name}
                  className="group flex items-center gap-2 px-3 py-2 hover:bg-muted/40"
                >
                  <CircleDot
                    className="h-3.5 w-3.5 flex-shrink-0"
                    style={{
                      color: isInitial
                        ? "var(--state-initial)"
                        : isTerminal
                          ? "var(--state-terminal-success)"
                          : "var(--state-default)",
                    }}
                  />
                  <Button
                    variant="ghost"
                    size="sm"
                    className="min-w-0 flex-1 justify-start truncate text-left font-mono text-xs"
                    onClick={() => onSelectState(s.name)}
                    title="Edit state"
                  >
                    {s.name}
                  </Button>
                  {isInitial && (
                    <Badge variant="secondary" className="text-[9px] uppercase tracking-wider">
                      Initial
                    </Badge>
                  )}
                  {isTerminal && (
                    <Badge variant="secondary" className="text-[9px] uppercase tracking-wider">
                      Terminal
                    </Badge>
                  )}
                  {onDeleteState && (
                    <Button
                      variant="ghost-danger"
                      size="icon-sm"
                      className="ml-1 opacity-0 group-hover:opacity-100"
                      onClick={() => onDeleteState(s.name)}
                      title="Delete state"
                      aria-label="Delete state"
                    >
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section>
        <div className="mb-2 flex items-center justify-between">
          <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Transitions ({def.transitions.length})
          </div>
          {onCreateTransition && def.states.length >= 2 && (
            <Button
              variant="ghost"
              size="sm"
              className="text-[11px]"
              onClick={() => {
                const a = def.states[0]?.name;
                const b = def.states[1]?.name ?? def.states[0]?.name;
                if (a && b) onCreateTransition(a, b);
              }}
            >
              <Plus className="h-3 w-3" /> New
            </Button>
          )}
        </div>
        {def.transitions.length === 0 ? (
          <div className="rounded-md border border-dashed border-border p-3 text-center text-xs text-muted-foreground">
            No transitions yet. Drag the <Plus className="inline h-3 w-3" /> handle on a state to
            create one.
          </div>
        ) : (
          <ul className="divide-y divide-border rounded-md border border-border">
            {def.transitions.map((t) => {
              const guards = t.guards?.length ?? 0;
              const tasks =
                (t.pre_transition_tasks?.length ?? 0) + (t.post_transition_tasks?.length ?? 0);
              return (
                <li
                  key={t.key}
                  className="group flex items-center gap-2 px-3 py-2 hover:bg-muted/40"
                >
                  <Button
                    variant="ghost"
                    size="sm"
                    className="flex min-w-0 flex-1 items-center justify-start gap-1.5 text-left text-xs"
                    onClick={() => onSelectTransition(t.key)}
                    title="Edit transition"
                  >
                    <span className="truncate font-mono">{t.from}</span>
                    <ArrowRight className="h-3 w-3 flex-shrink-0 text-muted-foreground" />
                    <span className="truncate font-mono">{t.to_state}</span>
                    <span className="ml-1 truncate text-muted-foreground">
                      — {t.label || t.trigger}
                    </span>
                  </Button>
                  {guards > 0 && (
                    <span className="inline-flex items-center gap-0.5 rounded bg-muted px-1 py-0.5 text-[9px] font-medium text-muted-foreground">
                      <Shield className="h-2.5 w-2.5" /> {guards}
                    </span>
                  )}
                  {tasks > 0 && (
                    <span className="inline-flex items-center gap-0.5 rounded bg-muted px-1 py-0.5 text-[9px] font-medium text-muted-foreground">
                      <ListChecks className="h-2.5 w-2.5" /> {tasks}
                    </span>
                  )}
                  {onDeleteTransition && (
                    <Button
                      variant="ghost-danger"
                      size="icon-sm"
                      className="ml-1 opacity-0 group-hover:opacity-100"
                      onClick={() => onDeleteTransition(t.key)}
                      title="Delete transition"
                      aria-label="Delete transition"
                    >
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}
