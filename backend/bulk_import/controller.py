"""REST surface for the bulk import review lifecycle."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, Header, Request, UploadFile, status

from bulk_import.models import (
    DEFAULT_UPLOAD_CONTENT_TYPE,
    FALLBACK_UPLOAD_PREFIX,
    MAX_BULK_IMPORT_FILES,
    BulkImportFixedRelationBinding,
    BulkImportJobListResponse,
    BulkImportJobResponse,
    BulkImportReviewRequest,
    BulkImportSpreadsheetMappingRequest,
)
from common.auth import require_permission
from common.utils import raise_http_error
from exceptions import ValidationError

if TYPE_CHECKING:
    from fastapi.params import Depends as DependsParam

    from bulk_import.manager import BulkImportServiceManager

BulkImportActor = Annotated[dict[str, object], Depends(require_permission("file", "write"))]


def _upload_filename(filename: str | None) -> str:
    """Return the supplied filename or a unique name for unnamed uploads."""
    return filename or f"{FALLBACK_UPLOAD_PREFIX}_{uuid4().hex[:8]}"


def _fixed_relation_bindings(value: str | None) -> list[BulkImportFixedRelationBinding]:
    """Parse the multipart JSON field into validated fixed parent choices."""
    try:
        payload = json.loads(value or "[]")
        if not isinstance(payload, list):
            raise ValueError("must be a list")
        return [BulkImportFixedRelationBinding.model_validate(item) for item in payload]
    except Exception as exc:
        raise ValidationError("fixed_relation_bindings must be a valid JSON list") from exc


class BulkImportRestController:
    """REST endpoints for the bulk import upload, review, and commit lifecycle."""

    def __init__(self, manager: BulkImportServiceManager) -> None:
        """Store the bulk import service manager the routes delegate to."""
        self.manager = manager

    @staticmethod
    def _error_context(request: Request, operation: str) -> dict[str, str]:
        """Build structured logging context for a failed controller operation."""
        return {
            "request_id": getattr(request.state, "request_id", "unknown"),
            "controller": "BulkImportRestController",
            "operation": operation,
        }

    def prepare(self, app: APIRouter, security: DependsParam | None = None) -> None:
        """Register the bulk import routes on the given router."""
        dependencies = [security] if security else None
        entity_write = Depends(require_permission("entity_record", "write"))
        bulk_dependencies = [*(dependencies or []), entity_write]
        self._register_create_job(app, bulk_dependencies)
        self._register_list_jobs(app, bulk_dependencies)
        self._register_get_job(app, bulk_dependencies)
        self._register_analyze(app, bulk_dependencies)
        self._register_review(app, bulk_dependencies)
        self._register_spreadsheet_mapping(app, bulk_dependencies)
        self._register_commit(app, bulk_dependencies)
        self._register_cancel(app, bulk_dependencies)
        self._register_resume(app, bulk_dependencies)

    def _register_create_job(self, app: APIRouter, bulk_dependencies: list) -> None:
        """Register the upload-and-create-job endpoint."""

        @app.post(
            "/bulk-import/jobs",
            status_code=status.HTTP_201_CREATED,
            response_model=BulkImportJobResponse,
            tags=["bulk-import"],
            dependencies=bulk_dependencies,
        )
        async def create_job(
            request: Request,
            actor: BulkImportActor,
            entity_type_id: Annotated[str, Form(min_length=1)],
            files: Annotated[list[UploadFile], File()],
            workflow_name: Annotated[str | None, Form()] = None,
            fixed_relation_bindings: Annotated[str | None, Form()] = None,
        ) -> BulkImportJobResponse:
            """Upload source files and create a new bulk import job."""
            try:
                if not files or len(files) > MAX_BULK_IMPORT_FILES:
                    raise ValueError(f"upload between 1 and {MAX_BULK_IMPORT_FILES} files")
                parsed_fixed_bindings = _fixed_relation_bindings(fixed_relation_bindings)
                stored: list[dict[str, object]] = []
                for upload in files:
                    stored.append(
                        self.manager.store_file(
                            dict(actor),
                            filename=_upload_filename(upload.filename),
                            content_type=upload.content_type or DEFAULT_UPLOAD_CONTENT_TYPE,
                            content=await upload.read(),
                        )
                    )
                return self.manager.create_job(
                    dict(actor),
                    entity_type_id=entity_type_id,
                    workflow_name=workflow_name,
                    files=stored,
                    fixed_relation_bindings=parsed_fixed_bindings,
                )
            except Exception as exc:
                raise_http_error(exc, self._error_context(request, "create"))

    def _register_list_jobs(self, app: APIRouter, bulk_dependencies: list) -> None:
        """Register the recent-imports list endpoint."""

        @app.get(
            "/bulk-import/jobs",
            response_model=BulkImportJobListResponse,
            tags=["bulk-import"],
            dependencies=bulk_dependencies,
        )
        def list_jobs(request: Request, actor: BulkImportActor) -> BulkImportJobListResponse:
            """List the caller's organization's recent bulk import jobs, newest first."""
            try:
                return self.manager.list_jobs(dict(actor))
            except Exception as exc:
                raise_http_error(exc, self._error_context(request, "list"))

    def _register_get_job(self, app: APIRouter, bulk_dependencies: list) -> None:
        """Register the fetch-job endpoint."""

        @app.get(
            "/bulk-import/jobs/{job_id}",
            response_model=BulkImportJobResponse,
            tags=["bulk-import"],
            dependencies=bulk_dependencies,
        )
        def get_job(request: Request, actor: BulkImportActor, job_id: str) -> BulkImportJobResponse:
            """Fetch a bulk import job's current state."""
            try:
                return self.manager.get_job(dict(actor), job_id)
            except Exception as exc:
                raise_http_error(exc, self._error_context(request, "get"))

    def _register_analyze(self, app: APIRouter, bulk_dependencies: list) -> None:
        """Register the analyze endpoint."""

        @app.post(
            "/bulk-import/jobs/{job_id}/analyze",
            response_model=BulkImportJobResponse,
            tags=["bulk-import"],
            dependencies=bulk_dependencies,
        )
        def analyze(request: Request, actor: BulkImportActor, job_id: str) -> BulkImportJobResponse:
            """Run extraction over the job's uploaded files and propose entity drafts."""
            try:
                return self.manager.analyze(dict(actor), job_id)
            except Exception as exc:
                raise_http_error(exc, self._error_context(request, "analyze"))

    def _register_review(self, app: APIRouter, bulk_dependencies: list) -> None:
        """Register the review endpoint."""

        @app.put(
            "/bulk-import/jobs/{job_id}/review",
            response_model=BulkImportJobResponse,
            tags=["bulk-import"],
            dependencies=bulk_dependencies,
        )
        def review(
            request: Request,
            actor: BulkImportActor,
            job_id: str,
            payload: BulkImportReviewRequest,
        ) -> BulkImportJobResponse:
            """Apply reviewer edits to proposed drafts before commit."""
            try:
                return self.manager.update_review(dict(actor), job_id, payload)
            except Exception as exc:
                raise_http_error(exc, self._error_context(request, "review"))

    def _register_commit(self, app: APIRouter, bulk_dependencies: list) -> None:
        """Register the commit endpoint."""

        @app.post(
            "/bulk-import/jobs/{job_id}/commit",
            response_model=BulkImportJobResponse,
            tags=["bulk-import"],
            dependencies=bulk_dependencies,
        )
        def commit(
            request: Request,
            actor: BulkImportActor,
            job_id: str,
            idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
        ) -> BulkImportJobResponse:
            """Create or match entities for selected drafts, attach files, and enroll workflows."""
            try:
                return self.manager.commit(dict(actor), job_id, idempotency_key)
            except Exception as exc:
                raise_http_error(exc, self._error_context(request, "commit"))

    def _register_cancel(self, app: APIRouter, bulk_dependencies: list) -> None:
        """Register cooperative cancellation for queued and running jobs."""

        @app.post(
            "/bulk-import/jobs/{job_id}/cancel",
            response_model=BulkImportJobResponse,
            tags=["bulk-import"],
            dependencies=bulk_dependencies,
        )
        def cancel(request: Request, actor: BulkImportActor, job_id: str) -> BulkImportJobResponse:
            try:
                return self.manager.cancel(dict(actor), job_id)
            except Exception as exc:
                raise_http_error(exc, self._error_context(request, "cancel"))

    def _register_resume(self, app: APIRouter, bulk_dependencies: list) -> None:
        """Register resumption from a cancelled job's durable progress."""

        @app.post(
            "/bulk-import/jobs/{job_id}/resume",
            response_model=BulkImportJobResponse,
            tags=["bulk-import"],
            dependencies=bulk_dependencies,
        )
        def resume(request: Request, actor: BulkImportActor, job_id: str) -> BulkImportJobResponse:
            try:
                return self.manager.resume(dict(actor), job_id)
            except Exception as exc:
                raise_http_error(exc, self._error_context(request, "resume"))

    def _register_spreadsheet_mapping(self, app: APIRouter, bulk_dependencies: list) -> None:
        """Register deterministic spreadsheet remapping and draft regeneration."""

        @app.put(
            "/bulk-import/jobs/{job_id}/spreadsheet-mapping",
            response_model=BulkImportJobResponse,
            tags=["bulk-import"],
            dependencies=bulk_dependencies,
        )
        def update_spreadsheet_mapping(
            request: Request,
            actor: BulkImportActor,
            job_id: str,
            payload: BulkImportSpreadsheetMappingRequest,
        ) -> BulkImportJobResponse:
            try:
                return self.manager.update_spreadsheet_mapping(dict(actor), job_id, payload)
            except Exception as exc:
                raise_http_error(exc, self._error_context(request, "spreadsheet_mapping"))
