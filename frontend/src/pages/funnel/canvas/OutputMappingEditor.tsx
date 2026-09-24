import { ArrowRight, Plus, Trash2 } from "lucide-react";

import type { EntityField } from "@/lib/state-machine/types";
import type { OutputMappingRow } from "./useAgentActionConfig";

interface OutputMappingEditorProps {
  entityFields: EntityField[];
  outputMappings: OutputMappingRow[];
  onOutputMappingChange: (index: number, patch: Partial<OutputMappingRow>) => void;
  onAddOutputMapping: () => void;
  onRemoveOutputMapping: (index: number) => void;
}

export function OutputMappingEditor({
  entityFields,
  outputMappings,
  onOutputMappingChange,
  onAddOutputMapping,
  onRemoveOutputMapping,
}: OutputMappingEditorProps) {
  return (
    <div className="space-y-2">
      <label className="text-xs font-medium">
        Output mapping <span className="text-destructive">*</span>
      </label>
      <p className="text-[11px] text-muted-foreground">
        Map each key the agent returns to the entity field it should be saved into.
      </p>
      {outputMappings.map((row, index) => (
        <div key={index} className="flex items-center gap-2">
          <input
            value={row.key}
            onChange={(e) => onOutputMappingChange(index, { key: e.target.value })}
            placeholder="agent key"
            className="h-8 min-w-0 flex-1 rounded-md border border-input bg-background px-2 font-mono text-xs"
          />
          <ArrowRight className="h-3 w-3 shrink-0 text-muted-foreground" />
          <select
            value={row.field}
            onChange={(e) => onOutputMappingChange(index, { field: e.target.value })}
            className="h-8 min-w-0 flex-1 truncate rounded-md border border-input bg-background px-2 text-xs"
          >
            <option value="">Select field…</option>
            {entityFields.map((field) => (
              <option key={field.field} value={field.field}>
                {field.field} ({field.type})
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => onRemoveOutputMapping(index)}
            disabled={outputMappings.length <= 1}
            className="shrink-0 rounded p-1 text-muted-foreground hover:bg-muted disabled:opacity-40"
            aria-label="Remove mapping"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      ))}
      <button
        type="button"
        onClick={onAddOutputMapping}
        className="inline-flex items-center gap-1 text-[11px] font-medium text-primary hover:underline"
      >
        <Plus className="h-3 w-3" /> Add mapping
      </button>
    </div>
  );
}
