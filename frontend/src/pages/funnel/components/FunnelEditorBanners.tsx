import type { ReactElement } from 'react';
import { AlertCircle, AlertTriangle, CheckCircle2 } from 'lucide-react';

import type { DraftResult, ValidateState } from '../useFunnelEditorActions';

interface FunnelEditorBannersProps {
  saveError: string | null;
  draftError: string | null;
  draftResult: DraftResult | null;
  successMessage: string | null;
  validateState: ValidateState;
}

function IssueList({
  issues,
}: {
  issues: { code: string; message: string; severity: string }[];
}): ReactElement {
  return (
    <ul className="mt-2 space-y-1.5">
      {issues.map((issue, i) => (
        <li key={i} className="flex items-start gap-2 text-xs">
          <span className="mt-0.5 inline-block min-w-[64px] font-mono uppercase tracking-wider opacity-70">
            {issue.severity || 'error'}
          </span>
          <span className="flex-1">
            <span className="font-mono opacity-70">{issue.code}</span>
            {' — '}
            {issue.message}
          </span>
        </li>
      ))}
    </ul>
  );
}

function ValidateResultBanner({ validateState }: { validateState: ValidateState }): ReactElement | null {
  if (validateState.status === 'error') {
    return (
      <div className="rounded-2xl border border-destructive/30 bg-destructive-subtle px-4 py-3 text-sm text-destructive">
        <div className="flex items-center gap-2">
          <AlertCircle className="h-4 w-4" />
          <span>{validateState.error}</span>
        </div>
      </div>
    );
  }

  if (validateState.status !== 'done') return null;

  const issues = validateState.issues ?? [];
  const errCount = issues.filter((i) => (i.severity || 'error') === 'error').length;
  const warnCount = issues.filter((i) => i.severity === 'warning').length;

  if (issues.length === 0 && validateState.canPublish) {
    return (
      <div className="rounded-2xl border border-success/30 bg-success-subtle px-4 py-3 text-sm text-success">
        <div className="flex items-center gap-2">
          <CheckCircle2 className="h-4 w-4" />
          <span>Validation passed. Ready to publish.</span>
        </div>
      </div>
    );
  }

  return (
    <div
      className={`rounded-2xl border px-4 py-3 text-sm ${
        errCount > 0
          ? 'border-destructive/30 bg-destructive-subtle text-destructive'
          : 'border-warning/30 bg-warning-subtle text-warning'
      }`}
    >
      <div className="flex items-center gap-2 font-medium">
        {errCount > 0 ? <AlertCircle className="h-4 w-4" /> : <AlertTriangle className="h-4 w-4" />}
        <span>
          {errCount > 0 ? `${errCount} error${errCount === 1 ? '' : 's'}` : ''}
          {errCount > 0 && warnCount > 0 ? ', ' : ''}
          {warnCount > 0 ? `${warnCount} warning${warnCount === 1 ? '' : 's'}` : ''}
          {!validateState.canPublish && ' — cannot publish'}
        </span>
      </div>
      <IssueList issues={issues} />
    </div>
  );
}

export function FunnelEditorBanners({
  saveError,
  draftError,
  draftResult,
  successMessage,
  validateState,
}: FunnelEditorBannersProps): ReactElement {
  return (
    <>
      {saveError && (
        <div className="rounded-2xl border border-destructive/30 bg-destructive-subtle px-4 py-3 text-sm text-destructive">
          {saveError}
        </div>
      )}

      {draftError && (
        <div className="rounded-2xl border border-destructive/30 bg-destructive-subtle px-4 py-3 text-sm text-destructive">
          {draftError}
        </div>
      )}

      {draftResult && draftResult.issues.length > 0 && (
        <div
          className={`rounded-2xl border px-4 py-3 text-sm ${
            draftResult.deactivated
              ? 'border-destructive/30 bg-destructive-subtle text-destructive'
              : 'border-warning/30 bg-warning-subtle text-warning'
          }`}
        >
          <div className="flex items-center gap-2 font-medium">
            {draftResult.deactivated ? (
              <AlertCircle className="h-4 w-4" />
            ) : (
              <AlertTriangle className="h-4 w-4" />
            )}
            <span>
              {draftResult.deactivated
                ? 'Workflow auto-deactivated due to validation errors.'
                : `${draftResult.issues.length} validation issue${
                    draftResult.issues.length === 1 ? '' : 's'
                  } in draft.`}
            </span>
          </div>
          <IssueList issues={draftResult.issues} />
        </div>
      )}

      {successMessage && (
        <div className="rounded-2xl border border-success/30 bg-success-subtle px-4 py-3 text-sm text-success">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4" />
            <span>{successMessage}</span>
          </div>
        </div>
      )}

      <ValidateResultBanner validateState={validateState} />
    </>
  );
}
