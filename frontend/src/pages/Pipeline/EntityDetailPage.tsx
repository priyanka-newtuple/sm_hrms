import { useEffect, useMemo } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft } from 'lucide-react';

import AccessDenied from '@/core/components/AccessDenied';
import DocumentPreviewPanel from '@/core/components/DocumentPreviewPanel';
import EntityIteratorControls from '@/core/components/EntityIteratorControls';
import { useEntityEditingLock } from '@/core/hooks/useEntityIterator';
import { useDocumentPreviewStore } from '@/core/stores/documentPreviewStore';
import { getEntityDisplayTitle } from '@/shared/utils/entityDisplay';
import { workflowEntities } from '@/core/services/api';
import EntityDetailContent from './components/EntityDetailSlideOver/EntityDetailContent';
import { usePipelineBoardData } from './hooks/usePipelineBoardData';
import { useWorkflowColumnEntities } from './hooks/useWorkflowColumnEntities';
import { invalidateWorkflowEntities, patchWorkflowEntityData } from './hooks/workflowEntityCache';
import { useFullWorkflowEntity } from '@/shared/hooks/useFullWorkflowEntity';
import { resolveFullWorkflowEntityDisplay } from '@/shared/hooks/fullWorkflowEntityIdentity';

/** Full-page variant of the entity detail view (the sheet variant is
 *  EntityDetailSlideOver). Deep-linkable: survives refresh by fetching the
 *  target entity directly; honors the same ?tab= / ?comment= params as the
 *  sheet. Prev/next iterates the entity's own current-state column (bounded
 *  to that column's loaded page) rather than every board-filtered entity —
 *  this page has no filter UI of its own, unlike the board it's linked from. */
export default function EntityDetailPage() {
  const { id, entityId } = useParams<{ id: string; entityId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const tabParam = searchParams.get('tab');
  const commentParam = searchParams.get('comment');
  // Set by embedders whose entity click didn't come from the /pipeline board
  // itself (e.g. the agent-mode canvas) — sends "back" there instead of the
  // board this page would otherwise default to. User-controlled (it's a
  // query param), so only trust it when it's an in-app path: a plain leading
  // "/" rules out absolute URLs ("https://evil.com"), and rejecting a second
  // leading "/" rules out scheme-relative ones ("//evil.com") — either would
  // otherwise turn this in-app back arrow into an open redirect.
  const returnToParam = searchParams.get('returnTo');
  const returnTo = returnToParam?.startsWith('/') && !returnToParam.startsWith('//') ? returnToParam : null;
  const replyParam = searchParams.get('reply');
  // Board filters (assignee, etc.) ride here as `filter_*` params, carried
  // over by PipelinePage's handleEntityClick — strip only the detail-page-
  // specific keys so "back to board" restores whatever filters were active.
  const backSearch = useMemo(() => {
    const params = new URLSearchParams(searchParams);
    params.delete('tab');
    params.delete('comment');
    params.delete('returnTo');
    params.delete('reply');
    return params.toString();
  }, [searchParams]);
  const backTarget = returnTo ? returnTo : { pathname: `/pipeline/${id}`, search: backSearch };

  const {
    workflow,
    loading,
    error,
    model,
    schemasForState,
    canView,
  } = usePipelineBoardData(id);

  const {
    data: entitySummary,
    isLoading: entitySummaryLoading,
    error: entitySummaryError,
  } = useQuery({
    queryKey: ['workflowEntitySummary', entityId],
    queryFn: () => workflowEntities.get(entityId ?? ''),
    enabled: Boolean(entityId),
  });

  const { items: iteratorEntities } = useWorkflowColumnEntities(
    model?.machineName ?? '',
    entitySummary?.current_state ?? '',
    {},
  );

  const {
    entity,
    loading: entityLoading,
    error: entityError,
    refetch: refetchEntity,
  } = useFullWorkflowEntity(entitySummary ?? null);
  const {
    displayedEntity,
    displayLoading: detailLoading,
  } = resolveFullWorkflowEntityDisplay(
    entitySummary ?? null,
    entity,
    entityLoading,
    entityError,
  );
  const entityIndex = iteratorEntities.findIndex(
    (candidate) =>
      candidate.entity_id === entityId
      && (!id || candidate.workflow_id === id),
  );
  const {
    editing,
    onEditingChange,
  } = useEntityEditingLock(displayedEntity?.entity_id);

  // Clear entity-specific preview state when navigating or leaving the page.
  const resetPreview = useDocumentPreviewStore((s) => s.reset);
  useEffect(() => {
    resetPreview();
    return resetPreview;
  }, [entityId, resetPreview]);

  const navigateEntity = (offset: -1 | 1) => {
    const target = iteratorEntities[entityIndex + offset];
    if (!target) return;
    const query = searchParams.toString();
    navigate(
      `/pipeline/${target.workflow_id ?? id}/entity/${target.entity_id}${query ? `?${query}` : ''}`,
    );
  };

  const refetchEntities = () => invalidateWorkflowEntities(queryClient);
  const patchEntityData = (targetEntityId: string, data: Record<string, unknown>) =>
    patchWorkflowEntityData(queryClient, targetEntityId, data);
  const updateEntity = async (targetEntityId: string, payload: Parameters<typeof workflowEntities.update>[1]) => {
    await workflowEntities.update(targetEntityId, payload);
  };

  if (loading) {
    return <div className="p-6 text-sm text-muted-foreground">Loading entity…</div>;
  }

  if (error || !workflow) {
    return (
      <div className="p-6">
        <h1 className="mb-2 text-xl font-semibold text-foreground">Workflow not found</h1>
        <p className="mb-4 text-sm text-muted-foreground">
          {error ?? (
            <>
              No workflow with id <code className="rounded bg-muted px-1 py-0.5">{id}</code>.
            </>
          )}
        </p>
        <Link to="/workflows" className="text-sm text-cobalt hover:underline">
          Go to workflows
        </Link>
      </div>
    );
  }

  if (!canView) {
    return (
      <div className="p-6">
        <AccessDenied entityType={workflow.entity_type} />
      </div>
    );
  }

  if (!displayedEntity) {
    if (entitySummaryLoading || entityLoading) {
      return <div className="p-6 text-sm text-muted-foreground">Loading entity…</div>;
    }
    return (
      <div className="p-6">
        <h1 className="mb-2 text-xl font-semibold text-foreground">Entity not found</h1>
        <p className="mb-4 text-sm text-muted-foreground">
          {entityError ?? (entitySummaryError ? String(entitySummaryError) : null) ?? <>No entity with id <code className="rounded bg-muted px-1 py-0.5">{entityId}</code> in this pipeline.</>}
        </p>
        <Link to={backTarget} className="text-sm text-cobalt hover:underline">
          Back to board
        </Link>
      </div>
    );
  }

  const title = getEntityDisplayTitle(displayedEntity.data, displayedEntity.entity_id);

  return (
    <div className="flex h-[calc(100svh-6rem)] min-w-0 flex-col overflow-hidden lg:h-[calc(100svh-8rem)]">
      <div className="mb-0.5 shrink-0">
        <div className="flex items-center justify-between gap-4">
          <div className="flex min-w-0 flex-wrap items-center gap-x-4 gap-y-1">
            <Link
              to={backTarget}
              className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
            >
              <ArrowLeft className="h-4 w-4" />
            </Link>
            <h1 className="truncate text-xl font-semibold leading-none text-foreground">{title}</h1>
            <p className="text-sm leading-none text-muted-foreground">{displayedEntity.entity_type}</p>
          </div>
          {entityIndex >= 0 && (
            <EntityIteratorControls
              current={entityIndex + 1}
              total={iteratorEntities.length}
              onPrevious={() => navigateEntity(-1)}
              onNext={() => navigateEntity(1)}
              disabled={editing || detailLoading}
              className="shrink-0"
            />
          )}
        </div>
      </div>

      <div className="flex min-h-0 flex-1 gap-4">
        <div className="relative flex min-w-0 flex-1 flex-col overflow-hidden">
          {detailLoading && (
            <div className="absolute inset-0 z-20 flex items-center justify-center bg-card/80">
              <span className="text-sm text-muted-foreground">Loading entity…</span>
            </div>
          )}
          <EntityDetailContent
            key={displayedEntity.entity_id}
            entity={displayedEntity}
            // Strictly the fields this record's current state collects. A
            // field from a state already passed stops rendering; its stored
            // value is unaffected.
            schemas={schemasForState(displayedEntity.current_state)}
            schemasAuthoritative
            onSaveEntity={updateEntity}
            onFileUploaded={() => { void refetchEntities(); refetchEntity(); }}
            initialTab={
              tabParam === 'comments' || tabParam === 'activity' ? tabParam : undefined
            }
            scrollToCommentId={commentParam}
            scrollToReplyId={replyParam}
            workflowId={id}
            compactChrome
            onTransitionExecuted={() => { void refetchEntities(); refetchEntity(); }}
            onEditingChange={onEditingChange}
            onEntityDataSaved={(newData) => {
              patchEntityData(displayedEntity.entity_id, newData);
              void refetchEntities();
              refetchEntity();
            }}
            onDeleted={() => {
              void refetchEntities();
              navigate(backTarget);
            }}
          />
        </div>
        <DocumentPreviewPanel layout="page" />
      </div>
    </div>
  );
}
