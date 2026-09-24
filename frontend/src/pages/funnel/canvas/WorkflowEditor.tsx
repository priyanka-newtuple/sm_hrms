import { useCallback, useEffect, useRef, useState } from "react";
import {
  CircleAlert,
  AlertTriangle,
  Plus,
  Settings2,
  Database,
  FileJson,
  ListChecks,
  ListOrdered,
  ChevronDown,
  ChevronUp,
} from "lucide-react";

import { WorkflowCanvas, type NodePositions } from "./WorkflowCanvas";
import { useMethodFieldsByState } from "@/pages/funnel/wizard/useMethodFieldsByState";
import { InspectorPanel, type InspectorMode } from "./InspectorPanel";

import type { StateMachineDocument, ValidationIssue } from "@/lib/state-machine/types";
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
// TEMPORARY DIAGNOSTICS — see lib/state-machine/diag.ts; strip with the bug.
import {
  diagLog,
  diagLogCommit,
  diagLogRefWrite,
  methodRefsSnapshot,
} from '@/lib/state-machine/diag';
import { formSchemas } from '@/core/services/api';
import {
  resyncEntitySchemaFields,
} from '@/lib/state-machine/entitySchema';

interface WorkflowEditorProps {
  doc: StateMachineDocument;
  onChange: (next: StateMachineDocument) => void;
  issues: ValidationIssue[];
  positions: NodePositions;
  onPositionsChange: (next: NodePositions) => void;
}

export function WorkflowEditor({
  doc,
  onChange: rawOnChange,
  issues,
  positions,
  onPositionsChange,
}: WorkflowEditorProps) {
  // TEMPORARY DIAGNOSTICS — every document write from the Canvas funnels
  // through here, so wrapping onChange logs all of them with their trigger.
  const onChange = (next: StateMachineDocument, trigger = 'canvas:unknown') => {
    diagLogCommit(trigger, doc, next);
    rawOnChange(next);
  };

  const [mode, setMode] = useState<InspectorMode>({ kind: "none" });
  const [selectedStateName, setSelectedStateName] = useState<string | null>(null);
  const [issuesOpen, setIssuesOpen] = useState(false);

  const def = doc.definition;

  // Always the latest doc for the async effect below — that effect's own
  // closure over `doc`/`def` goes stale the moment anything else edits the
  // document while its formSchemas.list() request is still in flight (e.g.
  // attaching a Method via the state inspector), and spreading that stale
  // snapshot into onChange would silently revert the concurrent edit.
  // The canvas had no view of its pinned Method Blocks; without one the
  // re-sync below cannot tell a method-owned field from a Form-owned one.
  const { fieldsByState } = useMethodFieldsByState(doc.definition.states);
  const methodFieldsRef = useRef(fieldsByState);
  // Declared before the re-sync effect on purpose: same-component effects run
  // in declaration order, so the ref is current before that effect's fetch is
  // even started. Writing it during render instead would be a render-phase
  // side effect, which StrictMode's double render and concurrent rendering
  // both make unsafe.
  useEffect(() => {
    methodFieldsRef.current = fieldsByState;
  }, [fieldsByState]);

  const docRef = useRef(doc);
  useEffect(() => {
    diagLogRefWrite('canvas docRef.current', docRef.current, doc);
    docRef.current = doc;
  }, [doc]);

  // Re-sync the entity schema from the entity type's forms on open so guard
  // field dropdowns reflect the latest form fields, not a stale snapshot.
  useEffect(() => {
    // TODO: Extract this form-schema sync block with the wizard once the P1
    // absent-forms behavior is verified in both editors.
    if (!def.entity_type || def.entity_type === 'entity') {
      diagLog('formSchemas.list SKIPPED (canvas)', `entityType=${def.entity_type ?? '<none>'}`);
      return;
    }
    let cancelled = false;
    const entityType = def.entity_type;
    diagLog('formSchemas.list KICKOFF (canvas)', `entityType=${entityType}`);
    formSchemas.list(def.entity_type).then((resp) => {
      diagLog(
        'formSchemas.list RESOLVED (canvas)',
        `entityType=${entityType} items=${resp.items.length} cancelled=${cancelled}`,
      );
      const latestDoc = docRef.current;
      const latestDef = latestDoc.definition;
      if (cancelled || latestDef.entity_type !== entityType) {
        diagLog('entity-schema re-sync BAILED (canvas)', 'cancelled or entityType changed');
        return;
      }
      if (resp.items.length === 0) {
        diagLog('entity-schema re-sync BAILED (canvas)', 'zero form items — no-op');
        return;
      }
      const {
        fields: syncedFields,
        transitions: prunedTransitions,
        unchanged,
      } = resyncEntitySchemaFields(
        latestDef,
        resp.items,
        Object.values(methodFieldsRef.current),
      );
      if (unchanged) {
        diagLog('entity-schema re-sync BAILED (canvas)', 'forms already match — no-op');
        return; // no-op when forms already match
      }
      // Merge base chosen ONCE; the resulting object is both logged and
      // committed as the same reference, so the log cannot misreport it.
      const mergeSource = 'docRef.current';
      const mergeBase = latestDoc;
      const mergeBaseDef = latestDef;
      diagLog(
        'entity-schema re-sync SOURCE (canvas)',
        `candidates: stale-closure doc{${methodRefsSnapshot(doc)}} | docRef.current{${methodRefsSnapshot(latestDoc)}} => SELECTED ${mergeSource}{${methodRefsSnapshot(mergeBase)}}`,
      );
      const committed = {
        ...mergeBase,
        definition: {
          ...mergeBaseDef,
          entity_schema: { entity_type: entityType, fields: syncedFields },
          transitions: prunedTransitions,
        },
      };
      diagLogCommit('entity-schema re-sync (canvas)', mergeBase, committed, `mergeSource=${mergeSource}`);
      rawOnChange(committed);
    }).catch((err) => {
      console.error('Failed to load form schemas for entity type', def.entity_type, err);
      toast.error('Could not load form fields', {
        description: 'Guard field options may be incomplete.',
      });
    });
    return () => {
      cancelled = true;
    };
  }, [def.entity_type]);

  const errorCount = issues.filter((i) => i.level === "error").length;
  const warningCount = issues.filter((i) => i.level === "warning").length;

  const selectedTransitionKey = mode.kind === "transition" ? mode.key : null;

  const closeInspector = useCallback(() => setMode({ kind: "none" }), []);
  const selectState = useCallback((name: string | null) => {
    setSelectedStateName(name);
    if (name === null) setMode({ kind: "none" });
  }, []);
  const editState = useCallback((name: string) => {
    setSelectedStateName(name);
    setMode({ kind: "state", name });
  }, []);
  const selectTransition = useCallback(
    (key: string | null) => setMode(key ? { kind: "transition", key } : { kind: "none" }),
    [],
  );
  const renameState = useCallback((oldName: string, newName: string) => {
    if (oldName === newName) return;
    if (positions[oldName]) {
      const { [oldName]: pos, ...rest } = positions;
      onPositionsChange({ ...rest, [newName]: pos });
    }
    setSelectedStateName(newName);
    setMode({ kind: "state", name: newName });
  }, [positions, onPositionsChange]);

  const addState = () => {
    const existing = new Set(doc.definition.states.map((s) => s.name));
    let i = doc.definition.states.length + 1;
    let name = `STATE_${i}`;
    while (existing.has(name)) {
      i += 1;
      name = `STATE_${i}`;
    }
    const isFirst = doc.definition.states.length === 0;
    const next: StateMachineDocument = {
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
    };
    onChange(next);
    onPositionsChange({
      ...positions,
      [name]: {
        x: 120 + (Object.keys(positions).length % 4) * 60,
        y: 120 + (Object.keys(positions).length % 4) * 60,
      },
    });
    setSelectedStateName(name);
    setMode({ kind: "state", name });
  };

  const createTransition = (from: string, to: string) => {
    const existing = new Set(doc.definition.transitions.map((t) => t.key));
    let n = doc.definition.transitions.length + 1;
    let key = `${from}_to_${to}`;
    while (existing.has(key)) {
      key = `${from}_to_${to}_${n++}`;
    }
    const next: StateMachineDocument = {
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
            auto_transition: null,
            description: "",
          },
        ],
      },
    };
    onChange(next);
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
    onChange({
      ...doc,
      definition: {
        ...def,
        states: newStates,
        transitions: newTransitions,
        initial_state: def.initial_state === name ? (newStates[0]?.name ?? "") : def.initial_state,
      },
    });
    const { [name]: _omit, ...restPositions } = positions;
    onPositionsChange(restPositions);
    if (selectedStateName === name) setSelectedStateName(null);
    if (mode.kind === "state" && mode.name === name) setMode({ kind: "none" });
  };

  const deleteTransition = (key: string) => {
    onChange({
      ...doc,
      definition: {
        ...doc.definition,
        transitions: doc.definition.transitions.filter((t) => t.key !== key),
      },
    });
    if (mode.kind === "transition" && mode.key === key) setMode({ kind: "none" });
  };

  // Keep selection valid when external doc changes (e.g. tab switch).
  useEffect(() => {
    if (selectedStateName && !doc.definition.states.find((s) => s.name === selectedStateName)) {
      setSelectedStateName(null);
    }
    if (mode.kind === "state" && !doc.definition.states.find((s) => s.name === mode.name)) {
      setMode({ kind: "none" });
    }
    if (mode.kind === "transition" && !doc.definition.transitions.find((t) => t.key === mode.key)) {
      setMode({ kind: "none" });
    }
  }, [doc, mode, selectedStateName]);

  return (
    <div className="flex min-h-0 flex-1">
      <nav className="flex w-14 flex-col items-center gap-1 border-r border-border bg-card py-3">
        <RailButton label="Add state" onClick={addState} active={false}>
          <Plus className="h-4 w-4" />
        </RailButton>
        <div className="my-2 h-px w-8 bg-border" />
        <RailButton
          label="Outline (states & transitions)"
          onClick={() => setMode({ kind: "list" })}
          active={mode.kind === "list"}
        >
          <ListOrdered className="h-4 w-4" />
        </RailButton>
        <RailButton
          label="Workflow settings"
          onClick={() => setMode({ kind: "settings" })}
          active={mode.kind === "settings"}
        >
          <Settings2 className="h-4 w-4" />
        </RailButton>
        <RailButton
          label="Entity schema"
          onClick={() => setMode({ kind: "schema" })}
          active={mode.kind === "schema"}
        >
          <Database className="h-4 w-4" />
        </RailButton>
        <RailButton
          label="JSON definition"
          onClick={() => setMode({ kind: "json" })}
          active={mode.kind === "json"}
        >
          <FileJson className="h-4 w-4" />
        </RailButton>
      </nav>

      <main className="relative flex-1 overflow-hidden">
        <WorkflowCanvas
          definition={doc.definition}
          positions={positions}
          onPositionsChange={onPositionsChange}
          selectedStateName={selectedStateName}
          selectedTransitionKey={selectedTransitionKey}
          onSelectState={selectState}
          onEditState={editState}
          onSelectTransition={selectTransition}
          onAddState={addState}
          onCreateTransition={createTransition}
          onDeleteState={deleteState}
          onDeleteTransition={deleteTransition}
        />

        {issues.length > 0 && (
          <div className="absolute left-1/2 top-3 z-10 w-[min(640px,calc(100%-2rem))] -translate-x-1/2">
            <div className="overflow-hidden rounded-md border border-border bg-card/95 shadow-md backdrop-blur">
              <Button variant="ghost"
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs bg-secondary"
                onClick={() => setIssuesOpen((o) => !o)}
              >
                <ListChecks className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="font-medium">Validation</span>
                {errorCount > 0 && (
                  <span className="inline-flex items-center gap-1 text-destructive">
                    <CircleAlert className="h-3 w-3" /> {errorCount}
                  </span>
                )}
                {warningCount > 0 && (
                  <span className="inline-flex items-center gap-1 text-warning">
                    <AlertTriangle className="h-3 w-3" /> {warningCount}
                  </span>
                )}
                <span className="ml-auto text-muted-foreground">
                  {issuesOpen ? (
                    <ChevronUp className="h-3.5 w-3.5" />
                  ) : (
                    <ChevronDown className="h-3.5 w-3.5" />
                  )}
                </span>
              </Button>
              {issuesOpen && (
                <ul className="max-h-56 divide-y divide-border overflow-auto border-t border-border">
                  {issues.map((issue, i) => (
                    <li key={i} className="flex items-start gap-2 px-3 py-2 text-xs">
                      {issue.level === "error" ? (
                        <CircleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0 text-destructive" />
                      ) : (
                        <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" />
                      )}
                      <div>
                        <div className="font-mono text-[11px] text-muted-foreground">
                          {issue.path}
                        </div>
                        <div className="text-foreground">{issue.message}</div>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        )}
      </main>

      <InspectorPanel
        doc={doc}
        onChange={onChange}
        mode={mode}
        onClose={closeInspector}
        onSelectState={selectState}
        onSelectTransition={selectTransition}
        onDeleteState={deleteState}
        onDeleteTransition={deleteTransition}
        onCreateTransition={createTransition}
        onRenameState={renameState}
      />
    </div>
  );
}

function RailButton({
  children,
  label,
  active,
  onClick,
}: {
  children: React.ReactNode;
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <Button
      variant="secondary"
      size="icon"
      onClick={onClick}
      title={label}
      aria-label={label}
      className={`rounded-md border transition-colors ${
        active
          ? "border-foreground bg-foreground text-background"
          : "border-transparent text-muted-foreground hover:border-border hover:bg-muted hover:text-foreground"
      }`}
    >
      {children}
    </Button>
  );
}
