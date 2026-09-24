import { useState } from 'react';
import { Plus, Trash2, Shield, AlertCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  GUARD_LIBRARY,
  type Guard,
  type GuardType,
  type Transition,
} from '@/lib/state-machine/types';

interface GuardsStepProps {
  transitions: Transition[];
  /** Per-state field lists, keyed by state name — each transition's guards
   *  are scoped to its `from` state's own attached Method Block(s), not
   *  every field in the workflow. See useMethodFieldsByState. */
  fieldsByState: Record<string, { field: string; type: string }[]>;
  onChange: (transitions: Transition[]) => void;
}

function newGuard(type: GuardType): Guard {
  return {
    type,
    field: '',
    value: '',
    message: '',
    config: {},
  };
}

const NUMERIC_FIELD_TYPES = new Set(['int', 'integer', 'float', 'number']);
const NUMERIC_GUARD_TYPES = new Set(['numerical_value_gte', 'numerical_value_lte', 'numerical_value_in_set']);

function needsField(type: string): boolean {
  return (
    type === 'field_present' ||
    type === 'field_exact_match' ||
    type === 'numerical_value_gte' ||
    type === 'numerical_value_lte' ||
    type === 'numerical_value_in_set'
  );
}

function getCompatibleFields(guardType: string, fields: { field: string; type: string }[]) {
  if (NUMERIC_GUARD_TYPES.has(guardType)) {
    return fields.filter((f) => NUMERIC_FIELD_TYPES.has(f.type));
  }
  return fields;
}

function needsValue(type: string): boolean {
  return type === 'field_exact_match' || type === 'numerical_value_gte' || type === 'numerical_value_lte';
}

function isNumericValueInSet(type: string): boolean {
  return type === 'numerical_value_in_set';
}

function isCompareDates(type: string): boolean {
  return type === 'compare_dates';
}

export default function GuardsStep({ transitions, fieldsByState, onChange }: GuardsStepProps) {
  const [selectedKey, setSelectedKey] = useState<string | null>(transitions[0]?.key ?? null);

  if (transitions.length === 0) {
    return (
      <div className="text-center py-12">
        <AlertCircle className="w-12 h-12 text-muted-foreground/60 mx-auto mb-4" />
        <p className="text-muted-foreground">Configure transitions first before adding guards.</p>
      </div>
    );
  }

  const effectiveSelectedKey =
    selectedKey && transitions.some((t) => t.key === selectedKey)
      ? selectedKey
      : transitions[0]?.key ?? null;
  const selected = transitions.find((t) => t.key === effectiveSelectedKey) ?? null;
  // Guards on a transition check the record as it stands in the state it's
  // leaving — so the picker is scoped to the `from` state's own attached
  // Method Block(s), not the `to_state`'s.
  const fields = selected ? fieldsByState[selected.from] ?? [] : [];

  const updateGuards = (transitionKey: string, guards: Guard[]) => {
    onChange(transitions.map((t) => (t.key === transitionKey ? { ...t, guards } : t)));
  };

  const addGuard = (type: GuardType) => {
    if (!selected) return;
    updateGuards(selected.key, [...selected.guards, newGuard(type)]);
  };

  const updateGuardAt = (index: number, updates: Partial<Guard>) => {
    if (!selected) return;
    const next = selected.guards.map((g, i) => (i === index ? { ...g, ...updates } : g));
    updateGuards(selected.key, next);
  };

  const removeGuardAt = (index: number) => {
    if (!selected) return;
    updateGuards(selected.key, selected.guards.filter((_, i) => i !== index));
  };

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-medium text-foreground mb-1">Guards</h3>
        <p className="text-sm text-muted-foreground">
          Conditions that must be met before a transition can fire.
        </p>
      </div>

      {/* Transition selector — wrapping tabs */}
      <div>
        <label className="block text-xs font-medium text-muted-foreground mb-2">Select Transition</label>
        <div className="flex flex-wrap gap-2 pb-1">
          {transitions.map((t) => {
            const isSelected = t.key === effectiveSelectedKey;
            return (
              <button
                key={t.key}
                onClick={() => setSelectedKey(t.key)}
                className={`flex-shrink-0 max-w-full min-w-0 flex items-center gap-2 px-3 py-2 rounded-lg border text-sm transition-colors ${
                  isSelected
                    ? 'bg-cobalt border-cobalt text-white'
                    : 'bg-muted/50 border-border text-foreground hover:bg-muted'
                }`}
              >
                <span className="font-mono text-xs truncate min-w-0">
                  {t.from} → {t.to_state}
                </span>
                {t.guards.length > 0 && (
                  <span
                    className={`inline-flex flex-shrink-0 items-center justify-center w-4 h-4 rounded-full text-[10px] font-semibold ${
                      isSelected ? 'bg-card/20 text-white' : 'bg-cobalt/10 text-cobalt'
                    }`}
                  >
                    {t.guards.length}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      <div>
          {selected ? (
            <div className="space-y-4">
              <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                <Shield className="w-4 h-4 text-muted-foreground" />
                Guards on "{selected.label}"
              </div>

              {selected.guards.length > 0 && (
                <div className="space-y-3">
                  {selected.guards.map((guard, index) => {
                    const meta = GUARD_LIBRARY.find((g) => g.type === guard.type);

                    return (
                      <div
                        key={`${selected.key}-guard-${index}`}
                        className="p-4 bg-card border border-border rounded-lg space-y-3"
                      >
                        <div className="flex items-center justify-between">
                          <div>
                            <span className="font-medium text-foreground">
                              {meta?.label ?? guard.type}
                            </span>
                            <p className="text-xs text-muted-foreground mt-0.5">{meta?.description}</p>
                          </div>
                          <Button
                            variant="ghost-danger"
                            size="icon-sm"
                            onClick={() => removeGuardAt(index)}
                          >
                            <Trash2 className="w-4 h-4" />
                          </Button>
                        </div>

                        <div className="grid grid-cols-2 gap-3">
                          {needsField(guard.type) && (
                            <div>
                              <label className="block text-xs font-medium text-muted-foreground mb-1">
                                Field <span className="text-destructive">*</span>
                              </label>
                              {(() => {
                                const compatibleFields = getCompatibleFields(guard.type, fields);
                                if (compatibleFields.length === 0) {
                                  return (
                                    <p className="text-xs text-warning py-1.5">
                                      {NUMERIC_GUARD_TYPES.has(guard.type)
                                        ? 'No numeric fields defined. Add an int or float field in the Basics step first.'
                                        : 'No fields defined. Add fields in the Basics step first.'}
                                    </p>
                                  );
                                }
                                return (
                                  <select
                                    value={guard.field}
                                    onChange={(e) => updateGuardAt(index, { field: e.target.value })}
                                    className="w-full px-2 py-1.5 text-sm border border-border rounded focus:outline-none focus:border-cobalt bg-card"
                                  >
                                    <option value="">Select a field</option>
                                    {compatibleFields.map((f) => (
                                      <option key={f.field} value={f.field}>{f.field}</option>
                                    ))}
                                  </select>
                                );
                              })()}
                            </div>
                          )}

                          {needsValue(guard.type) && (
                            <div>
                              <label className="block text-xs font-medium text-muted-foreground mb-1">
                                Value
                              </label>
                              <input
                                type={guard.type.startsWith('numerical_') ? 'number' : 'text'}
                                value={String(guard.value ?? '')}
                                onChange={(e) =>
                                  updateGuardAt(index, {
                                    value: guard.type.startsWith('numerical_')
                                      ? (e.target.value === '' ? null : Number(e.target.value))
                                      : e.target.value,
                                  })
                                }
                                className="w-full px-2 py-1.5 text-sm border border-border rounded focus:outline-none focus:border-cobalt"
                              />
                            </div>
                          )}

                          {isNumericValueInSet(guard.type) && (
                            <div className="col-span-2">
                              <label className="block text-xs font-medium text-muted-foreground mb-1">
                                Allowed values (comma-separated numbers)
                              </label>
                              <input
                                type="text"
                                defaultValue={Array.isArray(guard.value) ? (guard.value as number[]).join(', ') : ''}
                                onBlur={(e) => {
                                  const parsed = e.target.value
                                    .split(',')
                                    .map((s) => s.trim())
                                    .filter((s) => s !== '')
                                    .map(Number)
                                    .filter((n) => !Number.isNaN(n));
                                  updateGuardAt(index, { value: parsed });
                                }}
                                placeholder="e.g. 1, 2, 3"
                                className="w-full px-2 py-1.5 text-sm border border-border rounded focus:outline-none focus:border-cobalt"
                              />
                            </div>
                          )}

                          {isCompareDates(guard.type) && (
                            <>
                              <div>
                                <label className="block text-xs font-medium text-muted-foreground mb-1">
                                  Left field
                                </label>
                                {fields.filter((f) => f.type === 'datetime').length === 0 ? (
                                  <p className="text-xs text-warning py-1.5">No datetime fields defined.</p>
                                ) : (
                                  <select
                                    value={String(guard.config?.left ?? '')}
                                    onChange={(e) =>
                                      updateGuardAt(index, {
                                        config: { ...guard.config, left: e.target.value },
                                      })
                                    }
                                    className="w-full px-2 py-1.5 text-sm border border-border rounded focus:outline-none focus:border-cobalt bg-card"
                                  >
                                    <option value="">Select a field</option>
                                    {fields.filter((f) => f.type === 'datetime').map((f) => (
                                      <option key={f.field} value={f.field}>{f.field}</option>
                                    ))}
                                  </select>
                                )}
                              </div>
                              <div>
                                <label className="block text-xs font-medium text-muted-foreground mb-1">
                                  Right field
                                </label>
                                {fields.filter((f) => f.type === 'datetime').length === 0 ? (
                                  <p className="text-xs text-warning py-1.5">No datetime fields defined.</p>
                                ) : (
                                  <select
                                    value={String(guard.config?.right ?? '')}
                                    onChange={(e) =>
                                      updateGuardAt(index, {
                                        config: { ...guard.config, right: e.target.value },
                                      })
                                    }
                                    className="w-full px-2 py-1.5 text-sm border border-border rounded focus:outline-none focus:border-cobalt bg-card"
                                  >
                                    <option value="">Select a field</option>
                                    {fields.filter((f) => f.type === 'datetime').map((f) => (
                                      <option key={f.field} value={f.field}>{f.field}</option>
                                    ))}
                                  </select>
                                )}
                              </div>
                              <div>
                                <label className="block text-xs font-medium text-muted-foreground mb-1">
                                  Operator
                                </label>
                                <select
                                  value={String(guard.config?.op ?? 'lt')}
                                  onChange={(e) =>
                                    updateGuardAt(index, {
                                      config: { ...guard.config, op: e.target.value },
                                    })
                                  }
                                  className="w-full px-2 py-1.5 text-sm border border-border rounded focus:outline-none focus:border-cobalt"
                                >
                                  <option value="lt">left &lt; right</option>
                                  <option value="lte">left ≤ right</option>
                                  <option value="eq">left = right</option>
                                  <option value="gte">left ≥ right</option>
                                  <option value="gt">left &gt; right</option>
                                </select>
                              </div>
                            </>
                          )}
                        </div>

                        <div>
                          <label className="block text-xs font-medium text-muted-foreground mb-1">
                            Message (shown when guard fails)
                          </label>
                          <input
                            type="text"
                            value={guard.message}
                            onChange={(e) => updateGuardAt(index, { message: e.target.value })}
                            placeholder="e.g. Phone number must be provided"
                            className="w-full px-2 py-1.5 text-sm border border-border rounded focus:outline-none focus:border-cobalt"
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-2">Add Guard</label>
                <div className="flex flex-wrap gap-2">
                  {GUARD_LIBRARY.filter((g) => g.type !== 'custom').map((g) => (
                    <Button variant="primary"
                      key={g.type}
                      onClick={() => addGuard(g.type)}
                      className="flex items-center gap-2 px-3 py-1.5 bg-muted/50 text-foreground rounded-lg text-sm hover:bg-cobalt/10 hover:text-cobalt border border-border transition-colors"
                    >
                      <Plus className="w-3 h-3" />
                      {g.label}
                    </Button>
                  ))}
                </div>
              </div>

              {selected.guards.length === 0 && (
                <p className="text-sm text-muted-foreground italic">
                  No guards. This transition can always fire.
                </p>
              )}
            </div>
          ) : (
            <div className="flex items-center justify-center h-48 bg-muted/50 rounded-lg">
              <p className="text-muted-foreground">Select a transition to configure guards</p>
            </div>
          )}
        </div>
    </div>
  );
}
