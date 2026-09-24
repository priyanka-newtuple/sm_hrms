import { useEffect, useRef, useState } from 'react';
import { CalendarDays, Trash2, UserCheck, UserPlus } from 'lucide-react';
import { toast } from 'sonner';

import ConfirmDialog from '@/core/components/ConfirmDialog';
import EntityDocuments from '@/core/components/EntityDocuments';
import RelatedEntityDocuments from '@/core/components/RelatedEntityDocuments';
import { CommentList, CommentComposer } from '@/core/components/CommentThread';
import { useBackgroundWorkRefresh } from '@/core/hooks/useBackgroundWorkRefresh';
import { useComments } from '@/core/hooks/useComments';
import { useFeatureFlags } from '@/core/hooks/useFeatureFlags';
import { usePermissions } from '@/core/hooks/usePermissions';
import { users as usersApi, workflowEntities } from '@/core/services/api';
import type { WorkflowEntityState } from '@/core/services/api';
import { useAuth } from '@/core/auth';
import type { FormSchema, User } from '@/core/types';
import { DDSelect } from '@/pages/funnel/canvas/DDSelect';
import TransitionActions from '@/shared/components/TransitionActions';
import RerunStateActionButton from '@/shared/components/RerunStateActionButton';
import EntityDataSection from './EntityDataSection';
import SlaTag from './SlaTag';
import DueDateBadge from '../DueDateBadge';
import ActivityTimeline from './activity/ActivityTimeline';

export type EntityDetailTab = 'details' | 'activity' | 'comments';

/** DDSelect sentinel value for the "Unassigned" option (maps to null). */
const UNASSIGNED_OPTION = '__unassigned__';

export interface EntityDetailContentProps {
  entity: WorkflowEntityState;
  onTransitionExecuted: () => void;
  schemas?: FormSchema[];
  /** See EntityDataSectionProps.schemasAuthoritative. */
  schemasAuthoritative?: boolean;
  onSaveEntity: (
    entityId: string,
    payload: { data?: Record<string, unknown>; due_date?: string | null; schema_fields?: Array<Record<string, unknown>> },
  ) => Promise<void>;
  onEntityDataSaved?: (newData: Record<string, unknown>) => void;
  onFileUploaded?: () => void;
  initialTab?: EntityDetailTab;
  scrollToCommentId?: string | null;
  /** Set alongside scrollToCommentId when the target is a reply — replies
   *  are lazy-loaded, so scrollToCommentId points at the reply's *parent*
   *  (always fetched) and this is auto-expanded to reveal + scroll to it. */
  scrollToReplyId?: string | null;
  workflowId?: string;
  compactChrome?: boolean;
  onEditingChange?: (editing: boolean) => void;
  /** Called after the entity has been deleted, so the parent can close/navigate away. */
  onDeleted?: () => void;
}

const DAY_MS = 1000 * 60 * 60 * 24;

function daysSince(iso?: string): number | null {
  if (!iso) return null;
  return Math.floor((Date.now() - new Date(iso).getTime()) / DAY_MS);
}

function relativeDate(iso?: string): string {
  if (!iso) return '—';
  const diff = Date.now() - new Date(iso).getTime();
  const days = Math.floor(diff / DAY_MS);
  if (days === 0) return 'today';
  if (days < 7) return `${days}d ago`;
  if (days < 30) return `${Math.floor(days / 7)}w ago`;
  if (days < 365) return `${Math.floor(days / 30)}mo ago`;
  return `${Math.floor(days / 365)}y ago`;
}

interface MetricTileProps {
  label: string;
  value: string;
  sub?: string;
}

function MetricTile({ label, value, sub }: MetricTileProps) {
  return (
    <div className="bg-card px-3.5 py-2.5">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-[15px] font-medium text-foreground">
        {value}
        {sub && <span className="ml-1 text-xs font-normal text-muted-foreground">{sub}</span>}
      </p>
    </div>
  );
}

/** Flush 4-up metric row; the 1px gap reveals the border color as hairlines. */
function MetricStrip({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-4 gap-px overflow-hidden rounded-lg border border-border bg-border">
      {children}
    </div>
  );
}

const TABS: { id: EntityDetailTab; label: string }[] = [
  { id: 'details', label: 'Details' },
  { id: 'activity', label: 'Activity' },
  { id: 'comments', label: 'Comments' },
];

/** Entity detail body — badge row, tabs, tab panels, pinned comment composer.
 *  Shared by the slide-over sheet and the full-page view; the parent must be
 *  a bounded-height flex column so the body scrolls and the footer pins. */
export default function EntityDetailContent({
  entity,
  onTransitionExecuted,
  schemas = [],
  schemasAuthoritative = false,
  onSaveEntity,
  onEntityDataSaved,
  onFileUploaded,
  initialTab,
  scrollToCommentId,
  scrollToReplyId,
  workflowId,
  compactChrome = false,
  onEditingChange,
  onDeleted,
}: EntityDetailContentProps) {
  const { user } = useAuth();
  const { hideDueDate } = useFeatureFlags();
  const { can } = usePermissions();
  const [activeTab, setActiveTab] = useState<EntityDetailTab>(initialTab ?? 'details');
  const [orgUsers, setOrgUsers] = useState<User[]>([]);
  const [assigning, setAssigning] = useState(false);
  const [savingDueDate, setSavingDueDate] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const canDelete = can('delete', entity.entity_type);

  const refreshAfterBackgroundWork = useBackgroundWorkRefresh(
    entity.entity_id,
    onTransitionExecuted,
  );

  const commentState = useComments({
    entityId: entity.entity_id,
    workflowId,
  });

  // Load org users on mount to populate the assignee picker. (This component
  // only renders while the detail view is open, so mount ≙ open.)
  useEffect(() => {
    let active = true;
    usersApi
      .list('active')
      .then((list) => {
        if (active) setOrgUsers(list);
      })
      .catch((err) => {
        console.error('Failed to load org users for assignee picker:', err);
        if (active) setOrgUsers([]);
      });
    return () => {
      active = false;
    };
  }, []);

  // Hand the record back to whoever created it. The originator is resolved
  // server-side, so the browser never needs to know who that is — and the
  // backend stays the only authority on whether they can still be assigned.
  const handleAssignToOriginator = async () => {
    setAssigning(true);
    try {
      await workflowEntities.assignToOriginator(entity.entity_id);
      onEntityDataSaved?.(entity.data);
      toast.success('Assigned to originator');
    } catch (err) {
      toast.error('Could not assign to originator', {
        description: err instanceof Error ? err.message : undefined,
      });
    } finally {
      setAssigning(false);
    }
  };

  // Assign to a user, or clear the assignment when assigneeId is null.
  const handleAssign = async (assigneeId: string | null) => {
    const current = entity.assignee_id ?? null;
    if (assigneeId === current) return;
    setAssigning(true);
    try {
      await workflowEntities.setAssignee(entity.entity_id, assigneeId);
      onEntityDataSaved?.(entity.data);
    } finally {
      setAssigning(false);
    }
  };

  const handleDelete = async () => {
    setDeleting(true);
    try {
      await workflowEntities.delete(entity.entity_id);
      setConfirmingDelete(false);
      onDeleted?.();
    } catch (err) {
      toast.error('Could not delete entity', {
        description: err instanceof Error ? err.message : undefined,
      });
    } finally {
      setDeleting(false);
    }
  };

  const handleDueDateChange = async (value: string) => {
    setSavingDueDate(true);
    try {
      await workflowEntities.update(entity.entity_id, {
        due_date: value || null,
      });
      onEntityDataSaved?.(entity.data);
    } finally {
      setSavingDueDate(false);
    }
  };

  // When deep-linked into a specific tab, react to changes (e.g. clicking a
  // new notification while the detail view is already open for the same entity).
  useEffect(() => {
    if (initialTab) setActiveTab(initialTab);
  }, [initialTab]);

  // Scroll-to-comment when entering the comments tab via a deep link. If the
  // target is a reply, scrollToCommentId is its *parent* (replies are
  // lazy-loaded, so a link straight to a reply's own id has nothing to
  // scroll to until its parent's replies are expanded) — auto-expand it
  // first, then scroll to the reply once it's actually fetched in.
  const {
    comments: threadComments,
    expandedParentIds,
    repliesByParentId,
    toggleReplies,
    refreshReplies,
  } = commentState;
  // Tracks which (comment, reply) deep link we've already auto-expanded and
  // scrolled to. Without this, the effect re-fires on ANY thread interaction
  // (expandedParentIds/repliesByParentId/threadComments all change identity
  // on unrelated edits/likes elsewhere) and would forcibly re-expand a thread
  // the user just manually collapsed, since scrollToCommentId/scrollToReplyId
  // stay set in the URL until the whole panel closes.
  const handledDeepLinkRef = useRef<string | null>(null);
  // Bounds the auto-expand and stale-cache-refresh attempts below to exactly
  // one try per deep link — toggleReplies/refreshReplies swallow their own
  // errors (so this effect has no success/failure signal to key off), and
  // without this bound a persistent failure would re-fire the request on
  // every unrelated re-render forever instead of giving up once.
  const attemptedExpandRef = useRef<string | null>(null);
  const attemptedRefreshRef = useRef<string | null>(null);
  useEffect(() => {
    if (!scrollToCommentId || activeTab !== 'comments') return;
    const deepLinkKey = `${scrollToCommentId}:${scrollToReplyId ?? ''}`;
    if (handledDeepLinkRef.current === deepLinkKey) return;

    if (scrollToReplyId) {
      if (!expandedParentIds.has(scrollToCommentId)) {
        if (attemptedExpandRef.current !== deepLinkKey) {
          attemptedExpandRef.current = deepLinkKey;
          void toggleReplies(scrollToCommentId);
        }
        return; // re-runs once expandedParentIds/repliesByParentId update
      }
      const replies = repliesByParentId[scrollToCommentId] ?? [];
      if (!replies.some((r) => r.id === scrollToReplyId)) {
        // The parent may have already been expanded (and cached) before
        // this reply existed — e.g. the thread was open when the reply
        // that this deep link points to was posted. Force one refetch
        // before giving up, rather than treating "not found yet" as
        // "still loading" forever.
        if (attemptedRefreshRef.current !== deepLinkKey) {
          attemptedRefreshRef.current = deepLinkKey;
          void refreshReplies(scrollToCommentId);
        }
        return;
      }
      handledDeepLinkRef.current = deepLinkKey;
      const raf = requestAnimationFrame(() => {
        const el = document.getElementById(`comment-${scrollToReplyId}`);
        if (!el) return;
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        el.classList.add('comment-highlight');
        window.setTimeout(() => el.classList.remove('comment-highlight'), 1800);
      });
      return () => cancelAnimationFrame(raf);
    }

    const found = threadComments.find((c) => c.id === scrollToCommentId);
    if (!found) return;
    handledDeepLinkRef.current = deepLinkKey;
    const raf = requestAnimationFrame(() => {
      const el = document.getElementById(`comment-${scrollToCommentId}`);
      if (!el) return;
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      el.classList.add('comment-highlight');
      window.setTimeout(() => el.classList.remove('comment-highlight'), 1800);
    });
    return () => cancelAnimationFrame(raf);
  }, [
    scrollToCommentId,
    scrollToReplyId,
    activeTab,
    threadComments,
    expandedParentIds,
    repliesByParentId,
    toggleReplies,
    refreshReplies,
  ]);

  const stateEnteredDays = daysSince(entity.state_entered_at);

  const commentFooter =
    activeTab === 'comments' ? (
      <CommentComposer
        onSubmit={commentState.submit}
        submitting={commentState.submitting}
        anchorAutocompleteBottom
        error={commentState.lastError}
        onDismissError={commentState.clearError}
      />
    ) : undefined;

  return (
    <>
      <div className="flex-1 overflow-y-auto px-6">
        {/* Sticky header: badge row + tabs */}
        <div className="sticky top-0 z-10 -mx-6 px-6 bg-card pb-0">
          {/* State badge row */}
          <div className={`flex flex-wrap items-center gap-2 ${compactChrome ? 'py-2.5' : 'py-4'}`}>
            <span className="inline-flex items-center gap-1.5 rounded-full border border-cobalt/20 bg-cobalt/8 px-3 py-1 text-xs font-semibold tracking-wide text-cobalt">
              {entity.current_state}
            </span>
            {stateEnteredDays !== null && (
              <span className="text-xs text-muted-foreground">for {stateEnteredDays}d</span>
            )}
            {entity.sla_due_at && <SlaTag slaDate={entity.sla_due_at} />}
            {!hideDueDate && entity.due_date && <DueDateBadge value={entity.due_date} />}
            {!hideDueDate && (
              <label className="inline-flex items-center gap-1.5 rounded-md border border-border bg-background px-2 py-1 text-xs text-muted-foreground">
                <CalendarDays className="h-3.5 w-3.5" />
                <span>Due date</span>
                <input
                  key={entity.entity_id}
                  type="date"
                  defaultValue={entity.due_date?.slice(0, 10) ?? ''}
                  disabled={savingDueDate}
                  onChange={(event) => void handleDueDateChange(event.target.value)}
                  className="bg-transparent text-xs font-medium text-foreground outline-none disabled:opacity-50"
                  aria-label="Due date"
                />
              </label>
            )}
            <RerunStateActionButton
              entityId={entity.entity_id}
              currentState={entity.current_state}
              machineName={entity.machine_name}
              workflowId={entity.workflow_id ?? workflowId}
              // Refresh in place — onTransitionExecuted would close the slide-over.
              onCompleted={() => {
                onEntityDataSaved?.(entity.data);
                refreshAfterBackgroundWork();
              }}
            />
            <TransitionActions
              variant="inline"
              entityId={entity.entity_id}
              workflowId={entity.workflow_id ?? workflowId}
              onExecuted={() => {
                onTransitionExecuted();
                // Entry actions run in a worker and land after this response,
                // so re-check shortly afterwards instead of leaving the
                // assignee and timeline stale until a manual refresh.
                refreshAfterBackgroundWork();
              }}
              refreshKey={JSON.stringify(entity.data)}
            />
            {canDelete && (
              <button
                type="button"
                onClick={() => setConfirmingDelete(true)}
                title="Delete entity"
                aria-label="Delete entity"
                className="inline-flex items-center justify-center rounded-md p-1.5 text-muted-foreground transition-all duration-150 hover:scale-110 hover:bg-destructive/10 hover:text-destructive active:scale-95"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            )}
          </div>

          {/* Tabs */}
          <div className="flex border-b border-border">
            {TABS.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={[
                  'px-4 py-2.5 text-sm font-medium transition-colors',
                  activeTab === tab.id
                    ? 'border-b-2 border-cobalt text-cobalt'
                    : 'border-b-2 border-transparent text-muted-foreground hover:text-foreground',
                ].join(' ')}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>

        {/* Tab content */}
        <div className={`space-y-6 pb-8 ${compactChrome ? 'pt-4' : 'pt-6'}`}>
          {activeTab === 'details' && (
            <>
              {/* Assignee */}
              <div className="flex items-center gap-3">
                <p className="w-24 shrink-0 text-[13px] text-muted-foreground">Assignee</p>
                <div className="max-w-xs flex-1">
                  <DDSelect
                    value={entity.assignee_id ?? UNASSIGNED_OPTION}
                    placeholder={assigning ? 'Saving…' : 'Unassigned'}
                    options={[
                      { value: UNASSIGNED_OPTION, label: 'Unassigned' },
                      ...orgUsers.map((u) => ({
                        value: u.id,
                        label: u.full_name || u.email,
                      })),
                    ]}
                    onSelect={(v) =>
                      void handleAssign(v === UNASSIGNED_OPTION ? null : v)
                    }
                  />
                </div>
                {user?.id && entity.assignee_id !== user.id && (
                  <button
                    type="button"
                    onClick={() => void handleAssign(user.id)}
                    disabled={assigning}
                    className="inline-flex shrink-0 items-center gap-1 rounded-lg border border-cobalt/30 bg-cobalt/5 px-2.5 py-1.5 text-xs font-medium text-cobalt transition-colors hover:bg-cobalt/10 disabled:opacity-50"
                  >
                    <UserCheck className="h-3.5 w-3.5" />
                    Assign to me
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => void handleAssignToOriginator()}
                  disabled={assigning}
                  title="Assign this record to the person who created it"
                  className="inline-flex shrink-0 items-center gap-1 rounded-lg border border-cobalt/30 bg-cobalt/5 px-2.5 py-1.5 text-xs font-medium text-cobalt transition-colors hover:bg-cobalt/10 disabled:opacity-50"
                >
                  <UserPlus className="h-3.5 w-3.5" />
                  Assign to Originator
                </button>
              </div>

              {/* Metric strip — generic entity metadata (no domain-specific fields) */}
              <MetricStrip>
                <MetricTile
                  label="Days in stage"
                  value={stateEnteredDays !== null ? String(stateEnteredDays) : '—'}
                />
                <MetricTile label="Created" value={relativeDate(entity.created_at)} />
                <MetricTile label="Updated" value={relativeDate(entity.updated_at)} />
                <MetricTile label="Last move" value={relativeDate(entity.last_transition_at)} />
              </MetricStrip>

              <EntityDataSection
                entity={entity}
                schemas={schemas}
                schemasAuthoritative={schemasAuthoritative}
                onSave={onSaveEntity}
                onSaved={onEntityDataSaved}
                onEditingChange={onEditingChange}
              />

              <EntityDocuments
                entityId={entity.entity_id}
                entityType={entity.entity_type}
                entityData={entity.data}
                onUpdated={onFileUploaded}
              />
              <RelatedEntityDocuments entityId={entity.entity_id} />
            </>
          )}

          {activeTab === 'activity' && (
            <ActivityTimeline entityId={entity.entity_id} orgUsers={orgUsers} />
          )}

          {activeTab === 'comments' && (
            <CommentList
              comments={commentState.comments}
              editState={commentState.editState}
              replyingToId={commentState.replyingToId}
              submitting={commentState.submitting}
              repliesByParentId={commentState.repliesByParentId}
              expandedParentIds={commentState.expandedParentIds}
              loadingReplyParentId={commentState.loadingReplyParentId}
              onEditStart={(id, text) => commentState.setEditState({ id, text })}
              onEditSave={commentState.saveEdit}
              onEditCancel={() => commentState.setEditState(null)}
              onArchive={commentState.archive}
              onReplyToggle={(id) =>
                commentState.setReplyingToId(commentState.replyingToId === id ? null : id)
              }
              onReplySubmit={commentState.submitReply}
              onReplyCancel={() => commentState.setReplyingToId(null)}
              onToggleLike={commentState.toggleLike}
              onToggleReplies={commentState.toggleReplies}
            />
          )}
        </div>
      </div>

      {commentFooter && (
        <div className="border-t border-border bg-card px-6 py-4">
          {commentFooter}
        </div>
      )}

      <ConfirmDialog
        open={confirmingDelete}
        onClose={() => setConfirmingDelete(false)}
        onConfirm={handleDelete}
        title="Delete entity"
        message="This will permanently delete this entity. This action cannot be undone."
        confirmLabel="Delete"
        variant="danger"
        loading={deleting}
      />
    </>
  );
}
