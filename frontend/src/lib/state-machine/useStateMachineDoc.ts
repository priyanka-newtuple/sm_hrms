import { useCallback, useEffect, useMemo, useState } from "react";
import api from "@/core/services/api";
import { useAuth } from "@/core/auth";
import { STATE_MACHINES_CHANGED_EVENT } from "@/core/events";
import type { StateMachineCanvasMetadata, StateMachineRecord } from "@/core/types";
import { emptyMachine } from "./sample";
// TEMPORARY DIAGNOSTICS — see ./diag.ts; strip with the bug.
import { diagLog, diagLogCommit } from "./diag";
import type {
  StateMachineDefinition,
  StateMachineDocument,
  ValidationIssue,
} from "./types";
import { validateMachine } from "./validate";

interface UseStateMachineDocOptions {
  stateMachineId?: string;
}

export interface DraftSaveResult {
  record: StateMachineRecord;
  validation_issues: { code: string; message: string; severity: string; bucket?: string | null; action?: string | null }[];
  is_valid: boolean;
  deactivated: boolean;
}

type CanvasNodes = Record<string, { x: number; y: number }>;

interface UseStateMachineDocResult {
  doc: StateMachineDocument;
  setDoc: (next: StateMachineDocument) => void;
  patchDefinition: (patch: Partial<StateMachineDefinition>) => void;
  canvasNodes: CanvasNodes;
  setCanvasNodes: (next: CanvasNodes) => void;
  isCreating: boolean;
  isLoading: boolean;
  loadError: string | null;
  isDirty: boolean;
  hasDraft: boolean;
  isSaving: boolean;
  isSavingDraft: boolean;
  saveError: string | null;
  draftError: string | null;
  remoteIssues: ValidationIssue[] | null;
  localIssues: ValidationIssue[];
  save: () => Promise<StateMachineRecord | null>;
  saveDraft: () => Promise<DraftSaveResult | null>;
  reload: () => Promise<void>;
}

function recordToDoc(record: StateMachineRecord): StateMachineDocument {
  const rawDef = record.definition as unknown as StateMachineDefinition;
  const machineKey =
    typeof rawDef.machine_key === "string" && rawDef.machine_key.trim().length > 0
      ? rawDef.machine_key
      : record.machine_name;
  return {
    machine_name: record.machine_name,
    base_version: record.version,
    definition: { ...rawDef, machine_key: machineKey },
  };
}

function normalizeDefinitionShape(
  raw: Record<string, unknown> | null | undefined,
  fallback: StateMachineDefinition,
): StateMachineDefinition {
  const def = (raw ?? {}) as Partial<StateMachineDefinition> & Record<string, unknown>;
  const entitySchemaRaw = def.entity_schema as Partial<StateMachineDefinition["entity_schema"]> | undefined;
  return {
    machine_key: typeof def.machine_key === "string" ? def.machine_key : fallback.machine_key,
    name: typeof def.name === "string" ? def.name : fallback.name,
    description: typeof def.description === "string" ? def.description : fallback.description,
    entity_type: typeof def.entity_type === "string" ? def.entity_type : fallback.entity_type,
    entity_schema: {
      entity_type:
        typeof entitySchemaRaw?.entity_type === "string"
          ? entitySchemaRaw.entity_type
          : fallback.entity_schema.entity_type,
      fields: Array.isArray(entitySchemaRaw?.fields)
        ? entitySchemaRaw!.fields
        : fallback.entity_schema.fields,
    },
    states: Array.isArray(def.states) ? def.states : fallback.states,
    initial_state:
      typeof def.initial_state === "string" ? def.initial_state : fallback.initial_state,
    transitions: Array.isArray(def.transitions) ? def.transitions : fallback.transitions,
  };
}

export function useStateMachineDoc({
  stateMachineId,
}: UseStateMachineDocOptions): UseStateMachineDocResult {
  const { refreshPermissions } = useAuth();
  const [doc, setDocStateRaw] = useState<StateMachineDocument>(() => emptyMachine());

  // TEMPORARY DIAGNOSTICS — this is the ONE place the document actually
  // commits. Every call site (load, setDoc, patchDefinition, saveDraft,
  // publish) funnels through here, so nothing can write invisibly. Handles
  // both the value and updater forms.
  const setDocState = (
    next: StateMachineDocument | ((prev: StateMachineDocument) => StateMachineDocument),
    label = 'useStateMachineDoc:unlabelled',
  ) => {
    if (typeof next === 'function') {
      setDocStateRaw((prev) => {
        const computed = (next as (p: StateMachineDocument) => StateMachineDocument)(prev);
        diagLogCommit(`setDocState/${label}`, prev, computed, 'updater-form');
        return computed;
      });
      return;
    }
    diagLogCommit(`setDocState/${label}`, doc, next, 'value-form');
    setDocStateRaw(next);
  };
  const [canvasMetadata, setCanvasMetadata] = useState<StateMachineCanvasMetadata | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(Boolean(stateMachineId));
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isDirty, setIsDirty] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isSavingDraft, setIsSavingDraft] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [draftError, setDraftError] = useState<string | null>(null);
  const [remoteIssues, setRemoteIssues] = useState<ValidationIssue[] | null>(null);
  // The row_id of the draft (version=0) row to use for saveDraft / publish.
  // May differ from stateMachineId when the user opens a published row for editing.
  const [draftRowId, setDraftRowId] = useState<string | null>(null);

  const isCreating = !stateMachineId;
  const canvasNodes = canvasMetadata?.nodes ?? {};

  const load = useCallback(async () => {
    if (!stateMachineId) return;
    setIsLoading(true);
    setLoadError(null);
    setDraftRowId(null);
    try {
      const record = await api.stateMachines.getById(stateMachineId);

      // Always display the content from the row we were asked to load (draft or published).
      setDocState(recordToDoc(record), 'load(hydrate-from-server)');
      setCanvasMetadata(record.canvas_metadata ?? null);
      setIsDirty(false);
      setRemoteIssues(null);

      if (record.version >= 1) {
        // Published row — resolve the version-0 sibling if it exists.
        // If not, draftRowId stays null and saveDraft will seed it on first save.
        const draft = await api.stateMachines.getDraft(record.machine_name).catch(() => null);
        setDraftRowId(draft?.id ?? null);
      } else {
        // Already on the draft row — use its own id.
        setDraftRowId(stateMachineId);
      }
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "Failed to load state machine");
    } finally {
      setIsLoading(false);
    }
  }, [stateMachineId]);

  useEffect(() => {
    void load();
  }, [load]);

  const setDoc = useCallback((next: StateMachineDocument) => {
    setDocState(next, 'setDoc(from editor onChange)');
    setIsDirty(true);
  }, []);

  const updateCanvasNodes = useCallback((next: CanvasNodes) => {
    setCanvasMetadata((prev) => ({
      ...(prev ?? {}),
      nodes: next,
    }));
    setIsDirty(true);
  }, []);

  const patchDefinition = useCallback((patch: Partial<StateMachineDefinition>) => {
    setDocState((prev) => ({
      ...prev,
      definition: { ...prev.definition, ...patch },
    }), 'patchDefinition');
    setIsDirty(true);
  }, []);

  const localIssues = useMemo(() => validateMachine(doc), [doc]);

  const saveDraft = useCallback(async (): Promise<DraftSaveResult | null> => {
    let resolvedDraftRowId = draftRowId;
    if (!resolvedDraftRowId) {
      try {
        const seeded = await api.stateMachines.seedDraft(doc.machine_name);
        resolvedDraftRowId = seeded.id ?? null;
        setDraftRowId(seeded.id ?? null);
      } catch (err) {
        setDraftError(err instanceof Error ? err.message : `Failed to create draft for "${doc.machine_name}".`);
        return null;
      }
    }
    if (!resolvedDraftRowId) {
      setDraftError(`Failed to create draft for "${doc.machine_name}".`);
      return null;
    }
    setIsSavingDraft(true);
    setDraftError(null);
    try {
      const outgoingDef = {
        ...doc.definition,
        machine_key:
          typeof doc.definition.machine_key === "string" && doc.definition.machine_key.trim().length > 0
            ? doc.definition.machine_key
            : doc.machine_name,
      };

      // TEMPORARY DIAGNOSTICS — the payload exactly as it goes on the wire.
      diagLog(
        'PUT /draft REQUEST FIRING',
        `row=${resolvedDraftRowId} states=${JSON.stringify(
          (outgoingDef.states ?? []).map((s) => ({
            name: s.name,
            method_refs: s.method_refs ?? [],
          })),
        )}`,
      );
      const resp = await api.stateMachines.saveDraft(resolvedDraftRowId, outgoingDef, canvasMetadata);
      const safeDefinition = normalizeDefinitionShape(
        resp.record.definition as Record<string, unknown> | undefined,
        doc.definition,
      );
      setDocState({
        machine_name: resp.record.machine_name,
        base_version: resp.record.version,
        definition: safeDefinition,
      }, 'saveDraft(server-response-echo)');
      setCanvasMetadata(resp.record.canvas_metadata ?? null);
      setIsDirty(false);
      setRemoteIssues(null);
      // Refresh the shared workflow list, same as `publish` below.
      window.dispatchEvent(new Event(STATE_MACHINES_CHANGED_EVENT));
      return resp;
    } catch (err) {
      setDraftError(err instanceof Error ? err.message : "Failed to save draft");
      return null;
    } finally {
      setIsSavingDraft(false);
    }
  }, [doc, canvasMetadata, draftRowId]);

  const save = useCallback(async (): Promise<StateMachineRecord | null> => {
    let resolvedDraftRowId = draftRowId;
    if (!resolvedDraftRowId) {
      try {
        const seeded = await api.stateMachines.seedDraft(doc.machine_name);
        resolvedDraftRowId = seeded.id ?? null;
        setDraftRowId(seeded.id ?? null);
      } catch (err) {
        setSaveError(err instanceof Error ? err.message : `Failed to create draft for "${doc.machine_name}".`);
        return null;
      }
    }
    if (!resolvedDraftRowId) {
      setSaveError(`Failed to create draft for "${doc.machine_name}".`);
      return null;
    }
    setIsSaving(true);
    setSaveError(null);
    try {
      const outgoingDef = {
        ...doc.definition,
        machine_key:
          typeof doc.definition.machine_key === "string" && doc.definition.machine_key.trim().length > 0
            ? doc.definition.machine_key
            : doc.machine_name,
      };
      const result = await api.stateMachines.publish(resolvedDraftRowId, outgoingDef, canvasMetadata);
      const record = result.state_machine;
      setDocState(recordToDoc(record), 'publish(server-response-echo)');
      setCanvasMetadata(record.canvas_metadata ?? null);
      setIsDirty(false);
      setRemoteIssues(null);
      window.dispatchEvent(new Event(STATE_MACHINES_CHANGED_EVENT));
      // A newly published workflow can introduce a new entity type the caller's
      // system role now has access to; refresh permissions so its pipeline/records
      // don't wrongly render "Access Denied" until a manual page refresh (STAT-424).
      await refreshPermissions();
      return record;
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Failed to publish state machine");
      return null;
    } finally {
      setIsSaving(false);
    }
  }, [doc, canvasMetadata, draftRowId, refreshPermissions]);

  return {
    doc,
    setDoc,
    patchDefinition,
    canvasNodes,
    setCanvasNodes: updateCanvasNodes,
    isCreating,
    isLoading,
    loadError,
    isDirty,
    hasDraft: draftRowId !== null,
    isSaving,
    isSavingDraft,
    saveError,
    draftError,
    remoteIssues,
    localIssues,
    save,
    saveDraft,
    reload: load,
  };
}
