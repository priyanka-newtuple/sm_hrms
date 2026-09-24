import { request } from './client';

export interface BulkImportDraft {
  draft_id: string;
  data: Record<string, unknown>;
  file_ids: string[];
  confidence: number;
  selected: boolean;
  review_decision?: 'accepted' | 'modified' | 'rejected' | null;
  entity_id?: string | null;
  existing_entity?: boolean;
  attached_file_ids?: string[];
  files_attached?: boolean;
  workflow_enrolled?: boolean;
  error?: string | null;
  source_kind?: 'document' | 'spreadsheet';
  source_sheet_name?: string | null;
  source_row_number?: number | null;
  remote_file_references?: Array<{
    source_column: string;
    source_value: string;
    source_url?: string | null;
    filename?: string | null;
    file_id?: string | null;
    status: 'pending' | 'referenced' | 'resolved' | 'staged' | 'stored' | 'missing' | 'failed';
    error?: string | null;
  }>;
  relation_bindings?: BulkImportRelationBinding[];
}

export interface BulkImportRelationDefinition {
  relation_def_id: string;
  source_entity_type_id: string;
  source_entity_type_name: string;
  relation_type: 'REFERENCE' | 'SNAPSHOT';
  fixed_source_entity_id?: string | null;
  fixed_source_entity_label?: string | null;
}

export interface BulkImportRelationBinding extends BulkImportRelationDefinition {
  mode: 'fixed' | 'column';
  source_entity_id?: string | null;
  source_entity_label?: string | null;
  source_column?: string | null;
  source_value?: string | null;
  status: 'resolved' | 'missing';
  error?: string | null;
}

export interface BulkImportSpreadsheetSource {
  file_id: string;
  filename: string;
  sheet_name: string;
  row_count: number;
  columns: string[];
  column_mapping: Record<string, string[]>;
  remote_file_columns: string[];
  relation_column_mapping: Record<string, string>;
  unmapped_columns: string[];
}

export interface BulkImportSpreadsheetMapping {
  file_id: string;
  sheet_name: string;
  column_mapping: Record<string, string[]>;
  remote_file_columns: string[];
  relation_column_mapping: Record<string, string>;
}

export interface BulkImportJob {
  job_id: string;
  status: string;
  operation?: 'analyze' | 'commit' | null;
  entity_type_id: string;
  entity_type_name: string;
  workflow_name?: string | null;
  files: Array<{
    file_id: string;
    filename: string;
    content_type: string;
    size_bytes: number;
    origin?: 'upload' | 'remote';
    metadata?: Record<string, unknown>;
  }>;
  drafts: BulkImportDraft[];
  unmapped_file_ids: string[];
  processed_count: number;
  failed_count: number;
  created_count: number;
  existing_count: number;
  commit_processed_count: number;
  commit_total_count: number;
  cancel_requested: boolean;
  errors: string[];
  spreadsheet_sources: BulkImportSpreadsheetSource[];
  relation_definitions: BulkImportRelationDefinition[];
}

/** Lightweight view of a job for the recent-imports list — no files/drafts/errors payload. */
export interface BulkImportJobSummary {
  job_id: string;
  status: string;
  entity_type_id: string;
  entity_type_name: string;
  file_count: number;
  draft_count: number;
  created_at?: string | null;
  updated_at?: string | null;
}

/** Job statuses where the worker is actively processing — not yet actionable by a reviewer. */
export const BULK_IMPORT_ACTIVE_STATUSES: string[] = [
  'QUEUED',
  'PROCESSING',
  'COMMITTING',
  'CANCELLING',
];

export const bulkImports = {
  create: (
    entityTypeId: string,
    files: File[],
    workflowName?: string | null,
    fixedRelationBindings: Array<{ relation_def_id: string; source_entity_id: string }> = [],
  ) => {
    const body = new FormData();
    body.append('entity_type_id', entityTypeId);
    if (workflowName) body.append('workflow_name', workflowName);
    body.append('fixed_relation_bindings', JSON.stringify(fixedRelationBindings));
    files.forEach((file) => body.append('files', file, file.name));
    return request<BulkImportJob>('/bulk-import/jobs', { method: 'POST', body });
  },
  list: () => request<{ items: BulkImportJobSummary[] }>('/bulk-import/jobs'),
  get: (jobId: string) =>
    request<BulkImportJob>(`/bulk-import/jobs/${encodeURIComponent(jobId)}`),
  analyze: (jobId: string) =>
    request<BulkImportJob>(`/bulk-import/jobs/${encodeURIComponent(jobId)}/analyze`, {
      method: 'POST',
    }),
  review: (
    jobId: string,
    drafts: BulkImportDraft[],
    unmappedFileIds: string[],
    workflowName?: string | null,
  ) =>
    request<BulkImportJob>(`/bulk-import/jobs/${encodeURIComponent(jobId)}/review`, {
      method: 'PUT',
      body: JSON.stringify({
        drafts,
        unmapped_file_ids: unmappedFileIds,
        workflow_name: workflowName || null,
      }),
    }),
  updateSpreadsheetMapping: (jobId: string, mappings: BulkImportSpreadsheetMapping[]) =>
    request<BulkImportJob>(`/bulk-import/jobs/${encodeURIComponent(jobId)}/spreadsheet-mapping`, {
      method: 'PUT',
      body: JSON.stringify({ mappings }),
    }),
  commit: (jobId: string, idempotencyKey: string) =>
    request<BulkImportJob>(`/bulk-import/jobs/${encodeURIComponent(jobId)}/commit`, {
      method: 'POST',
      headers: { 'Idempotency-Key': idempotencyKey },
    }),
  cancel: (jobId: string) =>
    request<BulkImportJob>(`/bulk-import/jobs/${encodeURIComponent(jobId)}/cancel`, {
      method: 'POST',
    }),
  resume: (jobId: string) =>
    request<BulkImportJob>(`/bulk-import/jobs/${encodeURIComponent(jobId)}/resume`, {
      method: 'POST',
    }),
};
