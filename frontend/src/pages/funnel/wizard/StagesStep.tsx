import { useState } from 'react';
import {
  Plus,
  Trash2,
  ChevronDown,
  ChevronUp,
  Play,
  Square,
  Zap,
  Clock,
} from 'lucide-react';

import { type SlaUnit, buildSlaSeconds, slaToAmount, slaToUnit } from '@/shared/utils/sla';

function SlaInput({ value, onChange }: { value: number | null; onChange: (v: number | null) => void }) {
  const [unit, setUnit] = useState<SlaUnit>(slaToUnit(value));
  const [amount, setAmount] = useState(slaToAmount(value));

  const handleUnit = (u: SlaUnit) => {
    setUnit(u);
    onChange(buildSlaSeconds(amount, u));
  };

  const handleAmount = (v: string) => {
    setAmount(v);
    onChange(buildSlaSeconds(v, unit));
  };

  return (
    <div className="flex items-center gap-2">
      <select
        value={unit}
        onChange={(e) => handleUnit(e.target.value as SlaUnit)}
        className="h-8 rounded border border-border bg-card px-2 text-sm focus:outline-none focus:border-cobalt"
      >
        <option value="none">No deadline</option>
        <option value="minutes">Minutes</option>
        <option value="hours">Hours</option>
        <option value="days">Days</option>
      </select>
      {unit !== 'none' && (
        <input
          type="number"
          min={1}
          value={amount}
          onChange={(e) => handleAmount(e.target.value)}
          placeholder="1"
          className="w-20 px-2 py-1.5 text-sm border border-border rounded focus:outline-none focus:border-cobalt"
        />
      )}
    </div>
  );
}

import type { EntityField, MethodRef, StateAction, StateNode, Transition } from '@/lib/state-machine/types';
import { Button } from '@/components/ui/button';
import { StateActionsSection } from '../canvas/StateActionsSection';
import { StateMethodsSection } from '../canvas/StateMethodsSection';

interface StagesStepProps {
  /** Per-state field lists, keyed by state name — each state's own attached
   *  Method Block(s), not the workflow's flat entity_schema.fields. See
   *  useMethodFieldsByState. */
  fieldsByState: Record<string, EntityField[]>;
  entityType: string;
  states: StateNode[];
  initialState: string;
  transitions: Transition[];
  onChange: (patch: { states?: StateNode[]; initial_state?: string }) => void;
}

function hasTag(state: StateNode, tag: string): boolean {
  return Array.isArray(state.tags) && state.tags.includes(tag);
}

function withTag(state: StateNode, tag: string, present: boolean): StateNode {
  const tags = Array.isArray(state.tags) ? state.tags.filter((t) => t !== tag) : [];
  if (present) tags.push(tag);
  return { ...state, tags };
}

function reindexOrder(states: StateNode[]): StateNode[] {
  return states.map((s, i) => ({ ...s, order: i + 1 }));
}

export default function StagesStep({
  fieldsByState,
  entityType,
  states,
  initialState,
  transitions,
  onChange,
}: StagesStepProps) {
  const updateStateAt = (index: number, updates: Partial<StateNode>) => {
    const next = states.map((s, i) => (i === index ? { ...s, ...updates } : s));
    onChange({ states: next });
  };

  const saveActionsAt = (index: number, actions: StateAction[]) => {
    updateStateAt(index, { on_state_actions: actions });
  };

  const saveMethodsAt = (index: number, methodRefs: MethodRef[]) => {
    updateStateAt(index, { method_refs: methodRefs });
  };

  const renameStateAt = (index: number, newName: string) => {
    const oldName = states[index]?.name;
    const next = states.map((s, i) => (i === index ? { ...s, name: newName } : s));
    const patch: { states: StateNode[]; initial_state?: string } = { states: next };
    if (initialState === oldName) patch.initial_state = newName;
    onChange(patch);
  };

  const addState = () => {
    const next = reindexOrder([
      ...states,
      { name: '', description: '', tags: [], order: states.length + 1, sla_seconds: null },
    ]);
    onChange({ states: next });
  };

  const removeStateAt = (index: number) => {
    if (states.length <= 1) return;
    const removed = states[index];
    const next = reindexOrder(states.filter((_, i) => i !== index));
    const patch: { states: StateNode[]; initial_state?: string } = { states: next };
    if (initialState === removed.name) {
      const fallback = next.find((s) => hasTag(s, 'initial')) ?? next[0];
      patch.initial_state = fallback?.name ?? '';
    }
    onChange(patch);
  };

  const moveStateAt = (index: number, direction: 'up' | 'down') => {
    const target = direction === 'up' ? index - 1 : index + 1;
    if (target < 0 || target >= states.length) return;
    const next = [...states];
    [next[index], next[target]] = [next[target], next[index]];
    onChange({ states: reindexOrder(next) });
  };

  const setInitialAt = (index: number) => {
    const target = states[index];
    if (!target?.name) return;
    const next = states.map((s, i) => {
      let updated = withTag(s, 'initial', i === index);
      // An initial state cannot also be terminal.
      if (i === index) updated = withTag(updated, 'terminal', false);
      return updated;
    });
    onChange({ states: next, initial_state: target.name });
  };

  const toggleTerminalAt = (index: number) => {
    const target = states[index];
    if (!target) return;
    if (hasTag(target, 'initial')) return;
    const next = states.map((s, i) =>
      i === index ? withTag(s, 'terminal', !hasTag(s, 'terminal')) : s,
    );
    onChange({ states: next });
  };

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-medium text-foreground mb-1">States</h3>
        <p className="text-sm text-muted-foreground">
          Define the states this workflow moves through. Pick exactly one initial state and at least one terminal state.
        </p>
      </div>

      <div className="space-y-2">
        {states.map((state, index) => {
          const isInitial = hasTag(state, 'initial');
          const isTerminal = hasTag(state, 'terminal');
          const outgoingTransitions = transitions.filter((transition) => transition.from === state.name);
          const stateFields = fieldsByState[state.name] ?? [];

          return (
            <div
              key={`state-row-${index}`}
              className="border border-border rounded-lg bg-card p-4 space-y-3"
            >
              <div className="flex items-start gap-3">
                <div className="flex flex-col gap-1 mt-1">
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    onClick={() => moveStateAt(index, 'up')}
                    disabled={index === 0}
                    className="text-muted-foreground hover:text-muted-foreground"
                  >
                    <ChevronUp className="w-4 h-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    onClick={() => moveStateAt(index, 'down')}
                    disabled={index === states.length - 1}
                    className="text-muted-foreground hover:text-muted-foreground"
                  >
                    <ChevronDown className="w-4 h-4" />
                  </Button>
                </div>

                <div className="flex-1 grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">
                      State Name <span className="text-destructive">*</span>
                    </label>
                    <input
                      type="text"
                      value={state.name}
                      onChange={(e) => renameStateAt(index, e.target.value)}
                      placeholder="e.g. Screening"
                      className="w-full px-3 py-2 text-sm font-mono border border-border rounded-lg focus:outline-none focus:border-cobalt focus:ring-1 focus:ring-cobalt"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">
                      Description
                    </label>
                    <input
                      type="text"
                      value={state.description}
                      onChange={(e) => updateStateAt(index, { description: e.target.value })}
                      placeholder="Optional human-readable description"
                      className="w-full px-3 py-2 text-sm border border-border rounded-lg focus:outline-none focus:border-cobalt focus:ring-1 focus:ring-cobalt"
                    />
                  </div>
                </div>

                <Button
                  variant="ghost-danger"
                  size="icon-sm"
                  onClick={() => removeStateAt(index)}
                  disabled={states.length <= 1}
                  className="mt-1"
                >
                  <Trash2 className="w-4 h-4" />
                </Button>
              </div>

              <div className="flex items-center gap-4 pl-7">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="radio"
                    name="initial-state"
                    checked={isInitial}
                    onChange={() => setInitialAt(index)}
                    className="w-4 h-4 text-cobalt focus:ring-cobalt"
                  />
                  <span className="flex items-center gap-1 text-sm text-foreground">
                    <Play className="w-3 h-3 text-success" />
                    Initial
                  </span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={isTerminal}
                    onChange={() => toggleTerminalAt(index)}
                    disabled={isInitial}
                    className="w-4 h-4 text-cobalt focus:ring-cobalt rounded disabled:opacity-50"
                  />
                  <span
                    className={`flex items-center gap-1 text-sm ${
                      isInitial ? 'text-muted-foreground' : 'text-foreground'
                    }`}
                  >
                    <Square className="w-3 h-3 text-muted-foreground text-destructive" />
                    Terminal
                  </span>
                </label>
              </div>

              <div className="pl-7">
                <label className="flex items-center gap-1 text-xs font-medium text-muted-foreground mb-1.5">
                  <Clock className="w-3 h-3" />
                  SLA Deadline
                </label>
                <SlaInput
                  value={state.sla_seconds ?? null}
                  onChange={(v) => updateStateAt(index, { sla_seconds: v })}
                />
              </div>

              <div className="pl-7">
                <StateMethodsSection
                  methodRefs={state.method_refs ?? []}
                  onChange={(refs) => saveMethodsAt(index, refs)}
                  entityType={entityType}
                />
                {stateFields.length > 0 && (
                  <div className="mt-2 flex flex-wrap items-center gap-1.5">
                    <span className="text-[11px] font-medium text-muted-foreground">Fields on this state:</span>
                    {stateFields.map((f) => (
                      <span
                        key={f.field}
                        className="rounded-full bg-muted px-2 py-0.5 font-mono text-[10px] text-muted-foreground"
                      >
                        {f.field} ({f.type})
                      </span>
                    ))}
                  </div>
                )}
              </div>

              <div className="space-y-3 pl-7">
                <div className="flex items-center gap-2 rounded-lg border border-border bg-muted/50 px-3 py-2 text-sm text-foreground">
                  <Zap className="w-4 h-4 text-cobalt" />
                  <div>
                    <div className="font-medium">Actions on entry</div>
                    <div className="text-xs text-muted-foreground">
                      Run actions automatically, in order, when the workflow enters this state.
                    </div>
                  </div>
                </div>

                <StateActionsSection
                  actions={state.on_state_actions ?? []}
                  entityFields={stateFields}
                  entityType={entityType}
                  outgoingTransitions={outgoingTransitions}
                  onChange={(actions) => saveActionsAt(index, actions)}
                />
              </div>
            </div>
          );
        })}
      </div>

      <Button
        onClick={addState}
        variant="outline"
        className="w-full flex items-center justify-center gap-2 px-4 py-3 border-2 border-dashed border-border rounded-lg text-muted-foreground hover:border-cobalt hover:text-cobalt transition-colors"
      >
        <Plus className="w-4 h-4" />
        Add State
      </Button>
    </div>
  );
}
