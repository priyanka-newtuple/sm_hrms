import { useState } from "react";
import { toast } from "sonner";
import { ChevronDown, ChevronUp, Plus } from "lucide-react";

import { ActionEditor } from "./ActionEditor";
import { ENTITY_ASSIGN_USER_KIND } from "./userAssignment";
import type { EntityField, StateAction } from "@/lib/state-machine/types";

const MAX_CONFIG_HINT_LENGTH = 40;

interface StateActionsSectionProps {
  actions: StateAction[];
  entityFields: EntityField[];
  entityType: string;
  outgoingTransitions: { key: string; trigger: string; label?: string; to_state: string }[];
  onChange: (actions: StateAction[]) => void;
}

/** Short config value so two same-kind actions are distinguishable in the list. */
function configHint(action: StateAction): string | null {
  if (action.kind === ENTITY_ASSIGN_USER_KIND) {
    const config = action.config ?? {};
    if (config.assignment_type === "originator") return "Originator";
    const name = config.action_display_name ?? config.user_id;
    return name ? `User: ${String(name)}`.slice(0, MAX_CONFIG_HINT_LENGTH) : null;
  }
  const [key, value] =
    Object.entries(action.config ?? {}).find(([, v]) => v != null && v !== "") ?? [];
  if (!key) return null;
  const str = typeof value === "string" ? value : JSON.stringify(value);
  return `${key}: ${str}`.slice(0, MAX_CONFIG_HINT_LENGTH);
}

/** Ordered action-chain editor for one state; actions run top-to-bottom on entry. */
export function StateActionsSection({
  actions,
  entityFields,
  entityType,
  outgoingTransitions,
  onChange,
}: StateActionsSectionProps) {
  // editingIndex === actions.length means "adding a new action".
  const [editingIndex, setEditingIndex] = useState<number | null>(null);

  // Outcome triggers (and agent decision routing) only live on the last action.
  const enforceLastOnly = (list: StateAction[]): StateAction[] => {
    let stripped = false;
    const cleaned = list.map((action, i) => {
      const isLast = i === list.length - 1;
      const hasTriggers = Object.keys(action.outcome_triggers ?? {}).length > 0;
      const hasDecisionField = Boolean(action.config?.outcome_field);
      if (isLast || (!hasTriggers && !hasDecisionField)) return action;
      stripped = true;
      const config = { ...(action.config ?? {}) };
      delete config.outcome_field;
      return { ...action, config, outcome_triggers: {} };
    });
    if (stripped) {
      toast.info("Outcome transitions removed — only the last action can have them.");
    }
    return cleaned;
  };

  const move = (index: number, direction: -1 | 1) => {
    const target = index + direction;
    if (target < 0 || target >= actions.length) return;
    const next = [...actions];
    [next[index], next[target]] = [next[target], next[index]];
    onChange(enforceLastOnly(next));
    setEditingIndex(null);
  };

  const saveAt = (index: number, action: StateAction | null) => {
    if (action === null) {
      // Remove when editing an existing action; cancel when adding a new one.
      if (index < actions.length) onChange(actions.filter((_, i) => i !== index));
      setEditingIndex(null);
      return;
    }
    const next =
      index >= actions.length
        ? [...actions, action]
        : actions.map((existing, i) => (i === index ? action : existing));
    onChange(enforceLastOnly(next));
    setEditingIndex(null);
  };

  return (
    <div className="space-y-2">
      {actions.map((action, i) =>
        editingIndex === i ? (
          <ActionEditor
            key={`edit-${i}`}
            action={action}
            entityFields={entityFields}
            entityType={entityType}
            outgoingTransitions={outgoingTransitions}
            isLast={i === actions.length - 1}
            onSave={(saved) => saveAt(i, saved)}
          />
        ) : (
          <div
            key={`row-${i}`}
            className="flex items-center justify-between gap-2 rounded-lg border border-border bg-muted/40 px-3 py-2"
          >
            <div className="flex min-w-0 items-center gap-2">
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[11px] font-semibold text-primary">
                {i + 1}
              </span>
              <div className="min-w-0">
                <p className="truncate text-xs font-medium">{action.kind}</p>
                <p className="truncate text-[11px] text-muted-foreground">
                  {Object.keys(action.outcome_triggers ?? {}).length > 0
                    ? `${Object.keys(action.outcome_triggers).length} outcome transition${Object.keys(action.outcome_triggers).length === 1 ? "" : "s"}`
                    : `failure: ${String(action.failure_policy?.on_failure ?? "block")}`}
                  {configHint(action) ? ` · ${configHint(action)}` : ""}
                </p>
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-0.5">
              {actions.length > 1 && (
                <>
                  <button
                    type="button"
                    onClick={() => move(i, -1)}
                    disabled={i === 0}
                    className="h-7 rounded px-1 text-muted-foreground hover:bg-muted disabled:opacity-30"
                    aria-label="Move up"
                  >
                    <ChevronUp className="h-3.5 w-3.5" />
                  </button>
                  <button
                    type="button"
                    onClick={() => move(i, 1)}
                    disabled={i === actions.length - 1}
                    className="h-7 rounded px-1 text-muted-foreground hover:bg-muted disabled:opacity-30"
                    aria-label="Move down"
                  >
                    <ChevronDown className="h-3.5 w-3.5" />
                  </button>
                </>
              )}
              <button
                type="button"
                onClick={() => setEditingIndex(i)}
                className="h-7 rounded px-2 text-xs hover:bg-muted"
              >
                Edit
              </button>
              <button
                type="button"
                onClick={() => saveAt(i, null)}
                className="h-7 rounded px-2 text-xs text-destructive hover:bg-muted"
              >
                Remove
              </button>
            </div>
          </div>
        ),
      )}

      {editingIndex === actions.length ? (
        <ActionEditor
          action={null}
          entityFields={entityFields}
          entityType={entityType}
          outgoingTransitions={outgoingTransitions}
          isLast
          onSave={(saved) => saveAt(actions.length, saved)}
        />
      ) : (
        editingIndex === null && (
          <button
            type="button"
            onClick={() => setEditingIndex(actions.length)}
            className="inline-flex h-7 items-center gap-1 rounded-md border border-border px-2 text-xs"
          >
            <Plus className="h-3 w-3" /> Add action
          </button>
        )
      )}

      {actions.length > 1 && (
        <p className="text-[11px] text-muted-foreground">
          Actions run in order, top to bottom, when the workflow enters this state.
        </p>
      )}
    </div>
  );
}
