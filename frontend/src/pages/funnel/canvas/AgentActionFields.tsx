import type { EntityField } from "@/lib/state-machine/types";
import type { AgentDefinitionListItem } from "@/core/types";
import { AgentContextOptions } from "./AgentContextOptions";
import { AgentPicker } from "./AgentPicker";
import { DecisionRouter } from "./DecisionRouter";
import { InputFieldsSelector } from "./InputFieldsSelector";
import { OutputMappingEditor } from "./OutputMappingEditor";
import type { OutgoingTransition } from "./useActionEditor";
import type { OutcomeRoute, OutputMappingRow } from "./useAgentActionConfig";

interface AgentActionFieldsProps {
  agents: AgentDefinitionListItem[];
  loadingAgents: boolean;
  agentId: string;
  onAgentIdChange: (value: string) => void;
  promptInstructions: string;
  onPromptInstructionsChange: (value: string) => void;
  entityFields: EntityField[];
  inputFields: string[];
  onInputFieldToggle: (fieldName: string) => void;
  includeFiles: boolean;
  onIncludeFilesChange: (value: boolean) => void;
  includeRelations: string;
  onIncludeRelationsChange: (value: string) => void;
  outputMappings: OutputMappingRow[];
  onOutputMappingChange: (index: number, patch: Partial<OutputMappingRow>) => void;
  onAddOutputMapping: () => void;
  onRemoveOutputMapping: (index: number) => void;
  outgoingTransitions: OutgoingTransition[];
  outcomeField: string;
  onOutcomeFieldChange: (value: string) => void;
  outcomeRoutes: OutcomeRoute[];
  onOutcomeRouteChange: (index: number, patch: Partial<OutcomeRoute>) => void;
  onAddOutcomeRoute: () => void;
  onRemoveOutcomeRoute: (index: number) => void;
  /** False when the action is mid-chain — decision routing is last-action-only. */
  showDecisionRouter?: boolean;
}

/** Config fields for the agent_run action: agent picker, inputs to feed, and output→field mapping. */
export function AgentActionFields({
  agents,
  loadingAgents,
  agentId,
  onAgentIdChange,
  promptInstructions,
  onPromptInstructionsChange,
  entityFields,
  inputFields,
  onInputFieldToggle,
  includeFiles,
  onIncludeFilesChange,
  includeRelations,
  onIncludeRelationsChange,
  outputMappings,
  onOutputMappingChange,
  onAddOutputMapping,
  onRemoveOutputMapping,
  outgoingTransitions,
  outcomeField,
  onOutcomeFieldChange,
  outcomeRoutes,
  onOutcomeRouteChange,
  onAddOutcomeRoute,
  onRemoveOutcomeRoute,
  showDecisionRouter = true,
}: AgentActionFieldsProps) {
  return (
    <>
      <AgentPicker
        agents={agents}
        loadingAgents={loadingAgents}
        agentId={agentId}
        onAgentIdChange={onAgentIdChange}
      />

      <div className="space-y-1.5">
        <label className="text-xs font-medium">
          Instructions <span className="text-muted-foreground">(optional)</span>
        </label>
        <textarea
          value={promptInstructions}
          onChange={(e) => onPromptInstructionsChange(e.target.value)}
          placeholder="e.g. Evaluate this candidate for the role and score them 1–10."
          rows={3}
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
        />
      </div>

      <InputFieldsSelector
        entityFields={entityFields}
        inputFields={inputFields}
        onInputFieldToggle={onInputFieldToggle}
      />
      <AgentContextOptions
        includeFiles={includeFiles}
        onIncludeFilesChange={onIncludeFilesChange}
        includeRelations={includeRelations}
        onIncludeRelationsChange={onIncludeRelationsChange}
      />
      <OutputMappingEditor
        entityFields={entityFields}
        outputMappings={outputMappings}
        onOutputMappingChange={onOutputMappingChange}
        onAddOutputMapping={onAddOutputMapping}
        onRemoveOutputMapping={onRemoveOutputMapping}
      />
      {showDecisionRouter && (
        <DecisionRouter
          outgoingTransitions={outgoingTransitions}
          outcomeField={outcomeField}
          onOutcomeFieldChange={onOutcomeFieldChange}
          outcomeRoutes={outcomeRoutes}
          onOutcomeRouteChange={onOutcomeRouteChange}
          onAddOutcomeRoute={onAddOutcomeRoute}
          onRemoveOutcomeRoute={onRemoveOutcomeRoute}
        />
      )}
    </>
  );
}
