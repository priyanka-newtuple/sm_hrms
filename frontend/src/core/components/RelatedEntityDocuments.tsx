import { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertCircle, Download, Eye, FileText, FolderOpen, Loader2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import Badge from './Badge';
import { documents } from '../services/api';
import { downloadDocument } from '../services/api/documents';
import type { DocumentMetadata, RelatedEntityFile, RelatedEntityFileGroup } from '../types';
import { getFileIcon } from '../hooks/useDocumentPreview';
import { useDocumentPreviewStore } from '../stores/documentPreviewStore';

// Background poll so connector-generated related files appear without a reload.
const RELATED_POLL_INTERVAL_MS = 20000;

function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

function formatDate(dateString: string): string {
  return new Date(dateString).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

function relatedFileToDocument(file: RelatedEntityFile): DocumentMetadata {
  return {
    id: file.file_id,
    type: file.type_id,
    filename: file.filename,
    storage_key: file.storage_key,
    content_type: file.content_type,
    size_bytes: file.size_bytes,
    uploaded_at: file.created_at,
    uploaded_by: file.uploaded_by || 'unknown',
    metadata: file.metadata ?? {},
  };
}

export default function RelatedEntityDocuments({ entityId }: { entityId: string }) {
  const [groups, setGroups] = useState<RelatedEntityFileGroup[]>([]);
  const [configured, setConfigured] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const setPreviewDocs = useDocumentPreviewStore((s) => s.setDocs);
  const setPreviewActive = useDocumentPreviewStore((s) => s.setActive);

  const allDocs = useMemo(
    () => groups.flatMap((group) => group.files.map(relatedFileToDocument)),
    [groups],
  );

  const fetchRelatedFiles = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await documents.listRelated(entityId);
      setConfigured(response.configured);
      setGroups(response.groups ?? []);
    } catch (e) {
      setConfigured(false);
      setGroups([]);
      setError(e instanceof Error ? e.message : 'Failed to load related files');
    } finally {
      setLoading(false);
    }
  }, [entityId]);

  useEffect(() => {
    void fetchRelatedFiles();
  }, [fetchRelatedFiles]);

  // Silent refresh (no loading flicker) for the background poll.
  const refreshRelatedFilesSilently = useCallback(async () => {
    try {
      const response = await documents.listRelated(entityId);
      setConfigured(response.configured);
      setGroups(response.groups ?? []);
    } catch (e) {
      if (import.meta.env.DEV) console.debug('Related files poll refresh failed', e);
    }
  }, [entityId]);

  useEffect(() => {
    const timer = setInterval(refreshRelatedFilesSilently, RELATED_POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [refreshRelatedFilesSilently]);

  const handlePreview = (file: RelatedEntityFile) => {
    const doc = relatedFileToDocument(file);
    // Stamp the viewed entity as context and mark the docs as related-sourced
    // so EntityDocuments' own-docs refresh won't evict this preview.
    setPreviewDocs(allDocs.length ? allDocs : [doc], entityId, 'related');
    setPreviewActive(doc.id);
  };

  const handleDownload = async (file: RelatedEntityFile) => {
    try {
      await downloadDocument(relatedFileToDocument(file));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Download failed');
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-4">
        <Loader2 className="w-5 h-5 text-cobalt animate-spin" />
      </div>
    );
  }

  if (!configured) {
    return null;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <FolderOpen className="w-4 h-4 text-muted-foreground" />
          <span className="font-medium text-foreground">Related files</span>
          <Badge variant="default">{allDocs.length}</Badge>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">
          <AlertCircle className="w-4 h-4" />
          {error}
        </div>
      )}

      {groups.length === 0 ? (
        <div className="py-6 text-center">
          <FileText className="mx-auto mb-2 h-10 w-10 text-muted-foreground/40" />
          <p className="text-sm text-muted-foreground">No related files available</p>
        </div>
      ) : (
        <div className="space-y-3">
          {groups.map((group) => (
            <div key={`${group.relation_def_id}:${group.source_entity_id}`} className="space-y-2">
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <span className="font-medium text-foreground">{group.source_entity_label}</span>
                <Badge variant="default">{group.relation_type === 'REFERENCE' ? 'Live' : 'Snapshot'}</Badge>
              </div>
              {group.files.map((file) => (
                <div
                  key={file.file_id}
                  className="group rounded-lg bg-muted transition-colors hover:bg-muted/70"
                >
                  <div
                    onClick={() => handlePreview(file)}
                    className="flex items-center gap-3 p-3 lg:cursor-pointer"
                  >
                    <div className="shrink-0">{getFileIcon(file.filename)}</div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="truncate font-medium text-foreground" title={file.filename}>
                          {file.filename}
                        </span>
                        <Badge variant="default">{file.type_id}</Badge>
                      </div>
                      <div className="mt-0.5 flex items-center gap-3 text-xs text-muted-foreground">
                        <span>{formatFileSize(file.size_bytes)}</span>
                        <span title={`Uploaded on ${new Date(file.created_at).toLocaleString()}`}>
                          {formatDate(file.created_at)}
                        </span>
                        {file.uploaded_by && <span>{file.uploaded_by}</span>}
                      </div>
                    </div>
                    <div className="flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                      <Button
                        variant="ghost"
                        onClick={(e) => {
                          e.stopPropagation();
                          handlePreview(file);
                        }}
                        className="hidden rounded p-1.5 text-muted-foreground transition-colors hover:bg-cobalt/10 hover:text-cobalt lg:inline-flex"
                        title="Preview document"
                      >
                        <Eye className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        onClick={(e) => {
                          e.stopPropagation();
                          void handleDownload(file);
                        }}
                        className="rounded p-1.5 text-muted-foreground transition-colors hover:bg-cobalt/10 hover:text-cobalt"
                        title="Download"
                      >
                        <Download className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
