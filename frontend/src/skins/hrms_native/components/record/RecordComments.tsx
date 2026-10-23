import { CommentList, CommentComposer } from '@/core/components/CommentThread';
import { useComments } from './useRecordComments';
interface CommentThreadProps {
  entityId: string;
  workflowId?: string;
  scope: string;
}

export default function CommentThread({ entityId, workflowId, scope }: CommentThreadProps) {
  const {
    loading, loadError, retryLoad,
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
  } = useComments({ entityId, workflowId, scope });

  if (loading) return <p role="status">Loading comments…</p>;
  if (loadError) return <div role="alert"><p>{loadError}</p><button type="button" className="hrms-outline-button" onClick={retryLoad}>Retry</button></div>;
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
