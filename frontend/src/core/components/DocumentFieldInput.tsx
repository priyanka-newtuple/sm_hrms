/**
 * DocumentFieldInput
 *
 * A `document` field's value is a list of file ids. This uploads files against
 * the field's configured file type and keeps that list, so a document becomes
 * something a form captures rather than a separate panel bolted onto a record.
 *
 * Where the bytes land is not decided here: the file type carries a
 * `metadata.storage_provider`, so pointing a field at an S3-backed type is what
 * sends its uploads to S3. Nothing in this component is S3-specific.
 *
 * Upload happens immediately on pick — a file has to exist before its id can go
 * in the list, and the entity write rejects an id it can't find. Removing only
 * drops the id from the field; the uploaded file itself is left alone, since
 * other records or an earlier version of this one may still reference it.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Download, Eye, FileText, Loader2, Paperclip, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { documents } from '../services/api';
import { downloadDocument } from '../services/api/documents';
import { getApiErrorMessage } from '../services/api/client';
import { useDocumentTypes } from '../hooks/useDocumentTypes';
import { useDocumentPreviewStore } from '../stores/documentPreviewStore';
import type { DocumentMetadata, FormField } from '../types';

/** What we can show about one referenced file. Kept local: the field only ever
 *  stores the id, so everything else is looked up and may be missing. */
interface FileSummary {
  fileId: string;
  filename: string;
  sizeBytes?: number;
  missing?: boolean;
  /** The resolved record, kept so downloading uses the real thing rather than
   *  a fabricated stand-in. Absent when the lookup failed. */
  meta?: DocumentMetadata;
}

/** The shared preview panel is desktop-only, the same threshold
 *  EntityDocuments uses before falling back to its mobile viewer. */
function isNarrowViewport(): boolean {
  return typeof window !== 'undefined' && window.innerWidth < 1024;
}

/** The preview panel and the download helper only need an id and a filename
 *  (plus an optional source_url), so a file can be previewed before its full
 *  record has been fetched — and even if that fetch failed. Gating the trigger
 *  on the lookup is what previously left the filename inert. */
function toPreviewDoc(
  fileId: string,
  filename: string,
  meta?: DocumentMetadata | null,
): DocumentMetadata {
  if (meta) return meta;
  return {
    id: fileId,
    type: '',
    filename: filename || fileId,
    storage_key: '',
    content_type: '',
    size_bytes: 0,
    uploaded_at: new Date().toISOString(),
    uploaded_by: '',
    metadata: {},
  };
}

function formatSize(bytes?: number): string {
  if (!bytes || bytes <= 0) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

interface DocumentFieldInputProps {
  field: FormField;
  value: unknown;
  onChange: (value: unknown) => void;
  disabled?: boolean;
  invalid?: boolean;
  /** The record these files belong to. Absent while it is still being created,
   *  in which case uploads are stored unowned and the ids still save with the
   *  record — the entity write only requires that each file exists. */
  entityId?: string;
  /** Only the pipeline slide-over has a shared document preview surface. */
  showPreview?: boolean;
}

export default function DocumentFieldInput({
  field,
  value,
  onChange,
  disabled,
  invalid,
  entityId,
  showPreview = false,
}: DocumentFieldInputProps) {
  // Memoized so the upload callback and the lookup effect below don't see a
  // fresh array on every render.
  const fileIds = useMemo(
    () =>
      Array.isArray(value)
        ? (value as unknown[]).filter(
            (id): id is string => typeof id === 'string' && id.trim() !== '',
          )
        : [],
    [value],
  );
  const typeId = field.document_config?.type_id ?? '';
  const allowMultiple = field.document_config?.multiple !== false;

  const { documentTypes, loading: typesLoading, getDocumentType, isFileValid } = useDocumentTypes();
  // A field should name its document type, but one configured before that was
  // possible (or created straight through the API) won't. Rather than leave the
  // field unusable, let the type be chosen here for this upload.
  const [chosenTypeId, setChosenTypeId] = useState('');
  const effectiveTypeId = typeId || chosenTypeId;
  const documentType = effectiveTypeId ? getDocumentType(effectiveTypeId) : undefined;

  // Reuses the platform's own preview panel rather than a second viewer.
  // Published as 'related' so EntityDocuments' 20s poll of the entity's owned
  // list cannot evict an open field preview (see publishOwnedDocs).
  const setPreviewDocs = useDocumentPreviewStore((s) => s.setDocs);
  const setPreviewActive = useDocumentPreviewStore((s) => s.setActive);

  const [summaries, setSummaries] = useState<Record<string, FileSummary>>({});
  // Read inside the upload loop, which appends several files in one pass and
  // must see the summaries added earlier in that same pass.
  const summariesRef = useRef<Record<string, FileSummary>>(summaries);
  summariesRef.current = summaries;
  // `fileIds` is rebuilt every render, so the lookup effect keys off the joined
  // ids instead of the array's identity, and tracks in-flight ids so a re-render
  // mid-fetch doesn't request the same file twice.
  const fileIdsKey = fileIds.join('|');
  const inFlight = useRef<Set<string>>(new Set());
  // Mirrors the live value. Appending from the captured `fileIds` would undo a
  // removal made while an upload was in flight, resurrecting the removed id.
  const fileIdsRef = useRef<string[]>(fileIds);
  fileIdsRef.current = fileIds;
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Names come from the filehandler, one lookup per id. A file that has been
  // deleted out from under the field is marked rather than hidden, so the stale
  // reference is visible instead of silently disappearing.
  useEffect(() => {
    const ids = fileIdsKey ? fileIdsKey.split('|') : [];
    const unknown = ids.filter((id) => !summaries[id] && !inFlight.current.has(id));
    if (unknown.length === 0) return;
    unknown.forEach((id) => inFlight.current.add(id));
    void Promise.all(
      unknown.map(async (id): Promise<FileSummary> => {
        try {
          const meta = await documents.getMetadata('', id);
          return {
            fileId: id,
            filename: String(meta.filename || id),
            sizeBytes: typeof meta.size_bytes === 'number' ? meta.size_bytes : undefined,
            meta,
          };
        } catch {
          return { fileId: id, filename: id, missing: true };
        }
      }),
    ).then((resolved) => {
      resolved.forEach((summary) => inFlight.current.delete(summary.fileId));
      // Not discarded on unmount/key change: a file's name doesn't depend on
      // which ids the field currently holds, so a result that arrives after the
      // list changed is still correct. Bailing here used to drop it while the
      // id stayed marked resolved-or-in-flight, leaving a bare UUID on screen.
      setSummaries((prev) => {
        const next = { ...prev };
        for (const summary of resolved) next[summary.fileId] = summary;
        return next;
      });
    });
  }, [fileIdsKey, summaries]);

  /** Show one of this field's files in the shared preview panel. */
  const openPreview = useCallback(
    (meta: DocumentMetadata, known: Record<string, FileSummary>) => {
      const docs = fileIdsRef.current.map((id) =>
        toPreviewDoc(id, known[id]?.filename ?? id, known[id]?.meta),
      );
      setPreviewDocs(docs.length > 0 ? docs : [meta], entityId ?? null, 'related');
      setPreviewActive(meta.id);
    },
    [entityId, setPreviewDocs, setPreviewActive],
  );

  const handlePick = useCallback(
    async (picked: FileList | null) => {
      if (!picked || picked.length === 0) return;
      if (!effectiveTypeId) {
        setError('Choose a document type first.');
        return;
      }
      setUploading(true);
      setError(null);
      try {
        for (const file of Array.from(picked)) {
          const check = isFileValid(effectiveTypeId, file);
          if (!check.valid) {
            setError(check.error ?? `${file.name} is not allowed for this document type`);
            continue;
          }
          const uploaded = await documents.upload(
            entityId ?? '',
            effectiveTypeId,
            file,
            false,
            field.id,
          );
          if (!uploaded.document_id) continue;
          // Metadata is fetched now rather than left to the lazy effect, so the
          // file can be previewed the moment it lands.
          let meta: DocumentMetadata | undefined;
          try {
            meta = await documents.getMetadata('', uploaded.document_id);
          } catch {
            // Preview is a nicety; a failed lookup must not fail the upload.
          }
          const summary: FileSummary = {
            fileId: uploaded.document_id,
            filename: meta?.filename ?? uploaded.filename,
            sizeBytes: meta?.size_bytes ?? uploaded.size_bytes,
            meta,
          };
          setSummaries((prev) => ({ ...prev, [uploaded.document_id]: summary }));
          // Recorded per file, not once at the end: a later file failing would
          // otherwise leave the ones already uploaded stored but unreferenced,
          // with no way for the user to recover them. Read through the ref so a
          // removal made mid-upload is respected. Deduped because uploading an
          // identical file can hand back an id already in the list, which the
          // backend rejects.
          const current = fileIdsRef.current;
          const next = allowMultiple ? [...current, uploaded.document_id] : [uploaded.document_id];
          const deduped = [...new Set(next)];
          fileIdsRef.current = deduped;
          onChange(deduped);
          if (showPreview && !isNarrowViewport()) {
            openPreview(toPreviewDoc(summary.fileId, summary.filename, meta), {
              ...summariesRef.current,
              [summary.fileId]: summary,
            });
          }
        }
      } catch (e) {
        setError(getApiErrorMessage(e, 'Failed to upload'));
      } finally {
        setUploading(false);
        if (inputRef.current) inputRef.current.value = '';
      }
    },
    [effectiveTypeId, entityId, field.id, allowMultiple, onChange, isFileValid, openPreview, showPreview],
  );

  const handleRemove = (fileId: string) => onChange(fileIds.filter((id) => id !== fileId));

  const accept = documentType?.allowed_extensions?.length
    ? documentType.allowed_extensions.join(',')
    : undefined;

  return (
    <div className={`rounded-xl border px-4 py-3 ${invalid ? 'border-destructive' : 'border-border'}`}>
      {fileIds.length > 0 && (
        <ul className="mb-2 space-y-1.5">
          {fileIds.map((id) => {
            const summary = summaries[id];
            return (
              <li key={id} className="flex items-center gap-2 rounded-lg bg-muted/50 px-3 py-2 text-sm">
                <FileText className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
                {!summary?.missing && showPreview && !isNarrowViewport() ? (
                  <button
                    type="button"
                    onClick={() =>
                      openPreview(
                        toPreviewDoc(id, summary?.filename ?? id, summary?.meta),
                        summaries,
                      )
                    }
                    className="min-w-0 flex-1 truncate text-left text-foreground hover:underline"
                    title="Preview"
                  >
                    {summary?.filename ?? id}
                  </button>
                ) : (
                  <span className={`min-w-0 flex-1 truncate ${summary?.missing ? 'text-destructive' : 'text-foreground'}`}>
                    {summary?.filename ?? id}
                    {summary?.missing && <span className="ml-1 text-xs">(file not found)</span>}
                  </span>
                )}
                {summary?.sizeBytes ? (
                  <span className="flex-shrink-0 text-xs text-muted-foreground">
                    {formatSize(summary.sizeBytes)}
                  </span>
                ) : null}
                {!summary?.missing && showPreview && !isNarrowViewport() && (
                  <button
                    type="button"
                    onClick={() =>
                      openPreview(
                        toPreviewDoc(id, summary?.filename ?? id, summary?.meta),
                        summaries,
                      )
                    }
                    className="flex-shrink-0 text-muted-foreground transition-colors hover:text-foreground"
                    title="Preview"
                    aria-label={`Preview ${summary?.filename ?? id}`}
                  >
                    <Eye className="h-3.5 w-3.5" />
                  </button>
                )}
                {!summary?.missing && (
                  <button
                    type="button"
                    onClick={() =>
                      void downloadDocument(toPreviewDoc(id, summary?.filename ?? id, summary?.meta))
                    }
                    className="flex-shrink-0 text-muted-foreground transition-colors hover:text-foreground"
                    title="Download"
                  >
                    <Download className="h-3.5 w-3.5" />
                  </button>
                )}
                {!disabled && !uploading && (
                  <button
                    type="button"
                    onClick={() => handleRemove(id)}
                    className="flex-shrink-0 text-muted-foreground transition-colors hover:text-destructive"
                    title="Remove from this field"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}

      <input
        ref={inputRef}
        type="file"
        multiple={allowMultiple}
        accept={accept}
        className="hidden"
        onChange={(e) => void handlePick(e.target.files)}
      />

      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={() => inputRef.current?.click()}
          // Held until the types are in: isFileValid falls back to a .pdf/10MB
          // default when the type isn't loaded yet, which would reject a
          // perfectly valid file with a misleading message.
          disabled={disabled || uploading || typesLoading || !effectiveTypeId}
          title={!effectiveTypeId ? 'Choose a document type first' : undefined}
        >
          {uploading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Paperclip className="h-3.5 w-3.5" />}
          {fileIds.length > 0 && allowMultiple ? 'Add file' : 'Upload file'}
        </Button>
        {documentType && (
          <span className="text-xs text-muted-foreground">
            {documentType.display_name}
            {documentType.allowed_extensions?.length
              ? ` · ${documentType.allowed_extensions.join(' ')}`
              : ''}
            {documentType.max_size_mb ? ` · up to ${documentType.max_size_mb} MB` : ''}
          </span>
        )}
        {!typeId && !disabled && (
          <select
            value={chosenTypeId}
            onChange={(e) => setChosenTypeId(e.target.value)}
            className="h-8 rounded-lg border border-border px-2 text-xs focus:border-cobalt focus:outline-none focus:ring-2 focus:ring-cobalt/20"
            title="This field has no document type configured"
          >
            <option value="">Select a document type…</option>
            {documentTypes.map((type) => (
              <option key={type.type_id} value={type.type_id}>
                {type.display_name}
              </option>
            ))}
          </select>
        )}
      </div>

      {error && <p className="mt-2 text-xs text-destructive">{error}</p>}
    </div>
  );
}
