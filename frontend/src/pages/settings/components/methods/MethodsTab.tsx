/**
 * MethodsTab
 *
 * Settings tab for the Method Library (backend/method_library). A method is a
 * named, categorised, ordered list of fields — the same shape as a form, and
 * deliberately the same UI as the Forms tab, with one difference that drives
 * the whole design: a method cannot define a field. It only picks fields that
 * already exist in the Field Library, and each pick pins that field's current
 * version, so a method sees a stable field shape even after the field changes.
 *
 * So: no field editor here, only a picker, plus a route through to the Field
 * Library for when the field doesn't exist yet. A method's name, description
 * and category are live edits; its field list is versioned, and every change
 * to the list produces a new version rather than mutating the old one.
 */

import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { useSearchParams } from 'react-router-dom';
import { AlertCircle, ChevronLeft, ChevronRight, FileText, FolderKanban, Loader2, Plus, RefreshCw, Search, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { usePermissions } from '@/core/hooks/usePermissions';
import { connectors as connectorsApi, entityTypes as entityTypesApi } from '@/core/services/api';
import type {
  Connector,
  MethodIdentity,
  MethodVersion,
  MethodWithFields,
} from '@/core/types';
import MethodList from './components/MethodList';
import MethodFieldsEditor from './components/MethodFieldsEditor';
import MethodCategoryPanel from './components/MethodCategoryPanel';
import NewMethodModal from './components/NewMethodModal';
import RemoveFieldDialog from './components/RemoveFieldDialog';
import MethodActionDialog from './components/MethodActionDialog';
import { METHOD_PAGE_SIZE, useMethods } from './hooks/useMethods';
import { useMethodFields } from './hooks/useMethodFields';
import { useWorkflowFieldsByEntityType } from '@/shared/hooks/useWorkflowFieldsByEntityType';
import { getMethodLibraryLabels } from './libraryLabels';

export interface MethodsTabProps {
  /** The Settings screen edits Methods; Design presents the same API as Composite Blocks. */
  entity?: 'method' | 'composite-block';
  /** Extra content rendered inside the selected method's detail panel. Skin-owned. */
  renderExtra?: (method: MethodWithFields) => ReactNode;
}

export default function MethodsTab({ entity = 'method', renderExtra }: MethodsTabProps) {
  const labels = getMethodLibraryLabels(entity);
  const {
    entityTitle,
    entityTitlePlural,
    entityLower,
    entityLowerPlural,
    libraryLabel,
    libraryItemTitle,
    libraryItemTitlePlural,
    libraryItemLower,
    libraryItemLowerPlural,
    libraryItemPossessive,
  } = labels;
  const codePrefix = entity === 'composite-block' ? 'BLK' : 'FR';
  const { hasPermission } = usePermissions();
  const canWrite = hasPermission('method_library:write');
  const [, setSearchParams] = useSearchParams();

  const methodHook = useMethods({ entityLower, entityLowerPlural });
  const {
    methods,
    categories,
    total,
    offset,
    setOffset,
    search,
    setSearch,
    selectedMethod,
    setSelectedMethod,
    loadingDetail,
    loading,
    error,
    setError,
    fetchMethods,
    fetchCategories,
    handleSelectMethod,
  } = methodHook;

  const fieldHook = useMethodFields(selectedMethod, setSelectedMethod, setError, entityLower);
  const workflowFieldsByEntityType = useWorkflowFieldsByEntityType();

  // Entity types a method can be tagged against. Read-only here: the tag list
  // offers only types that already exist, it never creates one.
  const [availableEntityTypes, setAvailableEntityTypes] = useState<string[]>([]);
  useEffect(() => {
    let cancelled = false;
    void entityTypesApi
      .list({ limit: 200 })
      .then((response) => {
        if (cancelled) return;
        setAvailableEntityTypes(
          [...new Set(response.items.map((item) => item.name))].sort((a, b) => a.localeCompare(b)),
        );
      })
      .catch(() => {
        if (!cancelled) setAvailableEntityTypes([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Connectors a form can fetch from. Gated on the permission its list
  // endpoint requires: without it the request could only 403.
  const canReadConnectors = hasPermission('connector:read');
  const [connectors, setConnectors] = useState<Connector[]>([]);
  useEffect(() => {
    if (!canReadConnectors) return;
    let cancelled = false;
    void connectorsApi
      .list()
      .then((response) => {
        if (!cancelled) setConnectors(response.items ?? []);
      })
      .catch(() => {
        if (!cancelled) setConnectors([]);
      });
    return () => {
      cancelled = true;
    };
  }, [canReadConnectors]);

  type PendingAction =
    | { kind: 'delete'; id: string; label: string }
    | { kind: 'category-delete'; id: string; label: string };
  const [pendingAction, setPendingAction] = useState<PendingAction | null>(null);
  const [categoryModalOpen, setCategoryModalOpen] = useState(false);
  const hasLoadedMethods = useRef(false);

  useEffect(() => {
    // Only the first load should replace the tab with a loading state. Search,
    // paging and filter refreshes keep the current editor mounted.
    void fetchMethods(hasLoadedMethods.current);
    hasLoadedMethods.current = true;
  }, [fetchMethods]);
  useEffect(() => { void fetchCategories(); }, [fetchCategories]);

  // Open the first available method by default, and keep the detail pane
  // useful after a search, archive, or delete changes the visible page.
  useEffect(() => {
    const selectedIsVisible = selectedMethod
      ? methods.some((method) => method.method_id === selectedMethod.identity.method_id)
      : false;
    if (methods.length > 0 && !selectedIsVisible) {
      const firstActive = methods.find((method) => !method.is_archived) ?? methods[0];
      handleSelectMethod(firstActive);
    }
  }, [methods, selectedMethod, handleSelectMethod]);

  const goToFieldLibrary = () => setSearchParams({ tab: 'fields' }, { replace: false });

  const handleAddFields = async (libraryFieldIds: string[]) => {
    await fieldHook.addLibraryFields(libraryFieldIds);
  };

  const handleClone = async (method: MethodIdentity) => {
    const name = window.prompt(`Name for the copy of "${method.name}"`, `${method.name} copy`);
    if (!name?.trim()) return;
    await methodHook.handleCloneMethod(method.method_id, name.trim());
  };

  const handleCloneVersion = async (version: MethodVersion) => {
    if (!selectedMethod) return;
    const name = window.prompt(
      `Name for v${version.version} of "${selectedMethod.identity.name}"`,
      `${selectedMethod.identity.name} copy`,
    );
    if (!name?.trim()) return;
    await methodHook.handleCloneMethod(
      selectedMethod.identity.method_id,
      name.trim(),
      version.version_id,
    );
  };

  const pageStart = total === 0 ? 0 : offset + 1;
  const pageEnd = Math.min(offset + METHOD_PAGE_SIZE, total);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-muted flex items-center justify-center shrink-0">
            <FileText className="w-[18px] h-[18px] text-muted-foreground" />
          </div>
          <div>
            <h2 className="text-lg font-medium text-foreground">{entityTitlePlural}</h2>
            <p className="text-sm text-muted-foreground mt-0.5">
              Reusable ordered {libraryItemLower} lists, composed from {libraryLabel}.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            onClick={() => setCategoryModalOpen(true)}
            icon={<FolderKanban className="w-4 h-4" />}
          >
            Manage categories
          </Button>
          <Button
            variant="ghost"
            onClick={() => { void fetchMethods(); void fetchCategories(); }}
            icon={<RefreshCw className="w-4 h-4" />}
          >
            Refresh
          </Button>
          <Button
            variant="primary"
            onClick={() => methodHook.setShowNewMethodModal(true)}
            disabled={!canWrite}
            icon={<Plus className="w-4 h-4" />}
          >
            New {entityTitle}
          </Button>
        </div>
      </div>

      {!canWrite && (
        <div className="mb-4 rounded-lg border border-warning/30 bg-warning-subtle p-3 text-sm text-warning">
          You have read-only access to the {entityTitlePlural} library.
        </div>
      )}

      {error && (
        <div className="mb-4 flex items-center justify-between gap-2 rounded-lg border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive">
          <span className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            {error}
          </span>
          <button type="button" onClick={() => setError(null)} className="shrink-0">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Search */}
      <div className="mb-4 flex items-center gap-2">
        <div className="relative max-w-sm flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            type="search"
            value={search}
            onChange={(e) => { setOffset(0); setSearch(e.target.value); }}
            placeholder={`Search ${entityLowerPlural} by name or category…`}
            className="h-9 w-full rounded-lg border border-border pl-9 pr-3 text-sm focus:border-cobalt focus:outline-none focus:ring-2 focus:ring-cobalt/20"
          />
        </div>
        <label className="flex h-9 shrink-0 items-center gap-2 rounded-lg border border-border px-3 text-sm text-foreground">
          <input
            type="checkbox"
            checked={methodHook.showArchived}
            onChange={(e) => { setOffset(0); methodHook.setShowArchived(e.target.checked); }}
          />
          Show archived
        </label>
      </div>

      {methods.length === 0 && !search.trim() ? (
        <div className="rounded-xl border border-border bg-card py-16 text-center">
          <FileText className="mx-auto mb-3 h-10 w-10 text-muted-foreground/60" />
          <p className="text-sm font-medium text-foreground">No {entityLowerPlural} yet</p>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
            A {entityLower} is an ordered list of {libraryItemLowerPlural} drawn from the {libraryLabel}. Create one, then
            add the {libraryItemLowerPlural} it should capture.
          </p>
          <Button
            variant="outline"
            onClick={() => methodHook.setShowNewMethodModal(true)}
            className="mt-4"
            disabled={!canWrite}
            icon={<Plus className="w-4 h-4" />}
          >
            Create First {entityTitle}
          </Button>
        </div>
      ) : (
        <div className="flex flex-col gap-4 lg:grid lg:grid-cols-4 lg:gap-6">
          <div className="lg:col-span-1 space-y-4">
            <MethodList
              methods={methods}
              selectedMethodId={selectedMethod?.identity.method_id ?? null}
              editingMethodName={methodHook.editingMethodName}
              savingMethodName={methodHook.savingMethodName}
              canWrite={canWrite}
              onSelectMethod={(method) => {
                fieldHook.cancelEditField();
                handleSelectMethod(method);
              }}
              onNewMethod={() => methodHook.setShowNewMethodModal(true)}
              onDeleteMethod={(method) => setPendingAction({ kind: 'delete', id: method.method_id, label: method.name })}
              onArchiveMethod={(method) => void methodHook.handleArchiveToggle(method.method_id, 'archive')}
              onUnarchiveMethod={(method) => void methodHook.handleArchiveToggle(method.method_id, 'unarchive')}
              archivingMethodId={methodHook.archivingMethod}
              onStartRename={(method) =>
                methodHook.setEditingMethodName({ methodId: method.method_id, name: method.name })
              }
              onChangeRenameName={(name) =>
                methodHook.setEditingMethodName(
                  methodHook.editingMethodName
                    ? { ...methodHook.editingMethodName, name }
                    : null,
                )
              }
              onConfirmRename={() => void methodHook.handleConfirmRename()}
              onCancelRename={() => methodHook.setEditingMethodName(null)}
              onCloneMethod={(method) => void handleClone(method)}
              entityLabel={entityTitle}
              entityLabelPlural={entityTitlePlural}
              codePrefix={codePrefix}
            />

            {total > METHOD_PAGE_SIZE && (
              <div className="flex items-center justify-between rounded-xl border border-border bg-card px-3 py-2 text-xs text-muted-foreground">
                <span>{pageStart}–{pageEnd} of {total}</span>
                <div className="flex items-center gap-1">
                  <Button
                    variant="ghost"
                    size="icon"
                    disabled={offset === 0}
                    onClick={() => setOffset(Math.max(0, offset - METHOD_PAGE_SIZE))}
                    title="Previous page"
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    disabled={offset + METHOD_PAGE_SIZE >= total}
                    onClick={() => setOffset(offset + METHOD_PAGE_SIZE)}
                    title="Next page"
                  >
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            )}
          </div>

          <div className="lg:col-span-3">
            {selectedMethod ? (
              <MethodFieldsEditor
                key={`${selectedMethod.identity.method_id}-${selectedMethod.fields.length === 0 ? 'empty' : 'populated'}`}
                method={selectedMethod}
                categories={categories}
                editingField={fieldHook.editingField}
                savingField={fieldHook.savingField}
                reorderingIndex={fieldHook.reorderingIndex}
                canWrite={canWrite && !selectedMethod.identity.is_archived}
                loadingDetail={loadingDetail}
                existingFieldIds={selectedMethod.fields.map((field) => field.library_field_id)}
                addingFields={fieldHook.savingField}
                onAddFromLibrary={(ids) => void handleAddFields(ids)}
                onAddInheritedField={
                  entity === 'method' ? (pick) => fieldHook.addInheritedField(pick) : undefined
                }
                workflowFieldsByEntityType={workflowFieldsByEntityType}
                onGoToFieldLibrary={goToFieldLibrary}
                onEditField={fieldHook.startEditField}
                onChangeDraft={fieldHook.setEditingField}
                onSaveField={() => void fieldHook.saveEditedField()}
                onCancelEdit={fieldHook.cancelEditField}
                onDeleteField={fieldHook.requestDeleteField}
                onReorderFields={(from, to) => void fieldHook.reorderFields(from, to)}
                onRepinField={(linkId, versionId) => fieldHook.repinField(linkId, versionId)}
                repinningLinkId={fieldHook.repinningLinkId}
                canReadFieldLibrary={hasPermission('field_library:read')}
                onChangeCategory={(categoryId) =>
                  void methodHook.handleUpdateMetadata(selectedMethod.identity.method_id, {
                    category_id: categoryId,
                  })
                }
                onChangeDescription={(description) =>
                  void methodHook.handleUpdateMetadata(selectedMethod.identity.method_id, {
                    description: description || null,
                  })
                }
                connectors={connectors}
                onChangeConnector={
                  entity === 'method'
                    ? (connectorId) => void fieldHook.setConnector(connectorId)
                    : undefined
                }
                availableEntityTypes={availableEntityTypes}
                onChangeEntityTypes={(next) =>
                  void methodHook.handleUpdateMetadata(selectedMethod.identity.method_id, {
                    entity_types: next,
                  })
                }
                onClone={() => void handleClone(selectedMethod.identity)}
                onCloneVersion={(version) => void handleCloneVersion(version)}
                libraryLabel={libraryLabel}
                entityLabel={entityTitle}
                libraryItemTitle={libraryItemTitle}
                libraryItemLabel={libraryItemLower}
                libraryItemLabelPlural={libraryItemLowerPlural}
                selectedItemsLabel={entity === 'composite-block' ? 'step objects' : 'form fields'}
                libraryItemPossessive={libraryItemPossessive}
                libraryEntity={entity === 'composite-block' ? 'step-object' : 'field'}
                codePrefix={codePrefix}
                renderExtra={renderExtra}
              />
            ) : (
              <div className="flex h-64 items-center justify-center rounded-xl border border-border bg-card text-sm text-muted-foreground">
                {methods.length === 0 ? `No ${entityLowerPlural} match your search` : `Select a ${entityLower} to edit`}
              </div>
            )}
          </div>
        </div>
      )}

      {methodHook.showNewMethodModal && (
        <NewMethodModal
          categories={categories}
          creating={methodHook.creatingMethod}
          error={methodHook.newMethodError}
          canWrite={canWrite}
          onCreate={({ name, description, categoryId }) =>
            void methodHook.handleCreateMethod({
              name,
              description,
              category_id: categoryId,
              fields: [],
            })
          }
          onCreateCategory={methodHook.handleCreateCategory}
          onClose={() => {
            methodHook.setShowNewMethodModal(false);
            methodHook.setNewMethodError(null);
          }}
          entityLabel={entityTitle}
          itemLabelPlural={libraryItemTitlePlural}
          libraryLabel={libraryLabel}
        />
      )}

      <MethodCategoryPanel
        open={categoryModalOpen}
        onClose={() => setCategoryModalOpen(false)}
        categories={categories}
        canWrite={canWrite}
        savingCategory={methodHook.savingCategory}
        deletingCategory={methodHook.deletingCategory}
        onCreateCategory={methodHook.handleCreateCategory}
        onRenameCategory={methodHook.handleRenameCategory}
        onDeleteCategory={(category) => setPendingAction({
          kind: 'category-delete',
          id: category.category_id,
          label: category.name,
        })}
      />

      {fieldHook.pendingDeleteField && (
        <RemoveFieldDialog
          fieldLabel={fieldHook.pendingDeleteField.label ?? fieldHook.pendingDeleteField.field_key}
          onCancel={fieldHook.cancelDeleteField}
          onConfirm={() => void fieldHook.confirmDeleteField()}
          itemLabel={libraryItemTitle}
          parentLabel={entityLower}
          libraryLabel={libraryLabel}
        />
      )}

      {pendingAction?.kind === 'delete' && (
        <MethodActionDialog
          title={`Delete ${entityLower} permanently?`}
          description={<>Delete <span className="font-medium text-foreground">{pendingAction.label}</span> and all of its versions? This cannot be undone.</>}
          confirmLabel="Delete permanently"
          busy={methodHook.deletingMethod === pendingAction.id}
          onCancel={() => setPendingAction(null)}
          onConfirm={() => void methodHook.handleDeleteMethod(pendingAction.id).finally(() => setPendingAction(null))}
        />
      )}

      {pendingAction?.kind === 'category-delete' && (
        <MethodActionDialog
          title="Delete category?"
          description={<>Delete <span className="font-medium text-foreground">{pendingAction.label}</span>? Categories with {entityLowerPlural} assigned to them cannot be deleted.</>}
          confirmLabel="Delete category"
          busy={methodHook.deletingCategory === pendingAction.id}
          onCancel={() => setPendingAction(null)}
          onConfirm={() => void methodHook.handleDeleteCategory(pendingAction.id).finally(() => setPendingAction(null))}
        />
      )}
    </div>
  );
}
