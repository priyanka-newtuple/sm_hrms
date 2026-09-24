import { useEffect, useMemo, useState } from 'react';
import {
  ArrowLeft,
  ArrowRight,
  Check,
  ExternalLink,
  FileQuestion,
  Link2,
  Pencil,
  X,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import DocumentPreviewPanel from '@/core/components/DocumentPreviewPanel';
import SlideOver from '@/core/components/SlideOver';
import { useDocumentPreviewStore } from '@/core/stores/documentPreviewStore';
import type { BulkImportDraft, BulkImportJob } from '@/core/services/api';
import type { DocumentMetadata, FormField } from '@/core/types';
import EntityFormFields from '@/pages/records/detail/components/EntityFormFields';

export type BulkImportDecision = 'accepted' | 'modified' | 'rejected';

export interface ReviewIssueView {
  code: string;
  label: string;
  tone: 'destructive' | 'warning' | 'info';
}

interface BulkImportReviewDrawerProps {
  draft: BulkImportDraft | null;
  issues: ReviewIssueView[];
  fields: FormField[];
  files: BulkImportJob['files'];
  entityTypeName: string;
  open: boolean;
  position: number;
  total: number;
  reviewedCount: number;
  canGoPrevious: boolean;
  canGoNext: boolean;
  onClose: () => void;
  onPrevious: () => void;
  onNext: () => void;
  onAccept: (draftId: string) => void;
  onReject: (draftId: string) => void;
  onModify: (draftId: string, data: Record<string, unknown>) => void;
  onFilesChange: (draftId: string, fileIds: string[]) => void;
  onRemoteReferenceRemove: (
    draftId: string,
    sourceColumn: string,
    sourceValue: string,
  ) => void;
}

function asPreviewDocument(file: BulkImportJob['files'][number]): DocumentMetadata {
  return {
    id: file.file_id,
    type: 'bulk-import-source',
    filename: file.filename,
    storage_key: '',
    content_type: file.content_type,
    size_bytes: file.size_bytes,
    uploaded_at: '',
    uploaded_by: '',
  };
}

function asRemotePreviewDocument(
  reference: NonNullable<BulkImportDraft['remote_file_references']>[number],
): DocumentMetadata | null {
  if (!reference.source_url || reference.file_id || reference.status !== 'referenced') return null;
  let filename = 'remote-attachment';
  try {
    filename = decodeURIComponent(new URL(reference.source_url).pathname.split('/').pop() || filename);
  } catch {
    // The backend already validates the reference shape; keep a safe display fallback.
  }
  if (!filename.includes('.')) {
    const hint = reference.source_column.toLowerCase();
    filename += /image|photo|logo|thumbnail/.test(hint) ? '.jpg' : '.pdf';
  }
  return {
    id: `remote:${reference.source_url}`,
    type: 'bulk-import-remote-reference',
    filename,
    storage_key: '',
    content_type: 'application/octet-stream',
    size_bytes: 0,
    uploaded_at: '',
    uploaded_by: '',
    source_url: reference.source_url,
  };
}

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName);
}

export default function BulkImportReviewDrawer({
  draft,
  issues,
  fields,
  files,
  entityTypeName,
  open,
  position,
  total,
  reviewedCount,
  canGoPrevious,
  canGoNext,
  onClose,
  onPrevious,
  onNext,
  onAccept,
  onReject,
  onModify,
  onFilesChange,
  onRemoteReferenceRemove,
}: BulkImportReviewDrawerProps) {
  const [editing, setEditing] = useState(false);
  const [draftData, setDraftData] = useState<Record<string, unknown>>({});
  const previewFiles = useMemo(() => {
    const managed = files
      .filter((file) => draft?.file_ids.includes(file.file_id))
      .map(asPreviewDocument);
    const remote = (draft?.remote_file_references || [])
      .map(asRemotePreviewDocument)
      .filter((document): document is DocumentMetadata => document !== null);
    return [...managed, ...remote];
  }, [draft?.file_ids, draft?.remote_file_references, files]);
  const selectableFiles = useMemo(
    () => files.filter(
      (file) => file.origin !== 'remote'
        || draft?.remote_file_references?.some((reference) => reference.file_id === file.file_id),
    ),
    [draft?.remote_file_references, files],
  );
  const removableRemoteReferences = draft?.remote_file_references?.filter(
    (reference) => !reference.file_id,
  ) || [];

  useEffect(() => {
    setEditing(false);
    setDraftData(draft?.data ?? {});
  }, [draft?.draft_id, draft?.data]);

  useEffect(() => {
    if (!open || !draft) return;
    const previewStore = useDocumentPreviewStore.getState();
    previewStore.setCollapsed(false);
    previewStore.setDocs(
      previewFiles,
      `bulk-import:${draft.draft_id}`,
      'owned',
    );
    return () => useDocumentPreviewStore.getState().reset();
  }, [draft, open, previewFiles]);

  useEffect(() => {
    if (!open || !draft || editing) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (isTypingTarget(event.target)) return;
      const key = event.key.toLowerCase();
      if (key === 'a') {
        event.preventDefault();
        onAccept(draft.draft_id);
      } else if (key === 'r') {
        event.preventDefault();
        onReject(draft.draft_id);
      } else if (key === 'm' && !draft.existing_entity) {
        event.preventDefault();
        setEditing(true);
      } else if (event.key === 'ArrowLeft' && canGoPrevious) {
        event.preventDefault();
        onPrevious();
      } else if (event.key === 'ArrowRight' && canGoNext) {
        event.preventDefault();
        onNext();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [canGoNext, canGoPrevious, draft, editing, onAccept, onNext, onPrevious, onReject, open]);

  if (!draft) return null;

  const title = String(draft.data.identifier || `Proposed ${entityTypeName}`);
  const source = draft.source_kind === 'spreadsheet' && draft.source_row_number
    ? `${draft.source_sheet_name || 'Sheet'} row ${draft.source_row_number}`
    : previewFiles[0]?.filename || 'No matched document';

  return (
    <SlideOver
      open={open}
      onClose={onClose}
      title={title}
      subtitle={`${source} · ${Math.round(draft.confidence * 100)}% confidence`}
      size="2xl"
      contentClassName="min-h-0 overflow-hidden p-0"
      footer={
        <div className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-muted-foreground">
            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={!canGoPrevious}
                onClick={onPrevious}
                icon={<ArrowLeft />}
              >
                Previous
              </Button>
              <span className="tabular-nums">{position} of {total}</span>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={!canGoNext}
                onClick={onNext}
                icon={<ArrowRight />}
                iconPosition="right"
              >
                Next
              </Button>
            </div>
            <span>{reviewedCount} of {total} reviewed</span>
          </div>

          {editing ? (
            <div className="grid gap-2 sm:grid-cols-2">
              <Button
                type="button"
                variant="outline"
                size="lg"
                onClick={() => {
                  setDraftData(draft.data);
                  setEditing(false);
                }}
                icon={<X />}
              >
                Cancel changes
              </Button>
              <Button
                type="button"
                variant="primary"
                size="lg"
                onClick={() => onModify(draft.draft_id, draftData)}
                icon={<Check />}
              >
                Save and accept
              </Button>
            </div>
          ) : (
            <div className="grid gap-2 sm:grid-cols-3">
              <Button
                type="button"
                variant="outline-danger"
                size="lg"
                onClick={() => onReject(draft.draft_id)}
                icon={<X />}
              >
                Reject <span className="ml-1 opacity-60">R</span>
              </Button>
              <Button
                type="button"
                variant="outline"
                size="lg"
                disabled={Boolean(draft.existing_entity)}
                title={draft.existing_entity ? 'Existing-record updates are handled in the next improvement' : undefined}
                onClick={() => setEditing(true)}
                icon={<Pencil />}
              >
                Modify <span className="ml-1 opacity-60">M</span>
              </Button>
              <Button
                type="button"
                variant="success"
                size="lg"
                onClick={() => onAccept(draft.draft_id)}
                icon={<Check />}
              >
                Accept <span className="ml-1 opacity-70">A</span>
              </Button>
            </div>
          )}
        </div>
      }
    >
      <div className="flex h-full min-h-0">
        {previewFiles.length > 0 ? (
          <DocumentPreviewPanel layout="sheet" className="h-full border-r border-border" />
        ) : (
          <div className="hidden w-[24rem] shrink-0 flex-col items-center justify-center border-r border-border bg-muted/20 px-8 text-center lg:flex">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-muted text-muted-foreground">
              <FileQuestion className="h-5 w-5" />
            </div>
            <p className="mt-3 text-sm font-medium text-foreground">No document matched</p>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
              This record came from structured data or the agent did not assign a supporting document.
            </p>
          </div>
        )}

        <div className="min-w-0 flex-1 overflow-y-auto p-5 sm:p-6">
          {issues.length > 0 && (
            <div className="mb-5 rounded-xl border border-amber-500/25 bg-amber-500/5 p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-amber-700 dark:text-amber-400">
                Why this needs review
              </p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {issues.map((issue) => (
                  <span
                    key={issue.code}
                    className="rounded-full border border-amber-500/20 bg-background px-2.5 py-1 text-xs text-foreground"
                  >
                    {issue.label}
                  </span>
                ))}
              </div>
            </div>
          )}

          {(draft.relation_bindings || []).length > 0 && (
            <div className="mb-5 rounded-xl border border-border bg-background p-4">
              <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                <Link2 className="h-3.5 w-3.5" />
                Parent evidence
              </div>
              <div className="mt-3 space-y-2">
                {(draft.relation_bindings || []).map((binding) => (
                  <div
                    key={binding.relation_def_id}
                    className="flex flex-wrap items-center justify-between gap-2 text-sm"
                  >
                    <span className="text-muted-foreground">{binding.source_entity_type_name}</span>
                    <div className="text-right">
                      <div className={binding.status === 'resolved' ? 'font-medium text-foreground' : 'font-medium text-destructive'}>
                        {binding.source_entity_label || binding.source_value || 'Not resolved'}
                      </div>
                      <div className="text-[11px] text-muted-foreground">
                        {binding.mode === 'fixed'
                          ? 'Fixed parent for this import'
                          : `${binding.source_column || 'Parent column'}: ${binding.source_value || 'empty'}`}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          <details className="mb-5 rounded-xl border border-border bg-muted/15">
            <summary className="flex cursor-pointer list-none items-center justify-between px-4 py-3 text-sm font-medium text-foreground">
              Supporting documents
              <span className="rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">
                {draft.file_ids.length + removableRemoteReferences.length} matched
              </span>
            </summary>
            <div className="max-h-40 space-y-1 overflow-y-auto border-t border-border px-3 py-2">
              {selectableFiles.map((file) => (
                <label
                  key={file.file_id}
                  className="flex cursor-pointer items-center gap-2 rounded-lg px-2 py-2 text-xs text-foreground hover:bg-muted"
                >
                  <input
                    type="checkbox"
                    checked={draft.file_ids.includes(file.file_id)}
                    onChange={(event) => onFilesChange(
                      draft.draft_id,
                      event.target.checked
                        ? [...draft.file_ids, file.file_id]
                        : draft.file_ids.filter((fileId) => fileId !== file.file_id),
                    )}
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate">{file.filename}</span>
                    {file.origin === 'remote' && typeof file.metadata?.source_url === 'string' && (
                      <span className="block truncate text-[10px] text-muted-foreground">
                        Managed copy from {file.metadata.source_url}
                      </span>
                    )}
                  </span>
                </label>
              ))}
              {removableRemoteReferences.map((reference) => (
                <div
                  key={`${reference.source_column}:${reference.source_value}`}
                  className="flex items-center gap-2 rounded-lg px-2 py-2 text-xs text-foreground hover:bg-muted"
                >
                  <input
                    type="checkbox"
                    checked
                    aria-label={`Include ${reference.source_column}`}
                    onChange={() => onRemoteReferenceRemove(
                      draft.draft_id,
                      reference.source_column,
                      reference.source_value,
                    )}
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate">{reference.source_column}</span>
                    <span className="block truncate text-[10px] text-muted-foreground">
                      {reference.error || `Uploads after confirmation · ${reference.source_value}`}
                    </span>
                  </span>
                  {reference.source_url && (
                    <a
                      href={reference.source_url}
                      target="_blank"
                      rel="noreferrer"
                      aria-label={`Open ${reference.source_column}`}
                      className="rounded-md p-1 text-muted-foreground hover:bg-background hover:text-foreground"
                    >
                      <ExternalLink className="h-3.5 w-3.5" />
                    </a>
                  )}
                </div>
              ))}
            </div>
          </details>

          <div className="mb-3 flex items-center justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold text-foreground">Proposed entity</h3>
              <p className="text-xs text-muted-foreground">
                {editing ? 'Edit the proposed values, then save and accept.' : 'Review the values against the source document.'}
              </p>
            </div>
            {draft.existing_entity && (
              <span className="rounded-full bg-blue-500/10 px-2.5 py-1 text-xs font-medium text-blue-700 dark:text-blue-400">
                Existing record
              </span>
            )}
          </div>
          <div className="rounded-xl border border-border bg-background p-4">
            <EntityFormFields
              fields={fields}
              values={editing ? draftData : draft.data}
              onChange={(field, value) => setDraftData((current) => ({ ...current, [field]: value }))}
              entityType={entityTypeName}
              mode={editing ? 'edit' : 'view'}
              compact
            />
          </div>
        </div>
      </div>
    </SlideOver>
  );
}
