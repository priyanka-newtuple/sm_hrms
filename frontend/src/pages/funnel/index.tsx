import { useMemo, type ReactElement } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { ArrowLeft, Loader2 } from 'lucide-react';

import { useStateMachineDoc } from '@/lib/state-machine/useStateMachineDoc';
import { validateMachine } from '@/lib/state-machine/validate';

import { FunnelEditorBanners } from './components/FunnelEditorBanners';
import { FunnelEditorHeader } from './components/FunnelEditorHeader';
import { useFunnelEditorActions } from './useFunnelEditorActions';
import { WorkflowEditor } from './canvas/WorkflowEditor';
import FunnelBuilder from './wizard';

type View = 'wizard' | 'canvas';

function resolveView(param: string | null, fallback: View): View {
  return param === 'wizard' || param === 'canvas' ? param : fallback;
}

export default function FunnelEditorPage(): ReactElement {
  const { stateMachineId } = useParams<{ stateMachineId?: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const defaultView: View = stateMachineId ? 'wizard' : 'canvas';
  const view = resolveView(searchParams.get('view'), defaultView);

  const {
    doc,
    setDoc,
    isCreating,
    isLoading,
    loadError,
    isDirty,
    hasDraft,
    isSaving,
    isSavingDraft,
    saveError,
    draftError,
    save,
    saveDraft,
    canvasNodes,
    setCanvasNodes,
  } = useStateMachineDoc({ stateMachineId });

  const issues = useMemo(() => validateMachine(doc), [doc]);
  const errorCount = issues.filter((i) => i.level === 'error').length;

  const {
    successMessage,
    createDraftError,
    validateState,
    draftResult,
    handleSaveDraft,
    handleValidate,
    handleSave,
  } = useFunnelEditorActions({
    stateMachineId,
    view,
    navigate,
    doc,
    saveDraft,
    save,
    errorCount,
    isCreating,
  });

  const setView = (next: View): void => {
    const params = new URLSearchParams(searchParams);
    params.set('view', next);
    setSearchParams(params, { replace: true });
  };

  if (isLoading || (!stateMachineId && !createDraftError)) {
    return (
      <div className="mx-auto flex w-full max-w-[1600px] items-center justify-center py-24">
        <Loader2 className="h-6 w-6 animate-spin text-cobalt" />
      </div>
    );
  }

  if (createDraftError) {
    return (
      <div className="mx-auto flex w-full max-w-[1600px] flex-col gap-4 px-6 py-6">
        <Link
          to="/settings"
          className="inline-flex items-center gap-2 text-sm font-medium text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to settings
        </Link>
        <div className="rounded-2xl border border-destructive/30 bg-destructive-subtle px-4 py-3 text-sm text-destructive">
          {createDraftError}
        </div>
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="mx-auto flex w-full max-w-[1600px] flex-col gap-4 px-6 py-6">
        <Link
          to="/settings"
          className="inline-flex items-center gap-2 text-sm font-medium text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to settings
        </Link>
        <div className="rounded-2xl border border-destructive/30 bg-destructive-subtle px-4 py-3 text-sm text-destructive">
          {loadError}
        </div>
      </div>
    );
  }

  return (
    <div className="flex w-full flex-col gap-6 px-6 py-6 h-[calc(100svh-var(--header-height))] overflow-hidden">
      <FunnelEditorHeader
        doc={doc}
        isCreating={isCreating}
        view={view}
        setView={setView}
        validateState={validateState}
        isSavingDraft={isSavingDraft}
        isDirty={isDirty}
        isSaving={isSaving}
        hasDraft={hasDraft}
        errorCount={errorCount}
        onValidate={handleValidate}
        onSaveDraft={handleSaveDraft}
        onSave={handleSave}
        onOpenAutomation={() =>
          navigate(
            `/settings?tab=automations&workflow=${encodeURIComponent(doc.machine_name)}`,
          )
        }
      />

      <FunnelEditorBanners
        saveError={saveError}
        draftError={draftError}
        draftResult={draftResult}
        successMessage={successMessage}
        validateState={validateState}
      />

      {view === 'wizard' ? (
        <div className="flex-1 min-h-0 overflow-hidden rounded-3xl border border-border bg-card shadow-sm">
          <FunnelBuilder doc={doc} onChange={setDoc} isCreating={isCreating} />
        </div>
      ) : (
        <div className="flex-1 min-h-0 overflow-hidden rounded-3xl border border-border bg-card shadow-sm">
          <div className="flex h-full flex-col">
            <WorkflowEditor
              doc={doc}
              onChange={setDoc}
              issues={issues}
              positions={canvasNodes}
              onPositionsChange={setCanvasNodes}
            />
          </div>
        </div>
      )}
    </div>
  );
}
