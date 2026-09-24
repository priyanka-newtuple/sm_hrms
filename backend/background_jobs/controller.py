"""Background-jobs REST controller module."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Request, status

from background_jobs.models.request import CreateIntakeJobRequest, UploadIntakeSourceRequest
from background_jobs.models.response import (
    IntakeJobListResponse,
    IntakeJobResponse,
    IntakeOrchestrationStatusResponse,
)
from common.deps import get_db
from common.logger import logger, tracer
from common.utils import raise_http_error

if TYPE_CHECKING:
    from fastapi.params import Depends as DependsParam

    from auth.manager import AuthServiceManager
    from background_jobs.manager import BackgroundJobsServiceManager
    from database.manager import DatabaseServiceManager


class BackgroundJobsRestController:
    """Implements background_jobs REST controller."""

    def __init__(
        self,
        background_jobs_service_manager: BackgroundJobsServiceManager,
        database_service_manager: DatabaseServiceManager | None = None,
        auth_service_manager: AuthServiceManager | None = None,
    ) -> None:
        """Store the service manager; discard unused infrastructure dependencies."""
        _ = database_service_manager, auth_service_manager
        self.manager = background_jobs_service_manager

    @staticmethod
    def _route_dependencies(security: DependsParam | None) -> list[DependsParam] | None:
        """Return a list containing the security dependency, or None if not provided."""
        return [security] if security else None

    @staticmethod
    def _error_context(request_id: str, operation: str) -> dict[str, str]:
        """Build a standard error context dict for raise_http_error."""
        return {
            "request_id": request_id,
            "controller": "BackgroundJobsRestController",
            "operation": operation,
        }

    def prepare(self, app: APIRouter, security: DependsParam | None = None) -> None:
        """Register all background_jobs routes on the given router."""
        route_dependencies = self._route_dependencies(security)

        @app.get(
            "/background_jobs/status",
            status_code=status.HTTP_200_OK,
            tags=["background_jobs"],
            response_model=IntakeOrchestrationStatusResponse,
            dependencies=route_dependencies,
        )
        def status_endpoint(request: Request) -> IntakeOrchestrationStatusResponse:
            """Return the operational status of the background_jobs module."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("BackgroundJobsController.status"):
                try:
                    logger.info(
                        "background_jobs status requested", extra={"request_id": request_id}
                    )
                    return self.manager.get_status()
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "status"))

        @app.post(
            "/background_jobs/intake-jobs",
            status_code=status.HTTP_201_CREATED,
            tags=["background_jobs"],
            response_model=IntakeJobResponse,
            dependencies=route_dependencies,
        )
        def create_job_endpoint(
            request: Request, create_request: CreateIntakeJobRequest
        ) -> IntakeJobResponse:
            """Create a new intake job and return its representation."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("BackgroundJobsController.create_intake_job"):
                try:
                    logger.info(
                        "background_jobs create_intake_job", extra={"request_id": request_id}
                    )
                    return self.manager.create_intake_job(create_request)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "create_intake_job"))

        @app.post(
            "/background_jobs/intake-sources/upload",
            status_code=status.HTTP_201_CREATED,
            tags=["background_jobs"],
            response_model=IntakeJobResponse,
            dependencies=route_dependencies,
        )
        def upload_source_endpoint(
            request: Request, upload_request: UploadIntakeSourceRequest
        ) -> IntakeJobResponse:
            """Upload intake sources and create a corresponding intake job."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("BackgroundJobsController.upload_sources"):
                try:
                    logger.info("background_jobs upload_sources", extra={"request_id": request_id})
                    return self.manager.upload_sources(upload_request)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "upload_sources"))

        @app.get(
            "/background_jobs/intake-jobs/{organization_id}/{job_id}",
            status_code=status.HTTP_200_OK,
            tags=["background_jobs"],
            response_model=IntakeJobResponse,
            dependencies=route_dependencies,
        )
        def get_job_endpoint(
            request: Request, organization_id: str, job_id: str
        ) -> IntakeJobResponse:
            """Retrieve a single intake job by organisation and job id."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("BackgroundJobsController.get_intake_job"):
                try:
                    logger.info("background_jobs get_intake_job", extra={"request_id": request_id})

                    response = self.manager.get_intake_job(
                        organization_id=organization_id,
                        job_id=job_id,
                    )
                    if response is None:
                        raise HTTPException(
                            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
                        )
                    return response
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "get_intake_job"))

        @app.get(
            "/background_jobs/intake-jobs/{organization_id}",
            status_code=status.HTTP_200_OK,
            tags=["background_jobs"],
            response_model=IntakeJobListResponse,
            dependencies=route_dependencies,
        )
        def list_jobs_endpoint(
            request: Request,
            organization_id: str,
            status_filter: str | None = None,
        ) -> IntakeJobListResponse:
            """List all intake jobs for an organisation, with optional status filter."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("BackgroundJobsController.list_intake_jobs"):
                try:
                    logger.info(
                        "background_jobs list_intake_jobs", extra={"request_id": request_id}
                    )
                    return self.manager.list_intake_jobs(
                        organization_id=organization_id,
                        status=status_filter,
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "list_intake_jobs"))
