/**
 * useFieldArchiving
 *
 * Owns the archive and permanent-delete confirmation flows for the Fields
 * tab's row action menu, kept apart from FieldsTab's list/editing state.
 */

import { useState } from 'react';
import { toast } from 'sonner';
import { fieldLibrary } from '@/core/services/api';

interface UseFieldArchivingOptions {
  canWrite: boolean;
  refreshLibrary: () => Promise<void>;
  onDeleted: (libraryFieldId: string) => void;
}

export function useFieldArchiving({ canWrite, refreshLibrary, onDeleted }: UseFieldArchivingOptions) {
  const [openActionMenuId, setOpenActionMenuId] = useState<string | null>(null);
  const [archiveConfirmId, setArchiveConfirmId] = useState<string | null>(null);
  const [archiving, setArchiving] = useState(false);
  const [hardDeleteConfirmId, setHardDeleteConfirmId] = useState<string | null>(null);
  const [hardDeleting, setHardDeleting] = useState(false);
  const [hardDeleteError, setHardDeleteError] = useState<string | null>(null);

  async function handleArchive(id: string) {
    if (!canWrite) return;
    setArchiving(true);
    try {
      await fieldLibrary.archive(id);
      setArchiveConfirmId(null);
      toast.success('Field archived.');
      void refreshLibrary();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to archive field');
    } finally {
      setArchiving(false);
    }
  }

  async function handleHardDelete(id: string) {
    if (!canWrite) return;
    setHardDeleting(true);
    setHardDeleteError(null);
    try {
      await fieldLibrary.hardDelete(id);
      onDeleted(id);
      setHardDeleteConfirmId(null);
      toast.success('Field and all of its versions deleted permanently.');
      void refreshLibrary();
    } catch (e) {
      // The backend includes the number of referencing forms in this error,
      // which is the only usage detail currently exposed by the API.
      setHardDeleteError(e instanceof Error ? e.message : 'Failed to delete field');
    } finally {
      setHardDeleting(false);
    }
  }

  return {
    openActionMenuId,
    setOpenActionMenuId,
    archiveConfirmId,
    setArchiveConfirmId,
    archiving,
    hardDeleteConfirmId,
    setHardDeleteConfirmId,
    hardDeleting,
    hardDeleteError,
    setHardDeleteError,
    handleArchive,
    handleHardDelete,
  };
}
