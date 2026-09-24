"""Tasks REST controller module."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

try:
    from common.auth import require_permission, actor_str
    from common.logger import logger, tracer
except ImportError:  # pragma: no cover - package import fallback
    from backend.modular_backend.common.auth import require_permission, actor_str
    from backend.modular_backend.common.logger import logger, tracer

from tasks.manager import TasksServiceManager
from tasks.models.request import TaskCreateRequest, TaskListRequest, TaskUpdateRequest
from tasks.models.response import TaskListResponse, TaskReadResponse, TasksStatusResponse

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

TaskReadActor = Annotated[dict[str, object], Depends(require_permission("background_job", "read"))]
TaskWriteActor = Annotated[dict[str, object], Depends(require_permission("background_job", "write"))]


class TasksRestController:
    """Implements tasks REST controller."""

    def __init__(
        self,
        tasks_service_manager: TasksServiceManager,
        database_service_manager=None,
        auth_service_manager=None,
    ) -> None:  # noqa: ANN001
        super().__init__()
        self.tasks_service_manager = tasks_service_manager
        self.manager = tasks_service_manager
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
        """Prepare the tasks REST controller."""
        route_dependencies = self._route_dependencies(security)

        @app.get(
            "/tasks/status",
            status_code=status.HTTP_200_OK,
            tags=["tasks"],
            response_model=TasksStatusResponse,
            dependencies=route_dependencies,
        )
        def status_endpoint(request: Request):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("TasksController.status"):
                try:
                    logger.info("tasks status requested", extra={"request_id": request_id})
                    return self.tasks_service_manager.get_status()
                except HTTPException:
                    raise
                except RecordNotFoundException as exc:  # noqa: BLE001
                    logger.exception("tasks status failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except NotFoundError as exc:  # noqa: BLE001
                    logger.exception("tasks status failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except (ValidationError, ValueError) as exc:  # noqa: BLE001
                    logger.exception("tasks status failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
                except (AuthorizationError, PermissionError) as exc:  # noqa: BLE001
                    logger.exception("tasks status failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
                except ConflictError as exc:  # noqa: BLE001
                    logger.exception("tasks status failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
                except (DBException, PersistenceError, ServiceError) as exc:  # noqa: BLE001
                    logger.exception("tasks status failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
                except Exception as exc:  # noqa: BLE001
                    logger.exception("tasks status failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

        @app.post(
            "/entities/{entity_id}/tasks",
            status_code=status.HTTP_201_CREATED,
            tags=["tasks"],
            response_model=TaskReadResponse,
            dependencies=route_dependencies,
        )
        def create_entity_task_endpoint(
            request: Request,
            entity_id: str,
            payload: TaskCreateRequest,
            actor: TaskWriteActor,
        ):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("TasksController.create_entity_task"):
                try:
                    logger.info("tasks create_entity_task", extra={"request_id": request_id})
                    return self.tasks_service_manager.create_task_for_actor(actor, entity_id, payload)
                except HTTPException:
                    raise
                except RecordNotFoundException as exc:  # noqa: BLE001
                    logger.exception("tasks create_entity_task failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except NotFoundError as exc:  # noqa: BLE001
                    logger.exception("tasks create_entity_task failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except (ValidationError, ValueError) as exc:  # noqa: BLE001
                    logger.exception("tasks create_entity_task failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
                except (AuthorizationError, PermissionError) as exc:  # noqa: BLE001
                    logger.exception("tasks create_entity_task failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
                except ConflictError as exc:  # noqa: BLE001
                    logger.exception("tasks create_entity_task failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
                except (DBException, PersistenceError, ServiceError) as exc:  # noqa: BLE001
                    logger.exception("tasks create_entity_task failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
                except Exception as exc:  # noqa: BLE001
                    logger.exception("tasks create_entity_task failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

        @app.get(
            "/entities/{entity_id}/tasks",
            status_code=status.HTTP_200_OK,
            tags=["tasks"],
            response_model=TaskListResponse,
            dependencies=route_dependencies,
        )
        def list_entity_tasks_endpoint(
            request: Request,
            entity_id: str,
            actor: TaskReadActor,
            status_filter: str | None = Query(default=None, alias="status"),
        ):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("TasksController.list_entity_tasks"):
                try:
                    logger.info("tasks list_entity_tasks", extra={"request_id": request_id})
                    return self.tasks_service_manager.list_entity_tasks_for_actor(actor, entity_id, status_filter)
                except HTTPException:
                    raise
                except RecordNotFoundException as exc:  # noqa: BLE001
                    logger.exception("tasks list_entity_tasks failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except NotFoundError as exc:  # noqa: BLE001
                    logger.exception("tasks list_entity_tasks failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except (ValidationError, ValueError) as exc:  # noqa: BLE001
                    logger.exception("tasks list_entity_tasks failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
                except (AuthorizationError, PermissionError) as exc:  # noqa: BLE001
                    logger.exception("tasks list_entity_tasks failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
                except ConflictError as exc:  # noqa: BLE001
                    logger.exception("tasks list_entity_tasks failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
                except (DBException, PersistenceError, ServiceError) as exc:  # noqa: BLE001
                    logger.exception("tasks list_entity_tasks failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
                except Exception as exc:  # noqa: BLE001
                    logger.exception("tasks list_entity_tasks failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

        @app.get(
            "/tasks",
            status_code=status.HTTP_200_OK,
            tags=["tasks"],
            response_model=TaskListResponse,
            dependencies=route_dependencies,
        )
        def list_tasks_endpoint(
            request: Request,
            actor: TaskReadActor,
            assigned_to: str | None = Query(default=None),
            status_filter: str | None = Query(default=None, alias="status"),
            entity_type: str | None = Query(default=None),
            priority: str | None = Query(default=None),
            due_before: datetime | None = Query(default=None),
            due_after: datetime | None = Query(default=None),
            skip: int = Query(default=0, ge=0),
            limit: int = Query(default=50, ge=1, le=100),
        ):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("TasksController.list_tasks"):
                try:
                    logger.info("tasks list_tasks", extra={"request_id": request_id})
                    list_request = TaskListRequest(
                        organization_id=actor_str(actor, "organization_id"),
                        assigned_to=assigned_to,
                        status=status_filter,
                        entity_type=entity_type,
                        priority=priority,
                        due_before=due_before,
                        due_after=due_after,
                        skip=skip,
                        limit=limit,
                    )
                    return self.tasks_service_manager.list_tasks_for_actor(actor, list_request)
                except HTTPException:
                    raise
                except RecordNotFoundException as exc:  # noqa: BLE001
                    logger.exception("tasks list_tasks failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except NotFoundError as exc:  # noqa: BLE001
                    logger.exception("tasks list_tasks failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except (ValidationError, ValueError) as exc:  # noqa: BLE001
                    logger.exception("tasks list_tasks failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
                except (AuthorizationError, PermissionError) as exc:  # noqa: BLE001
                    logger.exception("tasks list_tasks failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
                except ConflictError as exc:  # noqa: BLE001
                    logger.exception("tasks list_tasks failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
                except (DBException, PersistenceError, ServiceError) as exc:  # noqa: BLE001
                    logger.exception("tasks list_tasks failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
                except Exception as exc:  # noqa: BLE001
                    logger.exception("tasks list_tasks failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

        @app.patch(
            "/tasks/{task_id}",
            status_code=status.HTTP_200_OK,
            tags=["tasks"],
            response_model=TaskReadResponse,
            dependencies=route_dependencies,
        )
        def update_task_endpoint(
            request: Request,
            task_id: str,
            payload: TaskUpdateRequest,
            actor: TaskWriteActor,
        ):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("TasksController.update_task"):
                try:
                    logger.info("tasks update_task", extra={"request_id": request_id})
                    updated = self.tasks_service_manager.update_task_for_actor(actor, task_id, payload)
                    if updated is None:
                        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
                    return updated
                except HTTPException:
                    raise
                except RecordNotFoundException as exc:  # noqa: BLE001
                    logger.exception("tasks update_task failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except NotFoundError as exc:  # noqa: BLE001
                    logger.exception("tasks update_task failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except (ValidationError, ValueError) as exc:  # noqa: BLE001
                    logger.exception("tasks update_task failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
                except (AuthorizationError, PermissionError) as exc:  # noqa: BLE001
                    logger.exception("tasks update_task failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
                except ConflictError as exc:  # noqa: BLE001
                    logger.exception("tasks update_task failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
                except (DBException, PersistenceError, ServiceError) as exc:  # noqa: BLE001
                    logger.exception("tasks update_task failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
                except Exception as exc:  # noqa: BLE001
                    logger.exception("tasks update_task failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

        @app.delete(
            "/tasks/{task_id}",
            status_code=status.HTTP_200_OK,
            tags=["tasks"],
            response_model=TaskReadResponse,
            dependencies=route_dependencies,
        )
        def archive_task_endpoint(
            request: Request,
            task_id: str,
            actor: TaskWriteActor,
        ):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("TasksController.archive_task"):
                try:
                    logger.info("tasks archive_task", extra={"request_id": request_id})
                    archived = self.tasks_service_manager.archive_task_for_actor(actor, task_id)
                    if archived is None:
                        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
                    return archived
                except HTTPException:
                    raise
                except RecordNotFoundException as exc:  # noqa: BLE001
                    logger.exception("tasks archive_task failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except NotFoundError as exc:  # noqa: BLE001
                    logger.exception("tasks archive_task failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
                except (ValidationError, ValueError) as exc:  # noqa: BLE001
                    logger.exception("tasks archive_task failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
                except (AuthorizationError, PermissionError) as exc:  # noqa: BLE001
                    logger.exception("tasks archive_task failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
                except ConflictError as exc:  # noqa: BLE001
                    logger.exception("tasks archive_task failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
                except (DBException, PersistenceError, ServiceError) as exc:  # noqa: BLE001
                    logger.exception("tasks archive_task failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
                except Exception as exc:  # noqa: BLE001
                    logger.exception("tasks archive_task failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")
