import type {
  Comment,
  CommentCreate,
  CommentUpdate,
  CommentReplyCreate,
  CommentListResponse,
  UserSearchResult,
} from '../../types';
import { request } from './client';

export const comments = {
  list: (
    entityId: string,
    params?: {
      state_name?: string;
      include_archived?: boolean;
    }
  ) => {
    const searchParams = new URLSearchParams();
    if (params?.state_name) searchParams.set('state_name', params.state_name);
    if (params?.include_archived) searchParams.set('include_archived', 'true');
    const query = searchParams.toString();
    return request<CommentListResponse>(
      `/entities/${entityId}/comments${query ? `?${query}` : ''}`
    );
  },

  create: (entityId: string, data: CommentCreate) =>
    request<Comment>(`/entities/${entityId}/comments`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  update: (commentId: string, data: CommentUpdate) =>
    request<Comment>(`/comments/${commentId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  archive: (commentId: string) =>
    request<{ message: string }>(`/comments/${commentId}`, {
      method: 'DELETE',
    }),

  reply: (commentId: string, data: CommentReplyCreate) =>
    request<Comment>(`/comments/${commentId}/replies`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // Fetched on demand (e.g. "View N replies" click) — not returned eagerly
  // with the main list, so a thread's initial payload stays light regardless
  // of how many replies it has.
  listReplies: (commentId: string) =>
    request<CommentListResponse>(`/comments/${commentId}/replies`),

  toggleLike: (commentId: string) =>
    request<Comment>(`/comments/${commentId}/like`, {
      method: 'POST',
    }),

  searchUsers: (query: string, limit = 10) => {
    const searchParams = new URLSearchParams({
      q: query,
      limit: limit.toString(),
    });
    return request<UserSearchResult[]>(`/users/search?${searchParams.toString()}`);
  },
};
