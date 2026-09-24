import { useEffect, useState } from "react";
import { toast } from "sonner";

import { agent } from "@/core/services/api";
import type { AgentDefinitionListItem } from "@/core/types";
import type { StateAction } from "@/lib/state-machine/types";

export interface OutputMappingRow {
  key: string;
  field: string;
}

export interface OutcomeRoute {
  outcome: string;
  trigger: string;
}

const toStringArray = (value: unknown): string[] =>
  Array.isArray(value) ? value.map((item) => String(item)) : [];

interface UseAgentActionConfigProps {
  action: StateAction | null;
  isAgentAction: boolean;
  kind: string;
  normalizeTransitionRef: (value: unknown) => string;
  /** False when this action is mid-chain — decision routing is last-action-only. */
  isLast?: boolean;
}

export function useAgentActionConfig({
  action,
  isAgentAction,
  kind,
  normalizeTransitionRef,
  isLast = true,
}: UseAgentActionConfigProps) {
  const [agents, setAgents] = useState<AgentDefinitionListItem[]>([]);
  const [loadingAgents, setLoadingAgents] = useState(false);
  const [agentId, setAgentId] = useState(String(action?.config?.agent_id ?? ""));
  const [promptInstructions, setPromptInstructions] = useState(
    String(action?.config?.prompt_instructions ?? ""),
  );
  const [includeFiles, setIncludeFiles] = useState(
    Boolean(action?.config?.include_files ?? false),
  );
  const [inputFields, setInputFields] = useState<string[]>(
    toStringArray(action?.config?.input_fields),
  );
  const [includeRelations, setIncludeRelations] = useState(
    toStringArray(action?.config?.include_relations).join(", "),
  );
  const [outputMappings, setOutputMappings] = useState<OutputMappingRow[]>(() => {
    const mapping = action?.config?.output_mapping;
    if (mapping && typeof mapping === "object" && !Array.isArray(mapping)) {
      const rows = Object.entries(mapping as Record<string, unknown>).map(
        ([key, field]) => ({ key, field: String(field) }),
      );
      if (rows.length) return rows;
    }
    return [{ key: "", field: "" }];
  });
  const [outcomeField, setOutcomeField] = useState(String(action?.config?.outcome_field ?? ""));
  const [outcomeRoutes, setOutcomeRoutes] = useState<OutcomeRoute[]>(() => {
    const hasOutcomeField = Boolean(String(action?.config?.outcome_field ?? "").trim());
    if (hasOutcomeField) {
      const rows = Object.entries(action?.outcome_triggers ?? {}).map(([outcome, trigger]) => ({
        outcome,
        trigger: normalizeTransitionRef(trigger),
      }));
      if (rows.length) return rows;
    }
    return [{ outcome: "", trigger: "" }];
  });

  useEffect(() => {
    if (!isAgentAction) return;
    setLoadingAgents(true);
    agent
      .listDefinitions(true)
      .then((r) => setAgents(Array.isArray(r) ? r.filter((a) => a.is_active) : []))
      .catch(() => toast.error("Failed to load agents."))
      .finally(() => setLoadingAgents(false));
  }, [isAgentAction]);

  useEffect(() => {
    if (kind !== "agent_run") {
      resetAgentConfig();
    }
  }, [kind]);

  const resetAgentConfig = () => {
    setAgentId("");
    setPromptInstructions("");
    setIncludeFiles(false);
    setInputFields([]);
    setIncludeRelations("");
    setOutputMappings([{ key: "", field: "" }]);
    setOutcomeField("");
    setOutcomeRoutes([{ outcome: "", trigger: "" }]);
  };

  const handleInputFieldToggle = (fieldName: string) => {
    setInputFields((prev) =>
      prev.includes(fieldName)
        ? prev.filter((name) => name !== fieldName)
        : [...prev, fieldName],
    );
  };

  const handleOutputMappingChange = (index: number, patch: Partial<OutputMappingRow>) => {
    setOutputMappings((prev) =>
      prev.map((row, i) => (i === index ? { ...row, ...patch } : row)),
    );
  };

  const addOutputMapping = () =>
    setOutputMappings((prev) => [...prev, { key: "", field: "" }]);

  const removeOutputMapping = (index: number) =>
    setOutputMappings((prev) =>
      prev.length <= 1 ? prev : prev.filter((_, i) => i !== index),
    );

  const handleOutcomeRouteChange = (index: number, patch: Partial<OutcomeRoute>) =>
    setOutcomeRoutes((prev) =>
      prev.map((row, i) => (i === index ? { ...row, ...patch } : row)),
    );

  const addOutcomeRoute = () =>
    setOutcomeRoutes((prev) => [...prev, { outcome: "", trigger: "" }]);

  const removeOutcomeRoute = (index: number) =>
    setOutcomeRoutes((prev) =>
      prev.length <= 1 ? prev : prev.filter((_, i) => i !== index),
    );

  const buildAgentAction = (
    failure_policy: Record<string, unknown>,
    defaultOutcomeTriggers: Record<string, string>,
  ): StateAction | null => {
    if (!agentId) {
      toast.error("Select an agent.");
      return null;
    }
    const mappingEntries = outputMappings
      .map((row) => [row.key.trim(), row.field.trim()] as const)
      .filter(([key, field]) => key && field);
    if (mappingEntries.length === 0) {
      toast.error("Add at least one output mapping.");
      return null;
    }

    const agentConfig: Record<string, unknown> = {
      agent_id: agentId,
      output_mapping: Object.fromEntries(mappingEntries),
      include_files: includeFiles,
    };
    const agentName = agents.find((a) => a.definition_id === agentId)?.display_name;
    if (agentName) agentConfig.action_display_name = agentName;
    if (inputFields.length > 0) agentConfig.input_fields = inputFields;
    const relations = includeRelations
      .split(",")
      .map((relation) => relation.trim())
      .filter(Boolean);
    if (relations.length > 0) agentConfig.include_relations = relations;
    if (promptInstructions.trim()) {
      agentConfig.prompt_instructions = promptInstructions.trim();
    }

    let outcomeTriggers = defaultOutcomeTriggers;
    // Decision routing is last-action-only.
    if (isLast && outcomeField.trim()) {
      const routeEntries = outcomeRoutes
        .map((row) => [row.outcome.trim(), row.trigger.trim()] as const)
        .filter(([outcome, trigger]) => outcome && trigger);
      if (routeEntries.length === 0) {
        toast.error("Add at least one decision → transition route.");
        return null;
      }
      agentConfig.outcome_field = outcomeField.trim();
      outcomeTriggers = Object.fromEntries(routeEntries);
    }

    return {
      kind,
      config: agentConfig,
      outcome_triggers: outcomeTriggers,
      failure_policy,
    };
  };

  return {
    agents,
    loadingAgents,
    agentId,
    setAgentId,
    promptInstructions,
    setPromptInstructions,
    includeFiles,
    setIncludeFiles,
    inputFields,
    handleInputFieldToggle,
    includeRelations,
    setIncludeRelations,
    outputMappings,
    handleOutputMappingChange,
    addOutputMapping,
    removeOutputMapping,
    outcomeField,
    setOutcomeField,
    outcomeRoutes,
    handleOutcomeRouteChange,
    addOutcomeRoute,
    removeOutcomeRoute,
    resetAgentConfig,
    buildAgentAction,
  };
}
