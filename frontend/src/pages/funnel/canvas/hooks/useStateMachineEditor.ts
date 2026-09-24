import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { createInitialDoc, createSampleDoc } from "@/lib/state-machine/draft";
import {
  buildEntityFieldsFromFormSchema,
  pruneTransitionsForEntityFields,
} from "@/lib/state-machine/entitySchema";
import { validateMachine, enrichIssues } from "@/lib/state-machine/validate";
import type { StateMachineDocument, ValidationIssue } from "@/lib/state-machine/types";
import api from "@/core/services/api";
import { useAuth } from "@/core/auth";
import { schemaForEntityType, useEntityStore } from "@/core/stores/entityStore";
import type { InspectorMode } from "../InspectorPanel";
import type { NodePositions } from "../utils/canvasUtils";
import {
  normalizeDraftForSubmit,
  normalizeStateMachineRecord,
  parseRemoteValidation,
} from "../utils/smNormalizers";

export function useStateMachineEditor() {
  const navigate = useNavigate();
  const { refreshPermissions } = useAuth();
  const { machineName: routeMachineName, version: routeVersion } = useParams<{
    machineName?: string;
    version?: string;
  }>();
  const editVersion =
    routeVersion !== undefined && routeVersion !== "" ? Number(routeVersion) : null;
  const isEditingExisting =
    Boolean(routeMachineName) && editVersion !== null && Number.isFinite(editVersion);

  const [doc, setDoc] = useState<StateMachineDocument>(() => createInitialDoc());
  const [positions, setPositions] = useState<NodePositions>({});
  const [mode, setMode] = useState<InspectorMode>({ kind: "none" });
  const [selectedStateName, setSelectedStateName] = useState<string | null>(null);
  const [remoteIssues, setRemoteIssues] = useState<ValidationIssue[] | null>(null);
  const [isValidating, setIsValidating] = useState(false);
  const [isPublishing, setIsPublishing] = useState(false);
  const [isSavingDraft, setIsSavingDraft] = useState(false);
  const [isPublished, setIsPublished] = useState(false);
  const [issuesOpen, setIssuesOpen] = useState(false);
  const [isLoadingMachine, setIsLoadingMachine] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const schemas = useEntityStore((state) => state.schemas);
  const fetchSchemas = useEntityStore((state) => state.fetchSchemas);

  const localIssues = useMemo(() => validateMachine(doc), [doc]);
  const issues = useMemo(() => {
    const remote = remoteIssues
      ? remoteIssues.map((i) => ({ ...i, source: "server" as const }))
      : [];
    const combined = remoteIssues ? [...localIssues, ...remote] : localIssues;
    return enrichIssues(combined, doc.definition);
  }, [localIssues, remoteIssues, doc.definition]);

  const errorCount = issues.filter((i) => i.level === "error").length;
  const warningCount = issues.filter((i) => i.level === "warning").length;
  const isValid = errorCount === 0;

  const stateIssueMap = useMemo(() => {
    const map: Record<string, "error" | "warning"> = {};
    for (const issue of issues) {
      if (issue.stateName) {
        if (issue.level === "error" || !map[issue.stateName]) {
          map[issue.stateName] = issue.level;
        }
      }
    }
    return map;
  }, [issues]);

  const transitionIssueMap = useMemo(() => {
    const map: Record<string, "error" | "warning"> = {};
    for (const issue of issues) {
      if (issue.transitionKey) {
        if (issue.level === "error" || !map[issue.transitionKey]) {
          map[issue.transitionKey] = issue.level;
        }
      }
    }
    return map;
  }, [issues]);

  const selectedTransitionKey = mode.kind === "transition" ? mode.key : null;

  const closeInspector = useCallback(() => setMode({ kind: "none" }), []);
  const selectState = useCallback((name: string | null) => setSelectedStateName(name), []);
  const editState = useCallback((name: string) => setMode({ kind: "state", name }), []);
  const selectTransition = useCallback(
    (key: string | null) => setMode(key ? { kind: "transition", key } : { kind: "none" }),
    [],
  );

  const resetForNewMachine = useCallback(() => {
    setDoc(createInitialDoc());
    setPositions({});
    setMode({ kind: "none" });
    setSelectedStateName(null);
    setRemoteIssues(null);
    setIsPublished(false);
    setIssuesOpen(false);
    setLoadError(null);
    navigate("/funnel/create");
  }, [navigate]);

  const loadExample = useCallback(() => {
    setRemoteIssues(null);
    setIsPublished(false);
    setIssuesOpen(false);
    setLoadError(null);
    setDoc(createSampleDoc());
    setPositions({});
    setMode({ kind: "none" });
    setSelectedStateName(null);
  }, []);

  const handleRenameState = useCallback((oldName: string, newName: string) => {
    setPositions((p) => {
      if (!p[oldName] || oldName === newName) return p;
      const { [oldName]: moved, ...rest } = p;
      return { ...rest, [newName]: moved };
    });
  }, []);

  useEffect(() => {
    if (!isEditingExisting && schemas.length === 0) {
      void fetchSchemas();
    }
  }, [fetchSchemas, isEditingExisting, schemas.length]);

  useEffect(() => {
    if (!isEditingExisting) {
      setRemoteIssues(null);
      setIsPublished(false);
      setIssuesOpen(false);
      setLoadError(null);
      return;
    }

    const machineName = routeMachineName!;
    const machineVersion = editVersion as number;
    let cancelled = false;
    setIsLoadingMachine(true);
    setLoadError(null);
    setRemoteIssues(null);
    setIsPublished(false);

    api.stateMachines
      .get(machineName, machineVersion)
      .then((record) => {
        if (cancelled) return;
        setDoc(normalizeStateMachineRecord(record));
        setPositions({});
        setMode({ kind: "none" });
        setSelectedStateName(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setLoadError(err instanceof Error ? err.message : "Failed to load state machine");
      })
      .finally(() => {
        if (!cancelled) setIsLoadingMachine(false);
      });

    return () => {
      cancelled = true;
    };
  }, [routeMachineName, editVersion, isEditingExisting]);

  // Sync entity schema when entity_type changes and a matching schema exists
  useEffect(() => {
    if (isEditingExisting) return;
    const entityType = doc.definition.entity_type.trim();
    if (!entityType) return;
    if (schemas.length === 0) return;
    const matchedSchema = schemaForEntityType(schemas, entityType);
    const nextFields = matchedSchema ? buildEntityFieldsFromFormSchema(matchedSchema) : [];
    const currentSchema = doc.definition.entity_schema;
    const prunedTransitions = pruneTransitionsForEntityFields(doc.definition.transitions, nextFields);
    const sameEntityType = currentSchema.entity_type === entityType;
    const sameFields = JSON.stringify(currentSchema.fields) === JSON.stringify(nextFields);
    const sameTransitions = JSON.stringify(prunedTransitions) === JSON.stringify(doc.definition.transitions);
    if (sameEntityType && sameFields && sameTransitions) return;
    setDoc({
      ...doc,
      definition: {
        ...doc.definition,
        entity_schema: { entity_type: entityType, fields: nextFields },
        transitions: prunedTransitions,
      },
    });
  }, [doc, isEditingExisting, schemas]);

  // Keep selection valid when doc changes externally
  useEffect(() => {
    if (mode.kind === "state" && !doc.definition.states.find((s) => s.name === mode.name)) {
      setMode({ kind: "none" });
    }
    if (
      mode.kind === "transition" &&
      !doc.definition.transitions.find((t) => t.key === mode.key)
    ) {
      setMode({ kind: "none" });
    }
    setSelectedStateName((s) =>
      s && !doc.definition.states.find((st) => st.name === s) ? null : s,
    );
  }, [doc, mode]);

  const addState = () => {
    const existing = new Set(doc.definition.states.map((s) => s.name));
    let i = doc.definition.states.length + 1;
    let name = `STATE_${i}`;
    while (existing.has(name)) {
      i += 1;
      name = `STATE_${i}`;
    }
    const isFirst = doc.definition.states.length === 0;
    setDoc({
      ...doc,
      definition: {
        ...doc.definition,
        states: [
          ...doc.definition.states,
          {
            name,
            description: "",
            tags: isFirst ? ["initial"] : [],
            order: doc.definition.states.length + 1,
            sla_seconds: null,
          },
        ],
        initial_state: isFirst ? name : doc.definition.initial_state,
      },
    });
    setPositions((p) => ({
      ...p,
      [name]: {
        x: 120 + (Object.keys(p).length % 4) * 60,
        y: 120 + (Object.keys(p).length % 4) * 60,
      },
    }));
  };

  const createTransition = (from: string, to: string) => {
    const existing = new Set(doc.definition.transitions.map((t) => t.key));
    let n = doc.definition.transitions.length + 1;
    let key = `${from}_to_${to}`;
    while (existing.has(key)) {
      key = `${from}_to_${to}_${n++}`;
    }
    setDoc({
      ...doc,
      definition: {
        ...doc.definition,
        transitions: [
          ...doc.definition.transitions,
          {
            key,
            trigger: key,
            label: `${from} → ${to}`,
            from,
            to_state: to,
            required_fields: [],
            guards: [],
            pre_transition_tasks: [],
            post_transition_tasks: [],
            auto_transition: { enabled: false, delay_seconds: 0 },
            description: "",
          },
        ],
      },
    });
    setMode({ kind: "transition", key });
  };

  const deleteState = (name: string) => {
    const def = doc.definition;
    const newStates = def.states
      .filter((s) => s.name !== name)
      .map((s, i) => ({ ...s, order: i + 1 }));
    const newTransitions = def.transitions.filter(
      (t) => t.from !== name && t.to_state !== name,
    );
    setDoc({
      ...doc,
      definition: {
        ...def,
        states: newStates,
        transitions: newTransitions,
        initial_state:
          def.initial_state === name ? (newStates[0]?.name ?? "") : def.initial_state,
      },
    });
    setPositions((p) => {
      const rest = { ...p };
      delete rest[name];
      return rest;
    });
    if (mode.kind === "state" && mode.name === name) setMode({ kind: "none" });
    setSelectedStateName((s) => (s === name ? null : s));
  };

  const deleteTransition = (key: string) => {
    setDoc({
      ...doc,
      definition: {
        ...doc.definition,
        transitions: doc.definition.transitions.filter((t) => t.key !== key),
      },
    });
    if (mode.kind === "transition" && mode.key === key) setMode({ kind: "none" });
  };

  const handleValidateRemote = async () => {
    setIsValidating(true);
    setRemoteIssues(null);
    const submitDoc = normalizeDraftForSubmit(doc);
    setDoc(submitDoc);
    let payload: unknown = null;
    let ok = true;
    try {
      payload = await api.stateMachines.validate(submitDoc);
    } catch (err) {
      ok = false;
      if (err && typeof err === "object" && "detail" in err) {
        payload = (err as { detail?: unknown; message?: string }).detail ?? {
          message: (err as { message?: string }).message ?? "Validation request failed.",
        };
      } else {
        payload = err instanceof Error ? { message: err.message } : null;
      }
    }
    const parsed = parseRemoteValidation(payload, ok);
    setRemoteIssues(parsed);
    if (!ok) {
      toast.error("Validation API error");
      setIssuesOpen(true);
    } else if (parsed.length === 0) {
      toast.success("Server validation passed");
    } else {
      const errs = parsed.filter((i) => i.level === "error").length;
      toast.warning(
        errs > 0
          ? `Server reported ${errs} error(s)`
          : `Server reported ${parsed.length} warning(s)`,
      );
      setIssuesOpen(true);
    }
    setIsValidating(false);
  };

  const handleSaveDraft = async () => {
    if (!isEditingExisting || !routeMachineName || editVersion === null) {
      toast.error(
        "Save as draft requires an existing draft. Click + in the sidebar to start one.",
      );
      return;
    }
    const hasEmptyStateName = doc.definition.states.some((s) => !s.name?.trim());
    if (hasEmptyStateName) {
      toast.error("All states must have a name before saving.");
      return;
    }
    setIsSavingDraft(true);
    setRemoteIssues(null);
    const submitDoc = normalizeDraftForSubmit(doc);
    setDoc(submitDoc);
    try {
      const resp = await api.stateMachines.saveDraft(
        routeMachineName,
        submitDoc.definition,
      );
      setDoc(normalizeStateMachineRecord(resp.record));
      window.dispatchEvent(new Event("state-machines-changed"));
      toast.success("Draft saved.");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      toast.error("Save draft failed", { description: msg });
    } finally {
      setIsSavingDraft(false);
    }
  };

  const handlePublish = async () => {
    if (localIssues.some((i) => i.level === "error")) {
      setIssuesOpen(true);
      toast.error("Fix validation errors before publishing.");
      return;
    }
    setIsPublishing(true);
    setRemoteIssues(null);
    const submitDoc = normalizeDraftForSubmit(doc);
    setDoc(submitDoc);
    try {
      const result = await api.stateMachines.publish(submitDoc.machine_name, submitDoc.definition);
      const reportIssues = parseRemoteValidation(result, true);
      if (reportIssues.length > 0) {
        setRemoteIssues(reportIssues);
        setIssuesOpen(true);
      }
      setIsPublished(true);
      const nextRecord = result.state_machine;
      const version = nextRecord?.version;
      if (nextRecord) {
        setDoc(normalizeStateMachineRecord(nextRecord));
        // Refresh the workflow/entity-type lists and the caller's permissions
        // before navigating, so the destination pipeline/records render with the
        // new workflow visible instead of a stale "Access Denied" (STAT-424).
        window.dispatchEvent(new Event("state-machines-changed"));
        await refreshPermissions();
        navigate(
          `/funnel/edit/${encodeURIComponent(nextRecord.machine_name)}/${nextRecord.version}`,
          { replace: true },
        );
      }
      toast.success(
        isEditingExisting
          ? `New version published (v${version}).`
          : `Machine published (v${version}).`,
      );
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      const errDetail =
        err && typeof err === "object" && "detail" in err
          ? (err as Record<string, unknown>).detail
          : null;
      const serverIssues = parseRemoteValidation(errDetail ?? { message: msg }, false);
      if (serverIssues.length > 0) {
        setRemoteIssues(serverIssues);
        setIssuesOpen(true);
        toast.error("Publish blocked by validation errors.");
      } else {
        toast.error("Publish failed", { description: msg });
      }
    } finally {
      setIsPublishing(false);
    }
  };

  return {
    isEditingExisting,
    doc,
    setDoc,
    positions,
    setPositions,
    mode,
    setMode,
    selectedStateName,
    issuesOpen,
    setIssuesOpen,
    isValidating,
    isPublishing,
    isSavingDraft,
    isPublished,
    isLoadingMachine,
    loadError,
    issues,
    errorCount,
    warningCount,
    isValid,
    stateIssueMap,
    transitionIssueMap,
    selectedTransitionKey,
    closeInspector,
    selectState,
    editState,
    selectTransition,
    resetForNewMachine,
    loadExample,
    handleRenameState,
    addState,
    createTransition,
    deleteState,
    deleteTransition,
    handleValidateRemote,
    handleSaveDraft,
    handlePublish,
  };
}

export type StateMachineEditorState = ReturnType<typeof useStateMachineEditor>;
