"""Playbooks REST controller module."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

try:
    from common.logger import logger, tracer
except ImportError:  # pragma: no cover - package import fallback
    from backend.modular_backend.common.logger import logger, tracer

from playbooks.manager import PlaybooksServiceManager
from playbooks.models.response import PlaybooksRuntimeStatusResponse


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



class PlaybooksRestController:
    """Implements playbooks REST controller."""

    def __init__(
        self,
        playbooks_service_manager: PlaybooksServiceManager,
        database_service_manager=None,
        auth_service_manager=None,
    ) -> None:  # noqa: ANN001
        super().__init__()
        self.playbooks_service_manager = playbooks_service_manager
        self.manager = playbooks_service_manager
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
        """Prepare the playbooks REST controller."""
        @app.get(
            "/playbooks/status",
            status_code=status.HTTP_200_OK,
            tags=["playbooks"],
            response_model=PlaybooksRuntimeStatusResponse,
            dependencies=self._route_dependencies(security),
        )
        def status_endpoint(request: Request):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("PlaybooksController.status"):
                try:
                    logger.info("playbooks status requested", extra={"request_id": request_id})
                    return self.playbooks_service_manager.get_status()
                except HTTPException:

                    raise

                except RecordNotFoundException as exc:  # noqa: BLE001
                    logger.exception("playbooks status failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except NotFoundError as exc:  # noqa: BLE001
                    logger.exception("playbooks status failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except (ValidationError, ValueError) as exc:  # noqa: BLE001
                    logger.exception("playbooks status failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
                except (AuthorizationError, PermissionError) as exc:  # noqa: BLE001
                    logger.exception("playbooks status failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
                except ConflictError as exc:  # noqa: BLE001
                    logger.exception("playbooks status failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
                except (DBException, PersistenceError, ServiceError) as exc:  # noqa: BLE001
                    logger.exception("playbooks status failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
                except Exception as exc:  # noqa: BLE001
                    logger.exception("playbooks status failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

        @app.get(
            "/playbooks_runtime/status",
            status_code=status.HTTP_200_OK,
            tags=["playbooks_runtime"],
            response_model=PlaybooksRuntimeStatusResponse,
            dependencies=self._route_dependencies(security),
        )
        def legacy_status_endpoint(request: Request):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("PlaybooksController.legacy_status"):
                try:
                    logger.info("playbooks_runtime status requested", extra={"request_id": request_id})
                    return self.playbooks_service_manager.get_status()
                except HTTPException:

                    raise

                except RecordNotFoundException as exc:  # noqa: BLE001
                    logger.exception("playbooks_runtime status failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except NotFoundError as exc:  # noqa: BLE001
                    logger.exception("playbooks_runtime status failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except (ValidationError, ValueError) as exc:  # noqa: BLE001
                    logger.exception("playbooks_runtime status failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
                except (AuthorizationError, PermissionError) as exc:  # noqa: BLE001
                    logger.exception("playbooks_runtime status failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
                except ConflictError as exc:  # noqa: BLE001
                    logger.exception("playbooks_runtime status failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
                except (DBException, PersistenceError, ServiceError) as exc:  # noqa: BLE001
                    logger.exception("playbooks_runtime status failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
                except Exception as exc:  # noqa: BLE001
                    logger.exception("playbooks_runtime status failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")
