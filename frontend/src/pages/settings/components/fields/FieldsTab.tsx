/**
 * FieldsTab
 *
 * Settings tab for Fields (backend/field_library), the organization-wide set
 * of reusable field definitions.
 *
 * Each row is a single compact line; the editor and version history both
 * live in `FieldDetailSheet` (a slide-over, tabbed into Configuration /
 * History) instead of expanding in place, so a field with many versions
 * doesn't push the rest of the list around. Editing still reuses the Forms
 * tab's own field types, per-type inputs, picklist binding, table columns,
 * auto-number affix, currency and calc builder (via `LibraryFieldEditor`,
 * forked from FieldRow). The Picklist panel/modals are the Forms tab's own
 * components, untouched.
 *
 * Name and description edits are lightweight in-place updates. A new version
 * is created when field type or settings change, so forms pinned to an older
 * version remain unchanged. Only the key is immutable after creation.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { toast } from 'sonner';
import {
  ChevronLeft,
  ChevronRight,
  Copy,
  FileText,
  History,
  LayoutGrid,
  List,
  Loader2,
  MoreHorizontal,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  Archive as ArchiveIcon,
  X,
} from 'lucide-react';
import Modal from '@/core/components/Modal';
import Badge from '@/core/components/Badge';
import ViewToggle from '@/core/components/ViewToggle';
import { Button } from '@/components/ui/button';
import { fieldLibrary } from '@/core/services/api';
import { usePermissions } from '@/core/hooks/usePermissions';
import type { FieldType, FieldVersion, FieldWithVersion, FormField, Picklist } from '@/core/types';
import { FIELD_TYPES, FIELD_TYPE_LABELS } from '../form-config/constants';
import { parsePicklistJson } from '../form-config/jsonConfig';
import { usePicklists } from '../form-config/hooks/usePicklists';
import FieldDetailSheet from './FieldDetailSheet';
import { formatLibraryCount } from './fieldLibraryCopy';
import PicklistPanel from '../form-config/components/PicklistPanel';
import EditPicklistModal from '../form-config/components/EditPicklistModal';
import JsonConfigEditorModal from '../form-config/components/JsonConfigEditorModal';
import { useFieldLibraryList } from './useFieldLibraryList';
import { useFieldArchiving } from './useFieldArchiving';
import {
  applyFieldSavePlan,
  buildFieldSavePlan,
  coerceImportedDraft,
  duplicateNameAndTypeError,
  formatFieldCode,
  importFieldDrafts,
  importSummaryToast,
  NEW_FIELD_DRAFT,
  toFormField,
  versionsNewestFirst,
} from './fieldLibraryUtils';

export type FieldsTabViewMode = 'cards' | 'table';

export interface FieldsTabProps {
  /** Optional alternate presentation used by Design › Step Objects. */
  viewMode?: FieldsTabViewMode;
  onViewModeChange?: (mode: FieldsTabViewMode) => void;
  /** Keep the Settings screen's Field wording while reusing its API screen in Design. */
  entity?: 'field' | 'step-object';
  /** Optional create/edit selector additions for a skin-specific library. */
  fieldTypeOptions?: readonly { value: string; label: string }[];
}

function fallbackUserLabel(id: string | null | undefined): string | null {
  return id ? `${id.slice(0, 8)}…` : null;
}

/** One row's in-progress edit, either a brand-new field, or an existing
 *  one being changed. Only one of these exists at a time, driving the one
 *  detail Sheet the whole tab shares. */
type Editing =
  | { isNew: true; field: FormField; description: string }
  | { isNew: false; target: FieldWithVersion; field: FormField; description: string };

export default function FieldsTab({ viewMode = 'table', onViewModeChange, entity = 'field', fieldTypeOptions }: FieldsTabProps) {
  const isStepObject = entity === 'step-object';
  const entityTitle = isStepObject ? 'Step Object' : 'Field';
  const entityTitlePlural = isStepObject ? 'Step Objects' : 'Fields';
  const entityLower = isStepObject ? 'step object' : 'field';
  const entityLowerPlural = isStepObject ? 'step objects' : 'fields';
  const codePrefix = isStepObject ? 'STP' : 'F';
  const { hasPermission } = usePermissions();
  const canWrite = hasPermission('field_library:write');

  const picklistHook = usePicklists();
  const { picklists, fetchPicklists } = picklistHook;
  useEffect(() => { void fetchPicklists(); }, [fetchPicklists]);
  const [picklistsExpanded, setPicklistsExpanded] = useState(false);
  const [jsonEditingPicklist, setJsonEditingPicklist] = useState<Picklist | null>(null);

  const {
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
  } = useFieldLibraryList();

  const [editing, setEditing] = useState<Editing | null>(null);
  const [detailTab, setDetailTab] = useState<'config' | 'history'>('config');
  const [editError, setEditError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const [historyItems, setHistoryItems] = useState<FieldVersion[] | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historySearch, setHistorySearch] = useState('');

  const [isImportOpen, setIsImportOpen] = useState(false);
  const [importText, setImportText] = useState('');
  const [importError, setImportError] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);

  const historyRequestId = useRef(0);

  const allFieldsForEditor = useMemo(
    () => {
      const source = editorFieldEntries.length > 0
        ? editorFieldEntries
        : fields.filter((entry) => !entry.identity.is_archived);
      const byKey = new Map(source.map((entry) => {
        const field = toFormField(entry);
        return [field.id, field] as const;
      }));
      if (editing) byKey.set(editing.field.id, editing.field);
      return [...byKey.values()];
    },
    [editorFieldEntries, fields, editing],
  );

  const loadHistory = useCallback(async (libraryFieldId: string) => {
    const requestId = ++historyRequestId.current;
    setHistoryLoading(true);
    try {
      const res = await fieldLibrary.listVersions(libraryFieldId);
      if (requestId === historyRequestId.current) setHistoryItems(versionsNewestFirst(res.items));
    } catch (e) {
      if (requestId === historyRequestId.current) {
        toast.error(e instanceof Error ? e.message : 'Failed to load version history');
        setHistoryItems([]);
      }
    } finally {
      if (requestId === historyRequestId.current) setHistoryLoading(false);
    }
  }, []);

  // The Sheet's History tab is fetched lazily (only once it's actually
  // selected), and reset whenever the Sheet opens on a different field, or
  // is closed, so stale versions never flash for the next field opened.
  const targetId = editing && !editing.isNew ? editing.target.identity.library_field_id : null;
  useEffect(() => {
    historyRequestId.current += 1;
    setHistoryItems(null);
    setHistorySearch('');
    setHistoryLoading(false);
  }, [targetId]);
  useEffect(() => {
    if (targetId && detailTab === 'history' && historyItems === null && !historyLoading) {
      void loadHistory(targetId);
    }
  }, [targetId, detailTab, historyItems, historyLoading, loadHistory]);

  function startCreate() {
    if (!canWrite) return;
    setEditing({ isNew: true, field: NEW_FIELD_DRAFT, description: '' });
    setDetailTab('config');
    setEditError(null);
  }

  function openField(target: FieldWithVersion, tab: 'config' | 'history' = 'config') {
    const safeTab = tab === 'config' && (!canWrite || target.identity.is_archived) ? 'history' : tab;
    setEditing({ isNew: false, target, field: toFormField(target), description: target.version.description ?? '' });
    setDetailTab(safeTab);
    setEditError(null);
  }

  function closeSheet() {
    setEditing(null);
    setEditError(null);
  }

  const {
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
  } = useFieldArchiving({
    canWrite,
    refreshLibrary,
    onDeleted: (id) => { if (targetId === id) closeSheet(); },
  });

  async function handleSave() {
    if (!editing || !canWrite) return;
    if (!editing.isNew && editing.target.identity.is_archived) {
      setEditError(`Archived ${entityLowerPlural} are read-only.`);
      return;
    }

    const activeEntries = editorFieldEntries.length > 0 ? editorFieldEntries : fields;
    const duplicateError = duplicateNameAndTypeError(
      activeEntries,
      editing.field.label,
      editing.field.type,
      editing.isNew ? undefined : editing.target.identity.library_field_id,
    );
    if (duplicateError) {
      setEditError(duplicateError);
      return;
    }

    const existingKeys = activeEntries
      .filter((entry) => !entry.identity.is_archived)
      .map((entry) => entry.identity.field_key);
    const { plan, error } = buildFieldSavePlan(editing, existingKeys, picklists);
    if (error !== null) {
      setEditError(error);
      return;
    }

    setSaving(true);
    setEditError(null);
    try {
      const { toastMessage } = await applyFieldSavePlan(plan, fieldLibrary);
      if (plan.kind === 'noop') toast.info(toastMessage);
      else toast.success(toastMessage);
      setEditing(null);
      void refreshLibrary();
    } catch (e) {
      setEditError(e instanceof Error ? e.message : `Failed to save ${entityLower}`);
    } finally {
      setSaving(false);
    }
  }

  function openImportModal() {
    if (!canWrite) return;
    setImportText('');
    setImportError(null);
    setIsImportOpen(true);
  }

  async function handleImport() {
    if (!canWrite) return;
    let parsed: unknown;
    try {
      parsed = JSON.parse(importText);
    } catch {
      setImportError('That is not valid JSON.');
      return;
    }
    const rawEntries = Array.isArray(parsed) ? parsed : [parsed];
    if (rawEntries.length === 0) {
      setImportError(`Add at least one ${entityLower} to import.`);
      return;
    }
    const drafts = rawEntries.map(coerceImportedDraft);
    if (drafts.some((d) => d === null)) {
      setImportError(`Every ${entityLower} needs at least a "name" (or "label"). Fix the JSON and try again.`);
      return;
    }

    setImporting(true);
    const activeEntries = editorFieldEntries.length > 0 ? editorFieldEntries : fields;
    const knownEntries = activeEntries.filter((entry) => !entry.identity.is_archived);
    const summary = await importFieldDrafts(
      drafts as { field: FormField; description: string }[],
      knownEntries,
      picklists,
      fieldLibrary.create,
    );
    setImporting(false);
    setIsImportOpen(false);
    if (summary.created > 0) void refreshLibrary();

    const { level, message } = importSummaryToast(summary);
    if (level === 'error') toast.error(message);
    else toast.success(message);
  }

  async function handleExport(field: FieldWithVersion) {
    const portable = {
      name: field.identity.name,
      field_key: field.identity.field_key,
      field_type: field.identity.field_type,
      description: field.version.description ?? undefined,
      settings: field.version.settings,
    };
    try {
      await navigator.clipboard.writeText(JSON.stringify(portable, null, 2));
      toast.success(`Copied "${field.identity.name}" as JSON`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : `Failed to copy ${entityLower} JSON`);
    }
  }

  const archivingField = archiveConfirmId
    ? fields.find((f) => f.identity.library_field_id === archiveConfirmId)
    : null;
  const hardDeletingField = hardDeleteConfirmId
    ? fields.find((f) => f.identity.library_field_id === hardDeleteConfirmId)
    : null;

  const pageStart = total === 0 ? 0 : offset + 1;
  const pageEnd = Math.min(offset + PAGE_SIZE, total);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-medium text-foreground">{entityTitlePlural}</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {isStepObject
              ? 'Create and manage reusable step objects for procedures.'
              : 'Create and manage reusable fields for forms.'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {onViewModeChange && (
            <ViewToggle
              value={viewMode === 'cards' ? 'kanban' : 'list'}
              onChange={(mode) => onViewModeChange(mode === 'kanban' ? 'cards' : 'table')}
              options={[
                { value: 'kanban', label: 'Cards', icon: <LayoutGrid className="size-3.5" /> },
                { value: 'list', label: 'Table', icon: <List className="size-3.5" /> },
              ]}
            />
          )}
          <Button variant="ghost" size="md" onClick={() => void refreshLibrary()} title="Reload from server">
            <RefreshCw className="h-4 w-4" />
            Refresh
          </Button>
          <Button
            variant="outline"
            size="md"
            onClick={openImportModal}
            disabled={!canWrite}
            title={canWrite ? `Create one or more ${entityLowerPlural} from JSON` : `You do not have permission to create ${entityLowerPlural}`}
          >
            Import JSON
          </Button>
          <Button
            variant={editing?.isNew ? 'outline' : 'primary'}
            size="md"
            onClick={editing?.isNew ? closeSheet : startCreate}
            disabled={!canWrite}
            title={editing?.isNew ? `Close the new ${entityLower} form` : undefined}
          >
            {editing?.isNew ? <X className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
            {editing?.isNew ? 'Cancel' : `Add ${entityLower}`}
          </Button>
        </div>
      </div>

      {loadError && (
        <div className="rounded-lg border border-destructive/30 bg-destructive-subtle p-3 text-sm text-destructive">
          {loadError}
        </div>
      )}

      {/* Search + type filter */}
      <div className="flex items-center gap-2">
        <div className="relative max-w-sm flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            type="search"
            value={search}
            onChange={(e) => {
              setOffset(0);
              setSearch(e.target.value);
            }}
            placeholder="Search name, key, type, description, settings…"
            className="h-9 w-full rounded-lg border border-border pl-9 pr-3 text-sm focus:border-cobalt focus:outline-none focus:ring-2 focus:ring-cobalt/20"
          />
        </div>
        <select
          value={typeFilter}
          onChange={(e) => {
            setOffset(0);
            setTypeFilter(e.target.value as FieldType | 'all');
          }}
          className="h-9 rounded-lg border border-border px-3 text-sm focus:border-cobalt focus:outline-none focus:ring-2 focus:ring-cobalt/20"
        >
          <option value="all">All types</option>
          {FIELD_TYPES.map((opt) => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
        <label className="flex h-9 shrink-0 items-center gap-2 rounded-lg border border-border px-3 text-sm text-foreground">
          <input
            type="checkbox"
            checked={showArchived}
            onChange={(e) => {
              setOffset(0);
              setShowArchived(e.target.checked);
            }}
          />
          Show archived
        </label>
      </div>

      {/* Picklists, same panel as the Forms tab, so Select/Multi Select/Picklist
          Multi fields created here have somewhere to manage their options. */}
      <PicklistPanel
        picklists={picklists}
        expanded={picklistsExpanded}
        deletingPicklist={picklistHook.deletingPicklist}
        canWrite={canWrite}
        onToggleExpanded={() => setPicklistsExpanded((v) => !v)}
        onCreatePicklist={picklistHook.handleCreatePicklist}
        onEditPicklist={picklistHook.handleEditPicklist}
        onEditPicklistJson={setJsonEditingPicklist}
        onDeletePicklist={(id) =>
          picklistHook.handleDeletePicklist(id, (msg) => toast.error(msg))
        }
      />

      {/* Library list, one compact line per item in table mode; cards and
          history both reuse the same API-backed editor in card mode. */}
      <div className="rounded-xl border border-border bg-card">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{entityTitlePlural}</span>
          <span className="text-xs text-muted-foreground">
            {formatLibraryCount(total, isSearching, entityLower, entityLowerPlural)}
          </span>
        </div>

        {/* The editor and version
          history both live in the detail Sheet instead of expanding here. */}
        <div className={`max-h-[65vh] min-h-[180px] overflow-y-auto ${viewMode === 'cards' ? 'grid gap-3 p-3 md:grid-cols-2 lg:grid-cols-3' : 'divide-y divide-border'}`}>
          {loading ? (
            <div className="flex items-center justify-center gap-2 py-10 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading {entityLowerPlural}…
            </div>
          ) : fields.length === 0 ? (
            <div className="py-10 text-center text-muted-foreground">
              <FileText className="mx-auto mb-3 h-10 w-10 text-muted-foreground/60" />
              <p className="text-sm">
                {isSearching || typeFilter !== 'all'
                  ? `No ${entityLowerPlural} match your filters`
                  : `No ${entityLowerPlural} configured yet`}
              </p>
              {!isSearching && typeFilter === 'all' && canWrite && (
                <Button variant="outline" onClick={startCreate} className="mt-3">
                  <Plus className="h-4 w-4" />
                  Add your first {entityLower}
                </Button>
              )}
            </div>
          ) : (
            fields.map((field) => {
              const { identity, version } = field;
              const required = version.settings?.required === true;
              const editable = canWrite && !identity.is_archived;
              const versionCreator = version.created_by_name ?? fallbackUserLabel(version.created_by);

              return (
                <div
                  key={identity.library_field_id}
                  role={editable ? 'button' : undefined}
                  tabIndex={editable ? 0 : undefined}
                  onClick={editable ? () => openField(field) : undefined}
                  onKeyDown={editable ? (e) => { if (e.key === 'Enter') openField(field); } : undefined}
                  className={viewMode === 'cards'
                    ? `relative flex min-h-[150px] flex-col gap-3 rounded-xl border border-border bg-card p-4 transition-shadow ${editable ? 'cursor-pointer hover:border-primary/50 hover:shadow-sm' : ''}`
                    : `flex items-center gap-3 px-4 py-2.5 ${editable ? 'cursor-pointer hover:bg-muted/40' : ''}`}
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="text-sm font-semibold text-foreground">{identity.name}</span>
                      <Badge variant="cobalt">{FIELD_TYPE_LABELS[identity.field_type as FieldType] ?? identity.field_type}</Badge>
                      {required && <Badge variant="warning">Required</Badge>}
                      {identity.is_archived && <Badge variant="default">Archived</Badge>}
                    </div>
                    <p className="mt-0.5 truncate text-xs text-muted-foreground">
                      {formatFieldCode(identity.field_count_id, codePrefix)} · v{version.version}
                      {versionCreator ? ` · Version created by ${versionCreator}` : ''}
                      {version.description ? ` · ${version.description}` : ''}
                    </p>
                  </div>

                  <div className={`flex flex-shrink-0 items-center gap-0.5 ${viewMode === 'cards' ? 'self-end' : ''}`} onClick={(e) => e.stopPropagation()}>
                    <Button variant="ghost" size="icon" onClick={() => openField(field, 'history')} title="Show version history">
                      <History className="h-4 w-4" />
                    </Button>
                    <div className="relative">
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => setOpenActionMenuId((current) => (
                          current === identity.library_field_id ? null : identity.library_field_id
                        ))}
                        title={`${entityTitle} actions`}
                      >
                        <MoreHorizontal className="h-4 w-4" />
                      </Button>
                      {openActionMenuId === identity.library_field_id && (
                        <>
                          <button
                            type="button"
                            aria-label="Close field actions"
                            className="fixed inset-0 z-20 cursor-default"
                            onClick={() => setOpenActionMenuId(null)}
                          />
                          <div className="absolute right-0 top-full z-30 mt-1 min-w-44 rounded-lg border border-border bg-card py-1 shadow-lg">
                            <button
                              type="button"
                              onClick={() => {
                                setOpenActionMenuId(null);
                                void handleExport(field);
                              }}
                              className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-foreground hover:bg-muted/50"
                            >
                              <Copy className="h-4 w-4" />
                              Copy JSON
                            </button>
                            {!identity.is_archived && canWrite && (
                              <button
                                type="button"
                                onClick={() => {
                                  setOpenActionMenuId(null);
                                  setArchiveConfirmId(identity.library_field_id);
                                }}
                                className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-foreground hover:bg-muted/50"
                              >
                                <ArchiveIcon className="h-4 w-4" />
                                Archive
                              </button>
                            )}
                            {canWrite && (
                              <button
                                type="button"
                                onClick={() => {
                                  setOpenActionMenuId(null);
                                  setHardDeleteError(null);
                                  setHardDeleteConfirmId(identity.library_field_id);
                                }}
                                className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-destructive hover:bg-destructive-subtle"
                              >
                                <Trash2 className="h-4 w-4" />
                                Delete permanently
                              </button>
                            )}
                          </div>
                        </>
                      )}
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Search is evaluated over every backend page, then the complete
            matching result is paginated here like the normal list. */}
        {total > PAGE_SIZE && (
          <div className="flex items-center justify-between border-t border-border px-4 py-3 text-sm text-muted-foreground">
            <span>{pageStart}–{pageEnd} of {total}</span>
            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                size="icon"
                disabled={offset === 0}
                onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
                title="Previous page"
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                disabled={offset + PAGE_SIZE >= total}
                onClick={() => setOffset((o) => o + PAGE_SIZE)}
                title="Next page"
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        )}
      </div>

      {/* Field detail Sheet: Configuration + History, one field at a time */}
      <FieldDetailSheet
        open={editing !== null}
        onOpenChange={(open) => { if (!open) closeSheet(); }}
        target={editing && !editing.isNew ? editing.target : null}
        tab={detailTab}
        onTabChange={setDetailTab}
        field={editing?.field ?? NEW_FIELD_DRAFT}
        description={editing?.description ?? ''}
        onChangeDescription={(value) => editing && setEditing({ ...editing, description: value })}
        onChangeField={(updated) => editing && setEditing({ ...editing, field: updated })}
        allFields={allFieldsForEditor}
        picklists={picklists}
        isNew={editing?.isNew ?? true}
        saving={saving}
        editError={editError}
        canWrite={canWrite}
        onSave={() => void handleSave()}
        onCancel={closeSheet}
        historyItems={historyItems}
        historyLoading={historyLoading}
        historySearch={historySearch}
        onHistorySearchChange={setHistorySearch}
        displayUser={fallbackUserLabel}
        entityLabel={entityTitle}
        codePrefix={codePrefix}
        fieldTypeOptions={fieldTypeOptions}
      />

      {/* Import JSON Modal */}
      <Modal open={isImportOpen} onClose={() => setIsImportOpen(false)} title={`Import ${entityTitlePlural} from JSON`} size="md">
        <div className="space-y-4">
          {importError && (
            <div className="rounded-lg border border-destructive/30 bg-destructive-subtle p-3 text-sm text-destructive">
              {importError}
            </div>
          )}
          <div>
            <label className="mb-1 block text-sm font-medium text-foreground">{entityTitle} JSON</label>
            <textarea
              className="w-full rounded-lg border border-border px-3 py-2 font-mono text-xs focus:border-cobalt focus:outline-none focus:ring-2 focus:ring-cobalt/20"
              rows={10}
              value={importText}
              onChange={(e) => setImportText(e.target.value)}
              placeholder={'{\n  "name": "Reagent name",\n  "field_type": "select",\n  "description": "Standard reagent picklist",\n  "settings": { "required": true, "enum_values": ["PBS", "DMEM"] }\n}'}
            />
            <p className="mt-1 text-xs text-muted-foreground">
              Paste a single {entityLower} object, or an array of them, the same shape "Copy JSON" produces.
            </p>
          </div>
          <div className="flex justify-end gap-3 border-t border-border pt-4">
            <Button variant="ghost" size="md" onClick={() => setIsImportOpen(false)} disabled={importing}>
              Cancel
            </Button>
            <Button variant="primary" size="md" onClick={() => void handleImport()} disabled={importing}>
              {importing ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              Import
            </Button>
          </div>
        </div>
      </Modal>

      {/* Archive Confirmation Modal */}
      <Modal open={archiveConfirmId !== null} onClose={() => setArchiveConfirmId(null)} title={`Archive ${entityTitle}`} size="sm">
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Archive <strong className="text-foreground">{archivingField?.identity.name}</strong>? It won't be
            deleted, and anything already referencing it keeps working. It won't be available for new use.
          </p>
          <div className="flex justify-end gap-3">
            <Button variant="ghost" size="md" onClick={() => setArchiveConfirmId(null)} disabled={archiving}>
              Cancel
            </Button>
            <Button
              variant="danger"
              size="md"
              onClick={() => archiveConfirmId && void handleArchive(archiveConfirmId)}
              disabled={archiving}
            >
              {archiving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              Archive
            </Button>
          </div>
        </div>
      </Modal>

      {/* Permanent delete confirmation. The API refuses deletion when any form
          uses the library item and returns the referencing-form count in its error. */}
      <Modal
        open={hardDeleteConfirmId !== null}
        onClose={() => {
          if (!hardDeleting) {
            setHardDeleteConfirmId(null);
            setHardDeleteError(null);
          }
        }}
        title={`Delete ${entityTitle} Permanently`}
        size="sm"
      >
        <div className="space-y-4">
          {hardDeleteError && (
            <div className="rounded-lg border border-destructive/30 bg-destructive-subtle p-3 text-sm text-destructive">
              {hardDeleteError}
            </div>
          )}
          <p className="text-sm text-muted-foreground">
            Permanently delete <strong className="text-foreground">{hardDeletingField?.identity.name}</strong> and
            every version? This cannot be undone. {entityTitlePlural} used by a form cannot be deleted; archive them instead.
          </p>
          <div className="flex justify-end gap-3">
            <Button
              variant="ghost"
              size="md"
              onClick={() => {
                setHardDeleteConfirmId(null);
                setHardDeleteError(null);
              }}
              disabled={hardDeleting}
            >
              Cancel
            </Button>
            <Button
              variant="danger"
              size="md"
              onClick={() => hardDeleteConfirmId && void handleHardDelete(hardDeleteConfirmId)}
              disabled={hardDeleting}
            >
              {hardDeleting ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              Delete permanently
            </Button>
          </div>
        </div>
      </Modal>

      {/* Edit/create picklist modal, same component the Forms tab uses */}
      {picklistHook.editingPicklist && (
        <EditPicklistModal
          editingPicklist={picklistHook.editingPicklist}
          saving={picklistHook.savingPicklist}
          canWrite={canWrite}
          onChange={(updated) => picklistHook.setEditingPicklist(updated)}
          onSave={(updated) => picklistHook.handleSavePicklist((msg) => toast.error(msg), updated)}
          onClose={() => picklistHook.setEditingPicklist(null)}
          onAddOption={picklistHook.handleAddPicklistOption}
          onRemoveOption={picklistHook.handleRemovePicklistOption}
          onChangeOption={picklistHook.handlePicklistOptionChange}
        />
      )}

      {jsonEditingPicklist && (
        <JsonConfigEditorModal
          key={jsonEditingPicklist.id}
          noun="Picklist"
          description={jsonEditingPicklist.name}
          canWrite={canWrite}
          load={async () => ({
            name: jsonEditingPicklist.name,
            options: jsonEditingPicklist.options,
          })}
          parse={parsePicklistJson}
          onSave={(data) => picklistHook.handleUpdatePicklistJson(jsonEditingPicklist, data)}
          onClose={() => setJsonEditingPicklist(null)}
        />
      )}
    </div>
  );
}
