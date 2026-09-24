import { useEffect, useState } from 'react';
import { ArrowRight, Plus, Trash2, AlertCircle } from 'lucide-react';
import type { StateNode, Transition } from '@/lib/state-machine/types';
import { Button } from '@/components/ui/button';

interface TransitionsStepProps {
  states: StateNode[];
  transitions: Transition[];
  onChange: (transitions: Transition[]) => void;
}

function isTerminal(state: StateNode): boolean {
  return Array.isArray(state.tags) && state.tags.includes('terminal');
}

function buildKey(from: string, to: string, used: Set<string>): string {
  const base = `${from}__to__${to}`.toLowerCase();
  if (!used.has(base)) return base;
  let n = 2;
  while (used.has(`${base}_${n}`)) n += 1;
  return `${base}_${n}`;
}

function defaultTrigger(to: string, usedTriggersFromSource: Set<string>): string {
  const base = `to_${to.toLowerCase().replace(/_/g, '')}`;
  if (!usedTriggersFromSource.has(base)) return base;
  let n = 2;
  while (usedTriggersFromSource.has(`${base}_${n}`)) n += 1;
  return `${base}_${n}`;
}

function newTransition(from: string, to: string, allTransitions: Transition[]): Transition {
  const usedKeys = new Set(allTransitions.map((t) => t.key));
  const usedTriggersFromSource = new Set(
    allTransitions.filter((t) => t.from === from).map((t) => t.trigger),
  );
  return {
    key: buildKey(from, to, usedKeys),
    trigger: defaultTrigger(to, usedTriggersFromSource),
    label: `Move to ${to}`,
    from,
    to_state: to,
    required_fields: [],
    guards: [],
    pre_transition_tasks: [],
    post_transition_tasks: [],
    auto_transition: null,
    description: '',
  };
}

export default function TransitionsStep({ states, transitions, onChange }: TransitionsStepProps) {
  const sourceStates = states.filter((s) => s.name && !isTerminal(s));
  const [selectedFrom, setSelectedFrom] = useState<string | null>(sourceStates[0]?.name ?? null);

  // Keep selection valid when states change.
  useEffect(() => {
    if (!selectedFrom || !sourceStates.find((s) => s.name === selectedFrom)) {
      setSelectedFrom(sourceStates[0]?.name ?? null);
    }
  }, [selectedFrom, sourceStates]);

  if (states.length === 0) {
    return (
      <div className="text-center py-12">
        <AlertCircle className="w-12 h-12 text-muted-foreground/60 mx-auto mb-4" />
        <p className="text-muted-foreground">Add states first before configuring transitions.</p>
      </div>
    );
  }

  const transitionsFromSelected = transitions.filter((t) => t.from === selectedFrom);
  const targetStates = states.filter((s) => s.name && s.name !== selectedFrom);
  const targetsAlreadyUsed = new Set(transitionsFromSelected.map((t) => t.to_state));

  const addTransition = (to: string) => {
    if (!selectedFrom || targetsAlreadyUsed.has(to)) return;
    onChange([...transitions, newTransition(selectedFrom, to, transitions)]);
  };

  const updateTransition = (key: string, updates: Partial<Transition>) => {
    onChange(transitions.map((t) => (t.key === key ? { ...t, ...updates } : t)));
  };

  const removeTransition = (key: string) => {
    onChange(transitions.filter((t) => t.key !== key));
  };

  const stateLabel = (name: string) => {
    const s = states.find((x) => x.name === name);
    return s?.description?.trim() ? `${name} — ${s.description}` : name;
  };

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-medium text-foreground mb-1">Transitions</h3>
        <p className="text-sm text-muted-foreground">
          Define how the entity moves between states. Each transition has a trigger event name, a label, optional SLA, and optional description.
        </p>
      </div>

      <div className="flex gap-6">
        <div className="w-56 shrink-0">
          <label className="block text-xs font-medium text-muted-foreground mb-2">From State</label>
          <div className="space-y-1">
            {sourceStates.length === 0 ? (
              <p className="text-sm text-muted-foreground italic">No non-terminal states</p>
            ) : (
              sourceStates.map((state) => {
                const isSelected = state.name === selectedFrom;
                const outgoing = transitions.filter((t) => t.from === state.name).length;
                return (
                  <Button variant="primary"
                    key={state.name}
                    onClick={() => setSelectedFrom(state.name)}
                    className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-left transition-colors ${
                      isSelected
                        ? 'bg-cobalt text-white'
                        : 'bg-muted/50 text-foreground hover:bg-muted'
                    }`}
                  >
                    <span className="flex-1 truncate font-mono text-xs">{state.name}</span>
                    <span className={`text-xs ${isSelected ? 'text-white/70' : 'text-muted-foreground'}`}>
                      {outgoing}
                    </span>
                  </Button>
                );
              })
            )}
          </div>
        </div>

        <div className="flex-1 space-y-4">
          {selectedFrom ? (
            <>
              <div className="flex items-center gap-2 text-sm">
                <span className="font-medium font-mono">{selectedFrom}</span>
                <ArrowRight className="w-4 h-4 text-muted-foreground" />
                <span className="text-muted-foreground">moves to...</span>
              </div>

              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-2">
                  Add transition to...
                </label>
                <div className="flex flex-wrap gap-2">
                  {targetStates.map((target) => {
                    const taken = targetsAlreadyUsed.has(target.name);
                    return (
                      <Button variant="primary"
                        key={target.name}
                        onClick={() => !taken && addTransition(target.name)}
                        disabled={taken}
                        className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm transition-colors font-mono ${
                          taken
                            ? 'bg-muted text-muted-foreground cursor-not-allowed'
                            : 'bg-muted/50 text-foreground hover:bg-cobalt/10 hover:text-cobalt border border-border'
                        }`}
                      >
                        <Plus className="w-3 h-3" />
                        {target.name}
                      </Button>
                    );
                  })}
                </div>
              </div>

              {transitionsFromSelected.length > 0 && (
                <div className="space-y-3">
                  {transitionsFromSelected.map((t) => (
                    <div key={t.key} className="bg-card border border-border rounded-lg p-3 space-y-3">
                      <div className="flex items-center gap-3">
                        <span className="text-xs text-muted-foreground font-mono whitespace-nowrap">
                          → {stateLabel(t.to_state)}
                        </span>
                        <Button
                          variant="ghost-danger"
                          size="icon-sm"
                          onClick={() => removeTransition(t.key)}
                          className="ml-auto"
                        >
                          <Trash2 className="w-4 h-4" />
                        </Button>
                      </div>

                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="block text-xs font-medium text-muted-foreground mb-1">
                            Trigger Event
                          </label>
                          <input
                            type="text"
                            value={t.trigger}
                            onChange={(e) =>
                              updateTransition(t.key, {
                                trigger: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ''),
                              })
                            }
                            placeholder="trigger_name"
                            className="w-full px-2 py-1.5 text-sm font-mono border border-border rounded focus:outline-none focus:border-cobalt"
                          />
                        </div>
                        <div>
                          <label className="block text-xs font-medium text-muted-foreground mb-1">
                            Label
                          </label>
                          <input
                            type="text"
                            value={t.label}
                            onChange={(e) => updateTransition(t.key, { label: e.target.value })}
                            placeholder="Button label"
                            className="w-full px-2 py-1.5 text-sm border border-border rounded focus:outline-none focus:border-cobalt"
                          />
                        </div>
                      </div>

                      <div>
                        <label className="block text-xs font-medium text-muted-foreground mb-1">
                          Description
                        </label>
                        <input
                          type="text"
                          value={t.description}
                          onChange={(e) => updateTransition(t.key, { description: e.target.value })}
                          placeholder="Optional"
                          className="w-full px-2 py-1.5 text-sm border border-border rounded focus:outline-none focus:border-cobalt"
                        />
                      </div>

                      {t.guards.length > 0 && (
                        <div className="text-xs text-warning bg-warning-subtle px-2 py-1 rounded inline-block">
                          {t.guards.length} guard{t.guards.length === 1 ? '' : 's'} attached
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {transitionsFromSelected.length === 0 && (
                <p className="text-sm text-warning bg-warning-subtle px-4 py-3 rounded-lg">
                  This state has no outgoing transitions yet.
                </p>
              )}
            </>
          ) : (
            <div className="flex items-center justify-center h-48 bg-muted/50 rounded-lg">
              <p className="text-muted-foreground">Select a state to configure its transitions</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
