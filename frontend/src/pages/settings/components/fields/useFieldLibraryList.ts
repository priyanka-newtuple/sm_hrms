/**
 * useFieldLibraryList
 *
 * Owns the Fields tab's list state: the current page, the filters that
 * invalidate it, and the full-catalogue fetch used for formula/table field
 * pickers. Kept separate from FieldsTab's editing/import/archive concerns
 * so each piece stays independently readable.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { fieldLibrary } from '@/core/services/api';
import type { FieldType, FieldWithVersion } from '@/core/types';
import { fetchAllLibraryFieldPages, matchesSearch } from './fieldLibraryUtils';

const PAGE_SIZE = 25;

export function useFieldLibraryList() {
  const [fields, setFields] = useState<FieldWithVersion[]>([]);
  const [editorFieldEntries, setEditorFieldEntries] = useState<FieldWithVersion[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState<FieldType | 'all'>('all');
  const [showArchived, setShowArchived] = useState(false);
  const isSearching = search.trim().length > 0;

  const fieldListRequestId = useRef(0);
  const editorFieldsRequestId = useRef(0);

  const fetchFields = useCallback(async () => {
    const requestId = ++fieldListRequestId.current;
    setLoading(true);
    setLoadError(null);
    try {
      const trimmed = search.trim();
      if (trimmed) {
        // Description/settings search is broader than the backend's name/key
        // search, so load every server page and paginate the matched result.
        const allEntries = await fetchAllLibraryFieldPages(fieldLibrary.list, {
          includeArchived: showArchived,
          fieldType: typeFilter === 'all' ? undefined : typeFilter,
        });
        if (requestId !== fieldListRequestId.current) return;
        const matched = allEntries.filter((field) => matchesSearch(field, trimmed));
        const lastOffset = matched.length > 0
          ? Math.floor((matched.length - 1) / PAGE_SIZE) * PAGE_SIZE
          : 0;
        const safeOffset = Math.min(offset, lastOffset);
        setFields(matched.slice(safeOffset, safeOffset + PAGE_SIZE));
        setTotal(matched.length);
        if (safeOffset !== offset) setOffset(safeOffset);
      } else {
        const res = await fieldLibrary.list({
          includeArchived: showArchived,
          fieldType: typeFilter === 'all' ? undefined : typeFilter,
          limit: PAGE_SIZE,
          offset,
        });
        if (requestId !== fieldListRequestId.current) return;
        if (res.total > 0 && offset >= res.total) {
          setOffset(Math.floor((res.total - 1) / PAGE_SIZE) * PAGE_SIZE);
          return;
        }
        setFields(res.items);
        setTotal(res.total);
      }
    } catch (e) {
      if (requestId === fieldListRequestId.current) {
        setLoadError(e instanceof Error ? e.message : 'Failed to load fields');
      }
    } finally {
      if (requestId === fieldListRequestId.current) setLoading(false);
    }
  }, [showArchived, search, typeFilter, offset]);
  useEffect(() => { void fetchFields(); }, [fetchFields]);

  const fetchEditorFields = useCallback(async () => {
    const requestId = ++editorFieldsRequestId.current;
    try {
      const entries = await fetchAllLibraryFieldPages(fieldLibrary.list, {
        includeArchived: false,
      });
      if (requestId === editorFieldsRequestId.current) setEditorFieldEntries(entries);
    } catch {
      // The visible page remains a safe fallback for formula/table options.
    }
  }, []);
  useEffect(() => { void fetchEditorFields(); }, [fetchEditorFields]);

  const refreshLibrary = useCallback(async () => {
    await Promise.all([fetchFields(), fetchEditorFields()]);
  }, [fetchFields, fetchEditorFields]);

  return {
    PAGE_SIZE,
    fields,
    editorFieldEntries,
    total,
    offset,
    setOffset,
    loading,
    loadError,
    search,
    setSearch,
    typeFilter,
    setTypeFilter,
    showArchived,
    setShowArchived,
    isSearching,
    refreshLibrary,
  };
}
