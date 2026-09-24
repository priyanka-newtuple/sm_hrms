import { expect, test } from '@playwright/test';

import { useDocumentPreviewStore } from '../../src/core/stores/documentPreviewStore';
import type { DocumentMetadata } from '../../src/core/types';

function doc(id: string): DocumentMetadata {
  return {
    id,
    document_id: id,
    filename: `${id}.pdf`,
    storage_key: `k/${id}`,
    content_type: 'application/pdf',
    size_bytes: 1,
    entity_id: 'ignored',
    document_type: 'resume',
  } as unknown as DocumentMetadata;
}

function resetStore() {
  useDocumentPreviewStore.getState().reset();
}

test('publishOwnedDocs keeps an active same-context preview that is not in the owned list', () => {
  resetStore();
  const store = useDocumentPreviewStore.getState();
  // User previews a related entity's file while viewing entity app-1.
  store.setDocs([doc('resume-1')], 'app-1', 'related');
  store.setActive('resume-1');

  // The own-docs poll for app-1 returns an empty list (entity owns nothing).
  useDocumentPreviewStore.getState().publishOwnedDocs('app-1', []);

  const state = useDocumentPreviewStore.getState();
  expect(state.docs.map((d) => d.id)).toEqual(['resume-1']);
  expect(state.docs[state.activeIndex]?.id).toBe('resume-1');
});

test('publishOwnedDocs keeps the related preview when owned docs exist but do not include it', () => {
  resetStore();
  useDocumentPreviewStore.getState().setDocs([doc('resume-1')], 'app-1', 'related');
  useDocumentPreviewStore.getState().setActive('resume-1');

  useDocumentPreviewStore.getState().publishOwnedDocs('app-1', [doc('assignment-1')]);

  expect(useDocumentPreviewStore.getState().docs.map((d) => d.id)).toEqual(['resume-1']);
});

test('publishOwnedDocs replaces stale content from a previously viewed entity', () => {
  resetStore();
  useDocumentPreviewStore.getState().setDocs([doc('resume-1')], 'app-1', 'related');
  useDocumentPreviewStore.getState().setActive('resume-1');

  useDocumentPreviewStore.getState().publishOwnedDocs('app-2', [doc('assignment-2')]);

  const state = useDocumentPreviewStore.getState();
  expect(state.contextEntityId).toBe('app-2');
  expect(state.docs.map((d) => d.id)).toEqual(['assignment-2']);
  expect(state.activeIndex).toBe(0);
});

test('publishOwnedDocs into an empty panel populates it', () => {
  resetStore();
  useDocumentPreviewStore.getState().publishOwnedDocs('app-1', [doc('a'), doc('b')]);

  const state = useDocumentPreviewStore.getState();
  expect(state.docs).toHaveLength(2);
  expect(state.contextEntityId).toBe('app-1');
});

test('publishOwnedDocs follows the active doc by id when the list reorders', () => {
  resetStore();
  useDocumentPreviewStore.getState().publishOwnedDocs('app-1', [doc('a'), doc('b')]);
  useDocumentPreviewStore.getState().setActive('b');

  useDocumentPreviewStore.getState().publishOwnedDocs('app-1', [doc('b'), doc('a'), doc('c')]);

  const state = useDocumentPreviewStore.getState();
  expect(state.docs[state.activeIndex]?.id).toBe('b');
});

test('setDocs follows the active doc by id across replacement lists', () => {
  resetStore();
  useDocumentPreviewStore.getState().setDocs([doc('a'), doc('b')], 'app-1');
  useDocumentPreviewStore.getState().setActive('b');

  useDocumentPreviewStore.getState().setDocs([doc('c'), doc('b')], 'app-1');

  const state = useDocumentPreviewStore.getState();
  expect(state.docs[state.activeIndex]?.id).toBe('b');
});

test('reset clears docs and context', () => {
  useDocumentPreviewStore.getState().setDocs([doc('a')], 'app-1');
  useDocumentPreviewStore.getState().reset();

  const state = useDocumentPreviewStore.getState();
  expect(state.docs).toHaveLength(0);
  expect(state.contextEntityId).toBeNull();
  expect(state.activeIndex).toBe(0);
});

test('publishOwnedDocs evicts an active owned document that was deleted', () => {
  resetStore();
  useDocumentPreviewStore.getState().publishOwnedDocs('app-1', [doc('a'), doc('b')]);
  useDocumentPreviewStore.getState().setActive('b');

  // Deleting doc b refetches the owned list without it.
  useDocumentPreviewStore.getState().publishOwnedDocs('app-1', [doc('a')]);

  const state = useDocumentPreviewStore.getState();
  expect(state.docs.map((d) => d.id)).toEqual(['a']);
  expect(state.docs[state.activeIndex]?.id).toBe('a');
});

test('publishOwnedDocs clears the panel when the last owned document is deleted', () => {
  resetStore();
  useDocumentPreviewStore.getState().publishOwnedDocs('app-1', [doc('a')]);
  useDocumentPreviewStore.getState().setActive('a');

  useDocumentPreviewStore.getState().publishOwnedDocs('app-1', []);

  const state = useDocumentPreviewStore.getState();
  expect(state.docs).toHaveLength(0);
  expect(state.docsSource).toBeNull();
});
