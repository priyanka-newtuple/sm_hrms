"""Views REST controller module."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

try:
    from common.auth import require_permission
    from common.logger import logger, tracer
except ImportError:  # pragma: no cover - package import fallback
    from backend.modular_backend.common.auth import require_permission
    from backend.modular_backend.common.logger import logger, tracer

from views.models.request import HeatmapRefreshRequest, PipelineListRequest, UpsertPipelineProjectionRequest
from views.models.response import (
    FunnelUsageResponse,
    HeatmapRefreshResponse,
    PipelineProjectionListResponse,
    PipelineProjectionResponse,
    ProjectionsStatusResponse,
)
from views.manager import ViewsServiceManager


try:
    from exceptions import (
        AuthorizationError,
        ConflictError,
        DBException,
        NotFoundError,
        PersistenceError,
        RecordNotFoundException,
        ServiceError,
        ValidationError,
    )
except ImportError:  # pragma: no cover - package import fallback
    from backend.modular_backend.exceptions import (
        AuthorizationError,
        ConflictError,
        DBException,
        NotFoundError,
        PersistenceError,
        RecordNotFoundException,
        ServiceError,
        ValidationError,
    )

ViewReadActor = Annotated[dict[str, object], Depends(require_permission("projection", "read"))]
ViewWriteActor = Annotated[dict[str, object], Depends(require_permission("projection", "write"))]


class ViewsRestController:
    """Implements views REST controller."""

    def __init__(
        self,
        views_service_manager: ViewsServiceManager,
        database_service_manager=None,
        auth_service_manager=None,
    ) -> None:  # noqa: ANN001
        super().__init__()
        self.views_service_manager = views_service_manager
        self.manager = views_service_manager
        self.database_service_manager = database_service_manager
        self.current_db = (
            database_service_manager.postgres_db_service()
            if database_service_manager and hasattr(database_service_manager, "postgres_db_service")
            else None
        )
        self.current_db_engine = getattr(self.current_db, "engine", None)
        self.auth_service_manager = auth_service_manager

    @staticmethod
    def _route_dependencies(security: Depends | None) -> list[Depends] | None:
        return [security] if security else None

    def prepare(self, app: APIRouter, security: Depends | None = None) -> None:
        """Prepare the views REST controller."""
        route_dependencies = self._route_dependencies(security)

        @app.get(
            "/views/status",
            status_code=status.HTTP_200_OK,
            tags=["views"],
            response_model=ProjectionsStatusResponse,
            dependencies=route_dependencies,
        )
        def status_endpoint(request: Request):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("ViewsController.status"):
                try:
                    logger.info("views status requested", extra={"request_id": request_id})
                    return self.views_service_manager.get_status()
                except HTTPException:

                    raise

                except RecordNotFoundException as exc:  # noqa: BLE001
                    logger.exception("views status failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except NotFoundError as exc:  # noqa: BLE001
                    logger.exception("views status failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except (ValidationError, ValueError) as exc:  # noqa: BLE001
                    logger.exception("views status failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
                except (AuthorizationError, PermissionError) as exc:  # noqa: BLE001
                    logger.exception("views status failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
                except ConflictError as exc:  # noqa: BLE001
                    logger.exception("views status failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
                except (DBException, PersistenceError, ServiceError) as exc:  # noqa: BLE001
                    logger.exception("views status failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
                except Exception as exc:  # noqa: BLE001
                    logger.exception("views status failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

        @app.get(
            "/projections/status",
            status_code=status.HTTP_200_OK,
            tags=["projections"],
            response_model=ProjectionsStatusResponse,
            dependencies=route_dependencies,
        )
        def legacy_status_endpoint(request: Request):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("ViewsController.legacy_status"):
                try:
                    logger.info("projections status requested", extra={"request_id": request_id})
                    return self.views_service_manager.get_status()
                except HTTPException:

                    raise

                except RecordNotFoundException as exc:  # noqa: BLE001
                    logger.exception("projections status failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except NotFoundError as exc:  # noqa: BLE001
                    logger.exception("projections status failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except (ValidationError, ValueError) as exc:  # noqa: BLE001
                    logger.exception("projections status failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
                except (AuthorizationError, PermissionError) as exc:  # noqa: BLE001
                    logger.exception("projections status failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
                except ConflictError as exc:  # noqa: BLE001
                    logger.exception("projections status failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
                except (DBException, PersistenceError, ServiceError) as exc:  # noqa: BLE001
                    logger.exception("projections status failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
                except Exception as exc:  # noqa: BLE001
                    logger.exception("projections status failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

        @app.post(
            "/views/lifecycle-projections",
            status_code=status.HTTP_200_OK,
            tags=["views"],
            response_model=PipelineProjectionResponse,
            dependencies=route_dependencies,
        )
        def upsert_projection_endpoint(
            request: Request,
            upsert_request: UpsertPipelineProjectionRequest,
            actor: ViewWriteActor,
        ):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("ViewsController.upsert_lifecycle_projection"):
                try:
                    logger.info("views upsert_lifecycle_projection", extra={"request_id": request_id})
                    return self.views_service_manager.upsert_lifecycle_projection_for_actor(actor, upsert_request)
                except HTTPException:
                    raise

                except RecordNotFoundException as exc:  # noqa: BLE001
                    logger.exception("views upsert_lifecycle_projection failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except NotFoundError as exc:  # noqa: BLE001
                    logger.exception("views upsert_lifecycle_projection failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except (ValidationError, ValueError) as exc:  # noqa: BLE001
                    logger.exception("views upsert_lifecycle_projection failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
                except (AuthorizationError, PermissionError) as exc:  # noqa: BLE001
                    logger.exception("views upsert_lifecycle_projection failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
                except ConflictError as exc:  # noqa: BLE001
                    logger.exception("views upsert_lifecycle_projection failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
                except (DBException, PersistenceError, ServiceError) as exc:  # noqa: BLE001
                    logger.exception("views upsert_lifecycle_projection failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
                except Exception as exc:  # noqa: BLE001
                    logger.exception("views upsert_lifecycle_projection failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

        @app.post(
            "/projections/lifecycle-projections",
            status_code=status.HTTP_200_OK,
            tags=["projections"],
            response_model=PipelineProjectionResponse,
            dependencies=route_dependencies,
        )
        def canonical_upsert_projection_endpoint(
            request: Request,
            upsert_request: UpsertPipelineProjectionRequest,
            actor: ViewWriteActor,
        ):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("ViewsController.canonical_upsert_lifecycle_projection"):
                try:
                    logger.info("projections canonical upsert_lifecycle_projection", extra={"request_id": request_id})
                    return self.views_service_manager.upsert_lifecycle_projection_for_actor(actor, upsert_request)
                except HTTPException:
                    raise

                except RecordNotFoundException as exc:  # noqa: BLE001
                    logger.exception("projections canonical upsert_lifecycle_projection failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except NotFoundError as exc:  # noqa: BLE001
                    logger.exception("projections canonical upsert_lifecycle_projection failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except (ValidationError, ValueError) as exc:  # noqa: BLE001
                    logger.exception("projections canonical upsert_lifecycle_projection failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
                except (AuthorizationError, PermissionError) as exc:  # noqa: BLE001
                    logger.exception("projections canonical upsert_lifecycle_projection failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
                except ConflictError as exc:  # noqa: BLE001
                    logger.exception("projections canonical upsert_lifecycle_projection failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
                except (DBException, PersistenceError, ServiceError) as exc:  # noqa: BLE001
                    logger.exception("projections canonical upsert_lifecycle_projection failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
                except Exception as exc:  # noqa: BLE001
                    logger.exception("projections canonical upsert_lifecycle_projection failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

        @app.post(
            "/projections/pipeline",
            status_code=status.HTTP_200_OK,
            tags=["projections"],
            response_model=PipelineProjectionResponse,
            dependencies=route_dependencies,
        )
        def legacy_upsert_pipeline_endpoint(
            request: Request,
            upsert_request: UpsertPipelineProjectionRequest,
            actor: ViewWriteActor,
        ):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("ViewsController.legacy_upsert_pipeline"):
                try:
                    logger.info("projections upsert_pipeline", extra={"request_id": request_id})
                    return self.views_service_manager.upsert_lifecycle_projection_for_actor(actor, upsert_request)
                except HTTPException:
                    raise

                except RecordNotFoundException as exc:  # noqa: BLE001
                    logger.exception("projections upsert_pipeline failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except NotFoundError as exc:  # noqa: BLE001
                    logger.exception("projections upsert_pipeline failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except (ValidationError, ValueError) as exc:  # noqa: BLE001
                    logger.exception("projections upsert_pipeline failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
                except (AuthorizationError, PermissionError) as exc:  # noqa: BLE001
                    logger.exception("projections upsert_pipeline failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
                except ConflictError as exc:  # noqa: BLE001
                    logger.exception("projections upsert_pipeline failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
                except (DBException, PersistenceError, ServiceError) as exc:  # noqa: BLE001
                    logger.exception("projections upsert_pipeline failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
                except Exception as exc:  # noqa: BLE001
                    logger.exception("projections upsert_pipeline failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

        @app.post(
            "/views/lifecycle-projections/list",
            status_code=status.HTTP_200_OK,
            tags=["views"],
            response_model=PipelineProjectionListResponse,
            dependencies=route_dependencies,
        )
        def list_projections_endpoint(
            request: Request,
            list_request: PipelineListRequest,
            actor: ViewReadActor,
        ):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("ViewsController.list_lifecycle_projections"):
                try:
                    logger.info("views list_lifecycle_projections", extra={"request_id": request_id})
                    return self.views_service_manager.list_lifecycle_projections_for_actor(actor, list_request)
                except HTTPException:
                    raise

                except RecordNotFoundException as exc:  # noqa: BLE001
                    logger.exception("views list_lifecycle_projections failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except NotFoundError as exc:  # noqa: BLE001
                    logger.exception("views list_lifecycle_projections failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except (ValidationError, ValueError) as exc:  # noqa: BLE001
                    logger.exception("views list_lifecycle_projections failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
                except (AuthorizationError, PermissionError) as exc:  # noqa: BLE001
                    logger.exception("views list_lifecycle_projections failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
                except ConflictError as exc:  # noqa: BLE001
                    logger.exception("views list_lifecycle_projections failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
                except (DBException, PersistenceError, ServiceError) as exc:  # noqa: BLE001
                    logger.exception("views list_lifecycle_projections failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
                except Exception as exc:  # noqa: BLE001
                    logger.exception("views list_lifecycle_projections failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

        @app.post(
            "/projections/lifecycle-projections/list",
            status_code=status.HTTP_200_OK,
            tags=["projections"],
            response_model=PipelineProjectionListResponse,
            dependencies=route_dependencies,
        )
        def canonical_list_projections_endpoint(
            request: Request,
            list_request: PipelineListRequest,
            actor: ViewReadActor,
        ):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("ViewsController.canonical_list_lifecycle_projections"):
                try:
                    logger.info("projections canonical list_lifecycle_projections", extra={"request_id": request_id})
                    return self.views_service_manager.list_lifecycle_projections_for_actor(actor, list_request)
                except HTTPException:
                    raise

                except RecordNotFoundException as exc:  # noqa: BLE001
                    logger.exception("projections canonical list_lifecycle_projections failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except NotFoundError as exc:  # noqa: BLE001
                    logger.exception("projections canonical list_lifecycle_projections failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except (ValidationError, ValueError) as exc:  # noqa: BLE001
                    logger.exception("projections canonical list_lifecycle_projections failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
                except (AuthorizationError, PermissionError) as exc:  # noqa: BLE001
                    logger.exception("projections canonical list_lifecycle_projections failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
                except ConflictError as exc:  # noqa: BLE001
                    logger.exception("projections canonical list_lifecycle_projections failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
                except (DBException, PersistenceError, ServiceError) as exc:  # noqa: BLE001
                    logger.exception("projections canonical list_lifecycle_projections failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
                except Exception as exc:  # noqa: BLE001
                    logger.exception("projections canonical list_lifecycle_projections failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

        @app.post(
            "/projections/pipeline/list",
            status_code=status.HTTP_200_OK,
            tags=["projections"],
            response_model=PipelineProjectionListResponse,
            dependencies=route_dependencies,
        )
        def legacy_list_pipeline_endpoint(
            request: Request,
            list_request: PipelineListRequest,
            actor: ViewReadActor,
        ):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("ViewsController.legacy_list_pipeline"):
                try:
                    logger.info("projections list_pipeline", extra={"request_id": request_id})
                    return self.views_service_manager.list_lifecycle_projections_for_actor(actor, list_request)
                except HTTPException:
                    raise

                except RecordNotFoundException as exc:  # noqa: BLE001
                    logger.exception("projections list_pipeline failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except NotFoundError as exc:  # noqa: BLE001
                    logger.exception("projections list_pipeline failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except (ValidationError, ValueError) as exc:  # noqa: BLE001
                    logger.exception("projections list_pipeline failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
                except (AuthorizationError, PermissionError) as exc:  # noqa: BLE001
                    logger.exception("projections list_pipeline failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
                except ConflictError as exc:  # noqa: BLE001
                    logger.exception("projections list_pipeline failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
                except (DBException, PersistenceError, ServiceError) as exc:  # noqa: BLE001
                    logger.exception("projections list_pipeline failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
                except Exception as exc:  # noqa: BLE001
                    logger.exception("projections list_pipeline failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

        @app.get(
            "/views/lifecycle-projections/{organization_id}/{subject_entity_id}",
            status_code=status.HTTP_200_OK,
            tags=["views"],
            response_model=PipelineProjectionResponse,
            dependencies=route_dependencies,
        )
        def get_projection_endpoint(
            request: Request,
            organization_id: str,
            subject_entity_id: str,
            actor: ViewReadActor,
        ):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("ViewsController.get_lifecycle_projection"):
                try:
                    logger.info("views get_lifecycle_projection", extra={"request_id": request_id})
                    return self.views_service_manager.get_lifecycle_projection_for_actor(
                        actor, organization_id, subject_entity_id
                    )
                except HTTPException:
                    raise

                except RecordNotFoundException as exc:  # noqa: BLE001
                    logger.exception("views get_lifecycle_projection failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except NotFoundError as exc:  # noqa: BLE001
                    logger.exception("views get_lifecycle_projection failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except (ValidationError, ValueError) as exc:  # noqa: BLE001
                    logger.exception("views get_lifecycle_projection failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
                except (AuthorizationError, PermissionError) as exc:  # noqa: BLE001
                    logger.exception("views get_lifecycle_projection failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
                except ConflictError as exc:  # noqa: BLE001
                    logger.exception("views get_lifecycle_projection failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
                except (DBException, PersistenceError, ServiceError) as exc:  # noqa: BLE001
                    logger.exception("views get_lifecycle_projection failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
                except Exception as exc:  # noqa: BLE001
                    logger.exception("views get_lifecycle_projection failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

        @app.get(
            "/projections/lifecycle-projections/{organization_id}/{subject_entity_id}",
            status_code=status.HTTP_200_OK,
            tags=["projections"],
            response_model=PipelineProjectionResponse,
            dependencies=route_dependencies,
        )
        def canonical_get_projection_endpoint(
            request: Request,
            organization_id: str,
            subject_entity_id: str,
            actor: ViewReadActor,
        ):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("ViewsController.canonical_get_lifecycle_projection"):
                try:
                    logger.info("projections canonical get_lifecycle_projection", extra={"request_id": request_id})
                    return self.views_service_manager.get_lifecycle_projection_for_actor(
                        actor, organization_id, subject_entity_id
                    )
                except HTTPException:
                    raise

                except RecordNotFoundException as exc:  # noqa: BLE001
                    logger.exception("projections canonical get_lifecycle_projection failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except NotFoundError as exc:  # noqa: BLE001
                    logger.exception("projections canonical get_lifecycle_projection failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except (ValidationError, ValueError) as exc:  # noqa: BLE001
                    logger.exception("projections canonical get_lifecycle_projection failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
                except (AuthorizationError, PermissionError) as exc:  # noqa: BLE001
                    logger.exception("projections canonical get_lifecycle_projection failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
                except ConflictError as exc:  # noqa: BLE001
                    logger.exception("projections canonical get_lifecycle_projection failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
                except (DBException, PersistenceError, ServiceError) as exc:  # noqa: BLE001
                    logger.exception("projections canonical get_lifecycle_projection failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
                except Exception as exc:  # noqa: BLE001
                    logger.exception("projections canonical get_lifecycle_projection failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

        @app.get(
            "/projections/pipeline/{organization_id}/{application_id}",
            status_code=status.HTTP_200_OK,
            tags=["projections"],
            response_model=PipelineProjectionResponse,
            dependencies=route_dependencies,
        )
        def legacy_get_pipeline_endpoint(
            request: Request,
            organization_id: str,
            application_id: str,
            actor: ViewReadActor,
        ):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("ViewsController.legacy_get_pipeline"):
                try:
                    logger.info("projections get_pipeline", extra={"request_id": request_id})
                    return self.views_service_manager.get_lifecycle_projection_for_actor(
                        actor, organization_id, application_id
                    )
                except HTTPException:
                    raise

                except RecordNotFoundException as exc:  # noqa: BLE001
                    logger.exception("projections get_pipeline failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except NotFoundError as exc:  # noqa: BLE001
                    logger.exception("projections get_pipeline failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except (ValidationError, ValueError) as exc:  # noqa: BLE001
                    logger.exception("projections get_pipeline failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
                except (AuthorizationError, PermissionError) as exc:  # noqa: BLE001
                    logger.exception("projections get_pipeline failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
                except ConflictError as exc:  # noqa: BLE001
                    logger.exception("projections get_pipeline failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
                except (DBException, PersistenceError, ServiceError) as exc:  # noqa: BLE001
                    logger.exception("projections get_pipeline failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
                except Exception as exc:  # noqa: BLE001
                    logger.exception("projections get_pipeline failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

        @app.post(
            "/views/lifecycle-usage",
            status_code=status.HTTP_200_OK,
            tags=["views"],
            response_model=FunnelUsageResponse,
            dependencies=route_dependencies,
        )
        def list_usage_endpoint(
            request: Request,
            list_request: PipelineListRequest,
            actor: ViewReadActor,
        ):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("ViewsController.list_lifecycle_usage"):
                try:
                    logger.info("views list_lifecycle_usage", extra={"request_id": request_id})
                    return self.views_service_manager.list_lifecycle_usage_for_actor(actor, list_request)
                except HTTPException:
                    raise

                except RecordNotFoundException as exc:  # noqa: BLE001
                    logger.exception("views list_lifecycle_usage failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except NotFoundError as exc:  # noqa: BLE001
                    logger.exception("views list_lifecycle_usage failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except (ValidationError, ValueError) as exc:  # noqa: BLE001
                    logger.exception("views list_lifecycle_usage failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
                except (AuthorizationError, PermissionError) as exc:  # noqa: BLE001
                    logger.exception("views list_lifecycle_usage failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
                except ConflictError as exc:  # noqa: BLE001
                    logger.exception("views list_lifecycle_usage failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
                except (DBException, PersistenceError, ServiceError) as exc:  # noqa: BLE001
                    logger.exception("views list_lifecycle_usage failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
                except Exception as exc:  # noqa: BLE001
                    logger.exception("views list_lifecycle_usage failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

        @app.post(
            "/projections/lifecycle-usage",
            status_code=status.HTTP_200_OK,
            tags=["projections"],
            response_model=FunnelUsageResponse,
            dependencies=route_dependencies,
        )
        def canonical_list_usage_endpoint(
            request: Request,
            list_request: PipelineListRequest,
            actor: ViewReadActor,
        ):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("ViewsController.canonical_list_lifecycle_usage"):
                try:
                    logger.info("projections canonical list_lifecycle_usage", extra={"request_id": request_id})
                    return self.views_service_manager.list_lifecycle_usage_for_actor(actor, list_request)
                except HTTPException:
                    raise

                except RecordNotFoundException as exc:  # noqa: BLE001
                    logger.exception("projections canonical list_lifecycle_usage failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except NotFoundError as exc:  # noqa: BLE001
                    logger.exception("projections canonical list_lifecycle_usage failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except (ValidationError, ValueError) as exc:  # noqa: BLE001
                    logger.exception("projections canonical list_lifecycle_usage failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
                except (AuthorizationError, PermissionError) as exc:  # noqa: BLE001
                    logger.exception("projections canonical list_lifecycle_usage failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
                except ConflictError as exc:  # noqa: BLE001
                    logger.exception("projections canonical list_lifecycle_usage failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
                except (DBException, PersistenceError, ServiceError) as exc:  # noqa: BLE001
                    logger.exception("projections canonical list_lifecycle_usage failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
                except Exception as exc:  # noqa: BLE001
                    logger.exception("projections canonical list_lifecycle_usage failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

        @app.post(
            "/projections/pipeline-funnels",
            status_code=status.HTTP_200_OK,
            tags=["projections"],
            response_model=FunnelUsageResponse,
            dependencies=route_dependencies,
        )
        def legacy_list_funnels_endpoint(
            request: Request,
            list_request: PipelineListRequest,
            actor: ViewReadActor,
        ):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("ViewsController.legacy_list_funnels"):
                try:
                    logger.info("projections list_funnels", extra={"request_id": request_id})
                    return self.views_service_manager.list_lifecycle_usage_for_actor(actor, list_request)
                except HTTPException:
                    raise

                except RecordNotFoundException as exc:  # noqa: BLE001
                    logger.exception("projections list_funnels failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except NotFoundError as exc:  # noqa: BLE001
                    logger.exception("projections list_funnels failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except (ValidationError, ValueError) as exc:  # noqa: BLE001
                    logger.exception("projections list_funnels failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
                except (AuthorizationError, PermissionError) as exc:  # noqa: BLE001
                    logger.exception("projections list_funnels failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
                except ConflictError as exc:  # noqa: BLE001
                    logger.exception("projections list_funnels failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
                except (DBException, PersistenceError, ServiceError) as exc:  # noqa: BLE001
                    logger.exception("projections list_funnels failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
                except Exception as exc:  # noqa: BLE001
                    logger.exception("projections list_funnels failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

        @app.post(
            "/views/lifecycle-heatmap/refresh",
            status_code=status.HTTP_200_OK,
            tags=["views"],
            response_model=HeatmapRefreshResponse,
            dependencies=route_dependencies,
        )
        def refresh_heatmap_endpoint(
            request: Request,
            refresh_request: HeatmapRefreshRequest,
            actor: ViewWriteActor,
        ):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("ViewsController.refresh_lifecycle_heatmap"):
                try:
                    logger.info("views refresh_lifecycle_heatmap", extra={"request_id": request_id})
                    return self.views_service_manager.refresh_lifecycle_heatmap_for_actor(actor, refresh_request)
                except HTTPException:
                    raise

                except RecordNotFoundException as exc:  # noqa: BLE001
                    logger.exception("views refresh_lifecycle_heatmap failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except NotFoundError as exc:  # noqa: BLE001
                    logger.exception("views refresh_lifecycle_heatmap failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except (ValidationError, ValueError) as exc:  # noqa: BLE001
                    logger.exception("views refresh_lifecycle_heatmap failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
                except (AuthorizationError, PermissionError) as exc:  # noqa: BLE001
                    logger.exception("views refresh_lifecycle_heatmap failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
                except ConflictError as exc:  # noqa: BLE001
                    logger.exception("views refresh_lifecycle_heatmap failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
                except (DBException, PersistenceError, ServiceError) as exc:  # noqa: BLE001
                    logger.exception("views refresh_lifecycle_heatmap failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
                except Exception as exc:  # noqa: BLE001
                    logger.exception("views refresh_lifecycle_heatmap failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

        @app.post(
            "/projections/lifecycle-heatmap/refresh",
            status_code=status.HTTP_200_OK,
            tags=["projections"],
            response_model=HeatmapRefreshResponse,
            dependencies=route_dependencies,
        )
        def canonical_refresh_heatmap_endpoint(
            request: Request,
            refresh_request: HeatmapRefreshRequest,
            actor: ViewWriteActor,
        ):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("ViewsController.canonical_refresh_lifecycle_heatmap"):
                try:
                    logger.info("projections canonical refresh_lifecycle_heatmap", extra={"request_id": request_id})
                    return self.views_service_manager.refresh_lifecycle_heatmap_for_actor(actor, refresh_request)
                except HTTPException:
                    raise

                except RecordNotFoundException as exc:  # noqa: BLE001
                    logger.exception("projections canonical refresh_lifecycle_heatmap failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except NotFoundError as exc:  # noqa: BLE001
                    logger.exception("projections canonical refresh_lifecycle_heatmap failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except (ValidationError, ValueError) as exc:  # noqa: BLE001
                    logger.exception("projections canonical refresh_lifecycle_heatmap failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
                except (AuthorizationError, PermissionError) as exc:  # noqa: BLE001
                    logger.exception("projections canonical refresh_lifecycle_heatmap failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
                except ConflictError as exc:  # noqa: BLE001
                    logger.exception("projections canonical refresh_lifecycle_heatmap failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
                except (DBException, PersistenceError, ServiceError) as exc:  # noqa: BLE001
                    logger.exception("projections canonical refresh_lifecycle_heatmap failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
                except Exception as exc:  # noqa: BLE001
                    logger.exception("projections canonical refresh_lifecycle_heatmap failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

        @app.post(
            "/projections/heatmap/refresh",
            status_code=status.HTTP_200_OK,
            tags=["projections"],
            response_model=HeatmapRefreshResponse,
            dependencies=route_dependencies,
        )
        def legacy_refresh_heatmap_endpoint(
            request: Request,
            refresh_request: HeatmapRefreshRequest,
            actor: ViewWriteActor,
        ):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("ViewsController.legacy_refresh_heatmap"):
                try:
                    logger.info("projections refresh_heatmap", extra={"request_id": request_id})
                    return self.views_service_manager.refresh_lifecycle_heatmap_for_actor(actor, refresh_request)
                except HTTPException:
                    raise

                except RecordNotFoundException as exc:  # noqa: BLE001
                    logger.exception("projections refresh_heatmap failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except NotFoundError as exc:  # noqa: BLE001
                    logger.exception("projections refresh_heatmap failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except (ValidationError, ValueError) as exc:  # noqa: BLE001
                    logger.exception("projections refresh_heatmap failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
                except (AuthorizationError, PermissionError) as exc:  # noqa: BLE001
                    logger.exception("projections refresh_heatmap failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
                except ConflictError as exc:  # noqa: BLE001
                    logger.exception("projections refresh_heatmap failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
                except (DBException, PersistenceError, ServiceError) as exc:  # noqa: BLE001
                    logger.exception("projections refresh_heatmap failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
                except Exception as exc:  # noqa: BLE001
                    logger.exception("projections refresh_heatmap failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")
