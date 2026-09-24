import { useState } from "react";

import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Separator } from "@/components/ui/separator";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Plus, Trash2, ArrowRight, Shield, ListChecks, ChevronDown, ChevronUp, Clock } from "lucide-react";

import {
  type Guard,
  type RequiredField,
  type StateMachineDocument,
  type Transition,
  type TransitionTask,
  type FieldType,
} from "@/lib/state-machine/types";
import { DDSelect } from "./DDSelect";
import { GuardForm, humanizeGuard } from "./GuardForm";
import { TaskList } from "./TaskList";

function emptyGuard(): Guard {
  return { type: "field_present", field: "", value: null, message: "", config: {} };
}

function emptyTask(): TransitionTask {
  return { task: "", label: "", order: 1, required: false, on_failure: "continue", config: {} };
}

interface TransitionsEditorProps {
  doc: StateMachineDocument;
  onChange: (next: StateMachineDocument) => void;
  selectedTransitionKey?: string | null;
  onSelectTransition?: (key: string) => void;
}

export function TransitionsEditor({
  doc,
  onChange,
  selectedTransitionKey,
  onSelectTransition,
}: TransitionsEditorProps) {
  const def = doc.definition;
  const stateOptions = def.states.map((s) => s.name);
  const fieldOptions = def.entity_schema.fields.map((f) => f.field);
  const [openKey, setOpenKey] = useState<string | undefined>(selectedTransitionKey ?? undefined);

  const updateTransitions = (next: Transition[]) =>
    onChange({ ...doc, definition: { ...def, transitions: next } });

  const addTransition = () => {
    const fromState = stateOptions[0] ?? "";
    const toState = stateOptions[1] ?? stateOptions[0] ?? "";
    const key = `transition_${def.transitions.length + 1}`;
    const t: Transition = {
      key,
      trigger: key,
      label: "New transition",
      from: fromState,
      to_state: toState,
      required_fields: [],
      guards: [],
      pre_transition_tasks: [],
      post_transition_tasks: [],
      auto_transition: { enabled: false, delay_seconds: 0 },
      description: "",
    };
    updateTransitions([...def.transitions, t]);
    setOpenKey(key);
    onSelectTransition?.(key);
  };

  const update = (idx: number, patch: Partial<Transition>) => {
    updateTransitions(def.transitions.map((t, i) => (i === idx ? { ...t, ...patch } : t)));
  };

  const remove = (idx: number) =>
    updateTransitions(def.transitions.filter((_, i) => i !== idx));

  return (
    <Card className="p-5">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h3 className="text-sm font-semibold text-foreground">Transitions</h3>
          <p className="mt-1 text-xs text-muted-foreground">
            How and when an entity moves from one state to another.
          </p>
        </div>
        <Button
          size="sm"
          variant="outline"
          onClick={addTransition}
          disabled={stateOptions.length < 1}
        >
          <Plus className="mr-1.5 h-3.5 w-3.5" />
          Add transition
        </Button>
      </div>

      {def.transitions.length === 0 ? (
        <div className="rounded-md border border-dashed border-border p-6 text-center text-xs text-muted-foreground">
          No transitions yet. Add at least one to connect your states.
        </div>
      ) : (
        <Accordion
          type="single"
          collapsible
          value={openKey}
          onValueChange={(v) => {
            setOpenKey(v);
            if (v) onSelectTransition?.(v);
          }}
          className="space-y-2"
        >
          {def.transitions.map((t, idx) => (
            <AccordionItem
              key={t.key}
              value={t.key}
              className={`rounded-md border ${
                selectedTransitionKey === t.key ? "border-foreground" : "border-border"
              } bg-muted/30 px-3`}
            >
              <AccordionTrigger className="py-3 hover:no-underline">
                <div className="flex flex-1 items-center justify-between gap-3 pr-3">
                  <div className="flex items-center gap-2 text-left">
                    <span className="font-mono text-xs font-medium">{t.from || "?"}</span>
                    <ArrowRight className="h-3.5 w-3.5 text-muted-foreground" />
                    <span className="font-mono text-xs font-medium">{t.to_state || "?"}</span>
                    <span className="ml-2 text-xs text-muted-foreground">{t.label}</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    {t.guards.length > 0 && (
                      <Badge variant="secondary" className="gap-1 text-[10px]">
                        <Shield className="h-3 w-3" /> {t.guards.length}
                      </Badge>
                    )}
                    {t.pre_transition_tasks.length + t.post_transition_tasks.length > 0 && (
                      <Badge variant="secondary" className="gap-1 text-[10px]">
                        <ListChecks className="h-3 w-3" />{" "}
                        {t.pre_transition_tasks.length + t.post_transition_tasks.length}
                      </Badge>
                    )}
                  </div>
                </div>
              </AccordionTrigger>
              <AccordionContent className="pb-4">
                <TransitionEditor
                  transition={t}
                  stateOptions={stateOptions}
                  fieldOptions={fieldOptions}
                  fieldsMeta={def.entity_schema.fields}
                  onChange={(patch) => update(idx, patch)}
                  onRemove={() => remove(idx)}
                />
              </AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      )}
    </Card>
  );
}


function IdentitySection({
  label,
  description,
  onChange,
}: {
  label: string;
  description: string;
  onChange: (patch: Partial<Transition>) => void;
}) {
  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <Label className="font-semibold">Step name</Label>
        <p className="text-xs text-muted-foreground">Shown to users as the action label</p>
        <Input value={label} onChange={(e) => onChange({ label: e.target.value })} placeholder="e.g. Send to review" className="text-sm" />
      </div>
      <div className="space-y-1.5">
        <Label className="font-semibold">Description</Label>
        <p className="text-xs text-muted-foreground">What happens when this step runs</p>
        <Textarea rows={2} value={description} onChange={(e) => onChange({ description: e.target.value })} placeholder="e.g. Moves the application into review so a recruiter can assess it" />
      </div>
    </div>
  );
}

function FlowSection({
  from,
  toState,
  stateOptions,
  onChange,
}: {
  from: string;
  toState: string;
  stateOptions: string[];
  onChange: (patch: Partial<Transition>) => void;
}) {
  const options = stateOptions.map((s) => ({ value: s, label: s }));
  return (
    <div className="space-y-3">
      <div>
        <p className="text-sm font-semibold">Flow</p>
        <p className="text-xs text-muted-foreground">Which state this step moves from and to</p>
      </div>
      <div className="flex items-end gap-3">
        <div className="min-w-0 flex-1 space-y-1">
          <Label className="text-xs text-muted-foreground">From</Label>
          <DDSelect value={from} options={options} onSelect={(v) => onChange({ from: v })} />
        </div>
        <div className="mb-2 flex h-9 shrink-0 items-center">
          <ArrowRight className="h-4 w-4 text-muted-foreground" />
        </div>
        <div className="min-w-0 flex-1 space-y-1">
          <Label className="text-xs text-muted-foreground">To</Label>
          <DDSelect value={toState} options={options} onSelect={(v) => onChange({ to_state: v })} />
        </div>
      </div>
    </div>
  );
}

function AutoTransitionSection({
  autoTransition,
  onChange,
}: {
  autoTransition: Transition["auto_transition"];
  onChange: (patch: Partial<Transition>) => void;
}) {
  return (
    <div className="rounded-lg border border-border bg-muted/30 p-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Clock className="h-4 w-4 text-muted-foreground" />
            <p className="text-sm font-semibold">Auto-advance</p>
          </div>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Automatically move to the next state after a set time — no manual action needed
          </p>
        </div>
        <Switch
          checked={!!autoTransition?.enabled}
          onCheckedChange={(v) =>
            onChange({ auto_transition: { enabled: v, delay_seconds: autoTransition?.delay_seconds ?? 0 } })
          }
        />
      </div>
      {autoTransition?.enabled && (
        <div className="mt-4 space-y-1.5">
          <Label className="text-xs font-semibold">Wait before advancing</Label>
          <Input
            type="number"
            min={0}
            className="w-32"
            placeholder="seconds"
            value={autoTransition.delay_seconds || ""}
            onChange={(e) => onChange({ auto_transition: { enabled: true, delay_seconds: Number(e.target.value) || 0 } })}
          />
        </div>
      )}
    </div>
  );
}

function RequiredFieldsSection({
  requiredFields,
  fieldOptions,
  fieldsMeta,
  onChange,
}: {
  requiredFields: RequiredField[];
  fieldOptions: string[];
  fieldsMeta: { field: string; type: FieldType }[];
  onChange: (next: RequiredField[]) => void;
}) {
  const fieldType = (name: string) => fieldsMeta.find((f) => f.field === name)?.type ?? "string";
  return (
    <Section
      title="Required information"
      hint="These fields must be filled in before this step can run."
      onAdd={() => onChange([...requiredFields, { field: fieldOptions[0] ?? "", required: true, type: fieldType(fieldOptions[0] ?? "") }])}
      addLabel="Add field"
      addDisabled={fieldOptions.length === 0}
    >
      {requiredFields.length === 0 ? (
        <EmptyHint>No requirements — this step can run any time.</EmptyHint>
      ) : (
        <div className="space-y-2">
          {requiredFields.map((rf, i) => (
            <div key={i} className="flex items-center gap-2">
              <div className="flex-1">
                <DDSelect
                  value={rf.field}
                  placeholder="Select a field"
                  options={fieldOptions.map((f) => ({ value: f, label: f }))}
                  onSelect={(v) => onChange(requiredFields.map((x, j) => j === i ? { ...x, field: v, type: fieldType(v) } : x))}
                />
              </div>
              <span className="w-20 truncate text-xs text-muted-foreground">{rf.type}</span>
              <Button variant="ghost" size="icon" onClick={() => onChange(requiredFields.filter((_, j) => j !== i))}>
                <Trash2 className="h-4 w-4 text-muted-foreground" />
              </Button>
            </div>
          ))}
        </div>
      )}
    </Section>
  );
}

function GuardsSection({
  guards,
  fieldsMeta,
  onChange,
}: {
  guards: Guard[];
  fieldsMeta: { field: string; type: FieldType }[];
  onChange: (next: Guard[]) => void;
}) {
  return (
    <Section
      title="Blockers"
      hint="Rules that must pass — if any fail, the step is blocked."
      onAdd={() => onChange([...guards, emptyGuard()])}
      addLabel="Add blocker"
    >
      {guards.length === 0 ? (
        <EmptyHint>No blockers — anyone can trigger this step.</EmptyHint>
      ) : (
        <div className="space-y-3">
          {guards.map((g, i) => (
            <div key={i} className="rounded-md border border-border bg-background p-3">
              <div className="mb-2 flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <Shield className="h-3.5 w-3.5 text-muted-foreground" />
                  <span className="text-xs font-medium">{humanizeGuard(g)}</span>
                </div>
                <Button variant="ghost" size="icon" onClick={() => onChange(guards.filter((_, j) => j !== i))}>
                  <Trash2 className="h-4 w-4 text-muted-foreground" />
                </Button>
              </div>
              <GuardForm
                guard={g}
                fieldsMeta={fieldsMeta}
                onChange={(patch) => onChange(guards.map((x, j) => j === i ? { ...x, ...patch } : x))}
              />
            </div>
          ))}
        </div>
      )}
    </Section>
  );
}

function AdvancedSection({
  keyValue,
  trigger,
  onChange,
}: {
  keyValue: string;
  trigger: string;
  onChange: (patch: Partial<Transition>) => void;
}) {
  const [show, setShow] = useState(false);
  return (
    <div>
      <Button
        variant="primary"
        type="button"
        onClick={() => setShow((v) => !v)}
        className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
      >
        {show ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
        Advanced settings
      </Button>
      {show && (
        <div className="mt-3 grid grid-cols-2 gap-3 rounded-md border border-dashed border-border p-3">
          <div className="space-y-1">
            <Label className="text-xs">Internal key</Label>
            <p className="text-[11px] text-muted-foreground">Used by the system to identify this transition</p>
            <Input value={keyValue} onChange={(e) => onChange({ key: e.target.value })} className="font-mono text-xs" />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Trigger Event</Label>
            <p className="text-[11px] text-muted-foreground">The event that fires this step via API</p>
            <Input value={trigger} onChange={(e) => onChange({ trigger: e.target.value })} className="font-mono text-xs" placeholder="start_screening" />
          </div>
        </div>
      )}
    </div>
  );
}

export function TransitionEditor({
  transition: t,
  stateOptions,
  fieldOptions,
  fieldsMeta,
  onChange,
  onRemove,
}: {
  transition: Transition;
  stateOptions: string[];
  fieldOptions: string[];
  fieldsMeta: { field: string; type: FieldType }[];
  onChange: (patch: Partial<Transition>) => void;
  onRemove: () => void;
}) {
  return (
    <div className="space-y-6 pt-1">
      <IdentitySection label={t.label} description={t.description} onChange={onChange} />
      <Separator />
      <FlowSection from={t.from} toState={t.to_state} stateOptions={stateOptions} onChange={onChange} />
      <Separator />
      <AutoTransitionSection autoTransition={t.auto_transition} onChange={onChange} />
      <Separator />
      <RequiredFieldsSection
        requiredFields={t.required_fields}
        fieldOptions={fieldOptions}
        fieldsMeta={fieldsMeta}
        onChange={(next) => onChange({ required_fields: next })}
      />
      <Separator />
      <GuardsSection
        guards={t.guards}
        fieldsMeta={fieldsMeta}
        onChange={(next) => onChange({ guards: next })}
      />
      <Separator />
      <Section
        title="Before actions"
        hint="Run these tasks before the state changes. A failing required task blocks the step."
        onAdd={() => onChange({ pre_transition_tasks: [...t.pre_transition_tasks, { ...emptyTask(), order: t.pre_transition_tasks.length + 1 }] })}
        addLabel="Add action"
      >
        <TaskList tasks={t.pre_transition_tasks} onChange={(next) => onChange({ pre_transition_tasks: next })} />
      </Section>
      <Section
        title="After actions"
        hint="Run these tasks after the state changes. Common uses: send notifications, log audit trail."
        onAdd={() => onChange({ post_transition_tasks: [...t.post_transition_tasks, { ...emptyTask(), order: t.post_transition_tasks.length + 1 }] })}
        addLabel="Add action"
      >
        <TaskList tasks={t.post_transition_tasks} onChange={(next) => onChange({ post_transition_tasks: next })} />
      </Section>
      <Separator />
      <AdvancedSection keyValue={t.key} trigger={t.trigger} onChange={onChange} />
      <Separator />
      <div className="flex justify-end pb-2">
        <Button variant="ghost" size="sm" onClick={onRemove} className="text-destructive hover:text-destructive">
          <Trash2 className="mr-1.5 h-3.5 w-3.5" />
          Delete this step
        </Button>
      </div>
    </div>
  );
}

function Section({
  title,
  hint,
  onAdd,
  addLabel,
  addDisabled,
  children,
}: {
  title: string;
  hint: string;
  onAdd: () => void;
  addLabel: string;
  addDisabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="mb-2 flex items-start justify-between gap-3">
        <div>
          <div className="text-xs font-semibold text-foreground">{title}</div>
          <p className="text-xs text-muted-foreground">{hint}</p>
        </div>
        <Button size="sm" variant="ghost" onClick={onAdd} disabled={addDisabled}>
          <Plus className="mr-1 h-3.5 w-3.5" />
          {addLabel}
        </Button>
      </div>
      {children}
    </div>
  );
}

function EmptyHint({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-md border border-dashed border-border p-3 text-center text-xs text-muted-foreground">
      {children}
    </div>
  );
}
