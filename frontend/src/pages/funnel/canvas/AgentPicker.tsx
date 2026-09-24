import { Loader2 } from "lucide-react";

import type { AgentDefinitionListItem } from "@/core/types";

const SELECT_CLASS = "h-9 w-full rounded-md border border-input bg-background px-3 text-sm";

interface AgentPickerProps {
  agents: AgentDefinitionListItem[];
  loadingAgents: boolean;
  agentId: string;
  onAgentIdChange: (value: string) => void;
}

export function AgentPicker({
  agents,
  loadingAgents,
  agentId,
  onAgentIdChange,
}: AgentPickerProps) {
  return (
    <div className="space-y-1.5">
      <label className="text-xs font-medium">
        Agent <span className="text-destructive">*</span>
      </label>
      {loadingAgents ? (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 className="h-3 w-3 animate-spin" /> Loading agents…
        </div>
      ) : (
        <select
          value={agentId}
          onChange={(e) => onAgentIdChange(e.target.value)}
          className={SELECT_CLASS}
        >
          <option value="">Select agent…</option>
          {agents.map((agent) => (
            <option key={agent.definition_id} value={agent.definition_id}>
              {agent.display_name || agent.name}
            </option>
          ))}
        </select>
      )}
    </div>
  );
}
