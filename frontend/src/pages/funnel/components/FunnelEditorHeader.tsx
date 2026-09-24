import type { ReactElement } from 'react';
import {
  ArrowLeft,
  FileText,
  GitBranch,
  LayoutGrid,
  ListChecks,
  Lock,
  Loader2,
  Rocket,
  Save,
  ShieldCheck,
  CalendarClock,
} from 'lucide-react';
import { Link } from 'react-router-dom';

import { Button } from '@/components/ui/button';
import { usePermissions } from '@/core/hooks/usePermissions';
import type { StateMachineDocument } from '@/lib/state-machine/types';

import type { ValidateState } from '../useFunnelEditorActions';

type View = 'wizard' | 'canvas';

interface FunnelEditorHeaderProps {
  doc: StateMachineDocument;
  isCreating: boolean;
  view: View;
  setView: (next: View) => void;
  validateState: ValidateState;
  isSavingDraft: boolean;
  isDirty: boolean;
  isSaving: boolean;
  hasDraft: boolean;
  errorCount: number;
  onValidate: () => void;
  onSaveDraft: () => void;
  onSave: () => void;
  onOpenAutomation: () => void;
}

export function FunnelEditorHeader({
  doc,
  isCreating,
  view,
  setView,
  validateState,
  isSavingDraft,
  isDirty,
  isSaving,
  hasDraft,
  errorCount,
  onValidate,
  onSaveDraft,
  onSave,
  onOpenAutomation,
}: FunnelEditorHeaderProps): ReactElement {
  const { hasPermission } = usePermissions();
  const canWrite = hasPermission('workflow:write');

  return (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div className="space-y-3">
        <Link
          to="/settings"
          className="inline-flex items-center gap-2 text-sm font-medium text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to settings
        </Link>

        <div>
          <h1 className="text-3xl font-semibold tracking-tight text-foreground">
            {isCreating ? 'Create workflow' : doc.definition.name || 'Edit workflow'}
          </h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
            {isCreating
              ? 'Define states, transitions, guards, and SLAs.'
              : 'Saving will publish a new version.'}
          </p>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <Button type="button" variant="outline" size="lg" onClick={onOpenAutomation} disabled={isCreating} className="gap-2" title={isCreating ? 'Publish the workflow before adding schedules' : undefined}>
          <CalendarClock className="h-4 w-4" /> View automations
        </Button>
        <div className="flex items-center gap-2 rounded-2xl border border-border bg-card px-4 py-3 text-sm text-muted-foreground shadow-sm">
          <GitBranch className="h-4 w-4 text-cobalt" />
          <span>{doc.definition.transitions.length} transitions</span>
          <span className="text-muted-foreground/60">|</span>
          <span>{doc.definition.states.length} states</span>
        </div>

        <div className="inline-flex rounded-xl border border-border bg-card p-1 shadow-sm">
          <Button
            type="button"
            variant={view === 'wizard' ? 'secondary' : 'default'}
            size="sm"
            onClick={() => setView('wizard')}
            className="flex items-center gap-2"
          >
            <ListChecks className="h-4 w-4" />
            Wizard
          </Button>
          <Button
            type="button"
            variant={view === 'canvas' ? 'secondary' : 'default'}
            size="sm"
            onClick={() => setView('canvas')}
            className="flex items-center gap-2"
          >
            <LayoutGrid className="h-4 w-4" />
            Canvas
          </Button>
        </div>

        <Button
          type="button"
          variant="outline"
          size="lg"
          onClick={onValidate}
          disabled={validateState.status === 'running'}
          className="gap-2"
        >
          {validateState.status === 'running' ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <ShieldCheck className="h-4 w-4" />
          )}
          {validateState.status === 'running' ? 'Validating...' : 'Validate'}
        </Button>

        <Button
          type="button"
          variant="outline"
          size="lg"
          onClick={onSaveDraft}
          disabled={!canWrite || isSavingDraft || (!isDirty && !hasDraft)}
          className="gap-2"
          title={!canWrite ? 'You need workflow:write permission' : undefined}
        >
          {isSavingDraft ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : !canWrite ? (
            <Lock className="h-4 w-4" />
          ) : (
            <FileText className="h-4 w-4" />
          )}
          {isSavingDraft ? 'Saving draft...' : 'Save as draft'}
        </Button>

        <Button
          variant="primary"
          type="button"
          size="lg"
          onClick={onSave}
          disabled={!canWrite || isSaving || !hasDraft || errorCount > 0}
          className="gap-2"
          title={!canWrite ? 'You need workflow:write permission' : undefined}
        >
          {isSaving ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : isCreating ? (
            <Save className="h-4 w-4" />
          ) : (
            <Rocket className="h-4 w-4" />
          )}
          {isSaving ? 'Saving...' : isCreating ? 'Save' : 'Publish new version'}
        </Button>
      </div>
    </div>
  );
}
