/**
 * useMethods
 *
 * The method list, the selected method's resolved detail, and every
 * metadata-level mutation (create, rename, re-categorise, clone, archive).
 * Mirrors the Forms tab's `useFormSchemas`, with one structural difference the
 * API forces: listing returns identities only, so the selected method's field
 * list comes from a second detail call.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { methodLibrary } from '@/core/services/api';
import { getApiErrorMessage } from '@/core/services/api/client';
import type {
  MethodCategory,
  MethodCreateRequest,
  MethodIdentity,
  MethodMetadataUpdateRequest,
  MethodWithFields,
} from '@/core/types';

export const METHOD_PAGE_SIZE = 25;

export interface EditingMethodName {
  methodId: string;
  name: string;
}

interface UseMethodsCopy {
  entityLower: string;
  entityLowerPlural: string;
}

export function useMethods({
  entityLower = 'form',
  entityLowerPlural = 'forms',
}: Partial<UseMethodsCopy> = {}) {
  const [methods, setMethods] = useState<MethodIdentity[]>([]);
  const [categories, setCategories] = useState<MethodCategory[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState('');
  const [appliedSearch, setAppliedSearch] = useState('');
  const [showArchived, setShowArchived] = useState(false);

  const [selectedMethod, setSelectedMethod] = useState<MethodWithFields | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [showNewMethodModal, setShowNewMethodModal] = useState(false);
  const [creatingMethod, setCreatingMethod] = useState(false);
  const [newMethodError, setNewMethodError] = useState<string | null>(null);

  const [editingMethodName, setEditingMethodName] = useState<EditingMethodName | null>(null);
  const [savingMethodName, setSavingMethodName] = useState(false);
  const [deletingMethod, setDeletingMethod] = useState<string | null>(null);
  const [archivingMethod, setArchivingMethod] = useState<string | null>(null);
  const [savingCategory, setSavingCategory] = useState<string | null>(null);
  const [deletingCategory, setDeletingCategory] = useState<string | null>(null);
  const [cloningMethod, setCloningMethod] = useState(false);

  // Guards against a slower earlier response overwriting a newer one when the
  // user switches methods or types in the search box quickly.
  const listRequestId = useRef(0);
  const detailRequestId = useRef(0);

  // Keep the input responsive while delaying server filtering until the user
  // pauses typing. This prevents one list reload per keystroke.
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setAppliedSearch(search);
      setOffset(0);
    }, 250);
    return () => window.clearTimeout(timer);
  }, [search]);

  const fetchCategories = useCallback(async () => {
    try {
      const res = await methodLibrary.categories.list();
      setCategories(res.items);
    } catch {
      // A missing category list only costs the picker its options — the grid
      // still lists every method, so this stays non-fatal.
    }
  }, []);

  /** `silent` skips the spinner, so a post-mutation refetch doesn't flash the
   *  whole list the way the Forms tab's own silent refetch avoids it. */
  const fetchMethods = useCallback(async (
    silent = false,
    overrides?: { offset?: number; search?: string },
  ) => {
    const requestId = ++listRequestId.current;
    const requestOffset = overrides?.offset ?? offset;
    const requestSearch = overrides?.search ?? appliedSearch;
    if (!silent) setLoading(true);
    try {
      const res = await methodLibrary.list({
        includeArchived: showArchived,
        search: requestSearch.trim() || undefined,
        limit: METHOD_PAGE_SIZE,
        offset: requestOffset,
      });
      if (requestId !== listRequestId.current) return;
      // A deletion can empty the last page out from under us.
      if (res.total > 0 && requestOffset >= res.total) {
        setOffset(Math.floor((res.total - 1) / METHOD_PAGE_SIZE) * METHOD_PAGE_SIZE);
        return;
      }
      setMethods(res.items);
      setTotal(res.total);
      setError(null);
    } catch (e) {
      if (requestId === listRequestId.current) {
        setError(getApiErrorMessage(e, `Failed to load ${entityLowerPlural}`));
      }
    } finally {
      // A silent refresh can replace the initial visible request. Whichever
      // request is latest must clear the initial spinner, otherwise the tab can
      // remain stuck on "Loading" forever.
      if (requestId === listRequestId.current) setLoading(false);
    }
  }, [appliedSearch, entityLowerPlural, offset, showArchived]);

  const loadMethodDetail = useCallback(async (methodId: string) => {
    const requestId = ++detailRequestId.current;
    setLoadingDetail(true);
    try {
      const detail = await methodLibrary.get(methodId);
      if (requestId === detailRequestId.current) setSelectedMethod(detail);
    } catch (e) {
      if (requestId === detailRequestId.current) {
        setError(getApiErrorMessage(e, `Failed to load ${entityLower}`));
        setSelectedMethod(null);
      }
    } finally {
      if (requestId === detailRequestId.current) setLoadingDetail(false);
    }
  }, [entityLower]);

  const handleSelectMethod = useCallback((identity: MethodIdentity) => {
    void loadMethodDetail(identity.method_id);
  }, [loadMethodDetail]);

  /** Re-reads the open method after its field list changed, so the version
   *  number and the resolved field shapes both reflect the new version. */
  const refreshSelected = useCallback(async () => {
    if (!selectedMethod) return;
    await loadMethodDetail(selectedMethod.identity.method_id);
  }, [selectedMethod, loadMethodDetail]);

  async function handleCreateMethod(payload: MethodCreateRequest) {
    setCreatingMethod(true);
    setNewMethodError(null);
    try {
      const created = await methodLibrary.create(payload);
      setShowNewMethodModal(false);
      // A newly-created method is always opened, even when the user created it
      // from another page or while a search was active. Fetch page one with the
      // cleared filter before selecting it so the auto-selection effect cannot
      // replace it with an older method.
      setSearch('');
      setAppliedSearch('');
      setOffset(0);
      await fetchMethods(true, { offset: 0, search: '' });
      setSelectedMethod(created);
      return created;
    } catch (e) {
      setNewMethodError(getApiErrorMessage(e, `Failed to create ${entityLower}`));
      return null;
    } finally {
      setCreatingMethod(false);
    }
  }

  /** Name, description and category all go through here: the backend applies
   *  only the members present and none of it creates a version. */
  async function handleUpdateMetadata(methodId: string, patch: MethodMetadataUpdateRequest) {
    try {
      const identity = await methodLibrary.updateMetadata(methodId, patch);
      setMethods((prev) => prev.map((m) => (m.method_id === methodId ? identity : m)));
      setSelectedMethod((prev) =>
        prev && prev.identity.method_id === methodId ? { ...prev, identity } : prev,
      );
      setError(null);
      return true;
    } catch (e) {
      setError(getApiErrorMessage(e, `Failed to update ${entityLower}`));
      return false;
    }
  }

  async function handleConfirmRename() {
    if (!editingMethodName) return;
    const name = editingMethodName.name.trim();
    if (!name) {
      setEditingMethodName(null);
      return;
    }
    setSavingMethodName(true);
    const ok = await handleUpdateMetadata(editingMethodName.methodId, { name });
    setSavingMethodName(false);
    if (ok) setEditingMethodName(null);
  }

  async function handleCloneMethod(methodId: string, name: string, sourceVersionId?: string) {
    setCloningMethod(true);
    try {
      const clone = await methodLibrary.clone(methodId, {
        name,
        source_version_id: sourceVersionId ?? null,
      });
      setSelectedMethod(clone);
      await fetchMethods(true);
      setError(null);
      return clone;
    } catch (e) {
      setError(getApiErrorMessage(e, `Failed to clone ${entityLower}`));
      return null;
    } finally {
      setCloningMethod(false);
    }
  }

  async function handleDeleteMethod(methodId: string) {
    setDeletingMethod(methodId);
    try {
      await methodLibrary.delete(methodId);
      if (selectedMethod?.identity.method_id === methodId) setSelectedMethod(null);
      await fetchMethods(true);
      setError(null);
    } catch (e) {
      setError(getApiErrorMessage(e, `Failed to delete ${entityLower}`));
    } finally {
      setDeletingMethod(null);
    }
  }

  /** Archive and unarchive are the same visibility change in two directions, not
   *  a removal: the backend allows either even while a method is in use, so there
   *  is no in-use guard here. The refetch reconciles the row out of (or back
   *  into) the current page according to the "Show archived" filter. Kept as one
   *  function so a fix to the identity reconciliation can't miss one direction. */
  async function handleArchiveToggle(
    methodId: string,
    action: 'archive' | 'unarchive',
  ): Promise<boolean> {
    setArchivingMethod(methodId);
    try {
      const identity =
        action === 'archive'
          ? await methodLibrary.archive(methodId)
          : await methodLibrary.unarchive(methodId);
      setMethods((prev) => prev.map((m) => (m.method_id === methodId ? identity : m)));
      setSelectedMethod((prev) =>
        prev && prev.identity.method_id === methodId ? { ...prev, identity } : prev,
      );
      await fetchMethods(true);
      setError(null);
      return true;
    } catch (e) {
      setError(getApiErrorMessage(e, `Failed to ${action} ${entityLower}`));
      return false;
    } finally {
      setArchivingMethod(null);
    }
  }

  async function handleCreateCategory(name: string) {
    try {
      const created = await methodLibrary.categories.create(name);
      setCategories((prev) => [...prev, created].sort((a, b) => a.name.localeCompare(b.name)));
      setError(null);
      return created;
    } catch (e) {
      setError(getApiErrorMessage(e, 'Failed to create category'));
      return null;
    }
  }

  async function handleRenameCategory(categoryId: string, name: string) {
    setSavingCategory(categoryId);
    try {
      const updated = await methodLibrary.categories.rename(categoryId, name.trim());
      setCategories((prev) =>
        prev.map((category) => (category.category_id === categoryId ? updated : category)),
      );
      setMethods((prev) =>
        prev.map((method) =>
          method.category_id === categoryId ? { ...method, category_name: updated.name } : method,
        ),
      );
      setSelectedMethod((prev) =>
        prev && prev.identity.category_id === categoryId
          ? { ...prev, identity: { ...prev.identity, category_name: updated.name } }
          : prev,
      );
      setError(null);
      return true;
    } catch (e) {
      setError(getApiErrorMessage(e, 'Failed to rename category'));
      return false;
    } finally {
      setSavingCategory(null);
    }
  }

  async function handleDeleteCategory(categoryId: string) {
    setDeletingCategory(categoryId);
    try {
      await methodLibrary.categories.remove(categoryId);
      setCategories((prev) => prev.filter((category) => category.category_id !== categoryId));
      setMethods((prev) =>
        prev.map((method) =>
          method.category_id === categoryId
            ? { ...method, category_id: null, category_name: null }
            : method,
        ),
      );
      setSelectedMethod((prev) =>
        prev && prev.identity.category_id === categoryId
          ? { ...prev, identity: { ...prev.identity, category_id: null, category_name: null } }
          : prev,
      );
      setError(null);
      return true;
    } catch (e) {
      setError(getApiErrorMessage(e, 'Failed to delete category'));
      return false;
    } finally {
      setDeletingCategory(null);
    }
  }

  return {
    methods,
    categories,
    total,
    offset,
    setOffset,
    search,
    setSearch,
    showArchived,
    setShowArchived,

    selectedMethod,
    setSelectedMethod,
    loadingDetail,
    loading,
    error,
    setError,

    showNewMethodModal,
    setShowNewMethodModal,
    creatingMethod,
    newMethodError,
    setNewMethodError,

    editingMethodName,
    setEditingMethodName,
    savingMethodName,
    deletingMethod,
    archivingMethod,
    savingCategory,
    deletingCategory,
    cloningMethod,

    fetchMethods,
    fetchCategories,
    refreshSelected,
    handleSelectMethod,
    handleCreateMethod,
    handleUpdateMetadata,
    handleConfirmRename,
    handleCloneMethod,
    handleDeleteMethod,
    handleArchiveToggle,
    handleCreateCategory,
    handleRenameCategory,
    handleDeleteCategory,
  };
}
