import type { BackgroundJob } from '../../types';
import { request, uploadFile } from './client';

type FileprocessorJobApiRecord = {
  job_id: string;
  filename?: string | null;
  mode: string;
  execution_mode?: string;
  agent_name?: string | null;
  agent_definition_id?: string | null;
  status: string;
  current_stage?: string | null;
  attempt_count: number;
  max_retries: number;
  error_message?: string | null;
  created_at: string;
  updated_at?: string;
  completed_at?: string | null;
};

type FileprocessorJobResultApiRecord = {
  job_id: string;
  file_id: string;
  success: boolean;
  execution_mode?: string;
  agent_name?: string | null;
  agent_definition_id?: string | null;
  detected_format: string;
  classification?: Record<string, unknown> | null;
  structured_output?: Record<string, unknown> | null;
  summary?: string | null;
  confidence_score?: number | null;
  warnings?: string[];
  errors?: string[];
  provider_trace?: Record<string, unknown>;
};

function mapFileprocessorStatusToJobStatus(rawStatus: string): BackgroundJob['status'] {
  switch (rawStatus) {
    case 'PENDING':
      return 'queued';
    case 'RUNNING':
      return 'processing';
    case 'COMPLETED':
      return 'completed';
    case 'FAILED':
    case 'RETRYABLE':
      return 'failed';
    default:
      return 'queued';
  }
}

function mapFileprocessorJob(record: FileprocessorJobApiRecord): BackgroundJob {
  const mappedStatus = mapFileprocessorStatusToJobStatus(record.status);
  return {
    id: String(record.job_id),
    job_type: `fileprocessor_${String(record.mode || 'full')}`,
    status: mappedStatus,
    execution_mode: record.execution_mode === 'agent' ? 'agent' : 'llm',
    agent_name: record.agent_name ?? null,
    agent_definition_id: record.agent_definition_id ?? null,
    filename: record.filename ?? null,
    progress: {
      total: 1,
      completed: mappedStatus === 'completed' ? 1 : 0,
      failed: mappedStatus === 'failed' ? 1 : 0,
    },
    error_message: record.error_message ?? undefined,
    created_at: String(record.created_at),
    updated_at: record.updated_at ?? undefined,
    completed_at: record.completed_at ?? undefined,
  };
}

export const jobs = {
  list: (params?: { status?: string; limit?: number; file_id?: string }) => {
    const searchParams = new URLSearchParams();
    if (params?.status) searchParams.set('status_filter', params.status);
    if (params?.file_id) searchParams.set('file_id', params.file_id);
    if (params?.limit) searchParams.set('limit', params.limit.toString());
    const query = searchParams.toString();
    return request<{ count: number; items: FileprocessorJobApiRecord[] }>(`/fileprocessor/jobs${query ? `?${query}` : ''}`).then((response) => {
      let items = response.items.map(mapFileprocessorJob);
      if (params?.limit && params.limit > 0) {
        items = items.slice(0, params.limit);
      }
      return { items, total: response.count };
    });
  },

  get: (jobId: string) =>
    request<FileprocessorJobApiRecord>(`/fileprocessor/jobs/${jobId}`).then(mapFileprocessorJob),

  getActive: async () => {
    const active = await jobs.list({ status: 'RUNNING', limit: 1 });
    if (active.items.length > 0) return active.items[0];
    const queued = await jobs.list({ status: 'PENDING', limit: 1 });
    return queued.items[0] ?? null;
  },

  retry: (jobId: string) =>
    request<FileprocessorJobApiRecord>(`/fileprocessor/jobs/${jobId}/retry`, { method: 'POST' }).then(mapFileprocessorJob),

  getResult: (jobId: string) =>
    request<FileprocessorJobResultApiRecord>(`/fileprocessor/jobs/${jobId}/result`),

  uploadAndProcess: async (typeId: string, file: File): Promise<{ file_id: string; job_id: string }> => {
    const uploaded = await uploadFile(typeId, file);

    const fileId = String(uploaded.file_id);

    if (!Boolean(uploaded.auto_dispatched)) {
      const dispatch = await request<{ accepted: boolean; job_id: string }>(
        `/filehandler/${fileId}/dispatch`,
        { method: 'POST', body: JSON.stringify({ mode: 'full' }) }
      );
      return { file_id: fileId, job_id: dispatch.job_id };
    }

    return { file_id: fileId, job_id: '' };
  },

  delete: async (_jobId: string) => ({ message: 'Delete is not supported for fileprocessor jobs' }),
};
