import { useCallback, useEffect, useRef, useState } from 'react';
import type { NavigateFunction } from 'react-router-dom';

import api from '@/core/services/api';
import type { StateMachineRecord } from '@/core/types';
import type { StateMachineDocument } from '@/lib/state-machine/types';
import type { DraftSaveResult } from '@/lib/state-machine/useStateMachineDoc';
// TEMPORARY DIAGNOSTICS — see lib/state-machine/diag.ts; strip with the bug.
import { diagLog, methodRefsSnapshot } from '@/lib/state-machine/diag';

export type ValidateIssue = {
  code: string;
  message: string;
  severity: string;
  bucket?: string | null;
};

export type ValidateState = {
  status: 'idle' | 'running' | 'done' | 'error';
  canPublish?: boolean;
  issues?: ValidateIssue[];
  error?: string;
};

export type DraftResult = {
  is_valid: boolean;
  deactivated: boolean;
  issues: { code: string; message: string; severity: string }[];
};

interface UseFunnelEditorActionsParams {
  stateMachineId: string | undefined;
  view: string;
  navigate: NavigateFunction;
  doc: StateMachineDocument;
  saveDraft: () => Promise<DraftSaveResult | null>;
  save: () => Promise<StateMachineRecord | null>;
  errorCount: number;
  isCreating: boolean;
}

interface UseFunnelEditorActionsResult {
  successMessage: string | null;
  createDraftError: string | null;
  validateState: ValidateState;
  draftResult: DraftResult | null;
  handleSaveDraft: () => Promise<void>;
  handleValidate: () => Promise<void>;
  handleSave: () => Promise<void>;
}

export function useFunnelEditorActions({
  stateMachineId,
  view,
  navigate,
  doc,
  saveDraft,
  save,
  errorCount,
  isCreating,
}: UseFunnelEditorActionsParams): UseFunnelEditorActionsResult {
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [createDraftError, setCreateDraftError] = useState<string | null>(null);
  const [validateState, setValidateState] = useState<ValidateState>({ status: 'idle' });
  const [draftResult, setDraftResult] = useState<DraftResult | null>(null);
  const draftRequested = useRef(false);

  useEffect(() => {
    if (stateMachineId) return;
    if (draftRequested.current) return;
    draftRequested.current = true;
    api.stateMachines
      .createDraft()
      .then((record) => {
        const target = record.id ?? record.machine_name;
        navigate(`/funnel/${encodeURIComponent(target)}/edit?view=${view}`, { replace: true });
      })
      .catch((err) => {
        draftRequested.current = false;
        setCreateDraftError(err instanceof Error ? err.message : 'Failed to create workflow');
      });
  }, [stateMachineId, view, navigate]);

  const handleSaveDraft = useCallback(async (): Promise<void> => {
    diagLog('"Save as draft" CLICKED', `doc{${methodRefsSnapshot(doc)}}`);
    setDraftResult(null);
    setSuccessMessage(null);
    const resp = await saveDraft();
    if (resp) {
      setDraftResult({
        is_valid: resp.is_valid,
        deactivated: resp.deactivated,
        issues: resp.validation_issues,
      });
      setSuccessMessage(
        resp.deactivated
          ? `Draft saved. Workflow auto-deactivated due to validation errors.`
          : resp.is_valid
            ? `Draft saved.`
            : `Draft saved with ${resp.validation_issues.length} issue${
                resp.validation_issues.length === 1 ? '' : 's'
              }.`,
      );
      // The URL can still point at the published row (e.g. reopened from the
      // Funnels list) while saveDraft() always writes to the separate draft
      // row — follow the save so a reload re-fetches the draft just written,
      // not the stale published row. Mirrors handleSave's redirect below.
      if (resp.record.id && resp.record.id !== stateMachineId) {
        navigate(`/funnel/${encodeURIComponent(resp.record.id)}/edit?view=${view}`, { replace: true });
      }
    }
  }, [saveDraft, stateMachineId, navigate, view]);

  const handleValidate = useCallback(async (): Promise<void> => {
    setValidateState({ status: 'running' });
    try {
      const submitDoc = {
        ...doc,
        definition: { ...doc.definition, machine_key: doc.machine_name },
      };
      const resp = (await api.stateMachines.validate(submitDoc)) as {
        can_publish?: boolean;
        validation_report?: { issues?: ValidateIssue[] };
        dry_run_report?: { issues?: ValidateIssue[] } | null;
      };
      const merged = [
        ...(resp.validation_report?.issues ?? []),
        ...(resp.dry_run_report?.issues ?? []),
      ];
      setValidateState({ status: 'done', canPublish: !!resp.can_publish, issues: merged });
    } catch (err) {
      setValidateState({
        status: 'error',
        error: err instanceof Error ? err.message : 'Validation failed',
      });
    }
  }, [doc]);

  const handleSave = useCallback(async (): Promise<void> => {
    if (errorCount > 0) return;
    setSuccessMessage(null);
    const record = await save();
    if (record) {
      if (record.id) {
        navigate(`/funnel/${encodeURIComponent(record.id)}/edit?view=${view}`, { replace: true });
      }
      setSuccessMessage(
        isCreating
          ? `Saved ${record.name} as v${record.version}.`
          : `Published ${record.name} as v${record.version}.`,
      );
    }
  }, [errorCount, isCreating, navigate, save, view]);

  return {
    successMessage,
    createDraftError,
    validateState,
    draftResult,
    handleSaveDraft,
    handleValidate,
    handleSave,
  };
}
