import { useMemo, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { DDSelect } from "./DDSelect";
import { StateActionsSection } from "./StateActionsSection";
import { StateMethodsSection } from "./StateMethodsSection";
import { ArrowRight, Check, Clock, Trash2, Zap } from "lucide-react";

import type { StateAction, StateMachineDocument } from "@/lib/state-machine/types";
import { type SlaUnit, buildSlaSeconds, slaToAmount, slaToUnit } from "@/shared/utils/sla";

type StateTagOption = "none" | "initial" | "terminal";

function tagOf(tags: string[]): StateTagOption {
  if (tags?.includes("initial")) return "initial";
  if (tags?.includes("terminal")) return "terminal";
  return "none";
}

interface StateInspectorProps {
  doc: StateMachineDocument;
  onChange: (next: StateMachineDocument) => void;
  stateName: string;
  onSelectTransition: (key: string) => void;
  onClose: () => void;
  onAfterDelete: () => void;
  onRename: (oldName: string, newName: string) => void;
}

export function StateInspector({
  doc,
  onChange,
  stateName,
  onSelectTransition,
  onClose,
  onAfterDelete,
  onRename,
}: StateInspectorProps) {
  const def = doc.definition;
  const idx = def.states.findIndex((x) => x.name === stateName);
  const s = idx >= 0 ? def.states[idx] : null;
  const savedTag: StateTagOption = s ? tagOf(s.tags ?? []) : "none";
  const savedDescription = s?.description ?? "";

  const savedSla = s?.sla_seconds ?? null;

  const [draft, setDraft] = useState({
    name: s?.name ?? stateName,
    tag: savedTag,
    description: savedDescription,
    sla_seconds: savedSla,
    slaUnit: slaToUnit(savedSla),
    slaAmount: slaToAmount(savedSla),
  });

  const isDirty = useMemo(
    () =>
      !!s &&
      (draft.name !== s.name ||
        draft.tag !== savedTag ||
        draft.description !== savedDescription ||
        draft.sla_seconds !== savedSla),
    [draft, s, savedTag, savedDescription, savedSla],
  );

  if (!s) {
    return (
      <div className="p-4 text-sm text-muted-foreground">
        State not found. It may have been removed.
      </div>
    );
  }

  const handleActionsChange = (actions: StateAction[]) => {
    const nextStates = def.states.map((state, i) =>
      i === idx ? { ...state, on_state_actions: actions } : state
    );
    onChange({ ...doc, definition: { ...def, states: nextStates } });
  };

  const handleMethodsChange = (methodRefs: NonNullable<typeof s.method_refs>) => {
    const nextStates = def.states.map((state, i) =>
      i === idx ? { ...state, method_refs: methodRefs } : state,
    );
    onChange({ ...doc, definition: { ...def, states: nextStates } });
  };

  const incoming = def.transitions.filter((t) => t.to_state === stateName);
  const outgoing = def.transitions.filter((t) => t.from === stateName);

  const applyUpdate = () => {
    const trimmedName = draft.name.trim();
    if (!trimmedName) {
      toast.error("State name is required.");
      return;
    }
    const collides = def.states.some((st, i) => i !== idx && st.name === trimmedName);
    if (collides) {
      toast.error(`State "${trimmedName}" already exists.`);
      return;
    }

    const oldName = s.name;
    const renamed = trimmedName !== oldName;

    const nextStates = def.states.map((state, i) => {
      if (i === idx) {
        const baseTags = (state.tags ?? []).filter(
          (t) => t !== "initial" && t !== "terminal",
        );
        const tags =
          draft.tag === "none" ? baseTags : [...baseTags, draft.tag];
        return {
          ...state,
          name: trimmedName,
          description: draft.description,
          tags,
          sla_seconds: draft.sla_seconds,
        };
      }
      if (draft.tag === "initial") {
        return { ...state, tags: (state.tags ?? []).filter((t) => t !== "initial") };
      }
      return state;
    });

    let nextTransitions = def.transitions;
    let nextInitial = def.initial_state;
    if (renamed) {
      nextTransitions = def.transitions.map((t) => ({
        ...t,
        from: t.from === oldName ? trimmedName : t.from,
        to_state: t.to_state === oldName ? trimmedName : t.to_state,
      }));
      if (def.initial_state === oldName) nextInitial = trimmedName;
    }
    if (draft.tag === "initial") nextInitial = trimmedName;
    else if (savedTag === "initial" && nextInitial === oldName) {
      nextInitial = "";
    }

    onChange({
      ...doc,
      definition: {
        ...def,
        states: nextStates,
        transitions: nextTransitions,
        initial_state: nextInitial,
      },
    });

    if (renamed) onRename(oldName, trimmedName);
    toast.success("State updated.");
  };

  const remove = () => {
    const newStates = def.states
      .filter((_, i) => i !== idx)
      .map((x, i) => ({ ...x, order: i + 1 }));
    const newTransitions = def.transitions.filter(
      (t) => t.from !== stateName && t.to_state !== stateName,
    );
    onChange({
      ...doc,
      definition: {
        ...def,
        states: newStates,
        transitions: newTransitions,
        initial_state:
          def.initial_state === stateName ? (newStates[0]?.name ?? "") : def.initial_state,
      },
    });
    onAfterDelete();
    onClose();
  };

  return (
    <div className="space-y-5 p-4">
      <div className="space-y-2">
        <Label className="text-xs">State name</Label>
        <Input
          value={draft.name}
          onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))}
          className="text-sm"
        />
      </div>

      <div className="space-y-2">
        <Label className="text-xs">Tag</Label>
        <DDSelect
          value={draft.tag}
          options={[
            { value: "none", label: "No tag" },
            { value: "initial", label: "Initial — workflow starts here" },
            { value: "terminal", label: "Terminal — workflow ends here" },
          ]}
          onSelect={(v) => setDraft((d) => ({ ...d, tag: v as StateTagOption }))}
        />
        {def.initial_state === s.name && (
          <Badge variant="secondary" className="mt-1 text-[10px] uppercase tracking-wider">
            Initial state
          </Badge>
        )}
      </div>

      <div className="space-y-2">
        <Label className="text-xs">Description</Label>
        <Textarea
          rows={3}
          value={draft.description}
          onChange={(e) => setDraft((d) => ({ ...d, description: e.target.value }))}
          placeholder="What does this state represent?"
        />
      </div>

      <div className="space-y-2">
        <Label className="text-xs flex items-center gap-1">
          <Clock className="h-3 w-3" />
          SLA Deadline
        </Label>
        <div className="flex items-center gap-2">
          <select
            value={draft.slaUnit}
            onChange={(e) => {
              const unit = e.target.value as SlaUnit;
              setDraft((d) => ({
                ...d,
                slaUnit: unit,
                sla_seconds: buildSlaSeconds(d.slaAmount, unit),
              }));
            }}
            className="h-9 flex-1 rounded-md border border-input bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          >
            <option value="none">No deadline</option>
            <option value="minutes">Minutes</option>
            <option value="hours">Hours</option>
            <option value="days">Days</option>
          </select>
          {draft.slaUnit !== "none" && (
            <Input
              type="number"
              min={1}
              className="w-24"
              placeholder="1"
              value={draft.slaAmount}
              onChange={(e) =>
                setDraft((d) => ({
                  ...d,
                  slaAmount: e.target.value,
                  sla_seconds: buildSlaSeconds(e.target.value, d.slaUnit),
                }))
              }
            />
          )}
        </div>
      </div>

      <div className="flex items-center gap-2 border-t border-border pt-3">
        <Button variant="primary" size="sm" onClick={applyUpdate} disabled={!isDirty}>
          <Check className="mr-1.5 h-3.5 w-3.5" />
          Update
        </Button>
        {isDirty && (
          <span className="text-[11px] text-muted-foreground">Unsaved changes</span>
        )}
      </div>

      <StateMethodsSection
        methodRefs={s.method_refs ?? []}
        onChange={handleMethodsChange}
        entityType={def.entity_type}
      />

      <div className="space-y-2 border-t border-border pt-4">
        <div className="flex items-center gap-1.5">
          <Zap className="h-3.5 w-3.5 text-primary" />
          <span className="text-xs font-semibold">Actions on entry</span>
        </div>
        <StateActionsSection
          actions={s.on_state_actions ?? []}
          entityFields={def.entity_schema?.fields ?? []}
          entityType={def.entity_type}
          outgoingTransitions={outgoing}
          onChange={handleActionsChange}
        />
      </div>

      <div className="space-y-2">
        <div className="text-xs font-semibold text-foreground">Connections</div>
        <div className="rounded-md border border-border">
          <div className="border-b border-border bg-muted/40 px-3 py-1.5 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            Incoming ({incoming.length})
          </div>
          {incoming.length === 0 ? (
            <div className="px-3 py-2 text-xs text-muted-foreground">No incoming transitions.</div>
          ) : (
            <ul className="divide-y divide-border">
              {incoming.map((t) => (
                <li key={t.key}>
                  <Button variant="ghost"
                    className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-xs hover:bg-muted/40"
                    onClick={() => onSelectTransition(t.key)}
                  >
                    <span className="font-mono">{t.from}</span>
                    <ArrowRight className="h-3 w-3 text-muted-foreground" />
                    <span className="ml-auto truncate text-muted-foreground">
                      {t.label || t.key}
                    </span>
                  </Button>
                </li>
              ))}
            </ul>
          )}
          <div className="border-y border-border bg-muted/40 px-3 py-1.5 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            Outgoing ({outgoing.length})
          </div>
          {outgoing.length === 0 ? (
            <div className="px-3 py-2 text-xs text-muted-foreground">No outgoing transitions.</div>
          ) : (
            <ul className="divide-y divide-border">
              {outgoing.map((t) => (
                <li key={t.key}>
                  <Button variant="ghost"
                    className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-xs hover:bg-muted/40"
                    onClick={() => onSelectTransition(t.key)}
                  >
                    <ArrowRight className="h-3 w-3 text-muted-foreground" />
                    <span className="font-mono">{t.to_state}</span>
                    <span className="ml-auto truncate text-muted-foreground">
                      {t.label || t.key}
                    </span>
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className="border-t border-border pt-3">
        <Button variant="ghost" size="sm" className="text-destructive" onClick={remove}>
          <Trash2 className="mr-1.5 h-3.5 w-3.5" />
          Delete state
        </Button>
      </div>
    </div>
  );
}
