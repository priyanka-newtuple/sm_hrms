import type {
  EntityField,
  MethodRef,
  StateMachineDefinition,
  StateMachineDocument,
  StateNode,
  Transition,
  ValidationIssue,
} from "@/lib/state-machine/types";
import type { StateMachineRecord } from "@/core/types";

export function normalizeWorkflowFieldType(type: string): string {
  return type === "date" ? "datetime" : type;
}

export function normalizeDraftForSubmit(doc: StateMachineDocument): StateMachineDocument {
  const machineName = doc.machine_name.trim();
  const entityType = doc.definition.entity_type.trim();
  const fieldTypeByName = new Map(
    doc.definition.entity_schema.fields.map((field) => [
      field.field,
      normalizeWorkflowFieldType(field.type),
    ] as const),
  );
  return {
    ...doc,
    machine_name: machineName,
    definition: {
      ...doc.definition,
      machine_key: machineName,
      entity_type: entityType,
      entity_schema: {
        ...doc.definition.entity_schema,
        entity_type: entityType,
        fields: doc.definition.entity_schema.fields.map((field) => ({
          ...field,
          type: normalizeWorkflowFieldType(field.type) as EntityField["type"],
        })),
      },
      transitions: doc.definition.transitions.map((transition) => ({
        ...transition,
        required_fields: transition.required_fields.map((requiredField) => ({
          ...requiredField,
          type: (fieldTypeByName.get(requiredField.field) ??
            (requiredField.type
              ? normalizeWorkflowFieldType(requiredField.type)
              : null)) as Transition["required_fields"][number]["type"],
        })),
      })),
    },
  };
}

export function normalizeStateMachineRecord(record: StateMachineRecord): StateMachineDocument {
  const raw = record.definition as Record<string, unknown>;
  const rawSchema = (raw.entity_schema ?? {}) as Record<string, unknown>;
  const fields = Array.isArray(rawSchema.fields) ? rawSchema.fields : [];
  const states = Array.isArray(raw.states) ? raw.states : [];
  const transitions = Array.isArray(raw.transitions) ? raw.transitions : [];

  const definition: StateMachineDefinition = {
    machine_key: String(raw.machine_key ?? record.machine_key ?? record.machine_name),
    name: String(raw.name ?? record.name ?? record.machine_name),
    description: String(raw.description ?? record.description ?? ""),
    entity_type: String(raw.entity_type ?? record.entity_type ?? rawSchema.entity_type ?? "entity"),
    entity_schema: {
      entity_type: String(rawSchema.entity_type ?? raw.entity_type ?? record.entity_type ?? "entity"),
      fields: fields.map((field): EntityField => {
        const item = field as Record<string, unknown>;
        return {
          field: String(item.field ?? ""),
          type: normalizeWorkflowFieldType(String(item.type ?? "string")) as EntityField["type"],
          required: Boolean(item.required ?? false),
          nullable: Boolean(item.nullable ?? true),
          default: item.default ?? null,
          enum_values: Array.isArray(item.enum_values) ? item.enum_values.map(String) : [],
          picklist_id: item.picklist_id == null ? null : String(item.picklist_id),
          description: String(item.description ?? ""),
        };
      }),
    },
    states: states.map((state, index): StateNode => {
      const item = state as Record<string, unknown>;
      // Accept both the list shape and the legacy singular key.
      const rawActions = Array.isArray(item.on_state_actions)
        ? item.on_state_actions
        : item.on_state_action && typeof item.on_state_action === "object"
          ? [item.on_state_action]
          : [];
      return {
        name: String(item.name ?? `state_${index + 1}`),
        description: String(item.description ?? ""),
        tags: Array.isArray(item.tags) ? item.tags.map(String) : [],
        order: Number(item.order ?? index + 1),
        on_state_actions: rawActions
          .filter((a): a is Record<string, unknown> => Boolean(a) && typeof a === "object")
          .map((rawAction) => ({
            kind: String(rawAction.kind ?? ""),
            config:
              rawAction.config && typeof rawAction.config === "object"
                ? (rawAction.config as Record<string, unknown>)
                : {},
            outcome_triggers:
              rawAction.outcome_triggers && typeof rawAction.outcome_triggers === "object"
                ? Object.fromEntries(
                    Object.entries(rawAction.outcome_triggers as Record<string, unknown>).map(
                      ([outcome, trigger]) => [outcome, String(trigger)],
                    ),
                  )
                : {},
            failure_policy:
              rawAction.failure_policy && typeof rawAction.failure_policy === "object"
                ? (rawAction.failure_policy as Record<string, unknown>)
                : {},
          })),
        sla_seconds:
          typeof item.sla_seconds === "number" || item.sla_seconds === null
            ? item.sla_seconds
            : null,
        method_refs: Array.isArray(item.method_refs)
          ? item.method_refs
              .filter((ref): ref is Record<string, unknown> => Boolean(ref) && typeof ref === "object")
              .map((ref): MethodRef => ({
                method_id: String(ref.method_id ?? ""),
                version_id: ref.version_id == null ? null : String(ref.version_id),
              }))
              .filter((ref) => ref.method_id.length > 0)
          : [],
      };
    }),
    initial_state: String(raw.initial_state ?? ""),
    transitions: transitions.map((transition): Transition => {
      const item = transition as Record<string, unknown>;
      return {
        key: String(item.key ?? ""),
        trigger: String(item.trigger ?? ""),
        label: String(item.label ?? item.trigger ?? ""),
        from: String(item.from ?? item.from_state ?? ""),
        to_state: String(item.to_state ?? ""),
        required_fields: Array.isArray(item.required_fields)
          ? (item.required_fields as Transition["required_fields"]).map((requiredField) => ({
              ...requiredField,
              type: (
                requiredField.type == null
                  ? null
                  : normalizeWorkflowFieldType(requiredField.type)
              ) as Transition["required_fields"][number]["type"],
            }))
          : [],
        guards: Array.isArray(item.guards) ? (item.guards as Transition["guards"]) : [],
        pre_transition_tasks: Array.isArray(item.pre_transition_tasks)
          ? (item.pre_transition_tasks as Transition["pre_transition_tasks"])
          : [],
        post_transition_tasks: Array.isArray(item.post_transition_tasks)
          ? (item.post_transition_tasks as Transition["post_transition_tasks"])
          : [],
        auto_transition:
          item.auto_transition && typeof item.auto_transition === "object"
            ? (item.auto_transition as Transition["auto_transition"])
            : null,
        description: String(item.description ?? ""),
      };
    }),
  };

  return {
    machine_name: record.machine_name,
    base_version: record.version,
    definition,
  };
}

export function parseRemoteValidation(payload: unknown, ok: boolean): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  if (payload == null) {
    if (!ok) issues.push({ level: "error", path: "server", message: "Empty error response." });
    return issues;
  }

  const normalizeLocationPath = (loc: unknown): string => {
    if (!Array.isArray(loc)) return "server";
    const segments = loc
      .filter((part) => part !== "body" && part !== "definition")
      .map((part) => String(part));
    if (segments.length === 0) return "server";
    let path = "";
    for (const segment of segments) {
      if (/^\d+$/.test(segment)) {
        path += `[${segment}]`;
      } else {
        path += path ? `.${segment}` : segment;
      }
    }
    return path;
  };

  const toIssue = (fallbackLevel: "error" | "warning", item: unknown): ValidationIssue => {
    if (typeof item === "string") return { level: fallbackLevel, path: "server", message: item };
    if (item && typeof item === "object") {
      const o = item as Record<string, unknown>;
      if (typeof o.msg === "string" && Array.isArray(o.loc)) {
        return { level: fallbackLevel, path: normalizeLocationPath(o.loc), message: o.msg };
      }
      const rawLevel = (o.level ?? o.severity) as string | undefined;
      const lvl: "error" | "warning" =
        rawLevel === "error" || rawLevel === "warning" ? rawLevel : fallbackLevel;
      const path = String(o.path ?? o.field ?? o.bucket ?? o.location ?? "server");
      const message = String(o.message ?? o.error ?? o.detail ?? JSON.stringify(o));
      return { level: lvl, path, message };
    }
    return { level: fallbackLevel, path: "server", message: String(item) };
  };

  const collectReportIssues = (report: unknown, fallbackLevel: "error" | "warning") => {
    if (!report || typeof report !== "object") return;
    const value = report as Record<string, unknown>;
    if (Array.isArray(value.issues)) {
      issues.push(...value.issues.map((it: unknown) => toIssue(fallbackLevel, it)));
    }
  };

  if (Array.isArray(payload)) return payload.map((it) => toIssue(ok ? "warning" : "error", it));
  const p = payload as Record<string, unknown>;

  if (
    (p.validation_report && typeof p.validation_report === "object") ||
    (p.dry_run_report && typeof p.dry_run_report === "object")
  ) {
    collectReportIssues(p.validation_report, "error");
    collectReportIssues(p.dry_run_report, "error");
    const validationInvalid =
      p.validation_report &&
      typeof p.validation_report === "object" &&
      (p.validation_report as Record<string, unknown>).valid === false;
    const dryRunInvalid =
      p.dry_run_report &&
      typeof p.dry_run_report === "object" &&
      (p.dry_run_report as Record<string, unknown>).valid === false;
    if (issues.length === 0 && (validationInvalid || dryRunInvalid || p.can_publish === false)) {
      issues.push({ level: "error", path: "server", message: "Server validation failed." });
    }
    return issues;
  }

  if (Array.isArray(p.issues)) issues.push(...p.issues.map((it: unknown) => toIssue("error", it)));
  if (Array.isArray(p.errors)) issues.push(...p.errors.map((it: unknown) => toIssue("error", it)));
  if (Array.isArray(p.warnings))
    issues.push(...p.warnings.map((it: unknown) => toIssue("warning", it)));
  if (issues.length === 0 && p.valid === false) {
    issues.push({
      level: "error",
      path: "server",
      message: typeof p.message === "string" ? p.message : "Server reported invalid machine.",
    });
  }
  if (issues.length === 0 && !ok) {
    issues.push({
      level: "error",
      path: "server",
      message: typeof p.message === "string" ? p.message : "Validation request failed.",
    });
  }
  return issues;
}
