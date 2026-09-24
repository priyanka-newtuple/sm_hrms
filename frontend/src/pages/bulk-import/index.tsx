import { useEffect, useMemo, useRef, useState } from 'react';
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom';
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Eye,
  FileText,
  Loader2,
  Paperclip,
  Plus,
  Search,
  ShieldCheck,
  Sparkles,
  Table2,
  UploadCloud,
  X,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { useBulkImportJob } from '@/core/hooks/useBulkImportJob';
import { useBulkImportJobs } from '@/core/hooks/useBulkImportJobs';
import { useEntityTypes } from '@/core/hooks/useEntityTypes';
import { useFeatureFlags } from '@/core/hooks/useFeatureFlags';
import { useFormSchemas } from '@/core/hooks/useFormSchemas';
import { usePermissions } from '@/core/hooks/usePermissions';
import { useSourcePickers } from '@/core/hooks/useSourcePickers';
import SourceLinkFields from '@/core/components/SourceLinkFields';
import {
  getEnterableFields,
  hasIdentifierTemplate,
  resolveIdentifierLabel,
} from '@/shared/utils/entityForm';
import type { FormField, StateMachineRecord } from '@/core/types';
import {
  BULK_IMPORT_ACTIVE_STATUSES,
  bulkImports,
  getApiErrorMessage,
  stateMachines,
  type BulkImportDraft,
  type BulkImportJob,
  type BulkImportSpreadsheetSource,
} from '@/core/services/api';
import AgentMissionControl from './components/AgentMissionControl';
import BulkImportPagination from './components/BulkImportPagination';
import BulkImportReviewDrawer, {
  type BulkImportDecision,
} from './components/BulkImportReviewDrawer';
import RecentImportsList from './components/RecentImportsList';

const ACCEPTED_FILES = '.pdf,.csv,.xls,.xlsx,.doc,.docx,.png,.jpg';
const ATTACHMENT_MAPPING_TARGET = '__managed_attachment__';
const RELATION_MAPPING_PREFIX = '__parent_relation__:';

const fileKey = (file: File) => `${file.name}:${file.size}:${file.lastModified}`;

const isSpreadsheetFile = (file: File) => /\.(csv|xls|xlsx)$/i.test(file.name);

const humanizeField = (field: string) =>
  field.replace(/[_-]+/g, ' ').replace(/\b\w/g, (character) => character.toUpperCase());

const normalizeEntityType = (value: string) =>
  value.replace(/^ATS\./i, '').trim().toLowerCase();

const REVIEW_CONFIDENCE_THRESHOLD = 0.8;
const REVIEW_PAGE_SIZE_DEFAULT = 25;

type ReviewFilter = 'exceptions' | 'ready' | 'all';

interface DraftReviewIssue {
  code: 'error' | 'low-confidence' | 'missing-required' | 'existing-record' | 'attachment-error' | 'parent-error';
  label: string;
  tone: 'destructive' | 'warning' | 'info';
}

const isEmptyReviewValue = (value: unknown) =>
  value === null
  || value === undefined
  || (typeof value === 'string' && value.trim() === '')
  || (Array.isArray(value) && value.length === 0);

const compactReviewValue = (value: unknown) => {
  if (isEmptyReviewValue(value)) return 'Not provided';
  if (Array.isArray(value)) return value.map(String).join(', ');
  if (typeof value === 'object') return 'Structured value';
  return String(value);
};

function getDraftReviewIssues(
  draft: BulkImportDraft,
  schemaFields: FormField[],
): DraftReviewIssue[] {
  const issues: DraftReviewIssue[] = [];
  if (draft.error) {
    issues.push({ code: 'error', label: draft.error, tone: 'destructive' });
  }
  if (draft.confidence < REVIEW_CONFIDENCE_THRESHOLD) {
    issues.push({
      code: 'low-confidence',
      label: `Low confidence (${Math.round(draft.confidence * 100)}%)`,
      tone: 'warning',
    });
  }
  const missingRequired = schemaFields
    .filter((field) => field.required && isEmptyReviewValue(draft.data[field.id]))
    .map((field) => field.label || humanizeField(field.id));
  if (missingRequired.length > 0) {
    issues.push({
      code: 'missing-required',
      label: `Missing required: ${missingRequired.join(', ')}`,
      tone: 'destructive',
    });
  }
  if (draft.existing_entity) {
    issues.push({
      code: 'existing-record',
      label: 'Possible existing record',
      tone: 'info',
    });
  }
  const failedReferences = (draft.remote_file_references || []).filter(
    (reference) => reference.status === 'failed' || reference.status === 'missing',
  );
  if (failedReferences.length > 0) {
    const firstFailure = failedReferences[0];
    issues.push({
      code: 'attachment-error',
      label: failedReferences.length === 1
        ? `${firstFailure.source_column}: ${firstFailure.error || 'attachment could not be imported'}`
        : `${failedReferences.length} attachment references need review. First: ${firstFailure.error || 'attachment could not be imported'}`,
      tone: 'warning',
    });
  }
  const missingParents = (draft.relation_bindings || []).filter(
    (binding) => binding.relation_type === 'REFERENCE' && binding.status !== 'resolved',
  );
  if (missingParents.length > 0) {
    issues.push({
      code: 'parent-error',
      label: missingParents[0].error || `Missing ${missingParents[0].source_entity_type_name}`,
      tone: 'destructive',
    });
  }
  return issues;
}

interface SpreadsheetFieldPickerProps {
  fields: FormField[];
  selected: string[];
  disabled: boolean;
  onChange: (fieldIds: string[]) => void;
}

function SpreadsheetFieldPicker({
  fields,
  selected,
  disabled,
  onChange,
}: SpreadsheetFieldPickerProps) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const selectedSet = new Set(selected);
  const fieldById = new Map(fields.map((field) => [field.id, field]));
  const normalizedSearch = search.trim().toLowerCase();
  const filteredFields = normalizedSearch
    ? fields.filter((field) =>
        `${field.label || ''} ${field.id}`.toLowerCase().includes(normalizedSearch),
      )
    : fields;

  return (
    <div className="flex flex-wrap items-center gap-2">
      {selected.map((fieldId) => {
        const field = fieldById.get(fieldId);
        const isAttachment = fieldId === ATTACHMENT_MAPPING_TARGET;
        return (
          <span
            key={fieldId}
            className="inline-flex items-center gap-1 rounded-full border border-primary/40 bg-primary/10 px-2.5 py-1 text-primary"
          >
            {isAttachment && <Paperclip className="h-3 w-3" />}
            {field?.label || humanizeField(fieldId)}
            <button
              type="button"
              disabled={disabled}
              aria-label={`Remove ${field?.label || humanizeField(fieldId)} mapping`}
              onClick={() => onChange(selected.filter((id) => id !== fieldId))}
              className="rounded-full p-0.5 hover:bg-primary/10 disabled:opacity-50"
            >
              <X className="h-3 w-3" />
            </button>
          </span>
        );
      })}
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger
          disabled={disabled}
          render={
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-7 rounded-full px-2.5 text-xs"
            >
              <Plus className="h-3.5 w-3.5" />
              {selected.length > 0 ? 'Add target' : 'Choose target'}
            </Button>
          }
        />
        {open && (
          <PopoverContent
            align="start"
            initialFocus={(interactionType) => interactionType === 'keyboard'}
            className="w-80 p-2"
          >
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search fields or attachments…"
                className="pl-8"
              />
            </div>
            <div className="max-h-64 overflow-y-auto py-1">
              {filteredFields.map((field) => (
                <label
                  key={field.id}
                  className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-2 hover:bg-muted"
                >
                  <input
                    type="checkbox"
                    checked={selectedSet.has(field.id)}
                    onChange={(event) =>
                      onChange(
                        event.target.checked
                          ? [...selected, field.id]
                          : selected.filter((id) => id !== field.id),
                      )
                    }
                    className="h-4 w-4 accent-primary"
                  />
                  <span className="min-w-0 flex-1 truncate">
                    {field.label || humanizeField(field.id)}
                  </span>
                  <span className="truncate text-[10px] text-muted-foreground">{field.id}</span>
                </label>
              ))}
              {filteredFields.length === 0 && (
                <div className="px-2 py-6 text-center text-muted-foreground">
                  No matching targets
                </div>
              )}
            </div>
          </PopoverContent>
        )}
      </Popover>
    </div>
  );
}

const MAPPING_PAGE_SIZE = 10;

interface SpreadsheetMappingSourceCardProps {
  source: BulkImportSpreadsheetSource;
  mappings: Record<string, string[]>;
  fields: FormField[];
  disabled: boolean;
  onChange: (column: string, fieldIds: string[]) => void;
}

function SpreadsheetMappingSourceCard({
  source,
  mappings,
  fields,
  disabled,
  onChange,
}: SpreadsheetMappingSourceCardProps) {
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(0);
  const normalizedSearch = search.trim().toLowerCase();
  const filteredColumns = source.columns.filter((column) =>
    !normalizedSearch || column.toLowerCase().includes(normalizedSearch),
  );
  const pageCount = Math.max(1, Math.ceil(filteredColumns.length / MAPPING_PAGE_SIZE));
  const safePage = Math.min(page, pageCount - 1);
  const visibleColumns = filteredColumns.slice(
    safePage * MAPPING_PAGE_SIZE,
    (safePage + 1) * MAPPING_PAGE_SIZE,
  );

  useEffect(() => {
    setPage(0);
  }, [search]);

  return (
    <div className="overflow-hidden rounded-xl border border-border bg-background text-xs">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3">
        <div>
          <div className="font-medium text-foreground">
            {source.filename} · {source.sheet_name}
          </div>
          <div className="mt-0.5 text-muted-foreground">
            {source.row_count} row{source.row_count === 1 ? '' : 's'} · {source.columns.length} columns
          </div>
        </div>
        <div className="relative w-full sm:w-64">
          <Search className="pointer-events-none absolute left-2.5 top-2 h-3.5 w-3.5 text-muted-foreground" />
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Find a source column"
            className="h-8 pl-8 text-xs"
          />
        </div>
      </div>
      <div className="hidden grid-cols-[minmax(0,0.9fr)_2rem_minmax(0,1.6fr)] items-center gap-3 border-b border-border bg-muted/20 px-4 py-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground md:grid">
        <span>CSV / Excel column</span>
        <span aria-hidden="true" />
        <span>Form field(s) or attachment</span>
      </div>
      <div className="divide-y divide-border">
        {visibleColumns.map((column) => {
          const selectedFields = mappings[column] || [];
          const attachmentSelected = selectedFields.includes(ATTACHMENT_MAPPING_TARGET);
          const formFieldCount = selectedFields.length - (attachmentSelected ? 1 : 0);
          return (
            <div
              key={column}
              className="grid gap-2 px-4 py-3 md:grid-cols-[minmax(0,0.9fr)_2rem_minmax(0,1.6fr)] md:items-center md:gap-3"
            >
              <div className="min-w-0">
                <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground md:hidden">
                  CSV / Excel column
                </div>
                <span className="block truncate font-medium text-foreground">{column}</span>
                <span className={selectedFields.length > 0 ? 'text-emerald-700 dark:text-emerald-400' : 'text-amber-700 dark:text-amber-400'}>
                  {selectedFields.length > 0
                    ? attachmentSelected && formFieldCount === 0
                      ? 'Imported as attachment'
                      : attachmentSelected
                        ? `Attachment + ${formFieldCount} field${formFieldCount === 1 ? '' : 's'}`
                        : `Mapped to ${formFieldCount} field${formFieldCount === 1 ? '' : 's'}`
                    : 'Not mapped'}
                </span>
              </div>
              <ArrowRight className="hidden h-4 w-4 text-muted-foreground md:block" />
              <div className="min-w-0">
                <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground md:hidden">
                  Form field(s) or attachment
                </div>
                <SpreadsheetFieldPicker
                  fields={fields}
                  selected={selectedFields}
                  disabled={disabled}
                  onChange={(fieldIds) => onChange(column, fieldIds)}
                />
              </div>
            </div>
          );
        })}
        {visibleColumns.length === 0 && (
          <div className="px-4 py-10 text-center text-muted-foreground">
            No source columns match “{search}”.
          </div>
        )}
      </div>
      <BulkImportPagination
        page={safePage}
        pageSize={MAPPING_PAGE_SIZE}
        total={filteredColumns.length}
        noun="columns"
        onPageChange={setPage}
      />
      {source.unmapped_columns.length > 0 && (
        <div className="border-t border-border bg-amber-500/5 px-4 py-2.5 text-amber-700 dark:text-amber-400">
          {source.unmapped_columns.length} column{source.unmapped_columns.length === 1 ? '' : 's'} currently ignored
        </div>
      )}
    </div>
  );
}

export default function BulkImportPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { bulkImportEnabled } = useFeatureFlags();
  const { can, hasPermission } = usePermissions();
  const sourceLinks = useSourcePickers();
  const { entityTypes, loading: typesLoading, getEntityType } = useEntityTypes();
  const requestedType = searchParams.get('entityType') || '';
  const preselectedWorkflowName = searchParams.get('workflow') || null;
  const jobIdParam = searchParams.get('job');
  const [entityTypeId, setEntityTypeId] = useState('');
  const [selectedWorkflowName, setSelectedWorkflowName] = useState(
    preselectedWorkflowName || '',
  );
  const [workflows, setWorkflows] = useState<StateMachineRecord[]>([]);
  const [workflowsLoading, setWorkflowsLoading] = useState(false);
  const [workflowsError, setWorkflowsError] = useState<string | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const {
    job,
    setJob,
    loading: jobLoading,
    error: jobLoadError,
  } = useBulkImportJob(jobIdParam);
  const { jobs: recentJobs, loading: recentJobsLoading } = useBulkImportJobs();
  const [busy, setBusy] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [spreadsheetMappings, setSpreadsheetMappings] = useState<
    Record<string, Record<string, string[]>>
  >({});
  const [spreadsheetMappingsDirty, setSpreadsheetMappingsDirty] = useState(false);
  const [reviewFilter, setReviewFilter] = useState<ReviewFilter>('exceptions');
  const [reviewPage, setReviewPage] = useState(0);
  const [reviewPageSize, setReviewPageSize] = useState(REVIEW_PAGE_SIZE_DEFAULT);
  const [activeDraftId, setActiveDraftId] = useState<string | null>(null);
  const [draftDecisions, setDraftDecisions] = useState<Record<string, BulkImportDecision>>({});
  const [selectedReviewIds, setSelectedReviewIds] = useState<Set<string>>(new Set());
  const requestedEntityType = useMemo(
    () => (requestedType ? getEntityType(requestedType) : undefined),
    [getEntityType, requestedType],
  );
  const requestedEntityTypeId = requestedEntityType
    ? requestedEntityType.entity_type_id || requestedEntityType.id
    : '';
  const selectedEntityTypeName = useMemo(
    () =>
      entityTypes.find((type) => (type.entity_type_id || type.id) === entityTypeId)?.name
      || requestedEntityType?.name
      || undefined,
    [entityTypeId, entityTypes, requestedEntityType],
  );
  const selectedEntityType = useMemo(
    () => entityTypes.find((type) =>
      (type.entity_type_id || type.id) === (job?.entity_type_id || entityTypeId),
    ) || requestedEntityType,
    [entityTypeId, entityTypes, job?.entity_type_id, requestedEntityType],
  );
  const bulkParentPickers = useMemo(
    () => sourceLinks.pickers.filter((picker) => !picker.declaration.relation_name),
    [sourceLinks.pickers],
  );
  const hasDocumentSources = files.some((file) => !isSpreadsheetFile(file));
  const missingRequiredDocumentParent = hasDocumentSources
    ? bulkParentPickers.find(
        (picker) => picker.declaration.relation_type === 'REFERENCE'
          && !sourceLinks.selections[picker.declaration.relation_def_id],
      )
    : undefined;
  const compatibleWorkflows = useMemo(() => {
    if (!selectedEntityTypeName) return [];
    const normalizedType = normalizeEntityType(selectedEntityTypeName);
    return workflows
      .filter(
        (workflow) =>
          workflow.is_active
          && normalizeEntityType(workflow.entity_type) === normalizedType,
      )
      .sort((left, right) => left.name.localeCompare(right.name));
  }, [selectedEntityTypeName, workflows]);
  const { schemas: reviewSchemas } = useFormSchemas(
    job?.entity_type_name || selectedEntityTypeName,
  );
  const reviewSchemaFields = useMemo(() => {
    const unique = new Map<string, FormField>();
    unique.set('identifier', {
      id: 'identifier',
      label: resolveIdentifierLabel(
        selectedEntityType?.schema_definition,
        job?.entity_type_name || selectedEntityTypeName,
      ),
      type: 'text',
      required: !hasIdentifierTemplate(selectedEntityType?.schema_definition),
      system: true,
      col_span: 'half',
    });
    reviewSchemas
      .filter((schema) => schema.is_active)
      .flatMap((schema) => getEnterableFields(schema))
      .forEach((field) => {
        if (!unique.has(field.id)) {
          unique.set(field.id, {
            ...field,
            col_span:
              field.col_span
              || (field.type === 'textarea' || field.type === 'table' ? undefined : 'half'),
          });
        }
      });
    return Array.from(unique.values());
  }, [job?.entity_type_name, reviewSchemas, selectedEntityType, selectedEntityTypeName]);
  const reviewEntries = useMemo(
    () => (job?.drafts ?? []).map((draft, index) => ({
      draft,
      index,
      issues: getDraftReviewIssues(draft, reviewSchemaFields),
    })),
    [job?.drafts, reviewSchemaFields],
  );
  const exceptionCount = reviewEntries.filter((entry) => entry.issues.length > 0).length;
  const readyCount = reviewEntries.length - exceptionCount;
  const visibleReviewEntries = reviewEntries.filter((entry) => {
    if (reviewFilter === 'exceptions') return entry.issues.length > 0;
    if (reviewFilter === 'ready') return entry.issues.length === 0;
    return true;
  });
  const pagedReviewEntries = visibleReviewEntries.slice(
    reviewPage * reviewPageSize,
    (reviewPage + 1) * reviewPageSize,
  );
  const pageReviewIds = pagedReviewEntries.map((entry) => entry.draft.draft_id);
  const selectedVisibleCount = visibleReviewEntries.filter((entry) =>
    selectedReviewIds.has(entry.draft.draft_id),
  ).length;
  const allPageSelected = pageReviewIds.length > 0
    && pageReviewIds.every((draftId) => selectedReviewIds.has(draftId));
  const somePageSelected = pageReviewIds.some((draftId) => selectedReviewIds.has(draftId));
  const allVisibleSelected = visibleReviewEntries.length > 0
    && selectedVisibleCount === visibleReviewEntries.length;
  const activeReviewIndex = visibleReviewEntries.findIndex(
    (entry) => entry.draft.draft_id === activeDraftId,
  );
  const activeReviewEntry = activeReviewIndex >= 0
    ? visibleReviewEntries[activeReviewIndex]
    : null;
  const reviewedVisibleCount = visibleReviewEntries.filter((entry) =>
    Boolean(draftDecisions[entry.draft.draft_id])
    || !entry.draft.selected
    || entry.issues.length === 0,
  ).length;
  const unreviewedExceptionCount = reviewEntries.filter((entry) =>
    entry.issues.length > 0
    && entry.draft.selected
    && !draftDecisions[entry.draft.draft_id],
  ).length;
  const previewFields = useMemo(
    () => reviewSchemaFields
      .filter((field) => field.id !== 'identifier')
      .sort((left, right) => Number(right.required) - Number(left.required))
      .slice(0, 3),
    [reviewSchemaFields],
  );

  useEffect(() => {
    if (!requestedEntityTypeId) return;
    setEntityTypeId((current) => current || requestedEntityTypeId);
  }, [requestedEntityTypeId]);

  useEffect(() => {
    if (!selectedEntityTypeName || job) {
      if (!job) sourceLinks.reset();
      return;
    }
    sourceLinks.load(selectedEntityTypeName);
  }, [job, selectedEntityTypeName, sourceLinks.load, sourceLinks.reset]);

  useEffect(() => {
    // A loaded job's own workflow_name always wins over a stale `workflow` URL
    // param — e.g. resuming a different recent job while the URL still carries
    // whatever workflow the original "Import and enroll" link set.
    if (job) {
      setSelectedWorkflowName(job.workflow_name || '');
    } else if (preselectedWorkflowName) {
      setSelectedWorkflowName(preselectedWorkflowName);
    }
    if (preselectedWorkflowName) return;
    if (!job) return;

    let cancelled = false;
    setWorkflowsLoading(true);
    setWorkflowsError(null);
    stateMachines
      .listPublished()
      .then((published) => {
        if (!cancelled) setWorkflows(published);
      })
      .catch((err) => {
        if (!cancelled) {
          setWorkflowsError(getApiErrorMessage(err, 'Workflows could not be loaded'));
        }
      })
      .finally(() => {
        if (!cancelled) setWorkflowsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [job?.job_id, job?.workflow_name, preselectedWorkflowName]);

  useEffect(() => {
    setSpreadsheetMappings(
      Object.fromEntries(
        (job?.spreadsheet_sources ?? []).map((source) => [
          `${source.file_id}:${source.sheet_name}`,
          Object.fromEntries(
            source.columns.flatMap((column) => {
              const targets = [...(source.column_mapping[column] || [])];
              if (source.remote_file_columns.includes(column)) {
                targets.push(ATTACHMENT_MAPPING_TARGET);
              }
              Object.entries(source.relation_column_mapping || {}).forEach(
                ([relationDefId, relationColumn]) => {
                  if (relationColumn === column) targets.push(`${RELATION_MAPPING_PREFIX}${relationDefId}`);
                },
              );
              return targets.length > 0 ? [[column, targets]] : [];
            }),
          ),
        ]),
      ),
    );
    setSpreadsheetMappingsDirty(false);
  }, [job?.job_id, job?.spreadsheet_sources]);

  useEffect(() => {
    setReviewFilter('exceptions');
    setReviewPage(0);
    setActiveDraftId(null);
    setDraftDecisions(Object.fromEntries(
      (job?.drafts ?? [])
        .filter((draft) => Boolean(draft.review_decision))
        .map((draft) => [draft.draft_id, draft.review_decision as BulkImportDecision]),
    ));
    setSelectedReviewIds(new Set());
  }, [job?.job_id]);

  useEffect(() => {
    setReviewPage(0);
    setActiveDraftId(null);
    setSelectedReviewIds(new Set());
  }, [reviewFilter, reviewPageSize]);

  const assignedFileIds = useMemo(
    () => new Set([
      ...(job?.drafts.flatMap((draft) => draft.file_ids) ?? []),
      ...(job?.spreadsheet_sources.map((source) => source.file_id) ?? []),
    ]),
    [job?.drafts, job?.spreadsheet_sources],
  );
  const unmappedFileIds = useMemo(
    () => job?.files.map((file) => file.file_id).filter((id) => !assignedFileIds.has(id)) ?? [],
    [assignedFileIds, job?.files],
  );

  if (!bulkImportEnabled || !hasPermission('entity_record:write')) {
    return <Navigate to="/records" replace />;
  }

  const updateDraft = (draftId: string, update: Partial<BulkImportDraft>) => {
    if (!job) return;
    setJob({
      ...job,
      drafts: job.drafts.map((draft) =>
        draft.draft_id === draftId ? { ...draft, ...update } : draft,
      ),
    });
  };

  const fieldsForDraft = (draft: BulkImportDraft): FormField[] => {
    const known = new Set(reviewSchemaFields.map((field) => field.id));
    const fallbackFields: FormField[] = Object.keys(draft.data)
      .filter((field) => !known.has(field))
      .map((field) => ({
        id: field,
        label: humanizeField(field),
        type: field === 'identifier' ? 'text' : 'text',
        required: field === 'identifier',
        system: false,
        col_span: 'half',
      }));
    return [...reviewSchemaFields, ...fallbackFields];
  };

  const openReviewEntry = (index: number) => {
    const entry = visibleReviewEntries[index];
    if (!entry) return;
    setActiveDraftId(entry.draft.draft_id);
    setReviewPage(Math.floor(index / reviewPageSize));
  };

  const advanceAfterDecision = (draftId: string) => {
    const currentIndex = visibleReviewEntries.findIndex(
      (entry) => entry.draft.draft_id === draftId,
    );
    const nextIndex = currentIndex + 1;
    if (currentIndex >= 0 && nextIndex < visibleReviewEntries.length) {
      openReviewEntry(nextIndex);
    } else {
      setActiveDraftId(null);
    }
  };

  const decideDraft = (
    draftId: string,
    decision: BulkImportDecision,
    data?: Record<string, unknown>,
  ) => {
    updateDraft(draftId, {
      selected: decision !== 'rejected',
      review_decision: decision,
      ...(data ? { data } : {}),
    });
    setDraftDecisions((current) => ({ ...current, [draftId]: decision }));
    advanceAfterDecision(draftId);
  };

  const toggleReviewSelection = (draftId: string, selected: boolean) => {
    setSelectedReviewIds((current) => {
      const next = new Set(current);
      if (selected) next.add(draftId);
      else next.delete(draftId);
      return next;
    });
  };

  const togglePageSelection = (selected: boolean) => {
    setSelectedReviewIds((current) => {
      const next = new Set(current);
      pageReviewIds.forEach((draftId) => {
        if (selected) next.add(draftId);
        else next.delete(draftId);
      });
      return next;
    });
  };

  const selectAllVisibleReviews = () => {
    setSelectedReviewIds((current) => new Set([
      ...current,
      ...visibleReviewEntries.map((entry) => entry.draft.draft_id),
    ]));
  };

  const applyBulkDecision = (decision: Extract<BulkImportDecision, 'accepted' | 'rejected'>) => {
    if (!job || selectedReviewIds.size === 0) return;
    setJob({
      ...job,
      drafts: job.drafts.map((draft) => selectedReviewIds.has(draft.draft_id)
        ? {
          ...draft,
          selected: decision === 'accepted',
          review_decision: decision,
        }
        : draft),
    });
    setDraftDecisions((current) => ({
      ...current,
      ...Object.fromEntries(Array.from(selectedReviewIds, (draftId) => [draftId, decision])),
    }));
    setSelectedReviewIds(new Set());
  };

  const openJob = (jobId: string) => {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.set('job', jobId);
        return next;
      },
      { replace: true },
    );
  };

  const startNewImport = () => {
    setJob(null);
    setFiles([]);
    setEntityTypeId(requestedEntityTypeId);
    setSelectedWorkflowName(preselectedWorkflowName || '');
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.delete('job');
        return next;
      },
      { replace: true },
    );
  };

  const uploadAndAnalyze = async () => {
    if (!entityTypeId || files.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      const created = await bulkImports.create(
        entityTypeId,
        files,
        preselectedWorkflowName,
        Object.entries(sourceLinks.selections)
          .filter(([relationDefId]) => bulkParentPickers.some(
            (picker) => picker.declaration.relation_def_id === relationDefId,
          ))
          .filter(([, sourceEntityId]) => Boolean(sourceEntityId))
          .map(([relationDefId, sourceEntityId]) => ({
            relation_def_id: relationDefId,
            source_entity_id: sourceEntityId,
          })),
      );
      const analyzed = await bulkImports.analyze(created.job_id);
      setJob(analyzed);
      openJob(analyzed.job_id);
    } catch (err) {
      setError(getApiErrorMessage(err, 'Bulk analysis failed'));
    } finally {
      setBusy(false);
    }
  };

  const addFiles = (selectedFiles: FileList | null) => {
    // FileList is live. Copy it before the input is cleared so React can safely
    // run this state updater later without observing an emptied FileList.
    const incomingFiles = selectedFiles ? Array.from(selectedFiles) : [];
    if (incomingFiles.length === 0) return;
    setFiles((current) => {
      const existing = new Set(current.map(fileKey));
      return [
        ...current,
        ...incomingFiles.filter((file) => !existing.has(fileKey(file))),
      ];
    });
  };

  const removeFile = (fileToRemove: File) => {
    const keyToRemove = fileKey(fileToRemove);
    setFiles((current) => current.filter((file) => fileKey(file) !== keyToRemove));
  };

  const updateSpreadsheetColumn = (
    fileId: string,
    sheetName: string,
    sourceColumn: string,
    targetFields: string[],
  ) => {
    const sourceKey = `${fileId}:${sheetName}`;
    setSpreadsheetMappings((current) => {
      const relationTargets = targetFields.filter((target) => target.startsWith(RELATION_MAPPING_PREFIX));
      const sheetMappings = Object.fromEntries(
        Object.entries(current[sourceKey] || {}).map(([column, targets]) => [
          column,
          targets.filter((target) =>
            column === sourceColumn || !relationTargets.includes(target),
          ),
        ]),
      );
      sheetMappings[sourceColumn] = targetFields;
      return {
        ...current,
        [sourceKey]: Object.fromEntries(
          Object.entries(sheetMappings).filter(([, targets]) => targets.length > 0),
        ),
      };
    });
    setSpreadsheetMappingsDirty(true);
  };

  const applySpreadsheetMappings = async () => {
    if (!job) return;
    const mappings = job.spreadsheet_sources.map((source) => ({
      file_id: source.file_id,
      sheet_name: source.sheet_name,
      column_mapping: Object.fromEntries(
        Object.entries(spreadsheetMappings[`${source.file_id}:${source.sheet_name}`] || {})
          .map(([column, targets]) => [
            column,
            targets.filter((target) =>
              target !== ATTACHMENT_MAPPING_TARGET
              && !target.startsWith(RELATION_MAPPING_PREFIX),
            ),
          ])
          .filter(([, targets]) => (targets as string[]).length > 0),
      ),
      remote_file_columns: Object.entries(
        spreadsheetMappings[`${source.file_id}:${source.sheet_name}`] || {},
      )
        .filter(([, targets]) => targets.includes(ATTACHMENT_MAPPING_TARGET))
        .map(([column]) => column),
      relation_column_mapping: Object.fromEntries(
        Object.entries(spreadsheetMappings[`${source.file_id}:${source.sheet_name}`] || {})
          .flatMap(([column, targets]) => targets
            .filter((target) => target.startsWith(RELATION_MAPPING_PREFIX))
            .map((target) => [target.slice(RELATION_MAPPING_PREFIX.length), column])),
      ),
    }));
    setBusy(true);
    setError(null);
    try {
      setJob(await bulkImports.updateSpreadsheetMapping(job.job_id, mappings));
    } catch (err) {
      setError(getApiErrorMessage(err, 'Spreadsheet mapping could not be updated'));
    } finally {
      setBusy(false);
    }
  };

  const saveReview = async (): Promise<BulkImportJob | null> => {
    if (!job) return null;
    const updated = await bulkImports.review(
      job.job_id,
      job.drafts,
      unmappedFileIds,
      selectedWorkflowName || null,
    );
    setJob(updated);
    return updated;
  };

  const saveReviewOnly = async () => {
    setBusy(true);
    setError(null);
    try {
      await saveReview();
    } catch (err) {
      setError(getApiErrorMessage(err, 'Review could not be saved'));
    } finally {
      setBusy(false);
    }
  };

  const commit = async () => {
    setBusy(true);
    setError(null);
    try {
      const reviewed = await saveReview();
      if (!reviewed) return;
      setJob(await bulkImports.commit(reviewed.job_id, crypto.randomUUID()));
    } catch (err) {
      setError(getApiErrorMessage(err, 'Bulk creation failed'));
    } finally {
      setBusy(false);
    }
  };

  const stopImport = async () => {
    if (!job) return;
    const confirmed = window.confirm(
      'Stop this bulk upload? Records already created will remain, and you can resume the remaining work later.',
    );
    if (!confirmed) return;
    setStopping(true);
    setError(null);
    try {
      setJob(await bulkImports.cancel(job.job_id));
    } catch (err) {
      setError(getApiErrorMessage(err, 'Bulk upload could not be stopped'));
    } finally {
      setStopping(false);
    }
  };

  const resumeImport = async () => {
    if (!job) return;
    setBusy(true);
    setError(null);
    try {
      setJob(await bulkImports.resume(job.job_id));
    } catch (err) {
      setError(getApiErrorMessage(err, 'Bulk upload could not be resumed'));
    } finally {
      setBusy(false);
    }
  };

  const completed = job?.status === 'COMPLETED';
  const hasCommitErrors = job?.status === 'COMPLETED_WITH_ERRORS';
  const isActiveStatus = Boolean(job && BULK_IMPORT_ACTIVE_STATUSES.includes(job.status));
  const isFailedStatus = job?.status === 'FAILED';
  const isCancelledStatus = job?.status === 'CANCELLED';
  const selectedCount = job?.drafts.filter((draft) => draft.selected).length ?? 0;

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Button variant="ghost" onClick={() => navigate(-1)} icon={<ArrowLeft />}>
            Back
          </Button>
          <h1 className="mt-3 text-2xl font-semibold text-foreground">Bulk import</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Upload mixed sources. AI will propose entities and map their supporting files.
          </p>
        </div>
        {preselectedWorkflowName && (
          <span className="rounded-full bg-primary/10 px-3 py-1.5 text-xs font-medium text-primary">
            Enroll in {preselectedWorkflowName}
          </span>
        )}
      </div>

      {jobLoading && (
        <div className="flex items-center gap-2 rounded-xl border border-border bg-card p-4 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading your import…
        </div>
      )}

      {jobLoadError && !jobLoading && (
        <div className="rounded-lg bg-destructive/10 p-3 text-sm text-destructive">
          {jobLoadError}
        </div>
      )}

      {!job && !jobLoading && (
        <section className="rounded-2xl border border-border bg-card p-6">
          <div className="grid gap-5 md:grid-cols-2">
            <label className="space-y-2 text-sm font-medium text-foreground">
              Entity type
              <select
                value={entityTypeId}
                onChange={(event) => {
                  setEntityTypeId(event.target.value);
                  if (!preselectedWorkflowName) setSelectedWorkflowName('');
                }}
                disabled={typesLoading || Boolean(preselectedWorkflowName && requestedEntityType)}
                className="h-10 w-full rounded-lg border border-input bg-background px-3 text-sm"
              >
                <option value="">Select an entity type</option>
                {entityTypes
                  .filter((type) => type.is_active && can('create', type.name))
                  .map((type) => (
                    <option
                      key={type.entity_type_id || type.id}
                      value={type.entity_type_id || type.id}
                    >
                      {type.display_name || type.name}
                    </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="flex cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed border-border bg-muted/30 p-6 text-center transition-colors hover:border-primary/50 hover:bg-primary/5"
            >
              <UploadCloud className="mb-2 h-7 w-7 text-primary" />
              <span className="text-sm font-medium text-foreground">Upload all source documents</span>
              <span className="mt-1 text-xs text-muted-foreground">
                CSV, spreadsheets, catalogs, résumés, images, and supporting documents
              </span>
            </button>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept={ACCEPTED_FILES}
              className="sr-only"
              onChange={(event) => {
                addFiles(event.target.files);
                event.target.value = '';
              }}
            />
          </div>
          {bulkParentPickers.length > 0 && (
            <div className="mt-5 rounded-xl border border-border bg-muted/20 p-4">
              <div className="mb-3">
                <div className="text-sm font-medium text-foreground">Parent records</div>
                <p className="mt-1 text-xs text-muted-foreground">
                  Select one fixed parent for every imported record, or leave it blank and map a spreadsheet column after analysis.
                </p>
              </div>
              <div className="grid gap-x-5 md:grid-cols-2">
                <SourceLinkFields
                  pickers={bulkParentPickers}
                  selections={sourceLinks.selections}
                  onChange={sourceLinks.setSelection}
                  requireReference={hasDocumentSources}
                />
              </div>
              {missingRequiredDocumentParent && (
                <p className="mt-1 text-xs text-destructive">
                  Select a fixed {missingRequiredDocumentParent.providerName} because document sources cannot map a parent column.
                </p>
              )}
            </div>
          )}
          {files.length > 0 && (
            <div className="mt-4 flex flex-wrap gap-2">
              {files.map((file) => (
                <span
                  key={fileKey(file)}
                  className="inline-flex items-center gap-1.5 rounded-full bg-muted py-1 pl-3 pr-1.5 text-xs"
                >
                  <span>{file.name}</span>
                  <button
                    type="button"
                    onClick={() => removeFile(file)}
                    aria-label={`Remove ${file.name}`}
                    className="rounded-full p-0.5 text-muted-foreground hover:bg-background hover:text-foreground"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </span>
              ))}
            </div>
          )}
          <div className="mt-5 flex justify-end">
            <Button
              variant="ai"
              size="md"
              loading={busy}
              disabled={!entityTypeId || files.length === 0 || Boolean(missingRequiredDocumentParent)}
              onClick={uploadAndAnalyze}
              icon={<Sparkles />}
            >
              Upload and organize
            </Button>
          </div>
        </section>
      )}

      {job && isActiveStatus && (
        <AgentMissionControl job={job} stopping={stopping} onStop={stopImport} />
      )}

      {job && isFailedStatus && (
        <div className="flex flex-col gap-3 rounded-xl border border-destructive/30 bg-destructive/10 p-5">
          <div className="flex items-center gap-3">
            <AlertCircle className="h-6 w-6 text-destructive" />
            <div className="font-medium">This import failed</div>
          </div>
          {job.errors.length > 0 && (
            <ul className="list-disc space-y-1 pl-5 text-sm text-destructive">
              {job.errors.map((message) => (
                <li key={message}>{message}</li>
              ))}
            </ul>
          )}
          <div>
            <Button variant="outline" onClick={startNewImport}>
              Start another import
            </Button>
          </div>
        </div>
      )}

      {job && isCancelledStatus && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card p-5">
          <div>
            <div className="font-medium text-foreground">Bulk upload stopped</div>
            <p className="mt-1 text-xs text-muted-foreground">
              {job.commit_processed_count} of {job.commit_total_count} records were processed. Records already created were preserved.
            </p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={startNewImport}>Start another import</Button>
            <Button variant="primary" loading={busy} onClick={resumeImport}>Resume import</Button>
          </div>
        </div>
      )}

      {job && !isActiveStatus && !isFailedStatus && !isCancelledStatus && (
        <>
          {job.spreadsheet_sources.length > 0 && (
            <section className="rounded-xl border border-border bg-card p-4">
              <div className="flex items-start gap-3">
                <Table2 className="mt-0.5 h-5 w-5 text-primary" />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2 text-sm font-medium text-foreground">
                    Spreadsheet mapping
                    <span className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-primary">
                      <Sparkles className="h-3 w-3" />
                      AI mapped
                    </span>
                  </div>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    The bulk-import agent matched fields and file-reference columns using headers and sample values. Rows and managed attachments are then applied deterministically.
                  </p>
                  <div className="mt-3 space-y-2">
                    {job.spreadsheet_sources.map((source) => {
                      const sourceKey = `${source.file_id}:${source.sheet_name}`;
                      return (
                      <SpreadsheetMappingSourceCard
                        key={`${source.file_id}:${source.sheet_name}`}
                        source={source}
                        mappings={spreadsheetMappings[sourceKey] || {}}
                        fields={[
                          {
                            id: ATTACHMENT_MAPPING_TARGET,
                            label: 'Attachment (managed copy)',
                            type: 'url',
                            required: false,
                            system: true,
                          },
                          ...job.relation_definitions
                            .filter((relation) => !relation.fixed_source_entity_id)
                            .map((relation) => ({
                              id: `${RELATION_MAPPING_PREFIX}${relation.relation_def_id}`,
                              label: `Parent: ${relation.source_entity_type_name}`,
                              type: 'text',
                              required: relation.relation_type === 'REFERENCE',
                              system: true,
                            } as FormField)),
                          ...reviewSchemaFields,
                        ]}
                        disabled={busy}
                        onChange={(column, fieldIds) =>
                          updateSpreadsheetColumn(
                            source.file_id,
                            source.sheet_name,
                            column,
                            fieldIds,
                          )
                        }
                      />
                      );
                    })}
                  </div>
                  <div className="mt-3 flex justify-end">
                    <Button
                      variant="outline"
                      loading={busy}
                      disabled={!spreadsheetMappingsDirty}
                      onClick={applySpreadsheetMappings}
                    >
                      Apply column mappings
                    </Button>
                  </div>
                </div>
              </div>
            </section>
          )}

          <div className="grid gap-3 sm:grid-cols-3">
            <div className="rounded-xl border border-border bg-card p-4">
              <div className="text-xs text-muted-foreground">Proposed entities</div>
              <div className="mt-1 text-2xl font-semibold">{job.drafts.length}</div>
            </div>
            <div className="rounded-xl border border-border bg-card p-4">
              <div className="text-xs text-muted-foreground">Files mapped</div>
              <div className="mt-1 text-2xl font-semibold">{assignedFileIds.size}</div>
            </div>
            <div className="rounded-xl border border-border bg-card p-4">
              <div className="text-xs text-muted-foreground">Needs review</div>
              <div className="mt-1 text-2xl font-semibold">
                {exceptionCount + unmappedFileIds.length + job.failed_count}
              </div>
            </div>
          </div>

          <section className="overflow-hidden rounded-2xl border border-border bg-card">
            <div className="flex flex-wrap items-end justify-between gap-4 border-b border-border px-5 py-4">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="font-medium text-foreground">Exception review</h2>
                  <span className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-primary">
                    <ShieldCheck className="h-3 w-3" />
                    AI triaged
                  </span>
                </div>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  Focus on records that need a decision. AI-cleared records remain available under Ready.
                </p>
              </div>
              {!preselectedWorkflowName && (
                <label className="min-w-64 space-y-1 text-xs font-medium text-foreground">
                  Enroll created records in
                  <select
                    value={selectedWorkflowName}
                    onChange={(event) => setSelectedWorkflowName(event.target.value)}
                    disabled={workflowsLoading}
                    className="h-9 w-full rounded-lg border border-input bg-background px-3 text-sm font-normal"
                  >
                    <option value="">
                      {workflowsLoading ? 'Loading workflows…' : 'No workflow enrollment'}
                    </option>
                    {compatibleWorkflows.map((workflow) => (
                      <option key={workflow.id || workflow.machine_key} value={workflow.machine_name}>
                        {workflow.name}
                      </option>
                    ))}
                  </select>
                  {workflowsError && (
                    <span className="block font-normal text-destructive">{workflowsError}</span>
                  )}
                  {!workflowsLoading
                    && !workflowsError
                    && compatibleWorkflows.length === 0 && (
                      <span className="block font-normal text-muted-foreground">
                        No active workflows use this entity type.
                      </span>
                    )}
                </label>
              )}
            </div>
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border bg-muted/20 px-5 py-3">
              <div className="inline-flex rounded-lg border border-border bg-background p-1 shadow-sm">
                {([
                  ['exceptions', 'Needs review', exceptionCount],
                  ['ready', 'Ready', readyCount],
                  ['all', 'All records', reviewEntries.length],
                ] as const).map(([filter, label, count]) => (
                  <button
                    key={filter}
                    type="button"
                    onClick={() => setReviewFilter(filter)}
                    className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                      reviewFilter === filter
                        ? 'bg-primary text-primary-foreground shadow-sm'
                        : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                    }`}
                  >
                    {label}
                    <span className={`rounded-full px-1.5 py-0.5 text-[10px] ${
                      reviewFilter === filter ? 'bg-white/20' : 'bg-muted'
                    }`}>
                      {count}
                    </span>
                  </button>
                ))}
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                  AI cleared {readyCount} of {reviewEntries.length} records
                </div>
                <label className="flex items-center gap-2 text-xs text-muted-foreground">
                  Rows
                  <select
                    value={reviewPageSize}
                    onChange={(event) => setReviewPageSize(Number(event.target.value))}
                    className="h-7 rounded-md border border-input bg-background px-2 text-xs text-foreground"
                  >
                    {[10, 25, 50].map((size) => (
                      <option key={size} value={size}>{size}</option>
                    ))}
                  </select>
                </label>
              </div>
            </div>
            {selectedReviewIds.size > 0 && (
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-primary/15 bg-primary/[0.045] px-5 py-3">
                <div className="flex flex-wrap items-center gap-2 text-xs text-foreground">
                  <span className="font-medium tabular-nums">
                    {selectedReviewIds.size} record{selectedReviewIds.size === 1 ? '' : 's'} selected
                  </span>
                  {allPageSelected && !allVisibleSelected && (
                    <Button variant="link" size="sm" onClick={selectAllVisibleReviews}>
                      Select all {visibleReviewEntries.length} records in this view
                    </Button>
                  )}
                  {allVisibleSelected && (
                    <span className="text-muted-foreground">
                      All records in this view are selected, including other pages.
                    </span>
                  )}
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setSelectedReviewIds(new Set())}
                  >
                    Clear
                  </Button>
                  <Button
                    variant="outline-danger"
                    size="sm"
                    onClick={() => applyBulkDecision('rejected')}
                  >
                    Reject selected
                  </Button>
                  <Button
                    variant="primary"
                    size="sm"
                    icon={<CheckCircle2 />}
                    onClick={() => applyBulkDecision('accepted')}
                  >
                    Accept selected
                  </Button>
                </div>
              </div>
            )}
            <div>
              {visibleReviewEntries.length === 0 && (
                <div className="flex flex-col items-center px-5 py-12 text-center">
                  <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-emerald-500/10 text-emerald-600">
                    <ShieldCheck className="h-5 w-5" />
                  </div>
                  <h3 className="mt-3 text-sm font-medium text-foreground">
                    {reviewFilter === 'exceptions' ? 'No exceptions need review' : 'No records in this view'}
                  </h3>
                  <p className="mt-1 max-w-sm text-xs text-muted-foreground">
                    {reviewFilter === 'exceptions'
                      ? 'The agent found no low-confidence, incomplete, failed, or existing-record cases.'
                      : 'Choose another review filter to inspect the imported records.'}
                  </p>
                  {reviewFilter === 'exceptions' && readyCount > 0 && (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="mt-4"
                      onClick={() => setReviewFilter('ready')}
                      icon={<Eye />}
                    >
                      View ready records
                    </Button>
                  )}
                </div>
              )}
              {visibleReviewEntries.length > 0 && (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[900px] border-separate border-spacing-0 text-sm">
                    <thead>
                      <tr className="text-left">
                        <th className="h-10 w-12 border-b border-border bg-muted/30 px-4">
                          <Checkbox
                            aria-label="Select all records on this page"
                            checked={allPageSelected}
                            indeterminate={somePageSelected && !allPageSelected}
                            onCheckedChange={(checked) => togglePageSelection(checked === true)}
                          />
                        </th>
                        <th className="h-10 border-b border-border bg-muted/30 px-4 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Record</th>
                        <th className="h-10 border-b border-border bg-muted/30 px-4 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Key details</th>
                        <th className="h-10 border-b border-border bg-muted/30 px-4 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Source</th>
                        <th className="h-10 border-b border-border bg-muted/30 px-4 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Review signal</th>
                        <th className="sticky right-0 h-10 border-b border-l border-border bg-muted px-4 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Decision</th>
                      </tr>
                    </thead>
                    <tbody>
                      {pagedReviewEntries.map(({ draft, index, issues }) => {
                        const sourceFile = job.files.find((file) => draft.file_ids.includes(file.file_id));
                        const sourceLabel = draft.source_kind === 'spreadsheet' && draft.source_row_number
                          ? `${draft.source_sheet_name || 'Sheet'} · row ${draft.source_row_number}`
                          : sourceFile?.filename || 'No matched document';
                        const decision = draftDecisions[draft.draft_id]
                          || (!draft.selected ? 'rejected' : issues.length === 0 ? 'accepted' : null);
                        const rowPreviewFields = previewFields.length > 0
                          ? previewFields
                          : Object.keys(draft.data)
                            .filter((field) => field !== 'identifier')
                            .slice(0, 3)
                            .map((field) => ({ id: field, label: humanizeField(field) }));
                        return (
                          <tr
                            key={draft.draft_id}
                            tabIndex={0}
                            onClick={() => setActiveDraftId(draft.draft_id)}
                            onKeyDown={(event) => {
                              if (event.key === 'Enter') setActiveDraftId(draft.draft_id);
                            }}
                            className={`group cursor-pointer outline-none transition-colors hover:bg-primary/[0.035] focus-visible:bg-primary/[0.05] ${
                              selectedReviewIds.has(draft.draft_id) ? 'bg-primary/[0.055]' : ''
                            }`}
                          >
                            <td
                              className="w-12 border-b border-border/70 px-4 py-3 align-top"
                              onClick={(event) => event.stopPropagation()}
                              onKeyDown={(event) => event.stopPropagation()}
                            >
                              <Checkbox
                                aria-label={`Select ${String(draft.data.identifier || `record ${index + 1}`)}`}
                                checked={selectedReviewIds.has(draft.draft_id)}
                                onCheckedChange={(checked) =>
                                  toggleReviewSelection(draft.draft_id, checked === true)
                                }
                              />
                            </td>
                            <td className="border-b border-border/70 px-4 py-3 align-top">
                              <div className="max-w-52 truncate font-medium text-foreground">
                                {String(draft.data.identifier || `Proposed ${job.entity_type_name} ${index + 1}`)}
                              </div>
                              <div className="mt-1 flex items-center gap-1.5 text-[11px] text-muted-foreground">
                                {draft.existing_entity ? 'Existing match' : job.entity_type_name}
                                <span>·</span>
                                {Math.round(draft.confidence * 100)}%
                              </div>
                            </td>
                            <td className="border-b border-border/70 px-4 py-3 align-top">
                              <div className="grid max-w-xl gap-x-4 gap-y-1 sm:grid-cols-3">
                                {rowPreviewFields.map((field) => (
                                  <div key={field.id} className="min-w-0">
                                    <div className="truncate text-[10px] font-medium uppercase tracking-wide text-muted-foreground">{field.label}</div>
                                    <div className={`truncate text-xs ${isEmptyReviewValue(draft.data[field.id]) ? 'text-amber-700 dark:text-amber-400' : 'text-foreground'}`}>
                                      {compactReviewValue(draft.data[field.id])}
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </td>
                            <td className="max-w-48 border-b border-border/70 px-4 py-3 align-top">
                              <div className="flex items-start gap-1.5 text-xs text-foreground">
                                <Paperclip className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" />
                                <span className="line-clamp-2">{sourceLabel}</span>
                              </div>
                            </td>
                            <td className="border-b border-border/70 px-4 py-3 align-top">
                              {issues.length > 0 ? (
                                <div className="flex max-w-56 items-center gap-1.5">
                                  <span className="truncate rounded-full border border-amber-500/25 bg-amber-500/10 px-2 py-0.5 text-[11px] font-medium text-amber-700 dark:text-amber-400">
                                    {issues[0].label}
                                  </span>
                                  {issues.length > 1 && <span className="text-[11px] text-muted-foreground">+{issues.length - 1}</span>}
                                </div>
                              ) : (
                                <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[11px] font-medium text-emerald-700 dark:text-emerald-400">
                                  <CheckCircle2 className="h-3 w-3" /> Ready
                                </span>
                              )}
                            </td>
                            <td className="sticky right-0 border-b border-l border-border/70 bg-card px-4 py-3 group-hover:bg-[color-mix(in_srgb,var(--card)_96%,var(--primary))]">
                              <div className="flex items-center justify-between gap-2">
                                <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${
                                  decision === 'rejected'
                                    ? 'bg-destructive/10 text-destructive'
                                    : decision === 'modified'
                                      ? 'bg-blue-500/10 text-blue-700 dark:text-blue-400'
                                      : decision === 'accepted'
                                        ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-400'
                                        : 'bg-muted text-muted-foreground'
                                }`}>
                                  {decision === 'rejected' ? 'Rejected' : decision === 'modified' ? 'Modified' : decision === 'accepted' ? 'Accepted' : 'Review'}
                                </span>
                                <Eye className="h-4 w-4 text-muted-foreground transition-colors group-hover:text-primary" />
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
              <BulkImportPagination
                page={reviewPage}
                pageSize={reviewPageSize}
                total={visibleReviewEntries.length}
                noun="records"
                onPageChange={setReviewPage}
              />
            </div>
          </section>

          {unmappedFileIds.length > 0 && (
            <div className="flex gap-3 rounded-xl border border-amber-500/30 bg-amber-500/10 p-4">
              <AlertCircle className="mt-0.5 h-5 w-5 text-amber-600" />
              <div>
                <div className="text-sm font-medium">{unmappedFileIds.length} unassigned files</div>
                <p className="text-xs text-muted-foreground">
                  Assign them using the file selectors, or leave them out of this import.
                </p>
              </div>
            </div>
          )}

          {completed ? (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-5">
              <div className="flex items-center gap-3">
                <CheckCircle2 className="h-6 w-6 text-emerald-600" />
                <div>
                  <div className="font-medium">
                    {job.created_count} entities created
                    {job.existing_count > 0 && ` · ${job.existing_count} existing records updated`}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Files were attached and workflow enrollment was applied where requested.
                  </p>
                </div>
              </div>
              <Button variant="outline" onClick={startNewImport}>
                Start another import
              </Button>
            </div>
          ) : (
            <div className="flex flex-wrap justify-end gap-3">
              <Button variant="outline" loading={busy} onClick={saveReviewOnly}>
                Save review
              </Button>
              <Button
                variant="primary"
                size="md"
                loading={busy}
                disabled={selectedCount === 0 || unreviewedExceptionCount > 0}
                onClick={commit}
              >
                {unreviewedExceptionCount > 0
                  ? `Review ${unreviewedExceptionCount} exception${unreviewedExceptionCount === 1 ? '' : 's'}`
                  : hasCommitErrors
                    ? 'Retry failed items'
                    : `Create ${selectedCount} ${job.entity_type_name}`}
              </Button>
            </div>
          )}
        </>
      )}

      {job && activeReviewEntry && (
        <BulkImportReviewDrawer
          open={Boolean(activeDraftId)}
          draft={activeReviewEntry.draft}
          issues={activeReviewEntry.issues}
          fields={fieldsForDraft(activeReviewEntry.draft)}
          files={job.files}
          entityTypeName={job.entity_type_name}
          position={activeReviewIndex + 1}
          total={visibleReviewEntries.length}
          reviewedCount={reviewedVisibleCount}
          canGoPrevious={activeReviewIndex > 0}
          canGoNext={activeReviewIndex < visibleReviewEntries.length - 1}
          onClose={() => setActiveDraftId(null)}
          onPrevious={() => openReviewEntry(activeReviewIndex - 1)}
          onNext={() => openReviewEntry(activeReviewIndex + 1)}
          onAccept={(draftId) => decideDraft(draftId, 'accepted')}
          onReject={(draftId) => decideDraft(draftId, 'rejected')}
          onModify={(draftId, data) => decideDraft(draftId, 'modified', data)}
          onFilesChange={(draftId, fileIds) => updateDraft(draftId, { file_ids: fileIds })}
          onRemoteReferenceRemove={(draftId, sourceColumn, sourceValue) => {
            const draft = job.drafts.find((item) => item.draft_id === draftId);
            if (!draft) return;
            const removed = draft.remote_file_references?.find(
              (reference) => reference.source_column === sourceColumn
                && reference.source_value === sourceValue,
            );
            updateDraft(draftId, {
              remote_file_references: (draft.remote_file_references ?? []).filter(
                (reference) => reference.source_column !== sourceColumn
                  || reference.source_value !== sourceValue,
              ),
              file_ids: removed?.file_id
                ? draft.file_ids.filter((fileId) => fileId !== removed.file_id)
                : draft.file_ids,
            });
          }}
        />
      )}

      {busy && job && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <FileText className="h-4 w-4" />
          Processing the import…
        </div>
      )}
      {error && <div className="rounded-lg bg-destructive/10 p-3 text-sm text-destructive">{error}</div>}

      {!job && !jobLoading && (
        <RecentImportsList jobs={recentJobs} loading={recentJobsLoading} onSelect={openJob} />
      )}
    </div>
  );
}
