import { useRef, useState } from 'react';
import { ChevronDown, ChevronUp, Trash2, ThumbsUp, Bold, Slash, AtSign, Smile, X } from 'lucide-react';
import MentionAutocomplete from './MentionAutocomplete';
import Tooltip from './Tooltip';
import { useAuth } from '@/core/auth';
import type { Comment } from '@/core/types';
import { useComments, type CommentEditState } from '@/core/hooks/useComments';
import {
  insertMention,
  parseMentionText,
  reconcileMentions,
  serializeMentionText,
} from '@/core/utils/mentions';
import { linkify } from '@/shared/utils/linkify';

// ── Helpers ───────────────────────────────────────────────────────────────────

const MENTION_RE = /@\[([^\]]+)\]\(([^)]+)\)/g;

function renderMentions(text: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  let last = 0;
  let match: RegExpExecArray | null;
  MENTION_RE.lastIndex = 0;
  while ((match = MENTION_RE.exec(text)) !== null) {
    if (match.index > last) parts.push(...linkify(text.slice(last, match.index), `c${match.index}`));
    parts.push(
      <span
        key={match.index}
        className="inline-flex items-center rounded-full bg-cobalt/10 px-2 py-0.5 text-xs font-semibold text-cobalt"
      >
        @{match[1]}
      </span>,
    );
    last = match.index + match[0].length;
  }
  if (last < text.length) parts.push(...linkify(text.slice(last), `c${last}`));
  return parts;
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

const AVATAR_PALETTE = [
  'bg-emerald-500',
  'bg-teal-500',
  'bg-violet-500',
  'bg-orange-400',
  'bg-rose-500',
  'bg-sky-500',
  'bg-amber-500',
  'bg-indigo-500',
];

function pickAvatarColor(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = (hash * 31 + name.charCodeAt(i)) | 0;
  return AVATAR_PALETTE[Math.abs(hash) % AVATAR_PALETTE.length];
}

function getInitials(name: string): string {
  return name
    .split(' ')
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? '')
    .join('');
}

// ── Avatar ────────────────────────────────────────────────────────────────────

interface AvatarProps {
  name: string;
  url?: string | null;
  size?: 'sm' | 'md';
}

function Avatar({ name, url, size = 'md' }: AvatarProps) {
  const [imgError, setImgError] = useState(false);
  const dim = size === 'sm' ? 'w-8 h-8 text-xs' : 'w-9 h-9 text-sm';
  if (url && !imgError) {
    return (
      <img
        src={url}
        alt={name}
        className={`${dim} rounded-full object-cover flex-shrink-0`}
        onError={() => setImgError(true)}
      />
    );
  }
  return (
    <div
      className={`${dim} ${pickAvatarColor(name)} rounded-full flex items-center justify-center flex-shrink-0`}
    >
      <span className="font-bold text-white leading-none">{getInitials(name)}</span>
    </div>
  );
}

const MAX_COMMENT_LENGTH = 1000;
/** Avatars shown in the like-tooltip stack before collapsing into a "+N" remainder. */
const MAX_LIKES_SHOWN = 8;

interface CommentInputBoxProps {
  initialValue?: string;
  onSubmit: (text: string) => Promise<void> | void;
  onCancel?: () => void;
  submitting?: boolean;
  placeholder?: string;
  submitLabel: string;
  anchorAutocompleteBottom?: boolean;
  autoFocus?: boolean;
}

function CommentInputBox({
  initialValue = '',
  onSubmit,
  onCancel,
  submitting = false,
  placeholder = 'Write a comment…',
  submitLabel,
  anchorAutocompleteBottom = false,
  autoFocus = false,
}: CommentInputBoxProps) {
  const initialDraft = parseMentionText(initialValue);
  const [text, setText] = useState(initialDraft.text);
  const [mentions, setMentions] = useState(initialDraft.mentions);
  const [mentionQuery, setMentionQuery] = useState('');
  const [mentionPos, setMentionPos] = useState<{ top: number; left: number } | null>(null);
  const [mentionStart, setMentionStart] = useState(-1);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const isMac = typeof navigator !== 'undefined' && /mac/i.test(navigator.platform);

  function autoGrow(el: HTMLTextAreaElement) {
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }

  function closeMention() {
    setMentionQuery('');
    setMentionPos(null);
    setMentionStart(-1);
  }

  function updateMentionState(
    value: string,
    cursor: number,
    target: HTMLTextAreaElement,
  ) {
    const atMatch = value.slice(0, cursor).match(/@([^\s@]*)$/);
    if (!atMatch) {
      closeMention();
      return;
    }

    const rect = target.getBoundingClientRect();
    setMentionQuery(atMatch[1]);
    setMentionStart(cursor - atMatch[0].length);
    setMentionPos(
      anchorAutocompleteBottom
        ? { top: rect.top, left: rect.left }
        : { top: rect.bottom, left: rect.left },
    );
  }

  function updateDraft(nextText: string, target: HTMLTextAreaElement) {
    setMentions((prev) => reconcileMentions(text, nextText, prev));
    setText(nextText);
    autoGrow(target);
    const cursor = target.selectionStart ?? nextText.length;
    updateMentionState(nextText, cursor, target);
  }

  async function handleSubmit() {
    const trimmedVisibleText = text.trim();
    if (!trimmedVisibleText || submitting) return;

    const rawText = serializeMentionText(text, mentions).trim();
    if (!rawText) return;

    await onSubmit(rawText);

    if (!onCancel) {
      setText('');
      setMentions([]);
      closeMention();
      if (textareaRef.current) textareaRef.current.style.height = 'auto';
    }
  }

  const charCount = text.length;

  return (
    <>
      <div className="rounded-xl border border-border bg-card focus-within:border-cobalt/40 focus-within:ring-2 focus-within:ring-cobalt/10 transition-all overflow-hidden">
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => updateDraft(e.target.value, e.target)}
          onKeyDown={(e) => {
            const isSubmit = isMac ? e.metaKey && e.key === 'Enter' : e.ctrlKey && e.key === 'Enter';
            if (isSubmit && !mentionPos) {
              e.preventDefault();
              void handleSubmit();
            }
            if (e.key === 'Escape') {
              e.preventDefault();
              if (mentionPos) {
                closeMention();
              } else {
                onCancel?.();
              }
            }
          }}
          placeholder={placeholder}
          className="w-full px-3.5 pt-3 pb-2 text-sm resize-none bg-transparent outline-none placeholder:text-muted-foreground leading-relaxed min-h-[72px]"
          rows={2}
          disabled={submitting}
          maxLength={MAX_COMMENT_LENGTH}
          autoFocus={autoFocus}
        />

        <div className="flex items-center justify-between px-2.5 pb-2.5 pt-1 border-t border-border">
          <div className="flex items-center gap-0.5">
            <button
              type="button"
              tabIndex={-1}
              className="rounded p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
              title="Bold"
            >
              <Bold className="w-3.5 h-3.5" />
            </button>
            <button
              type="button"
              tabIndex={-1}
              className="rounded p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
              title="Slash commands"
            >
              <Slash className="w-3.5 h-3.5" />
            </button>
            <button
              type="button"
              tabIndex={-1}
              onClick={() => {
                const el = textareaRef.current;
                if (!el) return;

                const pos = el.selectionStart ?? text.length;
                const nextText = text.slice(0, pos) + '@' + text.slice(pos);
                setMentions((prev) => reconcileMentions(text, nextText, prev));
                setText(nextText);

                const rect = el.getBoundingClientRect();
                setMentionQuery('');
                setMentionStart(pos);
                setMentionPos(
                  anchorAutocompleteBottom
                    ? { top: rect.top, left: rect.left }
                    : { top: rect.bottom, left: rect.left },
                );

                setTimeout(() => {
                  el.focus();
                  el.setSelectionRange(pos + 1, pos + 1);
                  autoGrow(el);
                }, 0);
              }}
              className="rounded p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
              title="Mention"
            >
              <AtSign className="w-3.5 h-3.5" />
            </button>
            <button
              type="button"
              tabIndex={-1}
              className="rounded p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
              title="Emoji"
            >
              <Smile className="w-3.5 h-3.5" />
            </button>
          </div>

          <div className="flex items-center gap-2">
            <span
              className={`text-[11px] tabular-nums ${charCount > MAX_COMMENT_LENGTH * 0.9 ? 'text-amber-500' : 'text-muted-foreground'}`}
            >
              {charCount}/{MAX_COMMENT_LENGTH}
            </span>
            {text.trim() && (
              <button
                type="button"
                onClick={() => {
                  if (onCancel) {
                    onCancel();
                    return;
                  }
                  setText('');
                  setMentions([]);
                  closeMention();
                  if (textareaRef.current) textareaRef.current.style.height = 'auto';
                }}
                className="text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
              >
                Cancel
              </button>
            )}
            <button
              type="button"
              onClick={() => void handleSubmit()}
              disabled={!text.trim() || submitting}
              className="rounded-lg bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-40 transition-colors"
            >
              {submitting ? '…' : submitLabel}
            </button>
          </div>
        </div>
      </div>

      {mentionPos && (
        <MentionAutocomplete
          query={mentionQuery}
          position={mentionPos}
          onSelect={(user) => {
            const next = insertMention(
              text,
              mentions,
              user,
              mentionStart,
              mentionStart + 1 + mentionQuery.length,
            );
            setText(next.text);
            setMentions(next.mentions);
            closeMention();

            setTimeout(() => {
              if (textareaRef.current) {
                textareaRef.current.focus();
                textareaRef.current.setSelectionRange(next.cursor, next.cursor);
                autoGrow(textareaRef.current);
              }
            }, 0);
          }}
          onClose={closeMention}
          anchorBottom={anchorAutocompleteBottom}
        />
      )}

      <p className="mt-1.5 text-[11px] text-muted-foreground">
        <kbd className="font-mono">{isMac ? '⌘↵' : 'Ctrl+↵'}</kbd> to submit ·{' '}
        <kbd className="font-mono bg-muted px-0.5 rounded">@</kbd> to mention
      </p>
    </>
  );
}

// ── CommentCard ───────────────────────────────────────────────────────────────

interface CommentCardProps {
  comment: Comment;
  editState: CommentEditState | null;
  currentUserId: string | null;
  isAdmin: boolean;
  /** Replies can't themselves be replied to — single-level threading only,
   *  matching the backend's rejection of reply-to-a-reply. */
  isReply?: boolean;
  replyingToId: string | null;
  submitting: boolean;
  /** Whether this comment's replies are currently expanded (top-level only). */
  repliesExpanded?: boolean;
  /** Whether this comment's replies are currently being fetched. */
  loadingReplies?: boolean;
  onEditStart: (id: string, text: string) => void;
  onEditSave: (id: string, text: string) => void;
  onEditCancel: () => void;
  onArchive: (id: string) => void;
  onReplyToggle: (id: string) => void;
  onReplySubmit: (parentId: string, text: string) => Promise<void>;
  onReplyCancel: () => void;
  onToggleLike: (id: string) => void;
  onToggleReplies: (parentId: string) => void;
}

function CommentCard({
  comment,
  editState,
  currentUserId,
  isAdmin,
  isReply = false,
  replyingToId,
  submitting,
  repliesExpanded = false,
  loadingReplies = false,
  onEditStart,
  onEditSave,
  onEditCancel,
  onArchive,
  onReplyToggle,
  onReplySubmit,
  onReplyCancel,
  onToggleLike,
  onToggleReplies,
}: CommentCardProps) {
  const isEditing = editState?.id === comment.id;
  const isAuthor = currentUserId !== null && comment.author_id === currentUserId;
  const canEdit = isAuthor || isAdmin;
  const isReplying = !isReply && replyingToId === comment.id;

  return (
    <div id={`comment-${comment.id}`} className="flex gap-3 group p-1 -m-1 rounded-lg">
      <Avatar name={comment.author_name} url={comment.author_avatar_url} size="sm" />
      <div className="flex-1 min-w-0">
        {/* Name + timestamp */}
        <div className="flex items-center gap-2 mb-1">
          <span className="text-sm font-semibold text-foreground">{comment.author_name}</span>
          <span className="text-[11px] text-muted-foreground">
            {timeAgo(comment.created_at)}
            {comment.is_edited && ' · edited'}
          </span>
        </div>

        {/* Body */}
        {isEditing ? (
          <div className="flex flex-col gap-2">
            <CommentInputBox
              initialValue={editState.text}
              onSubmit={(nextText) => onEditSave(comment.id, nextText)}
              onCancel={onEditCancel}
              submitLabel="Save"
              autoFocus
            />
          </div>
        ) : (
          <p className="text-sm text-foreground leading-relaxed break-words whitespace-pre-wrap">
            {renderMentions(comment.text)}
          </p>
        )}

        {/* Actions */}
        {!isEditing && (
          <div className="flex items-center gap-3 mt-1.5">
            {!isReply && (
              <button
                onClick={() => onReplyToggle(comment.id)}
                className="text-[11px] font-medium text-muted-foreground hover:text-foreground transition-colors"
              >
                Reply
              </button>
            )}
            <Tooltip
              content={
                comment.like_count === 0 ? null : (
                  <div className="flex items-center -space-x-1.5">
                    {comment.likes.slice(0, MAX_LIKES_SHOWN).map((like) => (
                      <div key={like.user_id} className="rounded-full ring-2 ring-popover">
                        <Avatar name={like.user_name} url={like.user_avatar_url} size="sm" />
                      </div>
                    ))}
                    {comment.likes.length > MAX_LIKES_SHOWN && (
                      <div className="flex h-8 w-8 items-center justify-center rounded-full ring-2 ring-popover bg-accent text-[10px] font-semibold text-muted-foreground">
                        +{comment.likes.length - MAX_LIKES_SHOWN}
                      </div>
                    )}
                  </div>
                )
              }
              disabled={comment.like_count === 0}
              position="top"
            >
              <button
                onClick={() => onToggleLike(comment.id)}
                className={`flex items-center gap-1 text-[11px] font-medium transition-colors ${
                  comment.liked_by_me ? 'text-cobalt' : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                <ThumbsUp className={`w-3 h-3 ${comment.liked_by_me ? 'fill-current' : ''}`} />
                {comment.like_count > 0 && <span>{comment.like_count}</span>}
              </button>
            </Tooltip>
            {canEdit && (
              <button
                onClick={() => onEditStart(comment.id, comment.text)}
                className="text-[11px] font-medium text-muted-foreground hover:text-foreground transition-colors"
              >
                Edit
              </button>
            )}
            {isAuthor && (
              <button
                onClick={() => onArchive(comment.id)}
                className="flex items-center gap-1 text-[11px] font-medium text-muted-foreground hover:text-red-500 transition-colors"
              >
                <Trash2 className="w-3 h-3" />
                Delete
              </button>
            )}
          </div>
        )}

        {/* View/hide replies — fetched only when expanded, not eagerly with
            the main list, so a thread's initial payload stays light. */}
        {!isReply && comment.reply_count > 0 && (
          <button
            onClick={() => onToggleReplies(comment.id)}
            className="mt-2 flex items-center gap-1.5 text-[11px] font-semibold text-muted-foreground hover:text-foreground transition-colors"
          >
            <span className="h-px w-6 bg-border" />
            {loadingReplies ? (
              <>
                <ChevronDown className="w-3 h-3" />
                Loading replies…
              </>
            ) : repliesExpanded ? (
              <>
                <ChevronUp className="w-3 h-3" />
                Hide replies
              </>
            ) : (
              <>
                <ChevronDown className="w-3 h-3" />
                {`View ${comment.reply_count} ${comment.reply_count === 1 ? 'reply' : 'replies'}`}
              </>
            )}
          </button>
        )}

        {/* Reply composer */}
        {isReplying && (
          <div className="mt-2">
            <CommentInputBox
              onSubmit={(text) => onReplySubmit(comment.id, text)}
              onCancel={onReplyCancel}
              submitting={submitting}
              submitLabel="Reply"
              placeholder={`Reply to ${comment.author_name}…`}
              autoFocus
            />
          </div>
        )}
      </div>
    </div>
  );
}

// ── CommentList ───────────────────────────────────────────────────────────────

export interface CommentListProps {
  /** Top-level comments only — replies aren't in this array, see repliesByParentId. */
  comments: Comment[];
  editState: CommentEditState | null;
  replyingToId: string | null;
  submitting: boolean;
  /** Replies fetched so far, keyed by parent id (empty until expanded). */
  repliesByParentId: Record<string, Comment[]>;
  /** Which top-level comments currently have their replies expanded. */
  expandedParentIds: Set<string>;
  /** Parent id currently fetching its replies, or null. */
  loadingReplyParentId: string | null;
  onEditStart: (id: string, text: string) => void;
  onEditSave: (id: string, text: string) => void;
  onEditCancel: () => void;
  onArchive: (id: string) => void;
  onReplyToggle: (id: string) => void;
  onReplySubmit: (parentId: string, text: string) => Promise<void>;
  onReplyCancel: () => void;
  onToggleLike: (id: string) => void;
  onToggleReplies: (parentId: string) => void;
}

export function CommentList({
  comments,
  editState,
  replyingToId,
  submitting,
  repliesByParentId,
  expandedParentIds,
  loadingReplyParentId,
  onEditStart,
  onEditSave,
  onEditCancel,
  onArchive,
  onReplyToggle,
  onReplySubmit,
  onReplyCancel,
  onToggleLike,
  onToggleReplies,
}: CommentListProps) {
  const { user } = useAuth();
  const currentUserId = user?.id ?? null;
  const isAdmin = false;

  if (comments.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 gap-2">
        <div className="w-10 h-10 rounded-full bg-muted flex items-center justify-center">
          <AtSign className="w-5 h-5 text-muted-foreground" />
        </div>
        <p className="text-sm font-medium text-muted-foreground">No comments yet</p>
        <p className="text-xs text-muted-foreground">Be the first — use @ to mention someone</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-5">
      {comments.map((comment) => {
        const isExpanded = expandedParentIds.has(comment.id);
        const isLoadingReplies = loadingReplyParentId === comment.id;
        const replies = repliesByParentId[comment.id] ?? [];
        return (
          <div key={comment.id} className="flex flex-col gap-3">
            <CommentCard
              comment={comment}
              editState={editState}
              currentUserId={currentUserId}
              isAdmin={isAdmin}
              replyingToId={replyingToId}
              submitting={submitting}
              repliesExpanded={isExpanded}
              loadingReplies={isLoadingReplies}
              onEditStart={onEditStart}
              onEditSave={onEditSave}
              onEditCancel={onEditCancel}
              onArchive={onArchive}
              onReplyToggle={onReplyToggle}
              onReplySubmit={onReplySubmit}
              onReplyCancel={onReplyCancel}
              onToggleLike={onToggleLike}
              onToggleReplies={onToggleReplies}
            />
            {isExpanded && replies.length > 0 && (
              <div className="ml-11 flex flex-col gap-3">
                {replies.map((reply) => (
                  <CommentCard
                    key={reply.id}
                    comment={reply}
                    editState={editState}
                    currentUserId={currentUserId}
                    isAdmin={isAdmin}
                    isReply
                    replyingToId={replyingToId}
                    submitting={submitting}
                    onEditStart={onEditStart}
                    onEditSave={onEditSave}
                    onEditCancel={onEditCancel}
                    onArchive={onArchive}
                    onReplyToggle={onReplyToggle}
                    onReplySubmit={onReplySubmit}
                    onReplyCancel={onReplyCancel}
                    onToggleLike={onToggleLike}
                    onToggleReplies={onToggleReplies}
                  />
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── CommentComposer ───────────────────────────────────────────────────────────

export interface CommentComposerProps {
  onSubmit: (text: string) => Promise<void>;
  submitting: boolean;
  anchorAutocompleteBottom?: boolean;
  error?: string | null;
  onDismissError?: () => void;
}

export function CommentComposer({
  onSubmit,
  submitting,
  anchorAutocompleteBottom = false,
  error,
  onDismissError,
}: CommentComposerProps) {
  const { user } = useAuth();

  return (
    <div className="flex gap-3 items-start" data-comment-composer="true">
      <Avatar name={user?.fullName ?? 'You'} url={user?.avatarUrl} size="sm" />
      <div className="flex-1 min-w-0">
        {/* Inline error banner */}
        {error && (
          <div
            role="alert"
            className="mb-2 flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-destructive"
          >
            <span className="flex-1">{error}</span>
            {onDismissError && (
              <button
                type="button"
                onClick={onDismissError}
                className="rounded p-0.5 text-rose-500 hover:bg-rose-100 hover:text-destructive transition-colors"
                aria-label="Dismiss error"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        )}

        <CommentInputBox
          onSubmit={onSubmit}
          submitting={submitting}
          anchorAutocompleteBottom={anchorAutocompleteBottom}
          submitLabel="Comment"
        />
      </div>
    </div>
  );
}

// ── CommentThread (default — simple inline use) ───────────────────────────────

interface CommentThreadProps {
  entityId: string;
  workflowId?: string;
}

export default function CommentThread({ entityId, workflowId }: CommentThreadProps) {
  const {
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
    expandedParentIds,
    loadingReplyParentId,
    toggleReplies,
    lastError,
    clearError,
  } = useComments({ entityId, workflowId });

  return (
    <div className="flex flex-col gap-4">
      <CommentList
        comments={comments}
        editState={editState}
        replyingToId={replyingToId}
        submitting={submitting}
        repliesByParentId={repliesByParentId}
        expandedParentIds={expandedParentIds}
        loadingReplyParentId={loadingReplyParentId}
        onEditStart={(id, text) => setEditState({ id, text })}
        onEditSave={saveEdit}
        onEditCancel={() => setEditState(null)}
        onArchive={archive}
        onReplyToggle={(id) => setReplyingToId(replyingToId === id ? null : id)}
        onReplySubmit={submitReply}
        onReplyCancel={() => setReplyingToId(null)}
        onToggleLike={toggleLike}
        onToggleReplies={toggleReplies}
      />
      <div className="border-t border-border pt-4">
        <CommentComposer
          onSubmit={submit}
          submitting={submitting}
          error={lastError}
          onDismissError={clearError}
        />
      </div>
    </div>
  );
}
