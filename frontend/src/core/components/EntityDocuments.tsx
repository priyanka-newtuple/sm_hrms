/**
 * EntityDocuments Component
 *
 * Generic component for displaying and managing documents attached to any entity.
 * Supports viewing, uploading, and deleting documents.
 * Filters available document types based on upload_contexts configuration.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import {
  FileText,
  Upload,
  Trash2,
  Loader2,
  AlertCircle,
  Check,
  FolderOpen,
  ChevronDown,
  Eye,
  Download,
  X,
  XCircle,
  Zap,
} from 'lucide-react';
import { documents, documentTypes } from '../services/api';
import { downloadDocument } from '../services/api/documents';
import type { DocumentMetadata, DocumentType } from '../types';
import ConfirmDialog from './ConfirmDialog';
import Modal from './Modal';
import Badge from './Badge';
import { Button } from '@/components/ui/button';
import { getFileIcon, useDocumentPreview } from '../hooks/useDocumentPreview';
import { useDocumentPreviewStore } from '../stores/documentPreviewStore';

// How often to re-poll the document list while an agent is still processing a document.
const PROCESSING_POLL_INTERVAL_MS = 4000;
// Background poll so connector-uploaded files appear without a reload: fast at first, then slow.
const FAST_POLL_INTERVAL_MS = 3000;
const FAST_POLL_WINDOW_MS = 60000;
const BACKGROUND_POLL_INTERVAL_MS = 20000;
// doc.status is typed as a plain string (see DocumentMetadata), not a union — a named
// constant guards against a typo'd literal silently never matching.
const DOC_STATUS_PROCESSING = 'PROCESSING';

/** Files uploaded from a document form field have a field key in their
 * Filehandler metadata. They belong to the entity for access and previews, but
 * are rendered in that field rather than duplicated in the general Documents
 * panel. */
function isDocumentFieldFile(doc: DocumentMetadata): boolean {
  const fieldKey = doc.metadata?.field_key;
  return typeof fieldKey === 'string' && fieldKey.trim().length > 0;
}

interface EntityDocumentsProps {
  entityId: string;
  entityType: string; // e.g., "ATS.Candidate", "ATS.Application", "ATS.Job"
  entityData: Record<string, unknown>;
  onUpdated?: () => void;
  compact?: boolean;
  title?: string; // Custom title, defaults to "Documents"
}

// Format file size
function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

// Format date
function formatDate(dateString: string): string {
  return new Date(dateString).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

export default function EntityDocuments({
  entityId,
  entityType,
  entityData,
  onUpdated,
  compact = false,
  title = 'Documents',
}: EntityDocumentsProps) {
  const [docList, setDocList] = useState<DocumentMetadata[]>([]);
  const [allDocTypes, setAllDocTypes] = useState<DocumentType[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Upload state
  const [uploading, setUploading] = useState(false);

  const resolveDocTypeLabel = (label: string | undefined, typeId: string) => {
    if (typeId === 'transcript') return 'Interview Transcript';
    return label || typeId;
  };

  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadWarning, setUploadWarning] = useState<string | null>(null);
  const [selectedDocType, setSelectedDocType] = useState<string>('');
  const [showUploadDropdown, setShowUploadDropdown] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Drag & drop state (handlers below, after availableDocTypes is defined)
  const [isDragOver, setIsDragOver] = useState(false);
  const [pendingDropFiles, setPendingDropFiles] = useState<File[] | null>(null);
  const [pendingDropMatchingTypes, setPendingDropMatchingTypes] = useState<DocumentType[]>([]);
  const dragCounterRef = useRef(0);

  // Delete state
  const [deleteConfirm, setDeleteConfirm] = useState<DocumentMetadata | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [mobilePreviewDoc, setMobilePreviewDoc] = useState<DocumentMetadata | null>(null);

  // Preview panel bridge — docs published to the store, panel renders elsewhere.
  // Own-docs lists go through publishOwnedDocs, which refuses to evict an
  // active preview of a doc outside the list (a related entity's file).
  const publishOwnedPreviewDocs = useDocumentPreviewStore((s) => s.publishOwnedDocs);
  const setPreviewDocs = useDocumentPreviewStore((s) => s.setDocs);
  const resetPreview = useDocumentPreviewStore((s) => s.reset);
  const setPreviewActive = useDocumentPreviewStore((s) => s.setActive);
  const activePreviewId = useDocumentPreviewStore((s) => s.docs[s.activeIndex]?.id);

  // Filter document types based on upload_contexts for this entity type
  const availableDocTypes = allDocTypes.filter((dt) => {
    // If no upload_contexts defined, allow all (backward compatibility)
    if (!dt.upload_contexts || dt.upload_contexts.length === 0) {
      return true;
    }
    // Check if entity type matches any upload context
    return dt.upload_contexts.some((ctx) => ctx.entity_type === entityType);
  });

  // Drag & drop handlers (must be after availableDocTypes)
  const handleDragEnter = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounterRef.current += 1;
    if (e.dataTransfer.types.includes('Files')) setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounterRef.current -= 1;
    if (dragCounterRef.current === 0) setIsDragOver(false);
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
    dragCounterRef.current = 0;
    const droppedFiles = Array.from(e.dataTransfer.files);
    if (droppedFiles.length === 0) return;

    // Find which doc types accept the dropped files' extensions
    const fileExts = droppedFiles.map((f) => `.${f.name.split('.').pop()?.toLowerCase()}`);
    const matchingTypes = availableDocTypes.filter((dt) =>
      fileExts.some((ext) => dt.allowed_extensions.includes(ext))
    );

    if (matchingTypes.length === 0) {
      // No doc type accepts these files — show clear error
      const exts = [...new Set(fileExts)].join(', ');
      const allowed = [...new Set(availableDocTypes.flatMap((dt) => dt.allowed_extensions))].join(', ');
      setUploadError(
        `${exts} files are not supported. Accepted formats: ${allowed}`
      );
      return;
    }

    if (matchingTypes.length === 1) {
      setSelectedDocType(matchingTypes[0].type_id);
      processFiles(droppedFiles, matchingTypes[0].type_id);
    } else {
      // Multiple matching types — show filtered picker
      setPendingDropFiles(droppedFiles);
      setPendingDropMatchingTypes(matchingTypes);
      setShowUploadDropdown(true);
    }
  }, [availableDocTypes]);

  const handleDropDocTypeSelect = (docTypeId: string) => {
    if (pendingDropFiles && pendingDropFiles.length > 0) {
      setSelectedDocType(docTypeId);
      setShowUploadDropdown(false);
      processFiles(pendingDropFiles, docTypeId);
      setPendingDropFiles(null);
    }
  };

  const fetchDocuments = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      setDocList([]);
      // Only clear the panel when it still shows a previously viewed entity;
      // same-entity content (e.g. an open related-file preview) is left alone.
      if (useDocumentPreviewStore.getState().contextEntityId !== entityId) {
        resetPreview();
      }
      const result = await documents.list(entityId);
      const generalDocs = result.items.filter(
        (doc) => !doc.metadata?.related_file_snapshot && !isDocumentFieldFile(doc),
      );
      setDocList(generalDocs);
      publishOwnedPreviewDocs(entityId, generalDocs);
    } catch (e) {
      setDocList([]);
      if (useDocumentPreviewStore.getState().contextEntityId !== entityId) {
        resetPreview();
      }
      setError(e instanceof Error ? e.message : 'Failed to load documents');
    } finally {
      setLoading(false);
    }
  }, [entityId, resetPreview, publishOwnedPreviewDocs]);

  // Load documents directly from API (filehandler-backed)
  useEffect(() => {
    void entityData; // retained for compatibility with callers
    fetchDocuments();
  }, [entityData, fetchDocuments]);

  // Silent refresh (no loading flicker) used to poll while agent processing runs.
  const refreshDocumentsSilently = useCallback(async () => {
    try {
      const result = await documents.list(entityId);
      const generalDocs = result.items.filter(
        (doc) => !doc.metadata?.related_file_snapshot && !isDocumentFieldFile(doc),
      );
      // A doc that was PROCESSING (per the current docList closure) and no longer is
      // just got its fields written by the agent (update_entity) — refetch the entity
      // so those fields actually show up, the same way document-upload-driven entity
      // creation already does.
      const previouslyProcessingIds = new Set(
        docList.filter((doc) => doc.status === DOC_STATUS_PROCESSING).map((doc) => doc.id)
      );
      const justFinishedProcessing = generalDocs.some(
        (doc) => previouslyProcessingIds.has(doc.id) && doc.status !== DOC_STATUS_PROCESSING
      );
      setDocList(generalDocs);
      publishOwnedPreviewDocs(entityId, generalDocs);
      if (justFinishedProcessing) {
        onUpdated?.();
      }
    } catch (e) {
      // Transient errors during polling are non-fatal; log at debug so persistent
      // failures are still observable in development.
      if (import.meta.env.DEV) console.debug('Document poll refresh failed', e);
    }
  }, [entityId, publishOwnedPreviewDocs, onUpdated, docList]);

  // Poll while any document is still being processed by an agent.
  useEffect(() => {
    if (!docList.some((doc) => doc.status === DOC_STATUS_PROCESSING)) return;
    const timer = setInterval(refreshDocumentsSilently, PROCESSING_POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [docList, refreshDocumentsSilently]);

  // Adaptive poll (skipped while processing-poll is active); self-reschedules fast→slow.
  const pollWindowStartRef = useRef(Date.now());
  useEffect(() => {
    if (docList.some((doc) => doc.status === DOC_STATUS_PROCESSING)) return;
    let timer: ReturnType<typeof setTimeout>;
    const schedule = () => {
      const withinFastWindow = Date.now() - pollWindowStartRef.current < FAST_POLL_WINDOW_MS;
      const delay = withinFastWindow ? FAST_POLL_INTERVAL_MS : BACKGROUND_POLL_INTERVAL_MS;
      timer = setTimeout(() => {
        void refreshDocumentsSilently();
        schedule();
      }, delay);
    };
    schedule();
    return () => clearTimeout(timer);
  }, [docList, refreshDocumentsSilently]);

  // Load all document types
  const fetchDocTypes = useCallback(async () => {
    try {
      const result = await documentTypes.list({ active_only: true });
      setAllDocTypes(result.items);
    } catch (e) {
      console.error('Failed to load document types:', e);
    }
  }, []);

  useEffect(() => {
    fetchDocTypes();
  }, [fetchDocTypes]);

  /** Validate files against a doc type's extension + size constraints. */
  function validateFileBatch(files: File[], docType: DocumentType) {
    const maxBytes = docType.max_size_mb * 1024 * 1024;
    const valid: File[] = [];
    const errors: string[] = [];
    for (const file of files) {
      const ext = `.${file.name.split('.').pop()?.toLowerCase()}`;
      if (!docType.allowed_extensions.includes(ext)) {
        errors.push(`${file.name}: ${ext} is not allowed (expected ${docType.allowed_extensions.join(', ')})`);
      } else if (file.size > maxBytes) {
        errors.push(`${file.name}: exceeds the ${docType.max_size_mb}MB limit`);
      } else {
        valid.push(file);
      }
    }
    return { valid, errors };
  }

  /** Classify upload results into failed + deduplicated lists. */
  function classifyResults(results: PromiseSettledResult<{ auto_deduplicated?: boolean }>[], files: File[]) {
    const failed: string[] = [];
    const duplicates: string[] = [];
    results.forEach((r, i) => {
      if (r.status === 'rejected') {
        const raw = r.reason instanceof Error ? r.reason.message : 'Upload failed';
        const ext = `.${files[i].name.split('.').pop()?.toLowerCase()}`;
        failed.push(raw.includes('content type') ? `${files[i].name}: content does not match ${ext}` : `${files[i].name}: ${raw}`);
      } else if (r.value.auto_deduplicated) {
        duplicates.push(files[i].name);
      }
    });
    return { failed, duplicates };
  }

  /** Shared upload logic for both file-input and drag-drop flows. */
  const processFiles = async (files: File[], docTypeId: string) => {
    const docType = allDocTypes.find((dt) => dt.type_id === docTypeId);
    if (!docType) { setUploadError('Invalid document type'); return; }

    const { valid, errors: validationErrors } = validateFileBatch(files, docType);
    if (valid.length === 0 && validationErrors.length > 0) {
      setUploadError(validationErrors.join('; '));
      return;
    }

    try {
      setUploading(true);
      setUploadError(null);
      setUploadWarning(null);
      const results = await Promise.allSettled(valid.map((f) => documents.upload(entityId, docTypeId, f)));
      const { failed, duplicates } = classifyResults(results, valid);

      if (results.some((r) => r.status === 'fulfilled')) {
        await fetchDocuments();
        onUpdated?.();
      }
      const allErrors = [...validationErrors, ...failed];
      if (allErrors.length > 0) setUploadError(`${allErrors.length} file${allErrors.length === 1 ? '' : 's'} could not be uploaded: ${allErrors.join('; ')}`);
      if (duplicates.length > 0) setUploadWarning(`${duplicates.length} file${duplicates.length === 1 ? ' was' : 's were'} already uploaded: ${duplicates.join(', ')}`);
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : 'Upload failed');
    } finally {
      setUploading(false);
      setSelectedDocType('');
    }
  };

  const handleUploadClick = (docTypeId: string) => {
    setSelectedDocType(docTypeId);
    setShowUploadDropdown(false);
    setUploadError(null);
    fileInputRef.current?.click();
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = Array.from(e.target.files || []);
    if (selectedFiles.length === 0 || !selectedDocType) return;
    await processFiles(selectedFiles, selectedDocType);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleDelete = async () => {
    if (!deleteConfirm) return;

    try {
      setDeleting(true);
      await documents.delete(entityId, deleteConfirm.id);
      await fetchDocuments();
      setDeleteConfirm(null);

      // Notify parent to refresh data
      if (onUpdated) {
        onUpdated();
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Delete failed');
    } finally {
      setDeleting(false);
    }
  };

  const handleDownload = async (doc: DocumentMetadata) => {
    try {
      await downloadDocument(doc);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Download failed');
    }
  };

  const handlePreviewOpen = (doc: DocumentMetadata) => {
    if (window.innerWidth >= 1024) {
      // The store may currently hold this entity's related files (their
      // preview list would not contain `doc`); republish the own list so
      // setActive can find it.
      if (!useDocumentPreviewStore.getState().docs.some((d) => d.id === doc.id)) {
        setPreviewDocs(docList, entityId);
      }
      setPreviewActive(doc.id);
      return;
    }
    setMobilePreviewDoc(doc);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-4">
        <Loader2 className="w-5 h-5 text-cobalt animate-spin" />
      </div>
    );
  }

  return (
    <div className={compact ? 'space-y-2' : 'space-y-4'}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <FolderOpen className="w-4 h-4 text-muted-foreground" />
          <span className={`font-medium text-foreground ${compact ? 'text-sm' : ''}`}>
            {title}
          </span>
          <Badge variant="default">{docList.length}</Badge>
        </div>

        {/* Upload dropdown */}
        <div className="relative">
          <Button
            variant="ghost"
            onClick={() => setShowUploadDropdown(!showUploadDropdown)}
            disabled={uploading}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-cobalt bg-cobalt/10 rounded-lg hover:bg-cobalt/20 transition-colors disabled:opacity-50 ${
              compact ? 'px-2 py-1' : ''
            }`}
            title={
              availableDocTypes.length > 0
                ? 'Attach one or more documents'
                : 'Open document upload options'
            }
          >
            {uploading ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Upload className="w-3.5 h-3.5" />
            )}
            {uploading ? 'Uploading...' : 'Upload'}
            <ChevronDown className="w-3 h-3" />
          </Button>

          {showUploadDropdown && (
            <>
              <div
                className="fixed inset-0 z-10"
                onClick={() => { setShowUploadDropdown(false); setPendingDropFiles(null); setPendingDropMatchingTypes([]); }}
              />
              <div className="absolute right-0 mt-1 w-52 bg-card rounded-xl shadow-lg border border-border py-1 z-20">
                <div className="px-3 py-1.5 text-xs text-muted-foreground border-b border-border">
                  {pendingDropFiles ? 'Upload as' : 'Select document type'}
                </div>
                {(pendingDropFiles ? pendingDropMatchingTypes : availableDocTypes).map((docType) => (
                  <Button
                    key={docType.type_id}
                    variant="ghost"
                    onClick={() => pendingDropFiles ? handleDropDocTypeSelect(docType.type_id) : handleUploadClick(docType.type_id)}
                    className="w-full flex items-center gap-2 px-3 py-2 text-sm text-foreground hover:bg-muted transition-colors"
                  >
                    <FileText className="w-4 h-4 text-muted-foreground shrink-0" />
                    <span className="flex-1 text-left text-sm">
                      {resolveDocTypeLabel(docType.display_name, docType.type_id)}
                    </span>
                  </Button>
                ))}
                {availableDocTypes.length === 0 && (
                  <div className="px-3 py-2 text-sm text-muted-foreground">
                    No document types available.
                  </div>
                )}
              </div>
            </>
          )}
        </div>

        <input
          ref={fileInputRef}
          type="file"
          multiple
          onChange={handleFileChange}
          className="hidden"
        />
      </div>

      {/* Error messages */}
      {(error || uploadError) && (
        <div className="flex items-center gap-2 text-sm text-destructive bg-destructive/10 px-3 py-2 rounded-lg">
          <AlertCircle className="w-4 h-4" />
          {error || uploadError}
          <Button variant="primary"
            onClick={() => {
              setError(null);
              setUploadError(null);
            }}
            className="ml-auto"
          >
            <X className="w-4 h-4" />
          </Button>
        </div>
      )}

      {/* Duplicate file warning */}
      {uploadWarning && (
        <div className="flex items-center gap-2 text-sm text-amber bg-amber/10 px-3 py-2 rounded-lg">
          <AlertCircle className="w-4 h-4 shrink-0" />
          {uploadWarning}
          <Button variant="primary" onClick={() => setUploadWarning(null)} className="ml-auto">
            <X className="w-4 h-4" />
          </Button>
        </div>
      )}

      {/* Document list — drag & drop zone */}
      <div
        className="relative"
        onDragEnter={handleDragEnter}
        onDragLeave={handleDragLeave}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
      >
      {docList.length === 0 ? (
        <div className={`flex flex-col items-center justify-center rounded-xl border-2 border-dashed transition-colors ${compact ? 'py-5' : 'py-8'} ${isDragOver ? 'border-cobalt bg-cobalt/5 scale-[1.01]' : pendingDropFiles ? 'border-cobalt/40 bg-cobalt/5' : 'border-gray-200 bg-gray-50/50 hover:border-gray-300'}`}>
          {pendingDropFiles ? (
            <>
              <Check className="w-7 h-7 text-cobalt mb-2" />
              <div className="space-y-1 w-full max-w-[220px]">
                {pendingDropFiles.slice(0, 3).map((f, i) => (
                  <div key={i} className="flex items-center gap-1.5 text-xs text-foreground">
                    <FileText className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
                    <span className="truncate flex-1">{f.name}</span>
                    <span className="text-[10px] text-muted-foreground shrink-0">{formatFileSize(f.size)}</span>
                  </div>
                ))}
                {pendingDropFiles.length > 3 && (
                  <p className="text-[10px] text-muted-foreground text-center">+{pendingDropFiles.length - 3} more</p>
                )}
              </div>
              <p className="text-xs text-cobalt font-medium mt-2">Select a document type from the dropdown above</p>
            </>
          ) : (
            <>
              <Upload className={`w-8 h-8 mb-2 ${isDragOver ? 'text-cobalt animate-bounce' : 'text-muted-foreground/40'}`} />
              <p className={`text-sm font-medium ${isDragOver ? 'text-cobalt' : 'text-muted-foreground'}`}>
                {isDragOver ? 'Drop files to upload' : 'Drag & drop files here'}
              </p>
              {!isDragOver && (
                <p className="text-xs text-muted-foreground mt-1">or use the Upload button above</p>
              )}
              {!isDragOver && availableDocTypes.length > 0 && (
                <p className="text-[11px] text-muted-foreground/60 mt-2">
                  Accepted: {availableDocTypes.flatMap(dt => dt.allowed_extensions).filter((v, i, a) => a.indexOf(v) === i).join(', ')}
                </p>
              )}
            </>
          )}
        </div>
      ) : (
        <div className="space-y-2 mb-3">
          {docList.map((doc) => {
            const docType = allDocTypes.find((dt) => dt.type_id === doc.type);
            const hasActionResults = doc.action_results && doc.action_results.actions_completed > 0;
            const hasActionErrors = doc.action_results && doc.action_results.actions_failed > 0;

            const isActivePreview = doc.id === activePreviewId;

            return (
              <div
                key={doc.id}
                className={`rounded-lg transition-colors group ${
                  isActivePreview
                    ? 'bg-cobalt/5 ring-1 ring-cobalt/40'
                    : 'bg-muted hover:bg-muted/70'
                }`}
              >
                {/* Main row — click loads the doc into the preview panel (desktop). */}
                <div
                  onClick={() => handlePreviewOpen(doc)}
                  className={`flex items-center gap-3 p-3 lg:cursor-pointer ${compact ? 'p-2' : ''}`}
                >
                  {/* File icon */}
                  <div className="flex-shrink-0">{getFileIcon(doc.filename)}</div>

                  {/* File info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span
                        className={`font-medium text-foreground truncate ${
                          compact ? 'text-sm' : ''
                        }`}
                        title={doc.filename}
                      >
                        {doc.filename}
                      </span>
                      {docType && (
                        <Badge variant="default" className="flex-shrink-0">
                          {resolveDocTypeLabel(docType.display_name, docType.type_id)}
                        </Badge>
                      )}
                      {/* Agent-processing status */}
                      {doc.status === 'PROCESSING' && (
                        <span className="flex items-center gap-1 text-xs text-cobalt flex-shrink-0" title="Agent is processing this document">
                          <Loader2 className="w-3 h-3 animate-spin" />
                          Processing
                        </span>
                      )}
                      {doc.status === 'PROCESSED' && (
                        <span className="flex items-center gap-1 text-xs text-emerald flex-shrink-0" title="Agent processing complete">
                          <Check className="w-3 h-3" />
                          Processed
                        </span>
                      )}
                      {doc.status === 'FAILED' && (
                        <span
                          className="flex items-center gap-1 text-xs text-rose flex-shrink-0"
                          title={doc.failure_reason || 'Agent processing failed'}
                        >
                          <AlertCircle className="w-3 h-3" />
                          Failed
                        </span>
                      )}
                      {/* Action results indicator */}
                      {hasActionResults && !hasActionErrors && (
                        <span
                          className="flex items-center gap-1 text-xs text-emerald"
                          title={`${doc.action_results!.actions_completed} action(s) completed`}
                        >
                          <Zap className="w-3 h-3" />
                          {doc.action_results!.actions_completed} action{doc.action_results!.actions_completed !== 1 ? 's' : ''}
                        </span>
                      )}
                      {hasActionErrors && (
                        <span
                          className="flex items-center gap-1 text-xs text-rose"
                          title={`${doc.action_results!.actions_failed} action(s) failed`}
                        >
                          <XCircle className="w-3 h-3" />
                          {doc.action_results!.actions_failed} failed
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-3 text-xs text-muted-foreground mt-0.5">
                      <span>{formatFileSize(doc.size_bytes)}</span>
                      <span title={`Uploaded on ${new Date(doc.uploaded_at).toLocaleString()}`}>
                        {formatDate(doc.uploaded_at)}
                      </span>
                      {/* Show created entity count */}
                      {doc.action_results?.created_entity_ids && doc.action_results.created_entity_ids.length > 0 && (
                        <span className="text-cobalt">
                          {doc.action_results.created_entity_ids.length} entity created
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <Button
                      variant="ghost"
                      onClick={(e) => {
                        e.stopPropagation();
                        handlePreviewOpen(doc);
                      }}
                      className="hidden lg:inline-flex p-1.5 text-muted-foreground hover:text-cobalt hover:bg-cobalt/10 rounded transition-colors"
                      title="Preview document"
                    >
                      <Eye className="w-4 h-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDownload(doc);
                      }}
                      className="p-1.5 text-muted-foreground hover:text-cobalt hover:bg-cobalt/10 rounded transition-colors"
                      title="Download"
                    >
                      <Download className="w-4 h-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      onClick={(e) => {
                        e.stopPropagation();
                        setDeleteConfirm(doc);
                      }}
                      className="p-1.5 text-muted-foreground hover:text-rose hover:bg-rose/10 rounded transition-colors"
                      title="Delete this document"
                    >
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </div>
                </div>

                {/* Action results detail row (if errors) */}
                {hasActionErrors && doc.action_results?.error && (
                  <div className="px-3 pb-2 ml-7">
                    <div className="text-xs text-destructive bg-destructive/10 px-2 py-1 rounded">
                      {doc.action_results.error}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Delete Confirmation */}
      <ConfirmDialog
        open={deleteConfirm !== null}
        onClose={() => setDeleteConfirm(null)}
        onConfirm={handleDelete}
        title="Delete Document"
        message={`Are you sure you want to delete "${deleteConfirm?.filename}"? This action cannot be undone.`}
        confirmLabel="Delete"
        variant="danger"
        loading={deleting}
      />

      {/* Drop zone below docs */}
      {docList.length > 0 && (
        <div className={`flex flex-col items-center justify-center rounded-xl border-2 border-dashed transition-colors py-4 ${isDragOver ? 'border-cobalt bg-cobalt/5' : pendingDropFiles ? 'border-cobalt/40 bg-cobalt/5' : 'border-gray-200 bg-gray-50/50 hover:border-gray-300'}`}>
          {pendingDropFiles ? (
            <>
              <Check className="w-5 h-5 text-cobalt mb-1.5" />
              <div className="space-y-0.5 w-full max-w-[220px]">
                {pendingDropFiles.slice(0, 3).map((f, i) => (
                  <div key={i} className="flex items-center gap-1.5 text-[11px] text-foreground">
                    <FileText className="w-3 h-3 text-muted-foreground shrink-0" />
                    <span className="truncate flex-1">{f.name}</span>
                    <span className="text-[10px] text-muted-foreground shrink-0">{formatFileSize(f.size)}</span>
                  </div>
                ))}
                {pendingDropFiles.length > 3 && (
                  <p className="text-[10px] text-muted-foreground text-center">+{pendingDropFiles.length - 3} more</p>
                )}
              </div>
              <p className="text-[10px] text-cobalt font-medium mt-1.5">Select a document type from the dropdown above</p>
            </>
          ) : (
            <>
              <Upload className={`w-6 h-6 mb-1.5 ${isDragOver ? 'text-cobalt animate-bounce' : 'text-muted-foreground/40'}`} />
              <p className={`text-xs font-medium ${isDragOver ? 'text-cobalt' : 'text-muted-foreground'}`}>
                {isDragOver ? 'Drop files to upload' : 'Drag & drop files here'}
              </p>
              {!isDragOver && availableDocTypes.length > 0 && (
                <p className="text-[10px] text-muted-foreground/50 mt-1">
                  {availableDocTypes.flatMap(dt => dt.allowed_extensions).filter((v, i, a) => a.indexOf(v) === i).join(', ')}
                </p>
              )}
            </>
          )}
        </div>
      )}
      </div>{/* end drag zone */}

      <MobileDocumentPreviewModal
        doc={mobilePreviewDoc}
        onClose={() => setMobilePreviewDoc(null)}
        onDownload={handleDownload}
      />
    </div>
  );
}

function MobileDocumentPreviewModal({
  doc,
  onClose,
  onDownload,
}: {
  doc: DocumentMetadata | null;
  onClose: () => void;
  onDownload: (doc: DocumentMetadata) => Promise<void>;
}) {
  const { loading, error, blobUrl, csvRows, excelBlob, excelRendering, excelContainerRef } =
    useDocumentPreview(doc);

  return (
    <Modal
      open={doc !== null}
      onClose={onClose}
      title={doc?.filename ?? 'Preview'}
      size="full"
    >
      {doc && (
        <div className="space-y-4 lg:hidden">
          <div className="flex items-center justify-end">
            <Button variant="ghost" onClick={() => void onDownload(doc)} title="Download">
              <Download className="w-4 h-4" />
              Download
            </Button>
          </div>

          <div className="h-[70vh] overflow-auto rounded-xl border border-border bg-muted/40">
            {loading ? (
              <div className="flex h-full items-center justify-center">
                <Loader2 className="h-8 w-8 animate-spin text-cobalt" />
              </div>
            ) : error ? (
              <div className="flex items-center gap-2 px-4 py-4 text-sm text-destructive">
                <AlertCircle className="h-4 w-4 shrink-0" />
                {error}
              </div>
            ) : csvRows ? (
              <div className="h-full w-full overflow-auto bg-card text-foreground">
                <table className="border-collapse text-sm">
                  <tbody>
                    {csvRows.map((row, ri) => (
                      <tr key={ri}>
                        {row.map((cell, ci) => (
                          <td
                            key={ci}
                            className={`whitespace-nowrap border border-border px-2 py-1 ${
                              ri === 0 ? 'bg-muted font-semibold' : ''
                            }`}
                          >
                            {cell}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : excelBlob ? (
              <div className="relative h-full w-full bg-card">
                <div ref={excelContainerRef} className="h-full w-full" />
                {excelRendering && (
                  <div className="absolute inset-0 flex items-center justify-center bg-card/70">
                    <Loader2 className="h-8 w-8 animate-spin text-cobalt" />
                  </div>
                )}
              </div>
            ) : blobUrl ? (
              <iframe src={blobUrl} className="h-full w-full" title={`Preview ${doc.filename}`} />
            ) : null}
          </div>
        </div>
      )}
    </Modal>
  );
}
