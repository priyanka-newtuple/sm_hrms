import type {
  ResumeUploadResponse,
  ResumeJobStatus,
  ResumeJobResults,
  BatchConfirmRequest,
  BatchConfirmResponse,
} from '../../../domains/ats/types/resumeUpload';
import type {
  PrepareUploadResponse,
  CompleteUploadRequest,
  CompleteUploadResponse,
} from '../../types';
import { getAccessToken } from '../../auth';
import { API_BASE, createApiError, request } from './client';

export const resumeUpload = {
  upload: async (files: File[]): Promise<ResumeUploadResponse> => {
    const formData = new FormData();
    files.forEach((file) => {
      formData.append('files', file);
    });

    const token = getAccessToken();
    const response = await fetch(`${API_BASE}/resumes/upload`, {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: formData,
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw createApiError({
        status: response.status,
        statusText: response.statusText,
        message: errorData.detail || response.statusText,
        detail: errorData,
      });
    }

    return response.json();
  },

  getJobStatus: (jobId: string) =>
    request<ResumeJobStatus>(`/resumes/jobs/${jobId}`),

  getJobResults: (jobId: string) =>
    request<ResumeJobResults>(`/resumes/jobs/${jobId}/results`),

  getPreviewUrl: (fileId: string) => {
    const token = getAccessToken();
    const url = `${API_BASE}/resumes/preview/${fileId}`;
    return token ? `${url}?token=${encodeURIComponent(token)}` : url;
  },

  confirm: (data: BatchConfirmRequest) =>
    request<BatchConfirmResponse>('/resumes/confirm', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  deleteJob: (jobId: string) =>
    request<{ message: string }>(`/resumes/jobs/${jobId}`, {
      method: 'DELETE',
    }),

  uploadCandidateResume: async (
    candidateId: string,
    file: File
  ): Promise<{ success: boolean; message: string; storage_key?: string }> => {
    const formData = new FormData();
    formData.append('file', file);

    const token = getAccessToken();
    const response = await fetch(`${API_BASE}/resumes/candidate/${candidateId}/resume`, {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: formData,
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw createApiError({
        status: response.status,
        statusText: response.statusText,
        message: errorData.detail || response.statusText,
        detail: errorData,
      });
    }

    return response.json();
  },

  prepareUpload: (files: Array<{ filename: string; size_bytes: number; content_type: string }>) =>
    request<PrepareUploadResponse>('/resumes/prepare-upload', {
      method: 'POST',
      body: JSON.stringify({ files }),
    }),

  uploadSingleFile: async (
    sessionId: string,
    fileId: string,
    file: File
  ): Promise<{ success: boolean; file_id: string; storage_key: string }> => {
    const formData = new FormData();
    formData.append('file', file);

    const token = getAccessToken();
    const response = await fetch(`${API_BASE}/resumes/upload-file/${sessionId}/${fileId}`, {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: formData,
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw createApiError({
        status: response.status,
        statusText: response.statusText,
        message: errorData.detail || response.statusText,
        detail: errorData,
      });
    }

    return response.json();
  },

  completeUpload: (data: CompleteUploadRequest) =>
    request<CompleteUploadResponse>('/resumes/complete-upload', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
};
