import type {
  StageComment,
  StageCommentCreate,
  StageCommentUpdate,
  StageCommentListResponse,
  TransitionCommentRequirements,
  CommentRequirementCheck,
} from '../../types';
import { request } from './client';

export const stageComments = {
  list: (entityId: string, params?: { stage?: string; include_archived?: boolean }) => {
    const searchParams = new URLSearchParams();
    if (params?.stage) searchParams.set('stage', params.stage);
    if (params?.include_archived) searchParams.set('include_archived', 'true');
    const query = searchParams.toString();
    return request<StageCommentListResponse>(
      `/entities/${entityId}/comments${query ? `?${query}` : ''}`
    );
  },

  create: (entityId: string, data: StageCommentCreate) =>
    request<StageComment>(`/entities/${entityId}/comments`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  update: (commentId: string, data: StageCommentUpdate) =>
    request<StageComment>(`/comments/${commentId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  archive: (commentId: string) =>
    request<StageComment>(`/comments/${commentId}`, {
      method: 'DELETE',
    }),

  getRequirements: (entityId: string) =>
    request<TransitionCommentRequirements>(`/entities/${entityId}/comment-requirements`),

  checkRequirement: (entityId: string, trigger: string) =>
    request<CommentRequirementCheck>(`/entities/${entityId}/comment-requirements/${trigger}`),
};
