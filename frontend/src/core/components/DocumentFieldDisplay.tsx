/**
 * DocumentFieldDisplay
 *
 * Read-only view of a `document` field. The field stores only file ids, so the
 * filenames are looked up — without this the record's detail view would show a
 * column of raw UUIDs.
 */

import { useEffect, useRef, useState } from 'react';
import { Download, Eye, FileText } from 'lucide-react';
import { documents } from '../services/api';
import { downloadDocument } from '../services/api/documents';
import { useDocumentPreviewStore } from '../stores/documentPreviewStore';
import type { DocumentMetadata } from '../types';

/** The preview panel and download helper need only an id and filename, so a
 *  file stays previewable before (or without) its full record being fetched. */
function toPreviewDoc(
  fileId: string,
  meta?: DocumentMetadata | null,
): DocumentMetadata {
  if (meta) return meta;
  return {
    id: fileId,
    type: '',
    filename: fileId,
    storage_key: '',
    content_type: '',
    size_bytes: 0,
    uploaded_at: new Date().toISOString(),
    uploaded_by: '',
    metadata: {},
  };
}

/** Desktop-only, matching EntityDocuments' own threshold. */
function isNarrowViewport(): boolean {
  return typeof window !== 'undefined' && window.innerWidth < 1024;
}

export default function DocumentFieldDisplay({
  value,
  entityId,
  showPreview = false,
}: {
  value: unknown;
  entityId?: string;
  /** Preview panel is available only from the pipeline slide-over. */
  showPreview?: boolean;
}) {
  const fileIds = Array.isArray(value)
    ? (value as unknown[]).filter((id): id is string => typeof id === 'string' && id.trim() !== '')
    : [];
  const key = fileIds.join('|');

  // Published as 'related' so the entity's own document poll can't evict an
  // open field preview.
  const setPreviewDocs = useDocumentPreviewStore((s) => s.setDocs);
  const setPreviewActive = useDocumentPreviewStore((s) => s.setActive);

  const [metas, setMetas] = useState<Record<string, DocumentMetadata | null>>({});
  const inFlight = useRef<Set<string>>(new Set());

  useEffect(() => {
    const ids = key ? key.split('|') : [];
    const unknown = ids.filter((id) => !(id in metas) && !inFlight.current.has(id));
    if (unknown.length === 0) return;
    unknown.forEach((id) => inFlight.current.add(id));
    void Promise.all(
      unknown.map(async (id) => {
        try {
          return [id, await documents.getMetadata('', id)] as const;
        } catch {
          // A deleted file still leaves its id on the record; null marks it so
          // the stale reference is visible rather than silently dropped.
          return [id, null] as const;
        }
      }),
    ).then((resolved) => {
      resolved.forEach(([id]) => inFlight.current.delete(id));
      // Kept even if the id list changed meanwhile: a filename is not scoped to
      // the current list, and discarding it would leave a bare UUID on screen
      // with the id already marked resolved.
      setMetas((prev) => ({ ...prev, ...Object.fromEntries(resolved) }));
    });
  }, [key, metas]);

  // Match the general Documents panel: when an entity opens with only
  // field-linked files, make the first resolved field list available to the
  // shared preview panel. Do not replace an already selected document (for
  // example, a general or another field document the user chose).
  useEffect(() => {
    if (!showPreview || !entityId || fileIds.length === 0 || !fileIds.every((id) => id in metas)) return;
    const currentPreview = useDocumentPreviewStore.getState();
    if (currentPreview.contextEntityId === entityId && currentPreview.docs.length > 0) return;
    setPreviewDocs(
      fileIds.map((id) => toPreviewDoc(id, metas[id])),
      entityId,
      'related',
    );
  }, [entityId, key, fileIds, metas, setPreviewDocs, showPreview]);

  if (fileIds.length === 0) {
    return (
      <div className="min-h-9 rounded-lg border border-border bg-muted px-3 py-2 text-sm text-muted-foreground">
        No files
      </div>
    );
  }

  return (
    <ul className="space-y-1.5">
      {fileIds.map((id) => {
        const meta = metas[id];
        return (
          <li
            key={id}
            className="flex items-center gap-2 rounded-lg border border-border bg-muted px-3 py-2 text-sm"
          >
            <FileText className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
            <span
              className={`min-w-0 flex-1 truncate ${meta === null ? 'text-destructive' : 'text-foreground'}`}
            >
              {meta ? meta.filename : id}
              {meta === null && <span className="ml-1 text-xs">(file not found)</span>}
            </span>
            {showPreview && meta !== null && !isNarrowViewport() && (
              <button
                type="button"
                onClick={() => {
                  const docs = fileIds.map((fid) => toPreviewDoc(fid, metas[fid]));
                  setPreviewDocs(docs, entityId ?? null, 'related');
                  setPreviewActive(id);
                }}
                className="flex-shrink-0 text-muted-foreground transition-colors hover:text-foreground"
                title="Preview"
              >
                <Eye className="h-3.5 w-3.5" />
              </button>
            )}
            {meta !== null && (
              <button
                type="button"
                onClick={() => void downloadDocument(toPreviewDoc(id, meta))}
                className="flex-shrink-0 text-muted-foreground transition-colors hover:text-foreground"
                title="Download"
              >
                <Download className="h-3.5 w-3.5" />
              </button>
            )}
          </li>
        );
      })}
    </ul>
  );
}
