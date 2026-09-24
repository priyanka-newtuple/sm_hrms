"""REST controller for filehandler module."""

from __future__ import annotations

import base64
import json
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile, status

from common.auth import actor_str, require_permission
from common.logger import logger, tracer
from common.utils import raise_http_error
from exceptions import NotFoundError
from filehandler.models.request import (
    FileListRequest,
    FileTypeCreateRequest,
    FileTypeUpdateRequest,
    FileUploadRequest,
)
from filehandler.models.response import (
    DownloadUrlResponse,
    FilehandlerStatusResponse,
    FileListResponse,
    FileRecordResponse,
    FileTypeListResponse,
    FileTypeResponse,
    FileTypeSeedResponse,
)

if TYPE_CHECKING:
    from fastapi.params import Depends as DependsParam

    from auth.manager import AuthServiceManager
    from database.manager import DatabaseServiceManager
    from filehandler.manager import FilehandlerServiceManager

FileReadActor = Annotated[dict[str, object], Depends(require_permission("file", "read"))]
FileWriteActor = Annotated[dict[str, object], Depends(require_permission("file", "write"))]


class FilehandlerRestController:
    """Implements filehandler REST controller."""

    def __init__(
        self,
        filehandler_service_manager: FilehandlerServiceManager,
        database_service_manager: DatabaseServiceManager | None = None,
        auth_service_manager: AuthServiceManager | None = None,
        *args: object,
    ) -> None:
        self.manager = filehandler_service_manager
        _ = database_service_manager, auth_service_manager

    @staticmethod
    def _route_dependencies(security: DependsParam | None) -> list[DependsParam] | None:
        return [security] if security else None

    @staticmethod
    def _error_context(request_id: str, operation: str) -> dict[str, str]:
        return {
            "request_id": request_id,
            "controller": "FilehandlerRestController",
            "operation": operation,
        }

    def prepare(self, app: APIRouter, security: DependsParam | None = None) -> None:
        """Prepare filehandler REST routes."""

        route_dependencies = self._route_dependencies(security)

        @app.get(
            "/filehandler/status",
            status_code=status.HTTP_200_OK,
            tags=["filehandler"],
            response_model=FilehandlerStatusResponse,
            dependencies=route_dependencies,
        )
        def status_endpoint(request: Request) -> FilehandlerStatusResponse:
            """Return runtime status for filehandler module."""

            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("FilehandlerController.status"):
                try:
                    logger.info("filehandler status requested", extra={"request_id": request_id})
                    return self.manager.get_status()
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "status"))

        @app.post(
            "/filehandler/upload",
            status_code=status.HTTP_201_CREATED,
            tags=["filehandler"],
            response_model=FileRecordResponse,
            dependencies=route_dependencies,
        )
        async def upload_file_endpoint(
            request: Request,
            actor: FileWriteActor,
            file: UploadFile = File(..., description="File to upload"),
            type_id: str = Query(..., min_length=1, description="File type configuration ID"),
            owner_entity_id: str | None = Query(None, description="ID of the entity this file belongs to"),
            owner_entity_type: str | None = Query(None, description="Type of the owning entity"),
            upload_folder: str | None = Query(None),
            metadata: str = Query("{}", description="JSON-encoded extra metadata dict"),
        ) -> FileRecordResponse:
            """Upload a file via multipart form. type_id and optional filters are query params."""

            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("FilehandlerController.upload"):
                try:
                    logger.info("filehandler upload requested", extra={"request_id": request_id})
                    organization_id = actor_str(actor, "organization_id")
                    user_id = actor_str(actor, "user_id")
                    if not user_id:
                        raise ValueError("Missing actor field: user_id")
                    file_bytes = await file.read()
                    try:
                        parsed_metadata: dict[str, object] = json.loads(metadata) if metadata and metadata != "{}" else {}
                    except json.JSONDecodeError:
                        raise ValueError("metadata must be a valid JSON object")
                    upload_request = FileUploadRequest(
                        type_id=type_id,
                        filename=file.filename or "upload",
                        content_type=file.content_type or "application/octet-stream",
                        content=base64.b64encode(file_bytes).decode("utf-8"),
                        owner_entity_id=owner_entity_id,
                        owner_entity_type=owner_entity_type,
                        upload_folder=upload_folder,
                        metadata=parsed_metadata,
                    )
                    return self.manager.upload_file(organization_id, user_id, upload_request)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "upload"))

        @app.post(
            "/filehandler/list",
            status_code=status.HTTP_200_OK,
            tags=["filehandler"],
            response_model=FileListResponse,
            dependencies=route_dependencies,
        )
        def list_files_endpoint(
            request: Request,
            list_request: FileListRequest,
            actor: FileReadActor,
        ) -> FileListResponse:
            """List files for actor organization with optional filters."""

            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("FilehandlerController.list"):
                try:
                    logger.info("filehandler list requested", extra={"request_id": request_id})
                    organization_id = actor_str(actor, "organization_id")
                    return self.manager.list_files(organization_id, list_request)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "list_files"))

        @app.get(
            "/filehandler/{file_id}",
            status_code=status.HTTP_200_OK,
            tags=["filehandler"],
            response_model=FileRecordResponse,
            dependencies=route_dependencies,
        )
        def get_file_endpoint(
            request: Request,
            file_id: str,
            actor: FileReadActor,
            owner_entity_id: str | None = None,
        ) -> FileRecordResponse:
            """Get one file metadata by id scoped to actor organization.

            When ``owner_entity_id`` is supplied, the file must also belong to that
            incident/record; otherwise it resolves to a 404 so a caller scoped to one
            incident cannot fetch another incident's file by enumerating its id.
            """

            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("FilehandlerController.get"):
                try:
                    logger.info("filehandler get requested", extra={"request_id": request_id})
                    organization_id = actor_str(actor, "organization_id")
                    return self.manager.get_file(organization_id, file_id, owner_entity_id)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "get_file"))

        @app.get(
            "/filehandler/{file_id}/content",
            tags=["filehandler"],
            dependencies=route_dependencies,
        )
        def get_file_content_endpoint(
            request: Request,
            file_id: str,
            actor: FileReadActor,
        ) -> Response:
            """Serve raw logo bytes for inline display (an org logo <img>).

            Restricted to `org_logo` files so it cannot be used to download
            other org files (resumes, documents) by enumerating their ids.
            The logo is fetched as a blob with the normal Authorization header,
            so no access token is placed in the URL.
            """
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("FilehandlerController.get_content"):
                try:
                    organization_id = actor_str(actor, "organization_id")
                    result = self.manager.get_file_content(
                        organization_id, file_id, type_id="org_logo"
                    )
                    if result is None:
                        raise NotFoundError("file content not found")
                    content, content_type = result
                    return Response(content=content, media_type=content_type)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "get_file_content"))

        @app.get(
            "/filehandler/{file_id}/download",
            tags=["filehandler"],
            dependencies=route_dependencies,
        )
        def download_file_endpoint(
            request: Request,
            file_id: str,
            actor: FileReadActor,
        ) -> Response:
            """Serve raw file bytes for any document type (preview/download).

            Unlike /content, not restricted to org_logo. Requires read-role auth.
            """
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("FilehandlerController.download"):
                try:
                    organization_id = actor_str(actor, "organization_id")
                    result = self.manager.get_file_content(organization_id, file_id)
                    if result is None:
                        raise NotFoundError("file content not found")
                    content, content_type = result
                    # These bytes are user-uploaded and `content_type` is whatever
                    # the uploader declared, so the browser must never render them
                    # inline on this origin: an uploaded HTML file would run as
                    # script with the viewer's session (stored XSS). `attachment`
                    # forces a download and `nosniff` stops the browser from
                    # ignoring the declared type. No filename is set: callers name
                    # the file client-side from its metadata.
                    return Response(
                        content=content,
                        media_type=content_type,
                        headers={
                            "Content-Disposition": "attachment",
                            "X-Content-Type-Options": "nosniff",
                        },
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "download_file"))

        @app.get(
            "/filehandler/{file_id}/download-url",
            status_code=status.HTTP_200_OK,
            tags=["filehandler"],
            response_model=DownloadUrlResponse,
            dependencies=route_dependencies,
        )
        def download_url_endpoint(
            request: Request,
            file_id: str,
            actor: FileReadActor,
        ) -> DownloadUrlResponse:
            """Return a URL to fetch file bytes from.

            For Azure-stored files returns a 15-minute SAS URL so the browser
            can stream directly from Azure Blob Storage. For local files returns
            the relative /download path (frontend falls back to its blob-proxy path).
            """
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("FilehandlerController.download_url"):
                try:
                    organization_id = actor_str(actor, "organization_id")
                    return self.manager.get_download_url(organization_id, file_id)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "download_url"))

        @app.delete(
            "/filehandler/{file_id}",
            status_code=status.HTTP_204_NO_CONTENT,
            tags=["filehandler"],
            dependencies=route_dependencies,
        )
        def delete_file_endpoint(
            request: Request,
            file_id: str,
            actor: FileWriteActor,
        ) -> None:
            """Delete one file metadata/filesystem content scoped to actor organization."""

            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("FilehandlerController.delete"):
                try:
                    logger.info("filehandler delete requested", extra={"request_id": request_id})
                    organization_id = actor_str(actor, "organization_id")
                    deleted = self.manager.delete_file(organization_id, file_id)
                    if not deleted:
                        raise NotFoundError("file not found")
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "delete_file"))

        @app.get(
            "/config/file-types",
            status_code=status.HTTP_200_OK,
            tags=["filehandler-config"],
            response_model=FileTypeListResponse,
            dependencies=route_dependencies,
        )
        def list_file_types_endpoint(
            request: Request,
            actor: FileReadActor,
            active_only: bool = Query(default=True),
        ) -> FileTypeListResponse:
            """List file type configurations in actor organization."""

            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("FilehandlerController.list_types"):
                try:
                    logger.info(
                        "filehandler list file types requested", extra={"request_id": request_id}
                    )
                    organization_id = actor_str(actor, "organization_id")
                    return self.manager.list_file_types(organization_id, active_only=active_only)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "list_file_types"))

        @app.post(
            "/config/file-types",
            status_code=status.HTTP_201_CREATED,
            tags=["filehandler-config"],
            response_model=FileTypeResponse,
            dependencies=route_dependencies,
        )
        def create_file_type_endpoint(
            request: Request,
            create_request: FileTypeCreateRequest,
            actor: FileWriteActor,
        ) -> FileTypeResponse:
            """Create file type configuration in actor organization."""

            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("FilehandlerController.create_type"):
                try:
                    logger.info(
                        "filehandler create file type requested", extra={"request_id": request_id}
                    )
                    organization_id = actor_str(actor, "organization_id")
                    return self.manager.create_file_type(organization_id, create_request)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "create_file_type"))

        @app.get(
            "/config/file-types/{type_id}",
            status_code=status.HTTP_200_OK,
            tags=["filehandler-config"],
            response_model=FileTypeResponse,
            dependencies=route_dependencies,
        )
        def get_file_type_endpoint(
            request: Request,
            type_id: str,
            actor: FileReadActor,
        ) -> FileTypeResponse:
            """Get file type by id for actor organization."""

            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("FilehandlerController.get_type"):
                try:
                    logger.info(
                        "filehandler get file type requested", extra={"request_id": request_id}
                    )
                    organization_id = actor_str(actor, "organization_id")
                    return self.manager.get_file_type(organization_id, type_id)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "get_file_type"))

        @app.put(
            "/config/file-types/{type_id}",
            status_code=status.HTTP_200_OK,
            tags=["filehandler-config"],
            response_model=FileTypeResponse,
            dependencies=route_dependencies,
        )
        def update_file_type_endpoint(
            request: Request,
            type_id: str,
            update_request: FileTypeUpdateRequest,
            actor: FileWriteActor,
        ) -> FileTypeResponse:
            """Update file type config in actor organization."""

            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("FilehandlerController.update_type"):
                try:
                    logger.info(
                        "filehandler update file type requested", extra={"request_id": request_id}
                    )
                    organization_id = actor_str(actor, "organization_id")
                    return self.manager.update_file_type(organization_id, type_id, update_request)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "update_file_type"))

        @app.delete(
            "/config/file-types/{type_id}",
            status_code=status.HTTP_204_NO_CONTENT,
            tags=["filehandler-config"],
            dependencies=route_dependencies,
        )
        def delete_file_type_endpoint(
            request: Request,
            type_id: str,
            actor: FileWriteActor,
        ) -> None:
            """Delete file type config in actor organization."""

            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("FilehandlerController.delete_type"):
                try:
                    logger.info(
                        "filehandler delete file type requested", extra={"request_id": request_id}
                    )
                    organization_id = actor_str(actor, "organization_id")
                    deleted = self.manager.delete_file_type(organization_id, type_id)
                    if not deleted:
                        raise NotFoundError("file type not found")
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "delete_file_type"))

        @app.post(
            "/config/file-types/seed",
            status_code=status.HTTP_200_OK,
            tags=["filehandler-config"],
            response_model=FileTypeSeedResponse,
            dependencies=route_dependencies,
        )
        def seed_file_types_endpoint(
            request: Request,
            actor: FileWriteActor,
        ) -> FileTypeSeedResponse:
            """Seed default file type configurations for actor organization."""

            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("FilehandlerController.seed_types"):
                try:
                    logger.info(
                        "filehandler seed file types requested", extra={"request_id": request_id}
                    )
                    organization_id = actor_str(actor, "organization_id")
                    return self.manager.seed_file_types(organization_id)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "seed_file_types"))

        @app.get(
            "/filehandler/serve/{file_id}",
            status_code=status.HTTP_200_OK,
            tags=["filehandler"],
        )
        def serve_thumbnail_endpoint(
            request: Request,
            file_id: str,
            sig: str = Query(...),
            exp: int = Query(...),
            org: str = Query(default=""),
        ) -> Response:
            """Serve a thumbnail image via a short-lived HMAC-signed URL (no auth header needed)."""

            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("FilehandlerController.serve_thumbnail"):
                try:
                    result = self.manager.serve_signed_thumbnail(file_id, sig, exp, org)
                    if result is None:
                        raise HTTPException(status_code=403, detail="Invalid or expired thumbnail URL")
                    file_bytes, content_type = result
                    return Response(
                        content=file_bytes,
                        media_type=content_type,
                        headers={
                            "Cache-Control": f"public, max-age={self.manager._THUMBNAIL_CACHE_MAX_AGE}",
                        },
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "serve_thumbnail"))
