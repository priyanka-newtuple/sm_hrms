"""Documents REST controller module."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

try:
    from common.logger import logger, tracer
except ImportError:  # pragma: no cover - package import fallback
    from backend.modular_backend.common.logger import logger, tracer

try:
    from common.auth import require_permission
except ImportError:  # pragma: no cover - package import fallback
    from backend.modular_backend.common.auth import require_permission

from .models.request import ListDocumentsRequest, UpdateDocumentStatusRequest, UploadDocumentRequest
from .models.response import (
    DocumentExtractionSummaryResponse,
    DocumentListResponse,
    DocumentResponse,
    DocumentStatusResponse,
    DocumentsStatusResponse,
)


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

DocReadActor = Annotated[dict[str, object], Depends(require_permission("document", "read"))]
DocWriteActor = Annotated[dict[str, object], Depends(require_permission("document", "write"))]


class DocumentsRestController:
    """Implements documents REST controller."""

    def __init__(
        self,
        documents_service_manager,
        database_service_manager=None,
        auth_service_manager=None,
    ) -> None:  # noqa: ANN001
        super().__init__()
        self.documents_service_manager = documents_service_manager
        self.service_manager = documents_service_manager
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
        """Prepare the documents REST controller."""
        route_dependencies = self._route_dependencies(security)

        @app.get(
            "/documents/status",
            status_code=status.HTTP_200_OK,
            tags=["documents"],
            response_model=DocumentsStatusResponse,
            dependencies=route_dependencies,
        )
        def status_endpoint(request: Request):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("DocumentsController.status"):
                try:
                    logger.info("documents status requested", extra={"request_id": request_id})
                    return self.documents_service_manager.get_status()
                except HTTPException:

                    raise

                except RecordNotFoundException as exc:  # noqa: BLE001
                    logger.exception("documents status failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except NotFoundError as exc:  # noqa: BLE001
                    logger.exception("documents status failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except (ValidationError, ValueError) as exc:  # noqa: BLE001
                    logger.exception("documents status failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
                except (AuthorizationError, PermissionError) as exc:  # noqa: BLE001
                    logger.exception("documents status failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
                except ConflictError as exc:  # noqa: BLE001
                    logger.exception("documents status failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
                except (DBException, PersistenceError, ServiceError) as exc:  # noqa: BLE001
                    logger.exception("documents status failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
                except Exception as exc:  # noqa: BLE001
                    logger.exception("documents status failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

        @app.post(
            "/documents/upload",
            status_code=status.HTTP_201_CREATED,
            tags=["documents"],
            response_model=DocumentResponse,
            dependencies=route_dependencies,
        )
        def upload_document_endpoint(
            request: Request,
            upload_request: UploadDocumentRequest,
            actor: DocWriteActor,
        ):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("DocumentsController.upload_document"):
                try:
                    logger.info("documents upload_document", extra={"request_id": request_id})
                    return self.documents_service_manager.upload_document_for_actor(actor, upload_request)
                except HTTPException:
                    raise

                except RecordNotFoundException as exc:  # noqa: BLE001
                    logger.exception("documents upload_document failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except NotFoundError as exc:  # noqa: BLE001
                    logger.exception("documents upload_document failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except (ValidationError, ValueError) as exc:  # noqa: BLE001
                    logger.exception("documents upload_document failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
                except (AuthorizationError, PermissionError) as exc:  # noqa: BLE001
                    logger.exception("documents upload_document failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
                except ConflictError as exc:  # noqa: BLE001
                    logger.exception("documents upload_document failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
                except (DBException, PersistenceError, ServiceError) as exc:  # noqa: BLE001
                    logger.exception("documents upload_document failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
                except Exception as exc:  # noqa: BLE001
                    logger.exception("documents upload_document failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

        @app.post(
            "/documents/update-status",
            status_code=status.HTTP_200_OK,
            tags=["documents"],
            response_model=DocumentStatusResponse,
            dependencies=route_dependencies,
        )
        def update_document_status_endpoint(
            request: Request,
            status_request: UpdateDocumentStatusRequest,
            actor: DocWriteActor,
        ):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("DocumentsController.update_document_status"):
                try:
                    logger.info("documents update_document_status", extra={"request_id": request_id})
                    return self.documents_service_manager.update_document_status_for_actor(actor, status_request)
                except HTTPException:
                    raise

                except RecordNotFoundException as exc:  # noqa: BLE001
                    logger.exception("documents update_document_status failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except NotFoundError as exc:  # noqa: BLE001
                    logger.exception("documents update_document_status failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except (ValidationError, ValueError) as exc:  # noqa: BLE001
                    logger.exception("documents update_document_status failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
                except (AuthorizationError, PermissionError) as exc:  # noqa: BLE001
                    logger.exception("documents update_document_status failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
                except ConflictError as exc:  # noqa: BLE001
                    logger.exception("documents update_document_status failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
                except (DBException, PersistenceError, ServiceError) as exc:  # noqa: BLE001
                    logger.exception("documents update_document_status failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
                except Exception as exc:  # noqa: BLE001
                    logger.exception("documents update_document_status failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

        @app.post(
            "/documents/list",
            status_code=status.HTTP_200_OK,
            tags=["documents"],
            response_model=DocumentListResponse,
            dependencies=route_dependencies,
        )
        def list_documents_endpoint(
            request: Request,
            list_request: ListDocumentsRequest,
            actor: DocReadActor,
        ):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("DocumentsController.list_documents"):
                try:
                    logger.info("documents list_documents", extra={"request_id": request_id})
                    return self.documents_service_manager.list_documents_for_actor(actor, list_request)
                except HTTPException:
                    raise

                except RecordNotFoundException as exc:  # noqa: BLE001
                    logger.exception("documents list_documents failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except NotFoundError as exc:  # noqa: BLE001
                    logger.exception("documents list_documents failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except (ValidationError, ValueError) as exc:  # noqa: BLE001
                    logger.exception("documents list_documents failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
                except (AuthorizationError, PermissionError) as exc:  # noqa: BLE001
                    logger.exception("documents list_documents failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
                except ConflictError as exc:  # noqa: BLE001
                    logger.exception("documents list_documents failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
                except (DBException, PersistenceError, ServiceError) as exc:  # noqa: BLE001
                    logger.exception("documents list_documents failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
                except Exception as exc:  # noqa: BLE001
                    logger.exception("documents list_documents failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

        @app.get(
            "/documents/{organization_id}/{document_id}",
            status_code=status.HTTP_200_OK,
            tags=["documents"],
            response_model=DocumentResponse,
            dependencies=route_dependencies,
        )
        def get_document_endpoint(
            request: Request,
            organization_id: str,
            document_id: str,
            actor: DocReadActor,
        ):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("DocumentsController.get_document"):
                try:
                    logger.info("documents get_document", extra={"request_id": request_id})
                    return self.documents_service_manager.get_document_for_actor(actor, organization_id, document_id)
                except HTTPException:
                    raise

                except RecordNotFoundException as exc:  # noqa: BLE001
                    logger.exception("documents get_document failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except NotFoundError as exc:  # noqa: BLE001
                    logger.exception("documents get_document failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except (ValidationError, ValueError) as exc:  # noqa: BLE001
                    logger.exception("documents get_document failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
                except (AuthorizationError, PermissionError) as exc:  # noqa: BLE001
                    logger.exception("documents get_document failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
                except ConflictError as exc:  # noqa: BLE001
                    logger.exception("documents get_document failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
                except (DBException, PersistenceError, ServiceError) as exc:  # noqa: BLE001
                    logger.exception("documents get_document failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
                except Exception as exc:  # noqa: BLE001
                    logger.exception("documents get_document failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

        @app.get(
            "/documents/{organization_id}/{document_id}/extraction-summary",
            status_code=status.HTTP_200_OK,
            tags=["documents"],
            response_model=DocumentExtractionSummaryResponse,
            dependencies=route_dependencies,
        )
        def extraction_summary_endpoint(
            request: Request,
            organization_id: str,
            document_id: str,
            actor: DocReadActor,
        ):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("DocumentsController.get_extraction_summary"):
                try:
                    logger.info("documents extraction_summary", extra={"request_id": request_id})
                    return self.documents_service_manager.get_extraction_summary_for_actor(
                        actor,
                        organization_id,
                        document_id,
                    )
                except HTTPException:
                    raise

                except RecordNotFoundException as exc:  # noqa: BLE001
                    logger.exception("documents extraction_summary failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except NotFoundError as exc:  # noqa: BLE001
                    logger.exception("documents extraction_summary failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except (ValidationError, ValueError) as exc:  # noqa: BLE001
                    logger.exception("documents extraction_summary failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
                except (AuthorizationError, PermissionError) as exc:  # noqa: BLE001
                    logger.exception("documents extraction_summary failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
                except ConflictError as exc:  # noqa: BLE001
                    logger.exception("documents extraction_summary failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
                except (DBException, PersistenceError, ServiceError) as exc:  # noqa: BLE001
                    logger.exception("documents extraction_summary failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
                except Exception as exc:  # noqa: BLE001
                    logger.exception("documents extraction_summary failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")
