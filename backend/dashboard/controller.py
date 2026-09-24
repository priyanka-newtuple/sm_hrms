"""Dashboard REST controller module."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from common.auth import require_permission
from common.logger import logger, tracer
from dashboard.manager import DashboardServiceManager
from dashboard.models.request import (
    DashboardDataRequest,
    DashboardQueryPreviewRequest,
    DashboardUpdateRequest,
)
from dashboard.models.response import (
    DashboardDataResponse,
    DashboardFilterOptionsResponse,
    DashboardMetricsResponse,
    DashboardQueryPreviewResponse,
    DashboardQuerySourcesResponse,
    DashboardRead,
    DashboardStatusResponse,
)
from exceptions import (
    AuthorizationError,
    ConflictError,
    DBException,
    NotFoundError,
    PersistenceError,
    ServiceError,
    ServiceUnavailableError,
    ValidationError,
)

DashboardReadActor = Annotated[dict, Depends(require_permission("dashboard", "read"))]
DashboardWriteActor = Annotated[dict, Depends(require_permission("dashboard", "write"))]


class DashboardRestController:
    """Dashboard REST controller."""

    def __init__(
        self,
        dashboard_service_manager: DashboardServiceManager,
    ) -> None:
        self.manager = dashboard_service_manager

    def prepare(self, app: APIRouter) -> None:
        dashboard_router = APIRouter(prefix="/dashboards", tags=["dashboards"])

        @dashboard_router.get("/status", response_model=DashboardStatusResponse)
        def get_status():
            return self.manager.get_status()

        @dashboard_router.get("/query-sources", response_model=DashboardQuerySourcesResponse)
        def get_query_sources(
            request: Request,
            actor: DashboardReadActor,
        ) -> DashboardQuerySourcesResponse:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("DashboardController.query_sources"):
                try:
                    logger.info("dashboard.query_sources", extra={"request_id": request_id})
                    return self.manager.list_query_sources_for_actor(actor)
                except HTTPException as exc:
                    logger.exception(
                        "dashboard.query_sources failed",
                        extra={"request_id": request_id, "status_code": exc.status_code},
                    )
                    raise
                except ValidationError as exc:
                    logger.exception("dashboard.query_sources failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
                except (AuthorizationError, PermissionError) as exc:
                    logger.exception("dashboard.query_sources failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
                except ServiceUnavailableError as exc:
                    logger.exception("dashboard.query_sources failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
                except (ServiceError, DBException, PersistenceError) as exc:
                    logger.exception("dashboard.query_sources failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
                except Exception as exc:
                    logger.exception("dashboard.query_sources failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

        @dashboard_router.post("/query-preview", response_model=DashboardQueryPreviewResponse)
        def preview_query(
            request: Request,
            payload: DashboardQueryPreviewRequest,
            actor: DashboardReadActor,
        ) -> DashboardQueryPreviewResponse:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("DashboardController.query_preview"):
                try:
                    logger.info("dashboard.query_preview", extra={"request_id": request_id, "source": payload.query.source})
                    return self.manager.preview_query_for_actor(actor, payload.query)
                except HTTPException as exc:
                    logger.exception(
                        "dashboard.query_preview failed",
                        extra={
                            "request_id": request_id,
                            "source": payload.query.source,
                            "status_code": exc.status_code,
                        },
                    )
                    raise
                except ValidationError as exc:
                    logger.exception("dashboard.query_preview failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
                except (AuthorizationError, PermissionError) as exc:
                    logger.exception("dashboard.query_preview failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
                except ServiceUnavailableError as exc:
                    logger.exception("dashboard.query_preview failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
                except (ServiceError, DBException, PersistenceError) as exc:
                    logger.exception("dashboard.query_preview failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
                except Exception as exc:
                    logger.exception("dashboard.query_preview failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

        @dashboard_router.get("/metrics", response_model=DashboardMetricsResponse)
        def list_metrics(
            request: Request,
            actor: DashboardReadActor,
            workflow_id: str | None = Query(None),
        ) -> DashboardMetricsResponse:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("DashboardController.metrics"):
                try:
                    logger.info("dashboard.metrics", extra={"request_id": request_id})
                    return self.manager.list_metrics(actor, workflow_id=workflow_id)
                except HTTPException:
                    raise
                except (AuthorizationError, PermissionError) as exc:
                    logger.exception("dashboard.metrics failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
                except ServiceUnavailableError as exc:
                    logger.exception("dashboard.metrics failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
                except (ServiceError, DBException, PersistenceError) as exc:
                    logger.exception("dashboard.metrics failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
                except Exception as exc:
                    logger.exception("dashboard.metrics failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

        @dashboard_router.post("/data", response_model=DashboardDataResponse)
        def get_data(
            request: Request,
            payload: DashboardDataRequest,
            actor: DashboardReadActor,
        ) -> DashboardDataResponse:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("DashboardController.data"):
                try:
                    logger.info(
                        "dashboard.data",
                        extra={"request_id": request_id, "widget_count": len(payload.items)},
                    )
                    return self.manager.get_data_for_actor(
                        actor,
                        payload.items,
                        anchor_entity_id=payload.anchor_entity_id,
                    )
                except HTTPException:
                    raise
                except (AuthorizationError, PermissionError) as exc:
                    logger.exception("dashboard.data failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
                except ServiceUnavailableError as exc:
                    logger.exception("dashboard.data failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
                except (ServiceError, DBException, PersistenceError) as exc:
                    logger.exception("dashboard.data failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
                except Exception as exc:
                    logger.exception("dashboard.data failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

        @dashboard_router.get("/filter-options", response_model=DashboardFilterOptionsResponse)
        def get_filter_options(
            request: Request,
            actor: DashboardReadActor,
            workflow_id: str | None = Query(None),
        ) -> DashboardFilterOptionsResponse:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("DashboardController.filter_options"):
                try:
                    logger.info("dashboard.filter_options", extra={"request_id": request_id})
                    return self.manager.get_filter_options_for_actor(actor, workflow_id=workflow_id)
                except HTTPException:
                    raise
                except (AuthorizationError, PermissionError) as exc:
                    logger.exception("dashboard.filter_options failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
                except ServiceUnavailableError as exc:
                    logger.exception("dashboard.filter_options failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
                except (ServiceError, DBException, PersistenceError) as exc:
                    logger.exception("dashboard.filter_options failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
                except Exception as exc:
                    logger.exception("dashboard.filter_options failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

        @dashboard_router.get("/{key}", response_model=DashboardRead)
        def get_dashboard(
            request: Request,
            key: str,
            actor: DashboardReadActor,
        ) -> DashboardRead:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("DashboardController.get"):
                try:
                    logger.info("dashboard.get", extra={"request_id": request_id, "dashboard_key": key})
                    return self.manager.get_dashboard_for_actor(actor, key)
                except HTTPException as exc:
                    logger.exception(
                        "dashboard.get failed",
                        extra={
                            "request_id": request_id,
                            "dashboard_key": key,
                            "status_code": exc.status_code,
                        },
                    )
                    raise
                except NotFoundError as exc:
                    logger.exception("dashboard.get failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except ValidationError as exc:
                    logger.exception("dashboard.get failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
                except (AuthorizationError, PermissionError) as exc:
                    logger.exception("dashboard.get failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
                except ConflictError as exc:
                    logger.exception("dashboard.get failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
                except (ServiceError, DBException, PersistenceError) as exc:
                    logger.exception("dashboard.get failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
                except Exception as exc:
                    logger.exception("dashboard.get failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

        @dashboard_router.put("/{key}", response_model=DashboardRead)
        def update_dashboard(
            request: Request,
            key: str,
            payload: DashboardUpdateRequest,
            actor: DashboardWriteActor,
        ) -> DashboardRead:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("DashboardController.update"):
                try:
                    logger.info("dashboard.update", extra={"request_id": request_id, "dashboard_key": key})
                    return self.manager.update_dashboard_for_actor(
                        actor,
                        key,
                        config=payload.config,
                        display_name=payload.display_name,
                        description=payload.description,
                    )
                except HTTPException as exc:
                    logger.exception(
                        "dashboard.update failed",
                        extra={
                            "request_id": request_id,
                            "dashboard_key": key,
                            "status_code": exc.status_code,
                        },
                    )
                    raise
                except NotFoundError as exc:
                    logger.exception("dashboard.update failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except ValidationError as exc:
                    logger.exception("dashboard.update failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
                except (AuthorizationError, PermissionError) as exc:
                    logger.exception("dashboard.update failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
                except ConflictError as exc:
                    logger.exception("dashboard.update failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
                except (ServiceError, DBException, PersistenceError) as exc:
                    logger.exception("dashboard.update failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
                except Exception as exc:
                    logger.exception("dashboard.update failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

        app.include_router(dashboard_router, tags=["dashboards"])
