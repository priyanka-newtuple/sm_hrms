import type {
  Comment,
  CommentCreate,
  CommentUpdate,
  CommentReplyCreate,
  CommentListResponse,
  UserSearchResult,
} from '@/core/types';
import { request } from '@/core/services/api/client';

export const recordComments = (recordId: string, scope: string) => {
 const base = `/hrms/records/${recordId}/${scope}`;
 return {
  list: (
    _entityId: string,
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
      `${base}/comments${query ? `?${query}` : ''}`
    );
  },

  create: (_entityId: string, data: CommentCreate) =>
    request<Comment>(`${base}/comments`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  update: (commentId: string, data: CommentUpdate) =>
    request<Comment>(`${base}/comments/${commentId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  archive: (commentId: string) =>
    request<{ message: string }>(`${base}/comments/${commentId}`, {
      method: 'DELETE',
    }),

  reply: (commentId: string, data: CommentReplyCreate) =>
    request<Comment>(`${base}/comments/${commentId}/replies`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // Fetched on demand (e.g. "View N replies" click) — not returned eagerly
  // with the main list, so a thread's initial payload stays light regardless
  // of how many replies it has.
  listReplies: (commentId: string) =>
    request<CommentListResponse>(`${base}/comments/${commentId}/replies`),

  toggleLike: (commentId: string) =>
    request<Comment>(`${base}/comments/${commentId}/like`, {
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
};
