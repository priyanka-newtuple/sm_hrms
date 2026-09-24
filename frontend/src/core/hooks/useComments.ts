import { useState, useEffect, useCallback } from 'react';
import { comments as commentsApi } from '@/core/services/api';
import { getApiErrorMessage } from '@/core/services/api/client';
import type { Comment } from '@/core/types';

export interface CommentEditState {
  id: string;
  text: string;
}

export interface UseCommentsParams {
  entityId: string;
  workflowId?: string;
}

export interface UseCommentsReturn {
  /** Top-level comments only — replies are fetched on demand, see below. */
  comments: Comment[];
  submitting: boolean;
  editState: CommentEditState | null;
  setEditState: (state: CommentEditState | null) => void;
  submit: (text: string) => Promise<void>;
  saveEdit: (commentId: string, text: string) => Promise<void>;
  archive: (commentId: string) => Promise<void>;
  /** Which top-level comment currently has its reply composer open, or null. */
  replyingToId: string | null;
  setReplyingToId: (id: string | null) => void;
  submitReply: (parentId: string, text: string) => Promise<void>;
  toggleLike: (commentId: string) => Promise<void>;
  /** Replies fetched so far, keyed by parent comment id. Empty until a
   *  parent's replies are expanded (or a reply is posted under it). */
  repliesByParentId: Record<string, Comment[]>;
  /** Parents whose repliesByParentId entry is known to NOT be the full
   *  list e.g. a reply posted while uncached, where the follow-up fetch
   *  of the authoritative full list failed. The partial entry still gets
   *  shown (so the user sees their own reply immediately), but toggleReplies
   *  treats these as unfetched and retries on the next expand instead of
   *  trusting it. */
  incompleteReplyParentIds: Set<string>;
  /** Which parents currently have their replies expanded/visible. */
  expandedParentIds: Set<string>;
  /** Parent id currently fetching its replies, or null. */
  loadingReplyParentId: string | null;
  /** Expand (fetching on first expand only) or collapse a comment's replies. */
  toggleReplies: (parentId: string) => Promise<void>;
  /** Unconditionally re-fetch a parent's replies, bypassing the cache — for
   *  a deep link to a reply posted after the thread was already cached. */
  refreshReplies: (parentId: string) => Promise<void>;
  lastError: string | null;
  clearError: () => void;
}

export function useComments({ entityId, workflowId }: UseCommentsParams): UseCommentsReturn {
  const [comments, setComments] = useState<Comment[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [editState, setEditState] = useState<CommentEditState | null>(null);
  const [replyingToId, setReplyingToId] = useState<string | null>(null);
  const [repliesByParentId, setRepliesByParentId] = useState<Record<string, Comment[]>>({});
  const [incompleteReplyParentIds, setIncompleteReplyParentIds] = useState<Set<string>>(new Set());
  const [expandedParentIds, setExpandedParentIds] = useState<Set<string>>(new Set());
  const [loadingReplyParentId, setLoadingReplyParentId] = useState<string | null>(null);
  const [lastError, setLastError] = useState<string | null>(null);

  const clearError = useCallback(() => setLastError(null), []);

  useEffect(() => {
    setComments([]);
    setEditState(null);
    setRepliesByParentId({});
    setIncompleteReplyParentIds(new Set());
    setExpandedParentIds(new Set());
    setLastError(null);
    if (!entityId) return;
    let cancelled = false;
    commentsApi
      .list(entityId)
      .then((res) => {
        if (!cancelled) setComments(res.comments);
      })
      .catch((e) => {
        if (!cancelled) {
          console.error('[useComments] load failed:', e);
          setLastError(getApiErrorMessage(e, 'Could not load comments'));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [entityId]);

  const submit = useCallback(
    async (text: string) => {
      if (!text.trim() || submitting) return;
      setSubmitting(true);
      try {
        const created = await commentsApi.create(entityId, {
          text,
          workflow_id: workflowId,
        });
        setComments((prev) => [...prev, created]);
        setLastError(null);
      } catch (e) {
        const message = getApiErrorMessage(e, 'Could not post comment');
        console.error('[useComments] submit failed:', e);
        setLastError(message);
      } finally {
        setSubmitting(false);
      }
    },
    [entityId, workflowId, submitting],
  );

  // A comment's own `parent_id` tells us definitively where it lives —
  // top-level array or a specific reply bucket — so edits/likes route there
  // without needing to search both.
  const applyUpdatedComment = useCallback((updated: Comment) => {
    if (!updated.parent_id) {
      setComments((prev) => prev.map((c) => (c.id === updated.id ? updated : c)));
      return;
    }
    setRepliesByParentId((prev) => {
      const bucket = prev[updated.parent_id!];
      if (!bucket) return prev;
      return {
        ...prev,
        [updated.parent_id!]: bucket.map((r) => (r.id === updated.id ? updated : r)),
      };
    });
  }, []);

  const saveEdit = useCallback(
    async (commentId: string, text: string) => {
      if (!text.trim()) return;
      try {
        const updated = await commentsApi.update(commentId, { text });
        applyUpdatedComment(updated);
        setEditState(null);
        setLastError(null);
      } catch (e) {
        const message = getApiErrorMessage(e, 'Could not save comment');
        console.error('[useComments] saveEdit failed:', e);
        setLastError(message);
      }
    },
    [applyUpdatedComment],
  );

  const archive = useCallback(
    async (commentId: string) => {
      try {
        await commentsApi.archive(commentId);
        // Find which reply bucket (if any) currently holds this comment, so
        // its parent's reply_count can be decremented too — the archive
        // response is just {message}, it doesn't tell us. Computed up front
        // from the current state (not inside a setState updater) since
        // updater-function execution order isn't guaranteed across
        // different useState hooks — mutating an outer variable from one
        // updater and reading it in another silently read a stale value.
        const parentIdOfDeletedReply =
          Object.keys(repliesByParentId).find((parentId) =>
            repliesByParentId[parentId].some((r) => r.id === commentId),
          ) ?? null;

        setRepliesByParentId((prev) => {
          const next: Record<string, Comment[]> = {};
          for (const [parentId, replies] of Object.entries(prev)) {
            next[parentId] = replies.filter((r) => r.id !== commentId);
          }
          return next;
        });
        setComments((prev) =>
          prev
            .filter((c) => c.id !== commentId)
            .map((c) =>
              c.id === parentIdOfDeletedReply
                ? { ...c, reply_count: Math.max(0, c.reply_count - 1) }
                : c,
            ),
        );
        setLastError(null);
      } catch (e) {
        const message = getApiErrorMessage(e, 'Could not delete comment');
        console.error('[useComments] archive failed:', e);
        setLastError(message);
      }
    },
    [repliesByParentId],
  );

  const submitReply = useCallback(
    async (parentId: string, text: string) => {
      if (!text.trim() || submitting) return;
      setSubmitting(true);
      try {
        const created = await commentsApi.reply(parentId, { text });
        setComments((prev) =>
          prev.map((c) => (c.id === parentId ? { ...c, reply_count: c.reply_count + 1 } : c)),
        );
        if (repliesByParentId[parentId]) {
          // Already have the full list cached (thread was expanded before) —
          // just append the new one.
          setRepliesByParentId((prev) => ({
            ...prev,
            [parentId]: [...prev[parentId], created],
          }));
        } else {
          // No cache yet, meaning any pre-existing replies were never
          // fetched — assuming an empty base here would silently hide them
          // behind a "complete" bucket containing only the new reply, since
          // toggleReplies treats any existing key as fully fetched. Fetch
          // the authoritative list instead (it already includes the reply
          // we just posted).
          try {
            const res = await commentsApi.listReplies(parentId);
            setRepliesByParentId((prev) => ({ ...prev, [parentId]: res.comments }));
            setIncompleteReplyParentIds((prev) => {
              if (!prev.has(parentId)) return prev;
              const next = new Set(prev);
              next.delete(parentId);
              return next;
            });
          } catch (fetchErr) {
            // The authoritative list failed to load, but the reply itself
            // posted fine show it anyway (same "see it land immediately"
            // promise as the cached-list branch above) rather than leaving
            // the thread looking like nothing happened. Marking this parent
            // incomplete is what keeps the earlier bug from coming back:
            // toggleReplies checks this set too, so a later collapse/expand
            // still does a real refetch instead of trusting this 1 item
            // list as the full truth.
            console.error('[useComments] submitReply: refresh after post failed:', fetchErr);
            setRepliesByParentId((prev) => ({ ...prev, [parentId]: [created] }));
            setIncompleteReplyParentIds((prev) => new Set(prev).add(parentId));
          }
        }
        // Show the just-posted reply immediately, same as Instagram — don't
        // make the author expand their own reply to see it landed.
        setExpandedParentIds((prev) => new Set(prev).add(parentId));
        setReplyingToId(null);
        setLastError(null);
      } catch (e) {
        const message = getApiErrorMessage(e, 'Could not post reply');
        console.error('[useComments] submitReply failed:', e);
        setLastError(message);
      } finally {
        setSubmitting(false);
      }
    },
    [submitting, repliesByParentId],
  );

  const toggleLike = useCallback(
    async (commentId: string) => {
      try {
        const updated = await commentsApi.toggleLike(commentId);
        applyUpdatedComment(updated);
        setLastError(null);
      } catch (e) {
        const message = getApiErrorMessage(e, 'Could not update like');
        console.error('[useComments] toggleLike failed:', e);
        setLastError(message);
      }
    },
    [applyUpdatedComment],
  );

  const toggleReplies = useCallback(
    async (parentId: string) => {
      if (expandedParentIds.has(parentId)) {
        setExpandedParentIds((prev) => {
          const next = new Set(prev);
          next.delete(parentId);
          return next;
        });
        return;
      }
      setExpandedParentIds((prev) => new Set(prev).add(parentId));
      // Skip the fetch only when the cache is both present AND not flagged
      // incomplete — a parent left over from submitReply's fallback (its
      // refetch failed, so only the just-posted reply is cached) must still
      // trigger a real fetch here rather than being trusted as done.
      if (repliesByParentId[parentId] && !incompleteReplyParentIds.has(parentId)) return;
      setLoadingReplyParentId(parentId);
      try {
        const res = await commentsApi.listReplies(parentId);
        setRepliesByParentId((prev) => ({ ...prev, [parentId]: res.comments }));
        setIncompleteReplyParentIds((prev) => {
          if (!prev.has(parentId)) return prev;
          const next = new Set(prev);
          next.delete(parentId);
          return next;
        });
        setLastError(null);
      } catch (e) {
        const message = getApiErrorMessage(e, 'Could not load replies');
        console.error('[useComments] toggleReplies failed:', e);
        setLastError(message);
        // Roll back the expand so the user can retry the click — but only
        // when there was nothing to fall back on. A parent that already has
        // an (incomplete) cached list stays expanded and keeps showing what
        // it has, same as before this retry attempt, instead of hiding it.
        if (!repliesByParentId[parentId]) {
          setExpandedParentIds((prev) => {
            const next = new Set(prev);
            next.delete(parentId);
            return next;
          });
        }
      } finally {
        setLoadingReplyParentId(null);
      }
    },
    [expandedParentIds, repliesByParentId, incompleteReplyParentIds],
  );

  const refreshReplies = useCallback(async (parentId: string) => {
    try {
      const res = await commentsApi.listReplies(parentId);
      setRepliesByParentId((prev) => ({ ...prev, [parentId]: res.comments }));
      setIncompleteReplyParentIds((prev) => {
        if (!prev.has(parentId)) return prev;
        const next = new Set(prev);
        next.delete(parentId);
        return next;
      });
      setLastError(null);
    } catch (e) {
      const message = getApiErrorMessage(e, 'Could not load replies');
      console.error('[useComments] refreshReplies failed:', e);
      setLastError(message);
    }
  }, []);

  return {
    comments,
    submitting,
    editState,
    setEditState,
    submit,
    saveEdit,
    archive,
    replyingToId,
    setReplyingToId,
    submitReply,
    toggleLike,
    repliesByParentId,
    incompleteReplyParentIds,
    expandedParentIds,
    loadingReplyParentId,
    toggleReplies,
    refreshReplies,
    lastError,
    clearError,
  };
}
