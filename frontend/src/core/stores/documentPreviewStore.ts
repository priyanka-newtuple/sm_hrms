import { create } from 'zustand';
import type { DocumentMetadata } from '../types';

/**
 * Bridges the document list (fetched inside EntityDocuments, deep in the
 * detail tree) to DocumentPreviewPanel (rendered beside the sheet / page).
 * Single global store — only one entity detail is visible at a time.
 *
 * Two components write here for the same viewed entity: EntityDocuments
 * (the entity's own files, republished by its background poll) and
 * RelatedEntityDocuments (files owned by related entities, published when the
 * user opens a preview). `contextEntityId` records which viewed entity the
 * current docs belong to, so a refresh can tell "stale content from a
 * previously viewed entity" (safe to replace) apart from "the user is
 * previewing a related file of this entity" (must not be evicted).
 */
/** Which panel published the current docs: the entity's own files or a
 * related entity's files. Owned lists are authoritative for owned docs (a doc
 * missing from a refetch was deleted), related lists must not be evicted by
 * own-docs refreshes. */
export type PreviewDocsSource = 'owned' | 'related';

interface DocumentPreviewStore {
  docs: DocumentMetadata[];
  /** The viewed entity whose detail published `docs` (own or related files). */
  contextEntityId: string | null;
  /** Provenance of `docs`; null when the panel is empty. */
  docsSource: PreviewDocsSource | null;
  activeIndex: number;
  /** Panel collapsed into its slim rail. Picking a document re-expands it. */
  collapsed: boolean;
  setDocs: (
    docs: DocumentMetadata[],
    contextEntityId?: string | null,
    source?: PreviewDocsSource,
  ) => void;
  /**
   * Republish an entity's own document list (initial load + background poll).
   * No-ops only when the active preview is a same-entity RELATED file — a
   * poll can never blank an open related preview. Owned content is always
   * replaced, so deleting the active owned document evicts it from the panel.
   */
  publishOwnedDocs: (contextEntityId: string, docs: DocumentMetadata[]) => void;
  setActive: (docId: string) => void;
  setCollapsed: (collapsed: boolean) => void;
  next: () => void;
  prev: () => void;
  reset: () => void;
}

/** Index of the active doc within a replacement list: follow it by id when it
 * survives the replacement, else fall back to the start of the new list. */
function carriedIndex(docs: DocumentMetadata[], activeId: string | undefined): number {
  if (!activeId) return 0;
  const index = docs.findIndex((doc) => doc.id === activeId);
  return index >= 0 ? index : 0;
}

export const useDocumentPreviewStore = create<DocumentPreviewStore>((set) => ({
  docs: [],
  contextEntityId: null,
  docsSource: null,
  activeIndex: 0,
  collapsed: false,

  setDocs: (docs, contextEntityId = null, source = 'owned') =>
    set((s) => ({
      docs,
      contextEntityId,
      docsSource: docs.length > 0 ? source : null,
      activeIndex: carriedIndex(docs, s.docs[s.activeIndex]?.id),
    })),

  publishOwnedDocs: (contextEntityId, docs) =>
    set((s) => {
      const activeId = s.docs[s.activeIndex]?.id;
      const sameContext = s.contextEntityId === contextEntityId;
      if (
        sameContext &&
        activeId &&
        s.docsSource === 'related' &&
        !docs.some((doc) => doc.id === activeId)
      ) {
        return {}; // active preview is a related entity's file — keep it
      }
      // Owned content (or a different entity's leftovers) is replaced
      // wholesale: a previously active owned doc that is gone was deleted.
      return {
        docs,
        contextEntityId,
        docsSource: docs.length > 0 ? 'owned' : null,
        activeIndex: sameContext ? carriedIndex(docs, activeId) : 0,
      };
    }),

  setActive: (docId) =>
    set((s) => {
      const i = s.docs.findIndex((d) => d.id === docId);
      return i >= 0 ? { activeIndex: i, collapsed: false } : {};
    }),

  setCollapsed: (collapsed) => set({ collapsed }),

  next: () =>
    set((s) => ({
      activeIndex: Math.min(s.activeIndex + 1, Math.max(s.docs.length - 1, 0)),
    })),

  prev: () => set((s) => ({ activeIndex: Math.max(s.activeIndex - 1, 0) })),

  reset: () =>
    set({ docs: [], contextEntityId: null, docsSource: null, activeIndex: 0, collapsed: false }),
}));
