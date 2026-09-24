import { useCallback, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { filterTemplates } from "./services/templateService.ts";
import { ListView } from "./components/ListView.tsx";
import { EditView } from "./components/EditView.tsx";
import { PreviewModal, ConfirmModal, SavedToast } from "./components/Modals.tsx";
import { useTemplateEditor } from "./hooks/useTemplateEditor.ts";
import { useTemplateLibrary } from "./hooks/useTemplateLibrary.ts";
import { useEntityTypes } from "./hooks/useEntityTypes.ts";
import { useFormVariables } from "./hooks/useFormVariables.ts";
import { Button } from "@/components/ui/button.tsx";
import { usePermissions } from "@/core/hooks/usePermissions";

export default function App() {
  const { hasPermission } = usePermissions();
  const canWrite = hasPermission("email_template:write");
  const [searchParams, setSearchParams] = useSearchParams();
  const templateView = searchParams.get("template");

  const {
    templates,
    isLoading,
    loadError,
    refreshTemplates,
    findTemplateById,
    saveTemplate,
    deleteTemplate,
  } = useTemplateLibrary();

  const {
    draft,
    editing,
    isEditing,
    dirty,
    previewOpen,
    savedToastVisible,
    saveError,
    deleteError,
    validationErrors,
    isSaving,
    isDeleting,
    shouldConfirmDiscard,
    updateDraft,
    saveDraft,
    resetDraft,
    removeCurrentTemplate,
    backToList,
    openPreview,
    closePreview,
    confirmDiscardChanges,
    cancelDiscardChanges,
    editorError,
  } = useTemplateEditor({
    templateView,
    findTemplateById,
    saveTemplate,
    deleteTemplate,
    navigateToList: useCallback(
      () => setSearchParams({ tab: "email_templates" }, { replace: true }),
      [setSearchParams],
    ),
    navigateToTemplate: useCallback(
      (templateId: string) =>
        setSearchParams({ tab: "email_templates", template: templateId }, { replace: true }),
      [setSearchParams],
    ),
  });

  const [query, setQuery] = useState("");

  const entityTypesList = useEntityTypes();
  const { formOptions, availableVariables } = useFormVariables(
    draft?.entityType ?? null,
    draft?.formId ?? null,
  );

  const filteredTemplates = useMemo(
    () => filterTemplates(templates, query),
    [templates, query],
  );

  const entityOptions = useMemo(() => {
    const currentValue = draft?.entityType ?? null;
    if (!currentValue || entityTypesList.some((et) => et.value === currentValue)) {
      return entityTypesList;
    }
    return [...entityTypesList, { value: currentValue, label: currentValue }];
  }, [draft?.entityType, entityTypesList]);

  const openTemplate = useCallback(
    (templateId: string) => setSearchParams({ tab: "email_templates", template: templateId }),
    [setSearchParams],
  );

  const startTemplateCreation = useCallback(
    () => {
      if (!canWrite) return;
      setSearchParams({ tab: "email_templates", template: "new" });
    },
    [canWrite, setSearchParams],
  );

  const handleEntityTypeChange = useCallback(
    (entityType: string | null) => {
      if (draft?.entityType === entityType) return;
      updateDraft({ entityType, formId: null });
    },
    [draft?.entityType, updateDraft],
  );

  const handleFormChange = useCallback(
    (formId: string | null) => updateDraft({ formId }),
    [updateDraft],
  );

  const handleDeleteFromList = useCallback(
    async (templateId: string) => {
      if (!canWrite) return;
      const template = findTemplateById(templateId);
      if (!template || template.isSystem) return;
      await deleteTemplate(templateId);
    },
    [canWrite, findTemplateById, deleteTemplate],
  );

  return (
    <div className="relative">
      <div>
        {loadError && !isEditing && (
            <div className="mb-4 flex items-center justify-between gap-3 rounded-2xl border border-destructive/30 bg-destructive-subtle px-4 py-3 text-sm text-destructive">
              <span>{loadError}</span>
              <Button variant="outline" size="sm" onClick={() => void refreshTemplates()}>
                Retry
              </Button>
            </div>
          )}

          {!templateView ? (
            <ListView
              templates={templates}
              filtered={filteredTemplates}
              query={query}
              onQuery={setQuery}
              onOpen={openTemplate}
              onCreate={startTemplateCreation}
              onDelete={(templateId) => void handleDeleteFromList(templateId)}
              loading={isLoading}
              canWrite={canWrite}
            />
          ) : editorError && !draft ? (
            <div className="mx-auto max-w-2xl rounded-2xl border border-destructive/30 bg-destructive-subtle px-6 py-10 text-center text-sm text-destructive">
              <p className="mb-4 font-medium">{editorError}</p>
              <Button variant="outline" onClick={backToList}>
                Back to list
              </Button>
            </div>
          ) : draft ? (
            <EditView
              draft={draft}
              editing={editing}
              dirty={dirty}
              entityTypes={entityOptions}
              formOptions={formOptions}
              availableVariables={availableVariables}
              validationErrors={validationErrors}
              saveError={saveError}
              deleteError={deleteError}
              isSaving={isSaving}
              isDeleting={isDeleting}
              onUpdate={updateDraft}
              onEntityTypeChange={handleEntityTypeChange}
              onFormChange={handleFormChange}
              onSave={() => {
                if (!canWrite) return;
                void saveDraft();
              }}
              onCancel={resetDraft}
              onDelete={() => {
                if (!canWrite) return;
                void removeCurrentTemplate();
              }}
              onPreview={openPreview}
              onBack={backToList}
              canWrite={canWrite}
            />
          ) : null}

          {previewOpen && draft && (
            <PreviewModal draft={draft} onClose={closePreview} />
          )}

          {shouldConfirmDiscard && (
            <ConfirmModal
              title="Discard unsaved changes?"
              message="You have unsaved edits to this template. Leave anyway and lose them?"
              confirmLabel="Discard changes"
              danger
              onCancel={cancelDiscardChanges}
              onConfirm={confirmDiscardChanges}
            />
          )}

          {savedToastVisible && <SavedToast />}
      </div>
    </div>
  );
}
