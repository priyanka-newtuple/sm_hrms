import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import type { StateAction, EntityField } from "@/lib/state-machine/types";
import type { ActionDefinition, EmailTemplate, FormSchema, User } from "@/core/types";
import type { EntitySchedule } from "@/core/services/api";
import { actionDefinitions, connectors as connectorsApi, emailTemplates, entityTypes, formSchemas, schedules, users as usersApi } from "@/core/services/api";
import type { Connector } from "@/core/types";
import { useAgentActionConfig } from "./useAgentActionConfig";
import {
  ENTITY_ASSIGN_USER_KIND,
  userLabel,
  type AssignmentType,
} from "./userAssignment";

const EMAIL_COMPATIBLE_TYPES = new Set(["email", "string", "text"]);
export type FailureMode = "block" | "fire_trigger" | "retry";

export interface OutgoingTransition {
  key: string;
  trigger: string;
  label?: string;
  to_state: string;
}

export interface UseActionEditorProps {
  action: StateAction | null;
  entityFields: EntityField[];
  entityType: string;
  outgoingTransitions: OutgoingTransition[];
  onSave: (action: StateAction | null) => void;
  /** False when this action has others after it in the chain — hides outcome triggers. */
  isLast?: boolean;
}

export function useActionEditor({
  action,
  entityFields,
  entityType,
  outgoingTransitions,
  onSave,
  isLast = true,
}: UseActionEditorProps) {
  const normalizeTransitionRef = (value: unknown): string => {
    const raw = String(value ?? "").trim();
    if (!raw) return "";
    const match = outgoingTransitions.find(
      (t) => t.trigger === raw || t.key === raw,
    );
    return match?.trigger ?? raw;
  };

  const normalizeOutcomeTriggerMap = (
    rawMap: Record<string, string> | null | undefined,
  ): Record<string, string> =>
    Object.fromEntries(
      Object.entries(rawMap ?? {}).map(([outcome, ref]) => [
        outcome,
        normalizeTransitionRef(ref),
      ]),
    );

  const [definitions, setDefinitions] = useState<ActionDefinition[]>([]);
  const [templates, setTemplates] = useState<EmailTemplate[]>([]);
  const [schemas, setSchemas] = useState<FormSchema[]>([]);
  const [connectorList, setConnectorList] = useState<Connector[]>([]);
  const [loadingDefs, setLoadingDefs] = useState(false);
  const [loadingTemplates, setLoadingTemplates] = useState(false);
  const [loadingSchemas, setLoadingSchemas] = useState(false);
  const [loadingConnectors, setLoadingConnectors] = useState(false);
  const [scheduleList, setScheduleList] = useState<EntitySchedule[]>([]);
  const [loadingSchedules, setLoadingSchedules] = useState(false);

  const [kind, setKind] = useState(action?.kind ?? "");
  const [connectorId, setConnectorId] = useState(String(action?.config?.connector_id ?? ""));
  const [writebackTarget, setWritebackTarget] = useState(
    String(action?.config?.writeback_target ?? "entity"),
  );
  const [templateId, setTemplateId] = useState(String(action?.config?.template_id ?? ""));
  const [formId, setFormId] = useState(String(action?.config?.form_id ?? ""));
  const [toField, setToField] = useState(String(action?.config?.to ?? ""));
  const [scheduleIds, setScheduleIds] = useState<string[]>(
    Array.isArray(action?.config?.schedule_ids)
      ? action.config.schedule_ids.map(String)
      : [],
  );
  const [activationPolicy, setActivationPolicy] = useState(
    String(action?.config?.activation_policy ?? "current_period"),
  );
  const [isCustomTo, setIsCustomTo] = useState(() => {
    const stored = String(action?.config?.to ?? "");
    if (!stored) return false;
    return !stored.match(/^\$entity\.[a-zA-Z_][a-zA-Z0-9_]*$/);
  });
  const [assignmentType, setAssignmentType] = useState<AssignmentType>(
    action?.config?.assignment_type === "originator" ? "originator" : "user",
  );
  const [assignmentUserId, setAssignmentUserId] = useState(
    String(action?.config?.user_id ?? ""),
  );
  const [orgUsers, setOrgUsers] = useState<User[]>([]);
  const [loadingOrgUsers, setLoadingOrgUsers] = useState(false);
  const [outcomeTriggers, setOutcomeTriggers] = useState<Record<string, string>>(
    normalizeOutcomeTriggerMap(action?.outcome_triggers),
  );
  const [failureMode, setFailureMode] = useState<FailureMode>(
    (action?.failure_policy?.on_failure as FailureMode) ?? "block",
  );
  const [failureTrigger, setFailureTrigger] = useState(
    normalizeTransitionRef(action?.failure_policy?.trigger),
  );
  const [retryMaxAttempts, setRetryMaxAttempts] = useState(
    String(action?.failure_policy?.max_attempts ?? "3"),
  );
  const [retryDelaySecs, setRetryDelaySecs] = useState(
    String(action?.failure_policy?.delay_seconds ?? "60"),
  );
  const [chainOnFailure, setChainOnFailure] = useState(
    String(action?.failure_policy?.on_chain_failure ?? "continue"),
  );

  useEffect(() => {
    setLoadingDefs(true);
    actionDefinitions
      .list()
      .then((r) => setDefinitions(Array.isArray(r.items) ? r.items : []))
      .catch(() => toast.error("Failed to load action types."))
      .finally(() => setLoadingDefs(false));
  }, []);

  const isMailAction = kind.startsWith("mail.");
  const isWebhookAction = kind === "webhook.http";
  const isAgentAction = kind === "agent_run";
  const isScheduleRunOnceAction = kind === "entity.run_schedules_once";
  const isScheduleActivationAction =
    kind === "entity.activate_schedules" || isScheduleRunOnceAction;
  const isUserAssignmentAction = kind === ENTITY_ASSIGN_USER_KIND;
  const agentAction = useAgentActionConfig({
    action,
    isAgentAction,
    kind,
    normalizeTransitionRef,
    isLast,
  });

  useEffect(() => {
    if (!isMailAction) return;
    setLoadingTemplates(true);
    emailTemplates
      .list()
      .then((r) => setTemplates(Array.isArray(r.items) ? r.items : []))
      .catch(() => toast.error("Failed to load email templates."))
      .finally(() => setLoadingTemplates(false));
  }, [isMailAction]);

  useEffect(() => {
    if (!isWebhookAction) return;
    setLoadingConnectors(true);
    connectorsApi
      .list()
      .then((r) => setConnectorList(Array.isArray(r.items) ? r.items : []))
      .catch(() => toast.error("Failed to load connectors."))
      .finally(() => setLoadingConnectors(false));
  }, [isWebhookAction, entityType]);

  useEffect(() => {
    if (!isScheduleActivationAction) return;
    setLoadingSchedules(true);
    Promise.all([schedules.list(), entityTypes.get(entityType)])
      .then(([scheduleResponse, entityTypeRecord]) => {
        const entityTypeId = entityTypeRecord.entity_type_id ?? entityTypeRecord.id;
        setScheduleList(
          (Array.isArray(scheduleResponse.items) ? scheduleResponse.items : []).filter(
            (schedule) => schedule.anchor_entity_type_id === entityTypeId,
          ),
        );
      })
      .catch(() => toast.error("Failed to load recurring schedules."))
      .finally(() => setLoadingSchedules(false));
  }, [entityType, isScheduleActivationAction]);

  useEffect(() => {
    if (!isUserAssignmentAction) return;
    setLoadingOrgUsers(true);
    usersApi
      .list("active")
      .then(setOrgUsers)
      .catch(() => toast.error("Failed to load organization users."))
      .finally(() => setLoadingOrgUsers(false));
  }, [isUserAssignmentAction]);

  const needsFormSchema =
    kind === "form.receive_data" || kind === "mail.send_email";

  useEffect(() => {
    if (!needsFormSchema) return;
    setLoadingSchemas(true);
    formSchemas
      .list(entityType)
      .then((r) => setSchemas(r.items.filter((s) => s.is_active)))
      .catch(() => toast.error("Failed to load form schemas."))
      .finally(() => setLoadingSchemas(false));
  }, [entityType, needsFormSchema]);

  const supportedOutcomes = useMemo(() => {
    const def = definitions.find((d) => d.kind === kind);
    if (!def) return [];
    const outcomeSchema = (def.output_schema as Record<string, unknown>)?.outcome as
      | Record<string, unknown>
      | undefined;
    const enumValues = outcomeSchema?.enum;
    if (Array.isArray(enumValues)) return enumValues as string[];
    if (isMailAction) return ["sent", "failed"];
    return [];
  }, [definitions, kind, isMailAction]);

  const emailFields = entityFields.filter((f) => EMAIL_COMPATIBLE_TYPES.has(f.type));

  const handleKindChange = (newKind: string) => {
    setKind(newKind);
    setConnectorId("");
    setTemplateId("");
    setFormId("");
    setScheduleIds([]);
    setActivationPolicy("current_period");
    // A new User Assignment starts unconfigured rather than inheriting whatever
    // the previously selected kind left behind. The controls only render for
    // that kind, so one default covers every case.
    setAssignmentType("user");
    setAssignmentUserId("");
    agentAction.resetAgentConfig();
    setOutcomeTriggers({});
  };

  const handleToChange = (value: string) => {
    if (value === "__custom__") {
      setIsCustomTo(true);
      setToField("");
    } else {
      setIsCustomTo(false);
      setToField(value);
    }
  };

  const handleOutcomeTriggerChange = (outcome: string, val: string) => {
    setOutcomeTriggers((prev) => {
      const next = { ...prev };
      if (val) next[outcome] = val;
      else delete next[outcome];
      return next;
    });
  };

  const buildFailurePolicy = (): Record<string, unknown> | null => {
    const failure_policy: Record<string, unknown> = { on_failure: failureMode };
    if (failureMode === "fire_trigger") {
      if (!failureTrigger) {
        toast.error("Select a failure transition.");
        return null;
      }
      failure_policy.trigger = failureTrigger;
    }
    if (failureMode === "retry") {
      failure_policy.max_attempts = Number(retryMaxAttempts) || 3;
      failure_policy.delay_seconds = Number(retryDelaySecs) || 60;
    }
    if (!isLast && chainOnFailure === "stop") {
      failure_policy.on_chain_failure = "stop";
    }
    return failure_policy;
  };

  const saveAgentAction = (failurePolicy: Record<string, unknown>) => {
    // Mid-chain actions may not define outcome triggers.
    const triggers = isLast ? outcomeTriggers : {};
    const agentActionPayload = agentAction.buildAgentAction(failurePolicy, triggers);
    if (agentActionPayload === null) {
      return;
    }
    onSave(agentActionPayload);
    toast.success("Action saved.");
  };

  /** Snapshot the picked connector/template/schedule/form name for display. */
  const buildActionDisplayName = (): string | undefined => {
    if (isScheduleActivationAction) {
      const names = scheduleList
        .filter((s) => scheduleIds.includes(s.schedule_id))
        .map((s) => s.name);
      return names.length === scheduleIds.length ? names.join(", ") : undefined;
    }
    if (isWebhookAction) {
      return connectorList.find((c) => c.id === connectorId)?.name;
    }
    if (isMailAction) {
      return templates.find((t) => t.template_id === templateId)?.name;
    }
    if (kind === "form.receive_data") {
      return schemas.find((s) => s.id === formId)?.name;
    }
    return undefined;
  };

  /** Config for the User Assignment action, or null when it is incomplete. */
  const buildUserAssignmentConfig = (): Record<string, unknown> | null => {
    if (assignmentType === "originator") {
      return { assignment_type: "originator" };
    }
    if (!assignmentUserId) {
      toast.error("Select the user to assign.");
      return null;
    }
    const chosen = orgUsers.find((user) => user.id === assignmentUserId);
    return {
      assignment_type: "user",
      user_id: assignmentUserId,
      ...(chosen ? { action_display_name: userLabel(chosen) } : {}),
    };
  };

  const buildStandardConfig = (): Record<string, unknown> | null => {
    if (isUserAssignmentAction) return buildUserAssignmentConfig();
    if (isScheduleActivationAction) {
      if (scheduleIds.length === 0) {
        toast.error("Select at least one recurring schedule.");
        return null;
      }
      return { schedule_ids: scheduleIds, activation_policy: activationPolicy };
    }
    const config: Record<string, unknown> = { to: toField };
    if (isWebhookAction) {
      if (!connectorId) {
        toast.error("Select a connector.");
        return null;
      }
      config.connector_id = connectorId;
      config.writeback_target = writebackTarget;
    }
    if (isMailAction) {
      if (!toField.trim()) {
        toast.error("Select or enter a recipient.");
        return null;
      }
      if (!templateId) {
        toast.error("Select an email template.");
        return null;
      }
      config.template_id = templateId;
      if (formId) config.form_id = formId;
    }
    if (kind === "form.receive_data") {
      if (!formId) {
        toast.error("Select a form schema.");
        return null;
      }
      config.form_id = formId;
    }
    const displayName = buildActionDisplayName();
    if (displayName) config.action_display_name = displayName;
    return config;
  };

  const saveStandardAction = (failurePolicy: Record<string, unknown>) => {
    const config = buildStandardConfig();
    if (config === null) {
      return;
    }
    onSave({
      kind,
      config,
      outcome_triggers: isLast ? outcomeTriggers : {},
      failure_policy: failurePolicy,
    });
    toast.success("Action saved.");
  };

  const handleSave = () => {
    if (!kind) {
      toast.error("Select an action kind.");
      return;
    }

    const failurePolicy = buildFailurePolicy();
    if (failurePolicy === null) {
      return;
    }

    if (isAgentAction) {
      saveAgentAction(failurePolicy);
      return;
    }
    saveStandardAction(failurePolicy);
  };

  return {
    definitions,
    templates,
    schemas,
    connectorList,
    writebackTarget,
    setWritebackTarget,
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
    isScheduleRunOnceAction,
    isUserAssignmentAction,
    orgUsers,
    loadingOrgUsers,
    assignmentType,
    setAssignmentType,
    assignmentUserId,
    setAssignmentUserId,
    scheduleList,
    scheduleIds,
    setScheduleIds,
    activationPolicy,
    setActivationPolicy,
    needsFormSchema,
    ...agentAction,
    handleKindChange,
    handleToChange,
    handleOutcomeTriggerChange,
    handleSave,
  };
}
