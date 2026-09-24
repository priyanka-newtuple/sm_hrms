"""Persistence adapters for tasks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from sqlalchemy import Column, DateTime, Index, String, Text
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

try:
    from database.manager import Base
except ImportError:  # pragma: no cover - package import fallback
    from backend.modular_backend.database.manager import Base

try:
    from exceptions import PersistenceError
except ImportError:  # pragma: no cover - package import fallback
    from backend.modular_backend.exceptions import PersistenceError

from .models.interface import TaskContract, TaskSource, TaskStatus
from .models.request import TaskCreateRequest


class TaskModel(Base):
    __tablename__ = "tasks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id = Column(String(36), nullable=False, index=True)
    entity_id = Column(String(36), nullable=False, index=True)
    entity_type = Column(String(128), nullable=False)
    title = Column(String(256), nullable=False)
    description = Column(Text, nullable=True)
    assigned_to = Column(String(36), nullable=True, index=True)
    created_by = Column(String(36), nullable=False)
    status = Column(String(32), nullable=False, default=TaskStatus.PENDING.value)
    priority = Column(String(32), nullable=False, default="MEDIUM")
    due_date = Column(DateTime(timezone=True), nullable=True)
    stage = Column(String(64), nullable=True)
    source = Column(String(32), nullable=False, default=TaskSource.MANUAL.value)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    archived_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_tasks_entity_stage", "entity_id", "stage"),
        Index("ix_tasks_assigned_status", "assigned_to", "status"),
        Index("ix_tasks_org_entity", "organization_id", "entity_id"),
        Index("ix_tasks_due_date", "due_date"),
    )


@dataclass
class TaskRecord:
    id: str
    organization_id: str
    entity_id: str
    entity_type: str
    title: str
    description: str | None
    assigned_to: str | None
    created_by: str
    status: str
    priority: str
    due_date: datetime | None
    stage: str | None
    source: str
    completed_at: datetime | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime | None


class TasksModelService:
    """Persistence service for tasks (DB-backed with in-memory fallback)."""

    def __init__(self, database_service_manager) -> None:  # noqa: ANN001
        super().__init__()
        self.database_manager = database_service_manager
        self.database_service_manager = database_service_manager
        self.current_db = (
            self.database_manager.postgres_db_service()
            if self.database_manager and hasattr(self.database_manager, "postgres_db_service")
            else None
        )
        self.current_db_engine = getattr(self.current_db, "engine", None)
        self.module_name = "tasks"
        self._tasks: dict[str, TaskRecord] = {}

    def _use_memory(self) -> bool:
        return self.current_db is None

    def _session(self) -> Session:
        if not self.current_db:
            raise PersistenceError("Database service manager unavailable")
        return self.current_db.get_db_session()

    def create_task(
        self,
        request: TaskCreateRequest,
        *,
        organization_id: str,
        entity_id: str,
        created_by: str,
        entity_type: str,
        stage: str | None,
        source: str,
    ) -> TaskContract:
        try:
            if self._use_memory():
                now = datetime.utcnow()
                record = TaskRecord(
                    id=str(uuid4()),
                    organization_id=organization_id,
                    entity_id=entity_id,
                    entity_type=entity_type,
                    title=request.title,
                    description=request.description,
                    assigned_to=request.assigned_to,
                    created_by=created_by,
                    status=TaskStatus.PENDING.value,
                    priority=request.priority,
                    due_date=request.due_date,
                    stage=stage,
                    source=source,
                    completed_at=None,
                    archived_at=None,
                    created_at=now,
                    updated_at=now,
                )
                self._tasks[record.id] = record
                return self._to_contract(record)

            session = self._session()
            model = TaskModel(
                organization_id=organization_id,
                entity_id=entity_id,
                entity_type=entity_type,
                title=request.title,
                description=request.description,
                assigned_to=request.assigned_to,
                created_by=created_by,
                status=TaskStatus.PENDING.value,
                priority=request.priority,
                due_date=request.due_date,
                stage=stage,
                source=source,
            )
            session.add(model)
            session.commit()
            session.refresh(model)
            return self._to_contract_from_model(model)
        except Exception as exc:  # noqa: BLE001
            raise PersistenceError(f"Unable to create task: {exc}") from exc

    def get_task(self, task_id: str, organization_id: str) -> TaskContract | None:
        if self._use_memory():
            record = self._tasks.get(task_id)
            if not record or record.organization_id != organization_id:
                return None
            return self._to_contract(record)

        session = self._session()
        model = (
            session.query(TaskModel)
            .filter(TaskModel.id == task_id, TaskModel.organization_id == organization_id)
            .first()
        )
        if not model:
            return None
        return self._to_contract_from_model(model)

    def list_entity_tasks(
        self,
        *,
        organization_id: str,
        entity_id: str,
        status: str | None = None,
        stage: str | None = None,
        include_archived: bool = False,
    ) -> list[TaskContract]:
        try:
            if self._use_memory():
                tasks: list[TaskContract] = []
                for record in self._tasks.values():
                    if record.organization_id != organization_id:
                        continue
                    if record.entity_id != entity_id:
                        continue
                    if not include_archived and record.archived_at is not None:
                        continue
                    if status and record.status != status:
                        continue
                    if stage and record.stage != stage:
                        continue
                    tasks.append(self._to_contract(record))
                tasks.sort(
                    key=lambda item: (
                        item.status in [TaskStatus.COMPLETED.value, TaskStatus.CANCELLED.value],
                        item.created_at,
                    )
                )
                return tasks

            session = self._session()
            query = session.query(TaskModel).filter(
                TaskModel.organization_id == organization_id,
                TaskModel.entity_id == entity_id,
            )
            if not include_archived:
                query = query.filter(TaskModel.archived_at.is_(None))
            if status:
                query = query.filter(TaskModel.status == status)
            if stage:
                query = query.filter(TaskModel.stage == stage)

            models = query.order_by(TaskModel.created_at.desc()).all()
            return [self._to_contract_from_model(model) for model in models]
        except Exception as exc:  # noqa: BLE001
            raise PersistenceError(f"Unable to list entity tasks: {exc}") from exc

    def list_tasks(
        self,
        *,
        organization_id: str,
        assigned_to: str | None = None,
        status: str | None = None,
        entity_type: str | None = None,
        priority: str | None = None,
        due_before: datetime | None = None,
        due_after: datetime | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[TaskContract], int]:
        try:
            if self._use_memory():
                tasks: list[TaskContract] = []
                for record in self._tasks.values():
                    if record.organization_id != organization_id:
                        continue
                    if record.archived_at is not None:
                        continue
                    if assigned_to and record.assigned_to != assigned_to:
                        continue
                    if status and record.status != status:
                        continue
                    if entity_type and record.entity_type != entity_type:
                        continue
                    if priority and record.priority != priority:
                        continue
                    if due_before and record.due_date and record.due_date > due_before:
                        continue
                    if due_after and record.due_date and record.due_date < due_after:
                        continue
                    tasks.append(self._to_contract(record))
                tasks.sort(key=lambda item: item.created_at, reverse=True)
                total = len(tasks)
                return tasks[skip: skip + limit], total

            session = self._session()
            query = session.query(TaskModel).filter(
                TaskModel.organization_id == organization_id,
                TaskModel.archived_at.is_(None),
            )
            if assigned_to:
                query = query.filter(TaskModel.assigned_to == assigned_to)
            if status:
                query = query.filter(TaskModel.status == status)
            if entity_type:
                query = query.filter(TaskModel.entity_type == entity_type)
            if priority:
                query = query.filter(TaskModel.priority == priority)
            if due_before:
                query = query.filter(TaskModel.due_date <= due_before)
            if due_after:
                query = query.filter(TaskModel.due_date >= due_after)

            total = query.count()
            models = query.order_by(TaskModel.created_at.desc()).offset(skip).limit(limit).all()
            return [self._to_contract_from_model(model) for model in models], total
        except Exception as exc:  # noqa: BLE001
            raise PersistenceError(f"Unable to list tasks: {exc}") from exc

    def update_task(
        self,
        *,
        task_id: str,
        organization_id: str,
        updates: dict[str, object],
    ) -> TaskContract | None:
        try:
            if self._use_memory():
                record = self._tasks.get(task_id)
                if not record or record.organization_id != organization_id or record.archived_at is not None:
                    return None
                old_status = record.status
                for field in ("title", "description", "assigned_to", "status", "priority", "due_date"):
                    if field in updates and updates[field] is not None:
                        setattr(record, field, updates[field])
                if record.status == TaskStatus.COMPLETED.value and old_status != TaskStatus.COMPLETED.value:
                    record.completed_at = datetime.utcnow()
                elif record.status != TaskStatus.COMPLETED.value and old_status == TaskStatus.COMPLETED.value:
                    record.completed_at = None
                record.updated_at = datetime.utcnow()
                self._tasks[task_id] = record
                return self._to_contract(record)

            session = self._session()
            model = (
                session.query(TaskModel)
                .filter(
                    TaskModel.id == task_id,
                    TaskModel.organization_id == organization_id,
                    TaskModel.archived_at.is_(None),
                )
                .first()
            )
            if not model:
                return None

            old_status = model.status
            for field in ("title", "description", "assigned_to", "status", "priority", "due_date"):
                if field in updates and updates[field] is not None:
                    setattr(model, field, updates[field])

            if model.status == TaskStatus.COMPLETED.value and old_status != TaskStatus.COMPLETED.value:
                model.completed_at = datetime.utcnow()
            elif model.status != TaskStatus.COMPLETED.value and old_status == TaskStatus.COMPLETED.value:
                model.completed_at = None

            session.commit()
            session.refresh(model)
            return self._to_contract_from_model(model)
        except Exception as exc:  # noqa: BLE001
            raise PersistenceError(f"Unable to update task: {exc}") from exc

    def archive_task(self, *, task_id: str, organization_id: str) -> TaskContract | None:
        try:
            if self._use_memory():
                record = self._tasks.get(task_id)
                if not record or record.organization_id != organization_id or record.archived_at is not None:
                    return None
                record.archived_at = datetime.utcnow()
                record.updated_at = datetime.utcnow()
                self._tasks[task_id] = record
                return self._to_contract(record)

            session = self._session()
            model = (
                session.query(TaskModel)
                .filter(
                    TaskModel.id == task_id,
                    TaskModel.organization_id == organization_id,
                    TaskModel.archived_at.is_(None),
                )
                .first()
            )
            if not model:
                return None
            model.archived_at = datetime.utcnow()
            session.commit()
            session.refresh(model)
            return self._to_contract_from_model(model)
        except Exception as exc:  # noqa: BLE001
            raise PersistenceError(f"Unable to archive task: {exc}") from exc

    def has_incomplete_tasks_for_stage(
        self,
        *,
        organization_id: str,
        entity_id: str,
        stage: str,
        source: str | None = None,
    ) -> bool:
        try:
            if self._use_memory():
                for record in self._tasks.values():
                    if record.organization_id != organization_id:
                        continue
                    if record.entity_id != entity_id:
                        continue
                    if record.stage != stage:
                        continue
                    if record.archived_at is not None:
                        continue
                    if source and record.source != source:
                        continue
                    if record.status in [TaskStatus.PENDING.value, TaskStatus.IN_PROGRESS.value]:
                        return True
                return False

            session = self._session()
            query = session.query(TaskModel).filter(
                TaskModel.organization_id == organization_id,
                TaskModel.entity_id == entity_id,
                TaskModel.stage == stage,
                TaskModel.archived_at.is_(None),
                TaskModel.status.in_([TaskStatus.PENDING.value, TaskStatus.IN_PROGRESS.value]),
            )
            if source:
                query = query.filter(TaskModel.source == source)
            return query.count() > 0
        except Exception as exc:  # noqa: BLE001
            raise PersistenceError(f"Unable to evaluate task guards: {exc}") from exc

    @staticmethod
    def _to_contract(record: TaskRecord) -> TaskContract:
        return TaskContract(
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
        )

    @staticmethod
    def _to_contract_from_model(model: TaskModel) -> TaskContract:
        return TaskContract(
            id=model.id,
            organization_id=model.organization_id,
            entity_id=model.entity_id,
            entity_type=model.entity_type,
            title=model.title,
            description=model.description,
            assigned_to=model.assigned_to,
            created_by=model.created_by,
            status=model.status,
            priority=model.priority,
            due_date=model.due_date,
            stage=model.stage,
            source=model.source,
            completed_at=model.completed_at,
            archived_at=model.archived_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
