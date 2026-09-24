import type {
  TranscriptionSession,
  TranscriptionSessionCreateRequest,
  TranscriptionSessionCreateResponse,
  TranscriptionSessionListResponse,
  TranscriptionFinalizeResponse,
} from '../../types';
import { API_BASE, request } from './client';

export const transcription = {
  createSession: (data: TranscriptionSessionCreateRequest) =>
    request<TranscriptionSessionCreateResponse>('/transcription/sessions', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  listSessions: (entityType: string, entityId: string) => {
    const query = new URLSearchParams({
      entity_type: entityType,
      entity_id: entityId,
    }).toString();
    return request<TranscriptionSessionListResponse>(`/transcription/sessions?${query}`);
  },

  getSession: (sessionId: string) =>
    request<TranscriptionSession>(`/transcription/sessions/${sessionId}`),

  finalizeSession: (sessionId: string) =>
    request<TranscriptionFinalizeResponse>(`/transcription/sessions/${sessionId}/finalize`, {
      method: 'POST',
    }),

  getStreamUrl: (sessionId: string, token?: string) => {
    const url = `${API_BASE}/transcription/sessions/${sessionId}/stream`;
    return token ? `${url}?token=${encodeURIComponent(token)}` : url;
  },
};
