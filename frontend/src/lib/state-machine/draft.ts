import { SAMPLE_MACHINE } from "./sample";
import type { StateMachineDocument } from "./types";

export function createDraftMachineKey(): string {
  const suffix = `${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
  return `workflow_${suffix}`;
}

export function createInitialDoc(): StateMachineDocument {
  const machineKey = createDraftMachineKey();
  return {
    machine_name: machineKey,
    base_version: 1,
    definition: {
      machine_key: machineKey,
      name: "New Workflow",
      description: "",
      entity_type: "entity",
      entity_schema: { entity_type: "entity", fields: [] },
      states: [{ name: "draft", description: "Initial state.", tags: ["initial"], order: 1, sla_seconds: null }],
      initial_state: "draft",
      transitions: [],
    },
  };
}

export function cloneMachineDocument(doc: StateMachineDocument): StateMachineDocument {
  return JSON.parse(JSON.stringify(doc)) as StateMachineDocument;
}

export function createSampleDoc(): StateMachineDocument {
  return cloneMachineDocument(SAMPLE_MACHINE);
}
