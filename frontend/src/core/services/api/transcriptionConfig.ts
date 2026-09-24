import type {
  TranscriptionConfig,
  TranscriptionConfigListResponse,
  TranscriptionConfigCreateRequest,
  TranscriptionConfigValidateRequest,
  TranscriptionConfigValidateResponse,
  TranscriptionProvidersListResponse,
  TranscriptionProvider,
  TranscriptionModelListRequest,
  TranscriptionModelListResponse,
} from '../../types';
import { request } from './client';
import { buildOrgQuery } from './internal';

export const transcriptionConfig = {
  listProviders: (orgId?: string) =>
    request<TranscriptionProvidersListResponse>(`/config/transcription/providers${buildOrgQuery(orgId)}`),

  list: (orgId?: string) =>
    request<TranscriptionConfigListResponse>(`/config/transcription${buildOrgQuery(orgId)}`),

  save: (data: TranscriptionConfigCreateRequest, orgId?: string) =>
    request<TranscriptionConfig>(`/config/transcription${buildOrgQuery(orgId)}`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  delete: (provider: TranscriptionProvider, orgId?: string) =>
    request<void>(`/config/transcription/${provider}${buildOrgQuery(orgId)}`, {
      method: 'DELETE',
    }),

  validate: (data: TranscriptionConfigValidateRequest) =>
    request<TranscriptionConfigValidateResponse>('/config/transcription/validate', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  listModels: (data: TranscriptionModelListRequest) =>
    request<TranscriptionModelListResponse>('/config/transcription/models', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
};
