import type {
  CandidateLike,
  CandidateLikeListResponse,
  BulkLikesSummaryResponse,
} from '../../types';
import { request } from './client';

export const candidateLikes = {
  list: (candidateId: string) =>
    request<CandidateLikeListResponse>(`/candidates/${candidateId}/likes`),

  like: (candidateId: string) =>
    request<CandidateLike>(`/candidates/${candidateId}/likes`, {
      method: 'POST',
    }),

  unlike: (candidateId: string) =>
    request<void>(`/candidates/${candidateId}/likes`, {
      method: 'DELETE',
    }),

  getBulkSummaries: (candidateIds: string[]) =>
    request<BulkLikesSummaryResponse>('/candidates/likes/bulk', {
      method: 'POST',
      body: JSON.stringify({ candidate_ids: candidateIds }),
    }),
};
