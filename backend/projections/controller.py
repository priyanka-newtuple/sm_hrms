"""Projections REST controller module."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from common.auth import require_permission, actor_str
from exceptions import NotFoundError, ServiceError

from projections.manager import ProjectionsServiceManager

ProjectionReadActor = Annotated[dict[str, object], Depends(require_permission("projection", "read"))]
ProjectionWriteActor = Annotated[dict[str, object], Depends(require_permission("projection", "write"))]
from projections.models.response import (
    FunnelsInUseResponse,
    HeatmapRead,
    HeatmapRefreshResponse,
    PipelineViewRead,
    ProjectionsStatusResponse,
    RebuildProjectionsResponse,
)


class ProjectionsRestController:
    """Projections REST controller — pipeline board, heatmap, funnels."""

    def __init__(
        self,
        projections_service_manager: ProjectionsServiceManager,
        database_service_manager: Any = None,
        auth_service_manager: Any = None,
    ) -> None:
        super().__init__()
        self.manager = projections_service_manager

    def prepare(self, app: APIRouter) -> None:
        projections_router = APIRouter(prefix="/projections", tags=["projections"])

        # ── Status ────────────────────────────────────────────────────────────

        @projections_router.get("/status", response_model=ProjectionsStatusResponse)
        def get_status():
            return self.manager.get_status()

        # ── Pipeline ──────────────────────────────────────────────────────────

        @projections_router.get("/pipeline", response_model=list[PipelineViewRead])
        def list_pipeline(
            actor: ProjectionReadActor,
            current_state: str | None = Query(default=None),
            job_id: str | None = Query(default=None),
            sla_risk: str | None = Query(default=None),
        ):
            """List pipeline board entries (Kanban cards) for the current org."""
            org_id = actor_str(actor, "organization_id")
            try:
                return self.manager.list_pipeline(
                    org_id, current_state=current_state, job_id=job_id, sla_risk=sla_risk, actor=actor
                )
            except ServiceError as exc:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

        @projections_router.get("/pipeline/{application_id}", response_model=PipelineViewRead)
        def get_pipeline_entry(
            application_id: str,
            actor: ProjectionReadActor,
        ):
            """Get a single pipeline board card by application ID."""
            org_id = actor_str(actor, "organization_id")
            try:
                return self.manager.get_pipeline_entry(org_id, application_id, actor=actor)
            except NotFoundError as exc:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
            except ServiceError as exc:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

        # ── Funnels ───────────────────────────────────────────────────────────

        @projections_router.get("/pipeline-funnels", response_model=FunnelsInUseResponse)
        def list_funnels(
            actor: ProjectionReadActor,
            job_id: str | None = Query(default=None),
        ):
            """Get distinct funnels in use — drives multi-funnel detection on the pipeline board."""
            org_id = actor_str(actor, "organization_id")
            try:
                return self.manager.list_funnels(org_id, job_id=job_id)
            except ServiceError as exc:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

        # ── Heatmap ───────────────────────────────────────────────────────────

        @projections_router.get("/heatmap", response_model=list[HeatmapRead])
        def list_heatmap(
            actor: ProjectionReadActor,
            job_id: str | None = Query(default=None),
        ):
            """List SLA heatmap aggregations grouped by job and state."""
            org_id = actor_str(actor, "organization_id")
            try:
                return self.manager.list_heatmap(org_id, job_id=job_id)
            except ServiceError as exc:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

        @projections_router.post("/heatmap/refresh", response_model=HeatmapRefreshResponse)
        def refresh_heatmap(
            actor: ProjectionWriteActor,
            job_id: str | None = Query(default=None),
        ):
            """Trigger heatmap aggregation refresh (admin/owner only)."""
            org_id = actor_str(actor, "organization_id")
            try:
                return self.manager.refresh_heatmap(org_id, job_id=job_id)
            except ServiceError as exc:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

        # ── Rebuild ───────────────────────────────────────────────────────────

        @projections_router.post("/rebuild", response_model=RebuildProjectionsResponse)
        def rebuild_projections(
            actor: ProjectionWriteActor,
            entity_type: str | None = Query(default=None),
        ):
            """Rebuild all projection rows from source entities (admin/owner only)."""
            org_id = actor_str(actor, "organization_id")
            try:
                return self.manager.rebuild_projections(org_id, entity_type=entity_type)
            except ServiceError as exc:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

        app.include_router(projections_router, tags=["projections"])
