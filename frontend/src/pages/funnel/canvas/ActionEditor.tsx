import { ArrowRight, Check, Loader2, X } from "lucide-react";

import type { StateAction, EntityField } from "@/lib/state-machine/types";
import { AgentActionFields } from "./AgentActionFields";
import { ScheduleActivationActionFields } from "./ScheduleActivationActionFields";
import { UserAssignmentActionFields } from "./UserAssignmentActionFields";
import { useActionEditor } from "./useActionEditor";

interface ActionEditorProps {
  action: StateAction | null;
  entityFields: EntityField[];
  entityType: string;
  outgoingTransitions: { key: string; trigger: string; label?: string; to_state: string }[];
  onSave: (action: StateAction | null) => void;
  /** False when other actions follow this one in the chain — hides outcome triggers. */
  isLast?: boolean;
}

/** Form for configuring a single state action — kind, recipient, template, form schema, outcome triggers, and failure policy. Calls onSave with the completed action or null to remove it. */
export function ActionEditor(props: ActionEditorProps) {
  const {
    definitions,
    templates,
    schemas,
    connectorList,
    emailFields,
    supportedOutcomes,
    loadingDefs,
    loadingTemplates,
    loadingSchemas,
    loadingConnectors,
    loadingSchedules,
    kind,
    connectorId,
    setConnectorId,
    writebackTarget,
    setWritebackTarget,
    templateId,
    setTemplateId,
    formId,
    setFormId,
    toField,
    setToField,
    isCustomTo,
    outcomeTriggers,
    failureMode,
    setFailureMode,
    failureTrigger,
    setFailureTrigger,
    retryMaxAttempts,
    setRetryMaxAttempts,
    retryDelaySecs,
    setRetryDelaySecs,
    chainOnFailure,
    setChainOnFailure,
    isMailAction,
    isWebhookAction,
    isAgentAction,
    isScheduleActivationAction,
    isUserAssignmentAction,
    orgUsers,
    loadingOrgUsers,
    assignmentType,
    setAssignmentType,
    assignmentUserId,
    setAssignmentUserId,
    isScheduleRunOnceAction,
    scheduleList,
    scheduleIds,
    setScheduleIds,
    activationPolicy,
    setActivationPolicy,
    needsFormSchema,
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
    handleKindChange,
    handleToChange,
    handleOutcomeTriggerChange,
    handleSave,
  } = useActionEditor(props);

  return (
    <div className="space-y-4 rounded-xl border border-border bg-muted/30 p-4">
      {/* Action kind */}
      <div className="space-y-1.5">
        <label className="text-xs font-medium">Action type</label>
        {loadingDefs ? (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="h-3 w-3 animate-spin" /> Loading…
          </div>
        ) : (
          <select
            value={kind}
            onChange={(e) => handleKindChange(e.target.value)}
            className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
          >
            <option value="">Select action…</option>
            {definitions.map((def) => (
              <option key={def.kind} value={def.kind}>
                {def.name}
              </option>
            ))}
          </select>
        )}
      </div>

      {/* Connector selector (webhook.http only) */}
      {isWebhookAction && (
        <div className="space-y-1.5">
          <label className="text-xs font-medium">Connector <span className="text-destructive">*</span></label>
          {loadingConnectors ? (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Loader2 className="h-3 w-3 animate-spin" /> Loading connectors…
            </div>
          ) : (
            <select
              value={connectorId}
              onChange={(e) => setConnectorId(e.target.value)}
              className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
            >
              <option value="">Select connector…</option>
              {connectorList.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          )}
        </div>
      )}

      {/* Write-back target (webhook.http only) */}
      {isWebhookAction && (
        <div className="space-y-1.5">
          <label className="text-xs font-medium">Write response to</label>
          <select
            value={writebackTarget}
            onChange={(e) => setWritebackTarget(e.target.value)}
            className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
          >
            <option value="entity">Entity fields — use the connector&apos;s response mapping</option>
          </select>
        </div>
      )}

      {/* Recipient (mail.* only) */}
      {isMailAction && (
        <div className="space-y-1.5">
          <label className="text-xs font-medium">To (recipient email)</label>
          <select
            value={isCustomTo ? "__custom__" : toField}
            onChange={(e) => handleToChange(e.target.value)}
            className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
          >
            <option value="">Select a field…</option>
            {emailFields.map((f) => (
              <option key={f.field} value={`$entity.${f.field}`}>
                {f.field} ({f.type})
              </option>
            ))}
            <option value="__custom__">Custom value…</option>
          </select>
          {isCustomTo && (
            <input
              value={toField}
              onChange={(e) => setToField(e.target.value)}
              placeholder="$entity.email or static@example.com"
              className="h-9 w-full rounded-md border border-input bg-background px-3 font-mono text-sm"
            />
          )}
        </div>
      )}

      {/* Email template (mail.* only) */}
      {isMailAction && (
        <div className="space-y-1.5">
          <label className="text-xs font-medium">Email template</label>
          {loadingTemplates ? (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Loader2 className="h-3 w-3 animate-spin" /> Loading templates…
            </div>
          ) : (
            <select
              value={templateId}
              onChange={(e) => setTemplateId(e.target.value)}
              className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
            >
              <option value="">Select template…</option>
              {templates.map((t) => (
                <option key={t.template_id} value={t.template_id}>
                  {t.name}
                </option>
              ))}
            </select>
          )}
        </div>
      )}

      {/* Form schema */}
      {needsFormSchema && (
        <div className="space-y-1.5">
          <label className="text-xs font-medium">
            Form schema
            {kind === "form.receive_data" && (
              <span className="ml-1 text-destructive">*</span>
            )}
            {kind !== "form.receive_data" && (
              <span className="ml-1 text-muted-foreground">(optional)</span>
            )}
          </label>
          {loadingSchemas ? (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Loader2 className="h-3 w-3 animate-spin" /> Loading forms…
            </div>
          ) : (
            <select
              value={formId}
              onChange={(e) => setFormId(e.target.value)}
              className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
            >
              <option value="">Select form…</option>
              {schemas.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          )}
        </div>
      )}

      {/* Agent config (agent_run only) */}
      {isAgentAction && (
        <AgentActionFields
          showDecisionRouter={props.isLast ?? true}
          agents={agents}
          loadingAgents={loadingAgents}
          agentId={agentId}
          onAgentIdChange={setAgentId}
          promptInstructions={promptInstructions}
          onPromptInstructionsChange={setPromptInstructions}
          entityFields={props.entityFields}
          inputFields={inputFields}
          onInputFieldToggle={handleInputFieldToggle}
          includeFiles={includeFiles}
          onIncludeFilesChange={setIncludeFiles}
          includeRelations={includeRelations}
          onIncludeRelationsChange={setIncludeRelations}
          outputMappings={outputMappings}
          onOutputMappingChange={handleOutputMappingChange}
          onAddOutputMapping={addOutputMapping}
          onRemoveOutputMapping={removeOutputMapping}
          outgoingTransitions={props.outgoingTransitions}
          outcomeField={outcomeField}
          onOutcomeFieldChange={setOutcomeField}
          outcomeRoutes={outcomeRoutes}
          onOutcomeRouteChange={handleOutcomeRouteChange}
          onAddOutcomeRoute={addOutcomeRoute}
          onRemoveOutcomeRoute={removeOutcomeRoute}
        />
      )}

      {isUserAssignmentAction && (
        <UserAssignmentActionFields
          users={orgUsers}
          loading={loadingOrgUsers}
          assignmentType={assignmentType}
          onAssignmentTypeChange={setAssignmentType}
          userId={assignmentUserId}
          onUserIdChange={setAssignmentUserId}
        />
      )}

      {isScheduleActivationAction && (
        <ScheduleActivationActionFields
          schedules={scheduleList}
          loading={loadingSchedules}
          selectedIds={scheduleIds}
          onSelectedIdsChange={setScheduleIds}
          policy={activationPolicy}
          onPolicyChange={setActivationPolicy}
          runOnce={isScheduleRunOnceAction}
        />
      )}

      {/* Outcome triggers — last action only; hidden for agent_run when the agent's decision drives routing */}
      {(props.isLast ?? true) &&
        supportedOutcomes.length > 0 &&
        !(isAgentAction && outcomeField.trim() !== "") && (
        <div className="space-y-2">
          <label className="text-xs font-medium">Outcome transitions</label>
          <p className="text-[11px] text-muted-foreground">
            Map each outcome to a transition trigger event. The engine fires that transition automatically.
          </p>
          {supportedOutcomes.map((outcome) => (
            <div key={outcome} className="flex items-center gap-2">
              <span
                title={outcome}
                className="min-w-16 max-w-40 shrink-0 truncate rounded bg-muted px-2 py-0.5 text-center text-[11px] font-mono font-medium"
              >
                {outcome}
              </span>
              <ArrowRight className="h-3 w-3 shrink-0 text-muted-foreground" />
              <select
                value={outcomeTriggers[outcome] ?? ""}
                onChange={(e) => handleOutcomeTriggerChange(outcome, e.target.value)}
                className="h-7 min-w-0 flex-1 truncate rounded-md border border-input bg-background px-2 text-xs"
              >
                <option value="">— no transition —</option>
                {props.outgoingTransitions.map((t) => (
                  <option key={t.key} value={t.trigger}>
                    {t.label || t.trigger} ({t.trigger}) → {t.to_state}
                  </option>
                ))}
              </select>
            </div>
          ))}
        </div>
      )}

      {/* Failure policy */}
      {kind && (
        <div className="space-y-2">
          <label className="text-xs font-medium">On failure</label>
          <select
            value={failureMode}
            onChange={(e) => setFailureMode(e.target.value as "block" | "fire_trigger" | "retry")}
            className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
          >
            <option value="block">Block — leave entity stuck (manual intervention)</option>
            <option value="fire_trigger">Fire transition — advance workflow on failure</option>
            {kind !== "form.receive_data" && (
              <option value="retry">Retry — automatically retry the action</option>
            )}
          </select>

          {failureMode === "fire_trigger" && (
            <select
              value={failureTrigger}
              onChange={(e) => setFailureTrigger(e.target.value)}
              className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
            >
              <option value="">— select transition trigger —</option>
              {props.outgoingTransitions.map((t) => (
                <option key={t.key} value={t.trigger}>
                  {t.label || t.trigger} ({t.trigger}) → {t.to_state}
                </option>
              ))}
            </select>
          )}

          {failureMode === "retry" && (
            <div className="grid grid-cols-2 gap-2">
              <label className="block space-y-1">
                <span className="text-[11px] text-muted-foreground">Max attempts</span>
                <input
                  type="number"
                  min={1}
                  max={10}
                  value={retryMaxAttempts}
                  onChange={(e) => setRetryMaxAttempts(e.target.value)}
                  className="h-8 w-full rounded-md border border-input bg-background px-3 text-sm"
                />
              </label>
              <label className="block space-y-1">
                <span className="text-[11px] text-muted-foreground">Delay (seconds)</span>
                <input
                  type="number"
                  min={0}
                  value={retryDelaySecs}
                  onChange={(e) => setRetryDelaySecs(e.target.value)}
                  className="h-8 w-full rounded-md border border-input bg-background px-3 text-sm"
                />
              </label>
            </div>
          )}

          {!(props.isLast ?? true) &&
            (failureMode === "fire_trigger" ? (
              <p className="rounded-md border border-dashed border-border px-2 py-1.5 text-[11px] text-muted-foreground">
                Firing a transition moves this entity to another state, so the
                remaining actions in this chain will not run.
              </p>
            ) : (
              <label className="block space-y-1">
                <span className="text-[11px] text-muted-foreground">
                  If this action fails, remaining actions
                </span>
                <select
                  value={chainOnFailure}
                  onChange={(e) => setChainOnFailure(e.target.value)}
                  className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
                >
                  <option value="continue">Continue — run the rest of the chain</option>
                  <option value="stop">Stop — skip the remaining actions</option>
                </select>
              </label>
            ))}
        </div>
      )}

      {/* Save/Remove */}
      <div className="flex items-center gap-2 border-t border-border pt-3">
        <button
          onClick={handleSave}
          disabled={!kind}
          className="inline-flex h-8 items-center gap-1.5 rounded-md bg-primary px-3 text-xs font-medium text-primary-foreground disabled:opacity-50"
        >
          <Check className="h-3.5 w-3.5" /> Save action
        </button>
        <button
          onClick={() => props.onSave(null)}
          className="inline-flex h-8 items-center gap-1.5 rounded-md px-3 text-xs font-medium text-destructive hover:bg-muted"
        >
          <X className="h-3.5 w-3.5" /> Remove
        </button>
      </div>
    </div>
  );
}
