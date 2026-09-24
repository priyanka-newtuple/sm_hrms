import type { StateMachineDefinition, StateMachineDocument, ValidationIssue } from "./types";

export function resolveIssuePath(
  path: string,
  def?: StateMachineDefinition,
): { humanPath: string; stateName?: string; transitionKey?: string } {
  if (!def) {
    return { humanPath: path };
  }
  // transitions[N]...
  const tMatch = path.match(/^transitions\[(\d+)\](.*)/);
  if (tMatch) {
    const idx = parseInt(tMatch[1], 10);
    const t = def.transitions?.[idx];
    const tLabel = t ? `"${t.from} → ${t.to_state}"` : `#${idx + 1}`;
    const suffix = tMatch[2].replace(/^\./, "");
    let sub = "";
    if (suffix) {
      const gm = suffix.match(/^guards\[(\d+)\]/);
      const rfm = suffix.match(/^required_fields\[(\d+)\]/);
      if (gm) sub = ` › Guard #${parseInt(gm[1], 10) + 1}`;
      else if (rfm) sub = ` › Required field #${parseInt(rfm[1], 10) + 1}`;
      else {
        const labels: Record<string, string> = {
          key: "Key", trigger: "Trigger", from: "From state",
          to_state: "To state", label: "Label", description: "Description",
        };
        sub = ` › ${labels[suffix] ?? suffix}`;
      }
    }
    return { humanPath: `Transition ${tLabel}${sub}`, transitionKey: t?.key };
  }
  // states[N]...
  const siMatch = path.match(/^states\[(\d+)\](.*)/);
  if (siMatch) {
    const idx = parseInt(siMatch[1], 10);
    const s = def.states?.[idx];
    const name = s?.name ?? `#${idx + 1}`;
    const suffix = siMatch[2].replace(/^\./, "");
    return {
      humanPath: suffix ? `State "${name}" › ${suffix}` : `State "${name}"`,
      stateName: s?.name,
    };
  }
  // states.NAME (reachability)
  const snMatch = path.match(/^states\.(.+)/);
  if (snMatch) {
    return { humanPath: `State "${snMatch[1]}"`, stateName: snMatch[1] };
  }
  const TOP: Record<string, string> = {
    machine_name: "Machine name",
    "definition.machine_key": "Machine key",
    "definition.name": "Display name",
    "definition.entity_type": "Entity type",
    initial_state: "Initial state",
    states: "States",
    transitions: "Transitions",
    definition: "Definition",
    server: "Server validation",
  };
  return { humanPath: TOP[path] ?? path };
}

export function enrichIssues(
  issues: ValidationIssue[],
  def?: StateMachineDefinition,
): ValidationIssue[] {
  return issues.map((issue) => {
    if (issue.humanPath) return issue;
    return { ...issue, ...resolveIssuePath(issue.path, def) };
  });
}

export function validateMachine(doc: StateMachineDocument): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  const def = doc?.definition;

  if (!doc.machine_name?.trim()) {
    issues.push({ level: "error", path: "machine_name", message: "Machine name is required.", source: "local" });
  }
  if (!def) {
    issues.push({ level: "error", path: "definition", message: "Definition is missing.", source: "local" });
    return issues;
  }
  if (!def.machine_key?.trim()) {
    issues.push({ level: "error", path: "definition.machine_key", message: "Machine key is required.", source: "local" });
  }
  if (!def.name?.trim()) {
    issues.push({ level: "error", path: "definition.name", message: "Display name is required.", source: "local" });
  }
  if (!def.entity_type?.trim()) {
    issues.push({ level: "error", path: "definition.entity_type", message: "Entity type is required.", source: "local" });
  }

  const stateNames = new Set<string>();
  def.states?.forEach((s, i) => {
    if (!s.name?.trim()) {
      issues.push({ level: "error", path: `states[${i}]`, message: "State name is required.", source: "local" });
    } else if (stateNames.has(s.name)) {
      issues.push({ level: "error", path: `states[${i}]`, message: `Duplicate state "${s.name}".`, source: "local" });
    } else {
      stateNames.add(s.name);
    }
  });

  if (def.states.length === 0) {
    issues.push({ level: "error", path: "states", message: "At least one state is required.", source: "local" });
  }

  if (!def.initial_state || !stateNames.has(def.initial_state)) {
    issues.push({
      level: "error",
      path: "initial_state",
      message: "Initial state must reference an existing state.",
      source: "local",
    });
  }

  const initialCount = def.states.filter((s) => s.tags?.includes("initial")).length;
  if (initialCount > 1) {
    issues.push({ level: "warning", path: "states", message: "Multiple states tagged as initial.", source: "local" });
  }

  const fieldNames = new Set(def.entity_schema?.fields?.map((f) => f.field) ?? []);

  const transitionKeys = new Set<string>();
  def.transitions?.forEach((t, i) => {
    if (!t.key?.trim()) {
      issues.push({ level: "error", path: `transitions[${i}].key`, message: "Transition key is required.", source: "local" });
    } else if (transitionKeys.has(t.key)) {
      issues.push({ level: "error", path: `transitions[${i}].key`, message: `Duplicate key "${t.key}".`, source: "local" });
    } else {
      transitionKeys.add(t.key);
    }
    if (!t.trigger?.trim()) {
      issues.push({ level: "error", path: `transitions[${i}].trigger`, message: "Trigger is required.", source: "local" });
    }
    if (!stateNames.has(t.from)) {
      issues.push({
        level: "error",
        path: `transitions[${i}].from`,
        message: `From state "${t.from}" does not exist.`,
        source: "local",
      });
    }
    if (!stateNames.has(t.to_state)) {
      issues.push({
        level: "error",
        path: `transitions[${i}].to_state`,
        message: `To state "${t.to_state}" does not exist.`,
        source: "local",
      });
    }
    t.required_fields?.forEach((rf, j) => {
      if (rf.field && !fieldNames.has(rf.field)) {
        issues.push({
          level: "warning",
          path: `transitions[${i}].required_fields[${j}]`,
          message: `Required field "${rf.field}" is not in entity schema.`,
          source: "local",
        });
        return;
      }
      const schemaField = def.entity_schema.fields.find((field) => field.field === rf.field);
      if (schemaField && rf.type && schemaField.type !== rf.type) {
        issues.push({
          level: "error",
          path: `transitions[${i}].required_fields[${j}]`,
          message: `Required field "${rf.field}" has type "${rf.type}" but schema now defines it as "${schemaField.type}".`,
          source: "local",
        });
      }
    });
    t.guards?.forEach((g, j) => {
      if (g.field && !fieldNames.has(g.field)) {
        issues.push({
          level: "warning",
          path: `transitions[${i}].guards[${j}]`,
          message: `Guard references unknown field "${g.field}".`,
          source: "local",
        });
      }
    });
  });

  def.states?.forEach((state, i) => {
    const actions = state.on_state_actions ?? [];
    if (actions.length === 0) return;

    const outgoingTriggers = new Set(
      def.transitions
        .filter((transition) => transition.from === state.name)
        .map((transition) => transition.trigger)
        .filter((trigger) => typeof trigger === "string" && trigger.trim().length > 0),
    );

    actions.forEach((action, j) => {
      const isLast = j === actions.length - 1;
      if (!isLast && Object.keys(action.outcome_triggers ?? {}).length > 0) {
        issues.push({
          level: "error",
          path: `states[${i}].on_state_actions[${j}].outcome_triggers`,
          message: `Only the last action in a chain may define outcome triggers ("${action.kind}" is not last).`,
          source: "local",
        });
      }

      Object.entries(action.outcome_triggers ?? {}).forEach(([outcome, trigger]) => {
        if (!trigger) return;
        if (!outgoingTriggers.has(trigger)) {
          issues.push({
            level: "error",
            path: `states[${i}].on_state_actions[${j}].outcome_triggers.${outcome}`,
            message: `Outcome "${outcome}" references missing transition trigger "${trigger}".`,
            source: "local",
          });
        }
      });

      const failureMode = String(action.failure_policy?.on_failure ?? "block");
      const failureTrigger = String(action.failure_policy?.trigger ?? "");
      if (failureMode === "fire_trigger" && !failureTrigger) {
        issues.push({
          level: "error",
          path: `states[${i}].on_state_actions[${j}].failure_policy.trigger`,
          message: "Failure policy is set to fire a trigger, but no transition was selected.",
          source: "local",
        });
      } else if (failureMode === "fire_trigger" && !outgoingTriggers.has(failureTrigger)) {
        issues.push({
          level: "error",
          path: `states[${i}].on_state_actions[${j}].failure_policy.trigger`,
          message: `Failure trigger "${failureTrigger}" does not match an outgoing transition trigger from this state.`,
          source: "local",
        });
      }
    });
  });

  // Reachability from initial state
  if (def.initial_state && stateNames.has(def.initial_state)) {
    const reachable = new Set<string>([def.initial_state]);
    let changed = true;
    while (changed) {
      changed = false;
      for (const t of def.transitions ?? []) {
        if (reachable.has(t.from) && !reachable.has(t.to_state)) {
          reachable.add(t.to_state);
          changed = true;
        }
      }
    }
    for (const s of def.states) {
      if (!reachable.has(s.name) && !s.tags?.includes("initial")) {
        issues.push({
          level: "warning",
          path: `states.${s.name}`,
          message: `State "${s.name}" is not reachable from initial state.`,
          source: "local",
        });
      }
    }
  }

  return issues;
}
