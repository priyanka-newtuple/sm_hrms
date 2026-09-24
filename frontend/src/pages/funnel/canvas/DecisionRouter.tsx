import { ArrowRight, Plus, Trash2 } from "lucide-react";

import type { OutgoingTransition } from "./useActionEditor";
import type { OutcomeRoute } from "./useAgentActionConfig";

const INPUT_CLASS = "h-9 w-full rounded-md border border-input bg-background px-3 text-sm";

interface DecisionRouterProps {
  outgoingTransitions: OutgoingTransition[];
  outcomeField: string;
  onOutcomeFieldChange: (value: string) => void;
  outcomeRoutes: OutcomeRoute[];
  onOutcomeRouteChange: (index: number, patch: Partial<OutcomeRoute>) => void;
  onAddOutcomeRoute: () => void;
  onRemoveOutcomeRoute: (index: number) => void;
}

export function DecisionRouter({
  outgoingTransitions,
  outcomeField,
  onOutcomeFieldChange,
  outcomeRoutes,
  onOutcomeRouteChange,
  onAddOutcomeRoute,
  onRemoveOutcomeRoute,
}: DecisionRouterProps) {
  return (
    <>
      <div className="space-y-1.5">
        <label className="text-xs font-medium">
          Decision field <span className="text-muted-foreground">(optional)</span>
        </label>
        <p className="text-[11px] text-muted-foreground">
          Which output key holds the agent&apos;s decision. When set, its value routes the workflow;
          otherwise the step always takes the &ldquo;success&rdquo; path.
        </p>
        <input
          value={outcomeField}
          onChange={(e) => onOutcomeFieldChange(e.target.value)}
          placeholder="e.g. recommendation"
          className={`${INPUT_CLASS} font-mono`}
        />
      </div>

      {outcomeField.trim() !== "" && (
        <div className="space-y-2">
          <label className="text-xs font-medium">
            Decision routes <span className="text-destructive">*</span>
          </label>
          <p className="text-[11px] text-muted-foreground">
            Map each possible decision value to the transition it should fire.
          </p>
          {outcomeRoutes.map((row, index) => (
            <div key={index} className="flex items-center gap-2">
              <input
                value={row.outcome}
                onChange={(e) => onOutcomeRouteChange(index, { outcome: e.target.value })}
                placeholder="decision value"
                className="h-8 min-w-0 flex-1 rounded-md border border-input bg-background px-2 font-mono text-xs"
              />
              <ArrowRight className="h-3 w-3 shrink-0 text-muted-foreground" />
              <select
                value={row.trigger}
                onChange={(e) => onOutcomeRouteChange(index, { trigger: e.target.value })}
                className="h-8 min-w-0 flex-1 truncate rounded-md border border-input bg-background px-2 text-xs"
              >
                <option value="">Select transition…</option>
                {outgoingTransitions.map((transition) => (
                  <option key={transition.key} value={transition.trigger}>
                    {transition.label || transition.trigger} → {transition.to_state}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => onRemoveOutcomeRoute(index)}
                disabled={outcomeRoutes.length <= 1}
                className="shrink-0 rounded p-1 text-muted-foreground hover:bg-muted disabled:opacity-40"
                aria-label="Remove route"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
          <button
            type="button"
            onClick={onAddOutcomeRoute}
            className="inline-flex items-center gap-1 text-[11px] font-medium text-primary hover:underline"
          >
            <Plus className="h-3 w-3" /> Add route
          </button>
        </div>
      )}
    </>
  );
}
