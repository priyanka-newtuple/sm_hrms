import type {
  DocumentMetadata,
  DocumentUploadResponse,
  RelatedEntityFileListResponse,
} from '../../types';
import { API_BASE, buildAuthHeaders, getCurrentOrganizationId, request, uploadFile } from './client';
import { mapFileRecordToDocument } from './internal';

export type DownloadUrlResult = { url: string; provider: string; expires_in: number | null };

export const documents = {
  upload: async (
    entityId: string,
    documentType: string,
    file: File,
    skipExtraction = false,
    fieldKey?: string,
  ): Promise<DocumentUploadResponse> => {
    // Upload only stores the file. Extraction is now driven by an agent calling
    // the read_document tool — filehandler no longer dispatches a processing job.
    void skipExtraction;
    const extraParams: Record<string, string> = {};
    if (entityId) extraParams['owner_entity_id'] = entityId;
    // Filehandler persists this metadata alongside the upload. It lets downstream
    // consumers distinguish a document captured by a specific form field from a
    // document added through the record's general Documents panel.
    if (fieldKey?.trim()) extraParams['metadata'] = JSON.stringify({ field_key: fieldKey.trim() });
    const uploaded = await uploadFile(documentType, file, extraParams);
    const wasDeduped = Boolean(uploaded.auto_deduplicated);

    return {
      document_id: String(uploaded.file_id || ''),
      filename: String(uploaded.filename || file.name),
      storage_key: String(uploaded.storage_key || ''),
      content_type: String(uploaded.content_type || file.type),
      size_bytes: Number(uploaded.size_bytes || file.size),
      entity_id: entityId,
      document_type: documentType,
      auto_deduplicated: wasDeduped,
    };
  },

  list: (entityId: string | null, documentType?: string) => {
    const organizationId = getCurrentOrganizationId();
    return request<{ count: number; items: Record<string, unknown>[] }>('/filehandler/list', {
      method: 'POST',
      body: JSON.stringify({
        organization_id: organizationId,
        type_id: documentType || undefined,
        owner_entity_id: entityId,
      }),
    }).then((response) => {
      const items = response.items.map(mapFileRecordToDocument);
      return { items, total: items.length };
    });
  },

  listRelated: (entityId: string) =>
    request<RelatedEntityFileListResponse>(
      `/entity-records/${encodeURIComponent(entityId)}/related-files`
    ),

  getMetadata: (entityId: string, documentId: string) => {
    void entityId;
    return request<Record<string, unknown>>(`/filehandler/${encodeURIComponent(documentId)}`).then(mapFileRecordToDocument);
  },

  /**
   * Get a URL to fetch raw file bytes from.
   *
   * For Azure-stored files the backend returns a 15-minute SAS URL that the
   * browser can use to stream directly from Azure Blob Storage (no auth headers
   * needed — the SAS token is embedded in the URL). For local files the backend
   * returns the relative /download path; the caller should fall back to
   * `fetchContent` for local files.
   *
   * @param documentId - The file ID to resolve.
   * @returns `{ url, provider, expires_in }` — provider is "azure" or "local".
   */
  getDownloadUrl: (documentId: string): Promise<DownloadUrlResult> => {
    return request(`/filehandler/${encodeURIComponent(documentId)}/download-url`);
  },

  /**
   * Fetch raw file content as a Blob for preview or download.
   *
   * Uses raw `fetch()` (bypassing `request()`) because the shared helper
   * calls `.json()` internally and cannot return binary content.
   *
   * @param documentId - The file ID to fetch.
   * @returns The Blob payload and its content-type header.
   * @throws Error if the HTTP response is not OK.
   */
  fetchContent: async (documentId: string): Promise<{ blob: Blob; contentType: string }> => {
    const res = await fetch(`${API_BASE}/filehandler/${encodeURIComponent(documentId)}/download`, {
      headers: buildAuthHeaders(),
    });
    if (!res.ok) throw new Error(`Failed to fetch file: ${res.status}`);
    const blob = await res.blob();
    const contentType = res.headers.get('content-type') || blob.type || 'application/octet-stream';
    return { blob, contentType };
  },

  getPreviewUrl: (entityId: string, documentId: string): string => {
    void entityId;
    return `${API_BASE}/filehandler/${encodeURIComponent(documentId)}/download`;
  },

  getPreviewUrlByKey: (storageKey: string): string => {
    return `${API_BASE}/documents/preview/${encodeURIComponent(storageKey)}`;
  },

  delete: (entityId: string, documentId: string, deleteFile = true) => {
    void entityId;
    void deleteFile;
    return request<void>(`/filehandler/${encodeURIComponent(documentId)}`, { method: 'DELETE' }).then(() => ({
      success: true,
      document_id: documentId,
      message: 'Deleted',
    }));
  },
};

/**
 * Trigger a browser download of a document. Azure files download via SAS URL;
 * local files are fetched as a blob first. Extracted from EntityDocuments so
 * both the document list and DocumentPreviewPanel share one implementation.
 */
export async function downloadDocument(doc: DocumentMetadata): Promise<void> {
  if (doc.source_url) {
    const a = document.createElement('a');
    a.href = doc.source_url;
    a.download = doc.filename;
    a.target = '_blank';
    a.rel = 'noreferrer';
    a.click();
    return;
  }
  const { url, provider }: DownloadUrlResult = await documents.getDownloadUrl(doc.id);
  if (provider === 'azure') {
    const a = document.createElement('a');
    a.href = url;
    a.download = doc.filename;
    a.click();
  } else {
    const { blob, contentType } = await documents.fetchContent(doc.id);
    const blobUrl = URL.createObjectURL(new Blob([blob], { type: contentType }));
    const a = document.createElement('a');
    a.href = blobUrl;
    a.download = doc.filename;
    a.click();
    URL.revokeObjectURL(blobUrl);
  }
}
