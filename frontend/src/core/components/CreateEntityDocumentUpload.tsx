/**
 * CreateEntityDocumentUpload
 *
 * "Upload" affordance for a create-entity modal (no entity exists yet). Uploads a
 * document unattached (no owner_entity_id), lets the same agent-processing pipeline
 * that update-entity uploads use (STAT-332) create the entity via the create_entity
 * tool, then polls the file until the agent finishes and hands the created entity back
 * to the caller. Does not touch EntityDocuments.tsx or the existing update-entity flow.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { AlertCircle, ChevronDown, FileText, Upload as UploadIcon, X } from 'lucide-react';

import { documents, documentTypes, workflowEntities } from '../services/api';
import type { WorkflowEntityState } from '../services/api';
import type { DocumentType } from '../types';
import { Button } from '@/components/ui/button';

const POLL_INTERVAL_MS = 4000;
const POLL_TIMEOUT_MS = 2 * 60 * 1000;
// File processing status literals (DocumentMetadata.status is typed as a plain string,
// not a union, so these guard against a typo'd comparison silently never matching).
const STATUS_PROCESSED = 'PROCESSED';
const STATUS_FAILED = 'FAILED';

interface CreateEntityDocumentUploadProps {
  entityType: string;
  disabled?: boolean;
  onEntityCreated: (entity: WorkflowEntityState) => void;
}

function normalize(value: string): string {
  return value.trim().toLowerCase();
}

function eligibleForCreate(docType: DocumentType, entityType: string): boolean {
  if (!docType.agent_enabled) return false;
  const postActions = docType.agent_config?.post_actions ?? [];
  return postActions.some(
    (action) => action.type === 'create_entity' && normalize(action.entity_type || '') === normalize(entityType)
  );
}

export default function CreateEntityDocumentUpload({
  entityType,
  disabled = false,
  onEntityCreated,
}: CreateEntityDocumentUploadProps) {
  const [docTypes, setDocTypes] = useState<DocumentType[]>([]);
  const [showDropdown, setShowDropdown] = useState(false);
  const [selectedDocType, setSelectedDocType] = useState<string>('');
  const [uploading, setUploading] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [duplicateWarning, setDuplicateWarning] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // Guards against a slow getMetadata round-trip overlapping the next interval tick —
  // without this, two in-flight checkStatus calls could both observe PROCESSED and
  // both call onEntityCreated (double-enrolling the same entity).
  const resolvedRef = useRef(false);

  useEffect(() => {
    documentTypes
      .list({ active_only: true })
      .then((result) => setDocTypes(result.items))
      .catch((e) => console.error('Failed to load document types:', e));
  }, []);

  useEffect(() => {
    return () => {
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    };
  }, []);

  const eligibleDocTypes = docTypes.filter((dt) => eligibleForCreate(dt, entityType));
  const busy = uploading || processing;

  const stopPolling = () => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  };

  // Marks this poll cycle done: stops the timer, clears the busy flag, blocks any
  // overlapping in-flight check from acting again, and optionally sets an error.
  const finish = useCallback((errorMessage?: string) => {
    resolvedRef.current = true;
    stopPolling();
    setProcessing(false);
    if (errorMessage) setError(errorMessage);
  }, []);

  // Checks the file's current status once. Returns true once a terminal state was
  // reached (so the caller stops polling) — false while still PROCESSING.
  const checkStatus = useCallback(
    async (fileId: string, startedAt: number): Promise<boolean> => {
      if (resolvedRef.current) return true;
      try {
        const doc = await documents.getMetadata('', fileId);
        if (resolvedRef.current) return true;
        if (doc.status === STATUS_PROCESSED) {
          finish();
          const createdEntityId = doc.metadata?.created_entity_id;
          if (typeof createdEntityId === 'string' && createdEntityId) {
            const entity = await workflowEntities.get(createdEntityId);
            onEntityCreated(entity);
          } else {
            setError(
              "Document processed, but no entity was created. Check the document type's agent configuration."
            );
          }
          return true;
        }
        if (doc.status === STATUS_FAILED) {
          finish(doc.failure_reason || 'Document processing failed.');
          return true;
        }
        if (Date.now() - startedAt > POLL_TIMEOUT_MS) {
          finish('Document processing is taking longer than expected. Try again shortly.');
          return true;
        }
        return false;
      } catch (e) {
        finish(e instanceof Error ? e.message : 'Failed to check processing status');
        return true;
      }
    },
    [onEntityCreated, finish]
  );

  const pollForResult = useCallback(
    async (fileId: string) => {
      resolvedRef.current = false;
      const startedAt = Date.now();
      // Check once immediately — a deduplicated upload reuses an already-terminal file,
      // so this resolves instantly instead of waiting a full interval tick to show it.
      const done = await checkStatus(fileId, startedAt);
      if (done) return;
      pollTimerRef.current = setInterval(() => void checkStatus(fileId, startedAt), POLL_INTERVAL_MS);
    },
    [checkStatus]
  );

  const handleTypeSelect = (docTypeId: string) => {
    setSelectedDocType(docTypeId);
    setShowDropdown(false);
    setError(null);
    setDuplicateWarning(null);
    fileInputRef.current?.click();
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !selectedDocType) return;

    const docType = docTypes.find((dt) => dt.type_id === selectedDocType);
    if (!docType) {
      setError('Invalid document type');
      return;
    }

    const ext = '.' + (file.name.split('.').pop()?.toLowerCase() ?? '');
    if (!docType.allowed_extensions.includes(ext)) {
      setError(`File type ${ext} not allowed. Allowed: ${docType.allowed_extensions.join(', ')}`);
      return;
    }
    const maxBytes = docType.max_size_mb * 1024 * 1024;
    if (file.size > maxBytes) {
      setError(`File size exceeds ${docType.max_size_mb}MB limit`);
      return;
    }

    try {
      setUploading(true);
      setError(null);
      setDuplicateWarning(null);
      const result = await documents.upload('', selectedDocType, file);
      setUploading(false);
      setProcessing(true);
      if (result.auto_deduplicated) {
        // Same content-hash as a prior upload — filehandler returned the existing file
        // record instead of processing a new one (matches EntityDocuments.tsx's dedup
        // handling). Its status may already be terminal (PROCESSED/FAILED) from that
        // earlier run — say so plainly instead of showing a confusing fresh-looking result.
        setDuplicateWarning(
          `"${file.name}" matches a document already uploaded before — showing its existing result, not a new run.`
        );
      }
      void pollForResult(result.document_id);
    } catch (e) {
      setUploading(false);
      setError(e instanceof Error ? e.message : 'Upload failed');
    } finally {
      setSelectedDocType('');
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const hasEligibleTypes = eligibleDocTypes.length > 0;

  return (
    <div className="relative inline-block">
      <Button
        type="button"
        variant="ghost"
        size="lg"
        disabled={disabled || !hasEligibleTypes}
        loading={busy}
        onClick={() => setShowDropdown((prev) => !prev)}
        title={
          hasEligibleTypes
            ? 'Upload a document and let the agent fill in the entity'
            : 'No document type is configured to auto-create this entity. Configure one in Settings → Document Types.'
        }
        icon={<UploadIcon className="w-4 h-4" />}
      >
        {uploading ? 'Uploading…' : processing ? 'Processing…' : 'Upload'}
        {hasEligibleTypes && <ChevronDown className="w-3 h-3 ml-1" />}
      </Button>

      {showDropdown && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setShowDropdown(false)} />
          <div className="absolute left-0 bottom-full mb-1 w-56 bg-card rounded-lg shadow-lg border border-border py-1 z-20">
            <div className="px-3 py-1.5 text-xs text-muted-foreground border-b border-border">
              Select document type
            </div>
            {eligibleDocTypes.map((docType) => (
              <Button
                key={docType.type_id}
                variant="ghost"
                onClick={() => handleTypeSelect(docType.type_id)}
                className="w-full flex items-center gap-2 px-3 py-2 text-sm text-foreground hover:bg-muted transition-colors min-w-0"
              >
                <FileText className="w-4 h-4 text-muted-foreground shrink-0" />
                <span className="truncate min-w-0 flex-1 text-left">
                  {docType.display_name || docType.type_id}
                </span>
              </Button>
            ))}
          </div>
        </>
      )}

      <input ref={fileInputRef} type="file" onChange={handleFileChange} className="hidden" />

      {(duplicateWarning || error) && (
        <div className="absolute left-0 bottom-full mb-1 w-64 flex flex-col gap-1.5 z-20">
          {duplicateWarning && (
            <div className="flex items-start gap-1.5 text-xs text-amber bg-amber/10 px-2.5 py-2 rounded-lg shadow-sm">
              <AlertCircle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
              <span className="flex-1">{duplicateWarning}</span>
              <Button variant="ghost" onClick={() => setDuplicateWarning(null)} className="p-0.5 flex-shrink-0">
                <X className="w-3 h-3" />
              </Button>
            </div>
          )}
          {error && (
            <div className="flex items-start gap-1.5 text-xs text-destructive bg-destructive/10 px-2.5 py-2 rounded-lg shadow-sm">
              <AlertCircle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
              <span className="flex-1">{error}</span>
              <Button variant="ghost" onClick={() => setError(null)} className="p-0.5 flex-shrink-0">
                <X className="w-3 h-3" />
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
