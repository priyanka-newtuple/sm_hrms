"""Business logic manager for tasks."""

from __future__ import annotations

from datetime import datetime, timedelta

try:
    from common.enums import ModuleStatus
except ImportError:  # pragma: no cover - package import fallback
    from backend.modular_backend.common.enums import ModuleStatus

try:
    from exceptions import AuthorizationError, NotFoundError, ServiceError, ValidationError
except ImportError:  # pragma: no cover - package import fallback
    from backend.modular_backend.exceptions import AuthorizationError, NotFoundError, ServiceError, ValidationError

from .models.interface import TaskContract, TaskSource, TaskStatus
from .models.request import EntityTaskListRequest, TaskCreateRequest, TaskListRequest, TaskUpdateRequest
from .models.response import TaskListResponse, TaskReadResponse, TasksStatusResponse


class TasksServiceManager:
    """Tasks orchestration service."""

    def __init__(
        self,
        tasks_db_model_service,
        database_service_manager,
        config,
        communications_service_manager=None,
        auth_service_manager=None,
        *dependencies,
    ) -> None:  # noqa: ANN001
        super().__init__()
        self.tasks_db_model_service = tasks_db_model_service
        self.db_model_service = tasks_db_model_service
        self.model_service = tasks_db_model_service
        self.database_service_manager = database_service_manager
        self.config = config
        self.dependencies = list(dependencies)
        self.module_name = "tasks"
        self._started = False
        self.communications_service_manager = communications_service_manager
        self.auth_service_manager = auth_service_manager

    def start(self) -> None:
        self._started = True

    def stop(self) -> None:
        self._started = False

    def get_status(self) -> TasksStatusResponse:
        return TasksStatusResponse(
            module=self.module_name,
            status=ModuleStatus.READY.value,
            started=self._started,
        )

    def create_task(
        self,
        request: TaskCreateRequest | dict[str, object],
        *,
        organization_id: str,
        entity_id: str,
        created_by: str,
        entity_type: str,
        stage: str | None = None,
        source: str = TaskSource.MANUAL.value,
    ) -> TaskReadResponse:
        try:
            task_request = (
                request if isinstance(request, TaskCreateRequest) else TaskCreateRequest.from_dict(request)
            )
            record = self.db_model_service.create_task(
                task_request,
                organization_id=organization_id,
                entity_id=entity_id,
                created_by=created_by,
                entity_type=entity_type,
                stage=stage,
                source=source,
            )
            self._notify_assignment_if_needed(record, actor_id=created_by)
            return self._to_read_response(record)
        except (ValidationError, AuthorizationError, NotFoundError):
            raise
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise ServiceError(f"Unable to create task: {exc}") from exc

    def update_task(
        self,
        *,
        task_id: str,
        organization_id: str,
        updates: dict[str, object],
        actor_id: str,
    ) -> TaskReadResponse | None:
        try:
            record = self.db_model_service.update_task(
                task_id=task_id,
                organization_id=organization_id,
                updates=updates,
            )
            if record is None:
                return None
            # Notify if reassigned
            if "assigned_to" in updates and updates.get("assigned_to"):
                self._notify_assignment_if_needed(record, actor_id=actor_id)
            return self._to_read_response(record)
        except (ValidationError, AuthorizationError, NotFoundError):
            raise
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise ServiceError(f"Unable to update task: {exc}") from exc

    def archive_task(self, *, task_id: str, organization_id: str) -> TaskReadResponse | None:
        try:
            record = self.db_model_service.archive_task(task_id=task_id, organization_id=organization_id)
            if record is None:
                return None
            return self._to_read_response(record)
        except (ValidationError, AuthorizationError, NotFoundError):
            raise
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise ServiceError(f"Unable to archive task: {exc}") from exc

    def list_entity_tasks(
        self,
        *,
        organization_id: str,
        entity_id: str,
        status: str | None = None,
    ) -> TaskListResponse:
        records = self.db_model_service.list_entity_tasks(
            organization_id=organization_id,
            entity_id=entity_id,
            status=status,
        )
        return TaskListResponse(
            tasks=[self._to_read_response(record) for record in records],
            total=len(records),
        )

    def list_tasks(self, request: TaskListRequest | dict[str, object]) -> TaskListResponse:
        try:
            list_request = request if isinstance(request, TaskListRequest) else TaskListRequest.model_validate(request)
            records, total = self.db_model_service.list_tasks(
                organization_id=list_request.organization_id,
                assigned_to=list_request.assigned_to,
                status=list_request.status,
                entity_type=list_request.entity_type,
                priority=list_request.priority,
                due_before=list_request.due_before,
                due_after=list_request.due_after,
                skip=list_request.skip,
                limit=list_request.limit,
            )
            return TaskListResponse(
                tasks=[self._to_read_response(record) for record in records],
                total=total,
            )
        except (ValidationError, AuthorizationError, NotFoundError):
            raise
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise ServiceError(f"Unable to list tasks: {exc}") from exc

    def has_incomplete_tasks_for_stage(
        self,
        *,
        organization_id: str,
        entity_id: str,
        stage: str,
        source: str | None = None,
    ) -> bool:
        return self.db_model_service.has_incomplete_tasks_for_stage(
            organization_id=organization_id,
            entity_id=entity_id,
            stage=stage,
            source=source,
        )

    def apply_side_effects(
        self,
        *,
        organization_id: str,
        entity_id: str,
        entity_type: str,
        to_state: str,
        owner_id: str | None,
        side_effects: list[dict[str, object]] | None,
    ) -> list[TaskReadResponse]:
        """Create tasks from transition side effects."""
        created: list[TaskReadResponse] = []
        for effect in side_effects or []:
            if effect.get("type") != "CREATE_TASK":
                continue

            due_date = None
            due_in_hours = effect.get("due_in_hours")
            if due_in_hours:
                try:
                    due_date = datetime.utcnow() + timedelta(hours=float(due_in_hours))
                except Exception:
                    due_date = None

            request = TaskCreateRequest(
                title=str(effect.get("title") or "Untitled task"),
                description=effect.get("description"),
                assigned_to=effect.get("assigned_to") or owner_id,
                priority=str(effect.get("priority") or "MEDIUM"),
                due_date=due_date,
                entity_type=entity_type,
            )
            created.append(
                self.create_task(
                    request,
                    organization_id=organization_id,
                    entity_id=entity_id,
                    created_by="system",
                    entity_type=entity_type,
                    stage=to_state,
                    source=TaskSource.AUTO.value,
                )
            )

        return created

    def create_task_for_actor(
        self,
        actor: dict[str, object],
        entity_id: str,
        request: TaskCreateRequest,
    ) -> TaskReadResponse:
        actor_user_id = self._require_actor_field(actor, "user_id")
        organization_id = self._require_actor_field(actor, "organization_id")
        if not request.entity_type:
            raise ValidationError("entity_type is required")
        entity_type = request.entity_type
        return self.create_task(
            request,
            organization_id=organization_id,
            entity_id=entity_id,
            created_by=actor_user_id,
            entity_type=entity_type,
        )

    def list_entity_tasks_for_actor(
        self,
        actor: dict[str, object],
        entity_id: str,
        status: str | None = None,
    ) -> TaskListResponse:
        organization_id = self._require_actor_field(actor, "organization_id")
        return self.list_entity_tasks(
            organization_id=organization_id,
            entity_id=entity_id,
            status=status,
        )

    def list_tasks_for_actor(
        self,
        actor: dict[str, object],
        request: TaskListRequest,
    ) -> TaskListResponse:
        organization_id = self._require_actor_field(actor, "organization_id")
        normalized = TaskListRequest(
            organization_id=organization_id,
            assigned_to=request.assigned_to,
            status=request.status,
            entity_type=request.entity_type,
            priority=request.priority,
            due_before=request.due_before,
            due_after=request.due_after,
            skip=request.skip,
            limit=request.limit,
        )
        return self.list_tasks(normalized)

    def update_task_for_actor(
        self,
        actor: dict[str, object],
        task_id: str,
        request: TaskUpdateRequest,
    ) -> TaskReadResponse | None:
        organization_id = self._require_actor_field(actor, "organization_id")
        actor_user_id = self._require_actor_field(actor, "user_id")
        updates = request.model_dump(exclude_none=True)
        if not updates:
            raise ValidationError("No fields to update")
        return self.update_task(
            task_id=task_id,
            organization_id=organization_id,
            updates=updates,
            actor_id=actor_user_id,
        )

    def archive_task_for_actor(
        self,
        actor: dict[str, object],
        task_id: str,
    ) -> TaskReadResponse | None:
        organization_id = self._require_actor_field(actor, "organization_id")
        return self.archive_task(task_id=task_id, organization_id=organization_id)

    def _notify_assignment_if_needed(self, record: TaskContract, actor_id: str) -> None:
        if not self.communications_service_manager:
            return
        if not record.assigned_to or record.assigned_to == actor_id:
            return
        try:
            # Use a generic template; downstream can map templates.
            payload = {
                "entity_id": record.entity_id,
                "entity_type": record.entity_type,
                "task_id": record.id,
                "title": record.title,
                "priority": record.priority,
            }
            self.communications_service_manager.create_notification(
                {
                    "recipient_id": record.assigned_to,
                    "organization_id": record.organization_id,
                    "template": "task_assigned",
                    "payload": payload,
                }
            )
        except Exception:
            # Notification failure should not block task creation.
            return

    @staticmethod
    def _to_read_response(record: TaskContract) -> TaskReadResponse:
        return TaskReadResponse(
            id=record.id,
            organization_id=record.organization_id,
            entity_id=record.entity_id,
            entity_type=record.entity_type,
            title=record.title,
            description=record.description,
            assigned_to=record.assigned_to,
            created_by=record.created_by,
            status=record.status,
            priority=record.priority,
            due_date=record.due_date,
            stage=record.stage,
            source=record.source,
            completed_at=record.completed_at,
            archived_at=record.archived_at,
            created_at=record.created_at,
            updated_at=record.updated_at,
            assigned_to_name=None,
            created_by_name=None,
        )

    @staticmethod
    def _require_actor_field(actor: dict[str, object], field: str) -> str:
        value = actor.get(field)
        if not value:
            raise ValidationError(f"Missing actor field: {field}")
        return str(value)
