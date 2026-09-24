import { useMemo } from "react";
import { Button } from "@/components/ui/button";
import {
  X,
  Settings2,
  CircleDot,
  ArrowRight,
  Database,
  FileJson,
  ListOrdered,
} from "lucide-react";
import type { StateMachineDocument, Transition } from "@/lib/state-machine/types";
import { TransitionEditor } from "./TransitionsEditor";
import { BasicsEditor } from "./BasicsEditor";
import { EntitySchemaEditor } from "./EntitySchemaEditor";
import { JsonView } from "./JsonView";
import { StateInspector } from "./StateInspector";
import { OutlineList } from "./OutlineList";

export type InspectorMode =
  | { kind: "none" }
  | { kind: "state"; name: string }
  | { kind: "transition"; key: string }
  | { kind: "settings" }
  | { kind: "schema" }
  | { kind: "json" }
  | { kind: "list" };

interface Props {
  doc: StateMachineDocument;
  onChange: (next: StateMachineDocument) => void;
  mode: InspectorMode;
  onClose: () => void;
  onSelectTransition: (key: string | null) => void;
  onSelectState: (name: string | null) => void;
  onDeleteTransition?: (key: string) => void;
  onDeleteState?: (name: string) => void;
  onCreateTransition?: (from: string, to: string) => void;
  onRenameState?: (oldName: string, newName: string) => void;
}

export function InspectorPanel({
  doc,
  onChange,
  mode,
  onClose,
  onSelectTransition,
  onSelectState,
  onDeleteTransition,
  onDeleteState,
  onCreateTransition,
  onRenameState,
}: Props) {
  const def = doc.definition;

  const title = useMemo(() => {
    switch (mode.kind) {
      case "state":
        return { icon: <CircleDot className="h-4 w-4" />, text: "State", sub: mode.name };
      case "transition": {
        const t = def.transitions.find((x) => x.key === mode.key);
        return {
          icon: <ArrowRight className="h-4 w-4" />,
          text: "Transition",
          sub: t ? `${t.from} → ${t.to_state}` : mode.key,
        };
      }
      case "settings":
        return { icon: <Settings2 className="h-4 w-4" />, text: "Workflow settings", sub: "" };
      case "schema":
        return { icon: <Database className="h-4 w-4" />, text: "Entity schema", sub: "" };
      case "json":
        return { icon: <FileJson className="h-4 w-4" />, text: "JSON definition", sub: "" };
      case "list":
        return {
          icon: <ListOrdered className="h-4 w-4" />,
          text: "Outline",
          sub: "States & transitions",
        };
      default:
        return null;
    }
  }, [mode, def.transitions]);

  if (mode.kind === "none") return null;

  return (
    <aside className="flex h-full w-[440px] shrink-0 flex-col overflow-hidden border-l border-border bg-card shadow-xl">
      <div className="flex items-center gap-2 border-b border-border px-4 py-3">
        <span className="flex h-7 w-7 items-center justify-center rounded-md bg-muted text-foreground">
          {title?.icon}
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold">{title?.text}</div>
          {title?.sub && (
            <div className="truncate font-mono text-[11px] text-muted-foreground">{title.sub}</div>
          )}
        </div>
        <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close inspector">
          <X className="h-4 w-4" />
        </Button>
      </div>

      {/* JSON mode gets its own non-scrolling flex container so JsonView
          can fill the exact remaining height and pin the Apply bar at the bottom. */}
      {mode.kind === "json" ? (
        <div className="flex flex-1 flex-col overflow-hidden p-4">
          <JsonView doc={doc} onChange={onChange} />
        </div>
      ) : (
        <div className="flex-1 overflow-x-hidden overflow-y-auto">
          {mode.kind === "state" && (
            <StateInspector
              key={mode.name}
              doc={doc}
              onChange={onChange}
              stateName={mode.name}
              onSelectTransition={(k) => onSelectTransition(k)}
              onClose={onClose}
              onAfterDelete={() => onSelectState(null)}
              onRename={(oldName, newName) => {
                onRenameState?.(oldName, newName);
                onSelectState(newName);
              }}
            />
          )}
          {mode.kind === "transition" && (
            <TransitionInspector
              doc={doc}
              onChange={onChange}
              transitionKey={mode.key}
              onAfterDelete={() => onSelectTransition(null)}
            />
          )}
          {mode.kind === "settings" && (
            <div className="p-4">
              <BasicsEditor doc={doc} onChange={onChange} />
            </div>
          )}
          {mode.kind === "schema" && (
            <div className="p-4">
              <EntitySchemaEditor doc={doc} />
            </div>
          )}
          {mode.kind === "list" && (
            <OutlineList
              doc={doc}
              onSelectState={(n) => onSelectState(n)}
              onSelectTransition={(k) => onSelectTransition(k)}
              onDeleteState={onDeleteState}
              onDeleteTransition={onDeleteTransition}
              onCreateTransition={onCreateTransition}
            />
          )}
        </div>
      )}
    </aside>
  );
}

function TransitionInspector({
  doc,
  onChange,
  transitionKey,
  onAfterDelete,
}: {
  doc: StateMachineDocument;
  onChange: (next: StateMachineDocument) => void;
  transitionKey: string;
  onAfterDelete: () => void;
}) {
  const def = doc.definition;
  const idx = def.transitions.findIndex((t) => t.key === transitionKey);
  if (idx < 0) {
    return (
      <div className="p-4 text-sm text-muted-foreground">
        Transition not found. It may have been removed.
      </div>
    );
  }
  const t = def.transitions[idx];

  const updateTransition = (patch: Partial<Transition>) =>
    onChange({
      ...doc,
      definition: {
        ...def,
        transitions: def.transitions.map((x, i) => (i === idx ? { ...x, ...patch } : x)),
      },
    });

  const remove = () => {
    onChange({
      ...doc,
      definition: { ...def, transitions: def.transitions.filter((_, i) => i !== idx) },
    });
    onAfterDelete();
  };

  return (
    <div className="min-w-0 p-4">
      <TransitionEditor
        transition={t}
        stateOptions={def.states.map((s) => s.name)}
        fieldOptions={def.entity_schema.fields.map((f) => f.field)}
        fieldsMeta={def.entity_schema.fields.map((f) => ({ field: f.field, type: f.type }))}
        onChange={updateTransition}
        onRemove={remove}
      />
    </div>
  );
}
