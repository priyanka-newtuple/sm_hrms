import { useEffect, useState } from "react";
import { createDraftTemplate, hasValidationErrors, validateTemplateDraft } from "../services/templateService.ts";
import type { Template, TemplateValidationErrors } from "../types";

interface TemplateEditorOptions {
  templateView: string | null;
  findTemplateById: (id: string) => Template | undefined;
  saveTemplate: (draft: Template) => Promise<Template>;
  deleteTemplate: (id: string) => Promise<void>;
  navigateToList: () => void;
  navigateToTemplate: (templateId: string) => void;
}

export function useTemplateEditor({
  templateView,
  findTemplateById,
  saveTemplate,
  deleteTemplate,
  navigateToList,
  navigateToTemplate,
}: TemplateEditorOptions) {
  const [draft, setDraft] = useState<Template | null>(null);
  const [baselineDraft, setBaselineDraft] = useState<Template | null>(null);
  const [dirty, setDirty] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [savedToastVisible, setSavedToastVisible] = useState(false);
  const [pendingNavigation, setPendingNavigation] = useState<(() => void) | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [validationErrors, setValidationErrors] = useState<TemplateValidationErrors>({});
  const [isSaving, setIsSaving] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [editorError, setEditorError] = useState<string | null>(null);

  useEffect(() => {
    setPreviewOpen(false);
    setSaveError(null);
    setDeleteError(null);
    setValidationErrors({});

    if (!templateView) {
      setDraft(null);
      setBaselineDraft(null);
      setDirty(false);
      setPendingNavigation(null);
      setEditorError(null);
      return;
    }

    if (templateView === "new") {
      const nextDraft = createDraftTemplate();
      setDraft(nextDraft);
      setBaselineDraft(nextDraft);
      setDirty(false);
      setPendingNavigation(null);
      setEditorError(null);
      return;
    }

    const editingTemplate = findTemplateById(templateView);
    if (!editingTemplate) {
      setDraft(null);
      setBaselineDraft(null);
      setDirty(false);
      setPendingNavigation(null);
      setEditorError("Template not found.");
      return;
    }

    setDraft({ ...editingTemplate });
    setBaselineDraft({ ...editingTemplate });
    setDirty(false);
    setPendingNavigation(null);
    setEditorError(null);
  }, [findTemplateById, templateView]);

  useEffect(() => {
    if (!savedToastVisible) {
      return;
    }

    const timeoutId = window.setTimeout(() => setSavedToastVisible(false), 2200);
    return () => window.clearTimeout(timeoutId);
  }, [savedToastVisible]);

  const requestNavigation = (action: () => void) => {
    if (dirty) {
      setPendingNavigation(() => action);
      return;
    }

    action();
  };

  const updateDraft = (patch: Partial<Template>) => {
    setDraft((currentDraft) => (currentDraft ? { ...currentDraft, ...patch } : null));
    setDirty(true);
    setSaveError(null);
    setDeleteError(null);
  };

  const saveDraft = async () => {
    if (!draft) {
      return;
    }

    const nextValidationErrors = validateTemplateDraft(draft);
    setValidationErrors(nextValidationErrors);

    if (hasValidationErrors(nextValidationErrors)) {
      return;
    }

    setIsSaving(true);
    setSaveError(null);

    try {
      const savedDraft = await saveTemplate(draft);
      setDraft(savedDraft);
      setBaselineDraft(savedDraft);
      setDirty(false);
      setSavedToastVisible(true);
      setValidationErrors({});
      if (draft.isNew) {
        navigateToTemplate(savedDraft.templateId);
      }
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : "Unable to save template.");
    } finally {
      setIsSaving(false);
    }
  };

  const resetDraft = () => {
    if (!baselineDraft) {
      return;
    }

    setDraft({ ...baselineDraft });
    setDirty(false);
    setSaveError(null);
    setDeleteError(null);
    setValidationErrors({});
  };

  const removeCurrentTemplate = async () => {
    if (!draft) {
      return;
    }

    if (draft.isNew) {
      navigateToList();
      return;
    }

    setIsDeleting(true);
    setDeleteError(null);

    try {
      await deleteTemplate(draft.templateId);
      setDirty(false);
      setPendingNavigation(null);
      navigateToList();
    } catch (error) {
      setDeleteError(error instanceof Error ? error.message : "Unable to delete template.");
    } finally {
      setIsDeleting(false);
    }
  };

  const backToList = () => {
    requestNavigation(navigateToList);
  };

  const confirmDiscardChanges = () => {
    pendingNavigation?.();
    setPendingNavigation(null);
  };

  const cancelDiscardChanges = () => {
    setPendingNavigation(null);
  };

  return {
    draft,
    editing: templateView && templateView !== "new" ? findTemplateById(templateView) : undefined,
    isEditing: draft != null,
    dirty,
    previewOpen,
    savedToastVisible,
    saveError,
    deleteError,
    validationErrors,
    isSaving,
    isDeleting,
    shouldConfirmDiscard: pendingNavigation != null,
    updateDraft,
    saveDraft,
    resetDraft,
    removeCurrentTemplate,
    backToList,
    openPreview: () => setPreviewOpen(true),
    closePreview: () => setPreviewOpen(false),
    confirmDiscardChanges,
    cancelDiscardChanges,
    editorError,
  };
}
