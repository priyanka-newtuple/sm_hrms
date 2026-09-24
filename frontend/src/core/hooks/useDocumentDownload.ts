import { useState } from 'react';
import { downloadDocument } from '../services/api/documents';
import type { DocumentMetadata } from '../types';

/**
 * Triggers a browser download for the given document and surfaces a failure
 * message scoped to that document. The error is derived against the current
 * doc id, so it clears automatically when the active document changes — no
 * reset effect required.
 *
 * Keeps the service call behind a hook so the component depends on an
 * abstraction, not on `services/` directly (Dependency Inversion).
 */
export function useDocumentDownload(doc: DocumentMetadata | null) {
  const [failure, setFailure] = useState<{ docId: string; message: string } | null>(null);

  const download = async () => {
    if (!doc) return;
    try {
      setFailure(null);
      await downloadDocument(doc);
    } catch (e) {
      setFailure({ docId: doc.id, message: e instanceof Error ? e.message : 'Download failed' });
    }
  };

  const error = doc && failure?.docId === doc.id ? failure.message : null;

  return { download, error };
}
