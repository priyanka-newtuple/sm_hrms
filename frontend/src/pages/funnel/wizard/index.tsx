import { useEffect, useMemo, useRef, useState } from 'react';
import {
  FileText,
  Layers,
  ArrowRightLeft,
  Shield,
  AlertCircle,
  CheckCircle,
} from 'lucide-react';
import BasicsStep from './BasicsStep';
import StagesStep from './StagesStep';
import TransitionsStep from './TransitionsStep';
import GuardsStep from './GuardsStep';
import ValidationPanel, { pathToStep, type WizardStep } from './ValidationPanel';
import { useMethodFieldsByState } from './useMethodFieldsByState';
import type {
  StateMachineDefinition,
  StateMachineDocument,
  ValidationIssue,
} from '@/lib/state-machine/types';
import { validateMachine } from '@/lib/state-machine/validate';
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
  pruneTransitionsForEntityFields,
} from '@/lib/state-machine/entitySchema';

interface FunnelBuilderProps {
  doc: StateMachineDocument;
  onChange: (next: StateMachineDocument) => void;
  isCreating: boolean;
  remoteIssues?: ValidationIssue[] | null;
}

interface StepConfig {
  id: WizardStep;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}

const STEPS: StepConfig[] = [
  { id: 'basics', label: 'Basics', icon: FileText },
  { id: 'stages', label: 'States', icon: Layers },
  { id: 'transitions', label: 'Transitions', icon: ArrowRightLeft },
  { id: 'guards', label: 'Guards', icon: Shield },
];

export default function FunnelBuilder({
  doc,
  onChange: rawOnChange,
  isCreating,
  remoteIssues = null,
}: FunnelBuilderProps) {
  const [activeStep, setActiveStep] = useState<WizardStep>('basics');

  // TEMPORARY DIAGNOSTICS — every document write from the Wizard funnels
  // through here. `next` is logged and committed as the same reference, so the
  // log can never disagree with what was actually written.
  const onChange = (next: StateMachineDocument, trigger = 'wizard:unknown') => {
    diagLogCommit(trigger, doc, next);
    rawOnChange(next);
  };

  const localIssues = useMemo(() => validateMachine(doc), [doc]);
  const issues = useMemo(
    () => (remoteIssues && remoteIssues.length > 0 ? [...localIssues, ...remoteIssues] : localIssues),
    [localIssues, remoteIssues],
  );
  const def = doc.definition;

  // Always the latest doc for the async effect below — that effect's own
  // closure over `doc`/`def` goes stale the moment anything else edits the
  // document while its formSchemas.list() request is still in flight (e.g.
  // attaching a Method on the States tab), and spreading that stale snapshot
  // into onChange would silently revert the concurrent edit.
  const docRef = useRef(doc);
  useEffect(() => {
    // TEMPORARY DIAGNOSTICS — the ref commit is a separate statement from any
    // onChange call, so it gets its own line rather than being assumed in sync.
    diagLogRefWrite('wizard docRef.current', docRef.current, doc);
    docRef.current = doc;
  }, [doc]);

  // Per-state field lists resolved from each state's own attached Method
  // Block(s) — scoped, unlike def.entity_schema.fields (which merges every
  // state's method fields into one flat list with no attribution back to
  // the state that contributed each one). Feeds the Guards field-picker and
  // the States tab's field preview/action pickers.
  const { fieldsByState } = useMethodFieldsByState(def.states);
  // Read inside the re-sync effect, which is keyed on entity_type: a ref keeps
  // it current without making the sync re-run whenever a method resolves.
  const methodFieldsRef = useRef(fieldsByState);
  // Declared before the re-sync effect on purpose: same-component effects run
  // in declaration order, so the ref is current before that effect's fetch is
  // even started. Writing it during render instead would be a render-phase
  // side effect, which StrictMode's double render and concurrent rendering
  // both make unsafe.
  useEffect(() => {
    methodFieldsRef.current = fieldsByState;
  }, [fieldsByState]);

  // Re-sync the entity schema from the entity type's forms on open so guard
  // field dropdowns reflect the latest form fields, not a stale snapshot.
  useEffect(() => {
    // TODO: Extract this form-schema sync block with the canvas editor once the
    // P1 absent-forms behavior is verified in both editors.
    if (!def.entity_type || def.entity_type === 'entity') {
      diagLog('formSchemas.list SKIPPED (wizard)', `entityType=${def.entity_type ?? '<none>'}`);
      return;
    }
    let cancelled = false;
    const entityType = def.entity_type;
    diagLog('formSchemas.list KICKOFF (wizard)', `entityType=${entityType}`);
    formSchemas.list(def.entity_type).then((resp) => {
      diagLog(
        'formSchemas.list RESOLVED (wizard)',
        `entityType=${entityType} items=${resp.items.length} cancelled=${cancelled}`,
      );
      const latestDoc = docRef.current;
      const latestDef = latestDoc.definition;
      if (cancelled || latestDef.entity_type !== entityType) {
        diagLog('entity-schema re-sync BAILED (wizard)', 'cancelled or entityType changed');
        return;
      }
      if (resp.items.length === 0) {
        diagLog('entity-schema re-sync BAILED (wizard)', 'zero form items — no-op');
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
        diagLog('entity-schema re-sync BAILED (wizard)', 'forms already match — no-op');
        return; // no-op when forms already match
      }
      // The merge base is chosen ONCE, here, and the resulting object is both
      // logged and committed as the same reference — the log cannot misreport
      // it. `mergeSource` names which candidate document actually won.
      const mergeSource = 'docRef.current';
      const mergeBase = latestDoc;
      const mergeBaseDef = latestDef;
      diagLog(
        'entity-schema re-sync SOURCE (wizard)',
        `candidates: stale-closure doc{${methodRefsSnapshot(doc)}} | docRef.current{${methodRefsSnapshot(latestDoc)}} => SELECTED ${mergeSource}{${methodRefsSnapshot(mergeBase)}}`,
      );
      const committed: StateMachineDocument = {
        ...mergeBase,
        definition: {
          ...mergeBaseDef,
          entity_schema: { entity_type: entityType, fields: syncedFields },
          transitions: prunedTransitions,
        },
      };
      diagLogCommit(
        'entity-schema re-sync (wizard)',
        mergeBase,
        committed,
        `mergeSource=${mergeSource}`,
      );
      rawOnChange(committed);
    }).catch((err) => {
      console.error('Failed to load form schemas for entity type', def.entity_type, err);
    });
    return () => {
      cancelled = true;
    };
  }, [def.entity_type]);

  const patchDefinition = (patch: Partial<StateMachineDefinition>, trigger = 'patchDefinition') => {
    onChange({ ...doc, definition: { ...def, ...patch } }, trigger);
  };

  const handleBasicsChange = (patch: {
    machineName?: string;
    machineKey?: string;
    displayName?: string;
    description?: string;
    entityType?: string;
    serviceId?: string | null;
  }) => {
    let next = doc;
    if (patch.machineName !== undefined) {
      next = { ...next, machine_name: patch.machineName };
    }
    const defPatch: Partial<StateMachineDefinition> = {};
    if (patch.machineKey !== undefined) defPatch.machine_key = patch.machineKey;
    if (patch.displayName !== undefined) defPatch.name = patch.displayName;
    if (patch.description !== undefined) defPatch.description = patch.description;
    if (patch.entityType !== undefined) {
      defPatch.entity_type = patch.entityType;
      defPatch.entity_schema = { entity_type: patch.entityType, fields: [] };
      defPatch.transitions = pruneTransitionsForEntityFields(def.transitions, []);
    }
    if (patch.serviceId !== undefined) defPatch.service_id = patch.serviceId;
    if (Object.keys(defPatch).length > 0) {
      next = { ...next, definition: { ...next.definition, ...defPatch } };
    }
    onChange(
      next,
      `handleBasicsChange(${Object.keys(patch).join(',') || 'none'})`,
    );
  };

  const handleStagesChange = (patch: { states?: typeof def.states; initial_state?: string }) => {
    const definitionPatch: Partial<StateMachineDefinition> = {};
    if (patch.states !== undefined) {
      definitionPatch.states = patch.states;
      // Drop transitions referencing states that no longer exist.
      const validNames = new Set(patch.states.map((s) => s.name));
      const remainingTransitions = def.transitions.filter(
        (t) => validNames.has(t.from) && validNames.has(t.to_state),
      );
      if (remainingTransitions.length !== def.transitions.length) {
        definitionPatch.transitions = remainingTransitions;
      }
    }
    if (patch.initial_state !== undefined) definitionPatch.initial_state = patch.initial_state;
    patchDefinition(definitionPatch, 'handleStagesChange (States tab / saveMethodsAt)');
  };

  const handleTransitionsChange = (transitions: typeof def.transitions) => {
    patchDefinition({ transitions }, 'handleTransitionsChange');
  };

  const stepStatus = (step: WizardStep): 'error' | 'warning' | 'complete' | 'default' => {
    const stepIssues = issues.filter((i) => pathToStep(i.path) === step);
    if (stepIssues.some((i) => i.level === 'error')) return 'error';
    if (stepIssues.some((i) => i.level === 'warning')) return 'warning';
    switch (step) {
      case 'basics':
        return def.machine_key && def.name && def.entity_type ? 'complete' : 'default';
      case 'stages':
        return def.states.length > 0 ? 'complete' : 'default';
      case 'transitions':
        return def.transitions.length > 0 ? 'complete' : 'default';
      default:
        return 'default';
    }
  };

  const renderStep = () => {
    switch (activeStep) {
      case 'basics':
        return (
          <BasicsStep
            machineName={doc.machine_name}
            machineKey={def.machine_key}
            displayName={def.name}
            description={def.description}
            entityType={def.entity_type}
            serviceId={def.service_id ?? null}
            identifierLocked={!isCreating}
            onChange={handleBasicsChange}
          />
        );
      case 'stages':
        return (
          <StagesStep
            fieldsByState={fieldsByState}
            entityType={def.entity_type}
            states={def.states}
            initialState={def.initial_state}
            transitions={def.transitions}
            onChange={handleStagesChange}
          />
        );
      case 'transitions':
        return (
          <TransitionsStep
            states={def.states}
            transitions={def.transitions}
            onChange={handleTransitionsChange}
          />
        );
      case 'guards':
        return (
          <GuardsStep transitions={def.transitions} fieldsByState={fieldsByState} onChange={handleTransitionsChange} />
        );
      default:
        return null;
    }
  };

  return (
    <div className="h-full bg-card border border-border rounded-xl overflow-hidden">
      <div className="flex h-full">
        <nav className="w-48 shrink-0 border-r border-border bg-muted/50 p-4 overflow-y-auto">
          <ul className="space-y-1">
            {STEPS.map((step) => {
              const status = stepStatus(step.id);
              const isActive = activeStep === step.id;
              const Icon = step.icon;
              return (
                <li key={step.id}>
                  <button
                    onClick={() => setActiveStep(step.id)}
                    className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                      isActive
                        ? 'bg-primary text-primary-foreground'
                        : 'text-foreground hover:bg-muted'
                    }`}
                  >
                    <Icon className={`w-4 h-4 ${isActive ? 'text-primary-foreground' : 'text-muted-foreground'}`} />
                    <span className="flex-1 text-left">{step.label}</span>
                    {status === 'error' && !isActive && (
                      <AlertCircle className="w-4 h-4 text-destructive" />
                    )}
                    {status === 'warning' && !isActive && (
                      <AlertCircle className="w-4 h-4 text-warning" />
                    )}
                    {status === 'complete' && !isActive && (
                      <CheckCircle className="w-4 h-4 text-success" />
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>

        <div className="flex-1 flex">
          <div className="flex-1 p-6 overflow-y-auto min-h-0">{renderStep()}</div>
          <ValidationPanel
            issues={issues}
            activeStep={activeStep}
            onNavigateToStep={setActiveStep}
          />
        </div>
      </div>
    </div>
  );
}
