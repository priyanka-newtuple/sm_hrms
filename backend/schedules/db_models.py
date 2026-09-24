"""Persistence for recurring entity schedules."""

from __future__ import annotations

import os
import uuid
from datetime import date, datetime
from typing import Any, ClassVar

from sqlalchemy import Boolean, Column, Date, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from database.manager import Base
from exceptions import ConflictError, PersistenceError
from schedules.models.interface import (
    RecurrenceRule,
    ScheduleCondition,
    ScheduleRecord,
    ScheduleTargetRecord,
    ScheduleTargetScope,
)


def _definitions_schema() -> str:
    return f"{os.environ.get('POSTGRES_APP_SCHEMA', 'public')}_definitions"


def _runtime_schema() -> str:
    return f"{os.environ.get('POSTGRES_APP_SCHEMA', 'public')}_runtime"


class ScheduleModel(Base):
    __tablename__ = "entity_schedules"
    __table_args__: ClassVar[tuple] = (
        UniqueConstraint("organization_id", "machine_name", "name", name="uq_entity_schedules_org_machine_name"),
        Index("ix_entity_schedules_org_machine", "organization_id", "machine_name"),
        {"schema": _definitions_schema()},
    )

    schedule_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), nullable=False)
    machine_name = Column(String(255), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    anchor_entity_type_id = Column(String(36), nullable=False)
    target_entity_type_id = Column(String(36), nullable=False)
    relation_def_id = Column(String(36), nullable=False)
    target_scope = Column(String(16), nullable=False, default=ScheduleTargetScope.ALL.value)
    recurrence_json = Column(JSONB, nullable=False)
    occurrences_per_batch = Column(Integer, nullable=False, default=1)
    lead_days = Column(Integer, nullable=False, default=30)
    timezone = Column(String(64), nullable=False, default="UTC")
    entity_data_json = Column(JSONB, nullable=False, default=dict)
    identifier_template = Column(String(512), nullable=False)
    owner_id = Column(String(128), nullable=True)
    assignee_id = Column(String(128), nullable=True)
    conditions_json = Column(JSONB, nullable=False, default=list)
    condition_mode = Column(String(8), nullable=False, default="all")
    is_enabled = Column(Boolean, nullable=False, default=True)
    starts_on = Column(Date, nullable=True)
    ends_on = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)


class ScheduleTargetModel(Base):
    __tablename__ = "entity_schedule_targets"
    __table_args__: ClassVar[tuple] = (
        UniqueConstraint("schedule_id", "anchor_entity_id", name="uq_entity_schedule_targets_schedule_anchor"),
        Index("ix_entity_schedule_targets_due", "organization_id", "is_enabled", "next_materialization_date"),
        {"schema": _runtime_schema()},
    )

    target_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), nullable=False)
    schedule_id = Column(String(36), nullable=False)
    anchor_entity_id = Column(String(36), nullable=False)
    next_due_date = Column(Date, nullable=False)
    next_materialization_date = Column(Date, nullable=False)
    assignee_id = Column(String(128), nullable=True)
    is_enabled = Column(Boolean, nullable=False, default=True)
    last_action_run_id = Column(String(36), nullable=True)
    last_result = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class SchedulesModelService:
    def __init__(self, database_service_manager: Any) -> None:
        self.database_service_manager = database_service_manager

    def _session(self):
        return self.database_service_manager.postgres_db_service().get_db_session()

    def create_schedule(self, values: dict[str, Any]) -> ScheduleRecord:
        schedule, _targets = self.create_schedule_with_targets(values, [])
        return schedule

    def create_schedule_with_targets(
        self,
        values: dict[str, Any],
        target_values: list[dict[str, Any]],
    ) -> tuple[ScheduleRecord, list[ScheduleTargetRecord]]:
        """Persist a schedule and all initial targets in one transaction."""
        db = self._session()
        try:
            row = ScheduleModel(**values)
            db.add(row)
            db.flush()
            target_rows = [
                ScheduleTargetModel(**target, schedule_id=row.schedule_id)
                for target in target_values
            ]
            db.add_all(target_rows)
            db.commit()
            db.refresh(row)
            for target_row in target_rows:
                db.refresh(target_row)
            return self._schedule(row), [self._target(target_row) for target_row in target_rows]
        except Exception as exc:
            db.rollback()
            if "uq_entity_schedules" in str(exc):
                raise ConflictError("a schedule with this name already exists for the workflow") from exc
            if "uq_entity_schedule_targets" in str(exc):
                raise ConflictError("an entity was selected more than once for this schedule") from exc
            raise PersistenceError(f"Unable to create schedule: {exc}") from exc
        finally:
            db.close()

    def get_schedule(self, organization_id: str, schedule_id: str) -> ScheduleRecord | None:
        db = self._session()
        try:
            row = db.query(ScheduleModel).filter_by(organization_id=organization_id, schedule_id=schedule_id).first()
            return self._schedule(row) if row else None
        finally:
            db.close()

    def list_schedules(self, organization_id: str, machine_name: str | None = None) -> list[ScheduleRecord]:
        db = self._session()
        try:
            query = db.query(ScheduleModel).filter_by(organization_id=organization_id)
            if machine_name:
                query = query.filter_by(machine_name=machine_name)
            return [self._schedule(row) for row in query.order_by(ScheduleModel.name.asc()).all()]
        finally:
            db.close()

    def list_enabled_all_scope_schedules(self) -> list[ScheduleRecord]:
        db = self._session()
        try:
            rows = db.query(ScheduleModel).filter_by(
                is_enabled=True,
                target_scope=ScheduleTargetScope.ALL.value,
            ).all()
            return [self._schedule(row) for row in rows]
        finally:
            db.close()

    def update_schedule(self, organization_id: str, schedule_id: str, values: dict[str, Any]) -> ScheduleRecord | None:
        db = self._session()
        try:
            row = db.query(ScheduleModel).filter_by(organization_id=organization_id, schedule_id=schedule_id).first()
            if row is None:
                return None
            for key, value in values.items():
                setattr(row, key, value)
            db.commit()
            db.refresh(row)
            return self._schedule(row)
        except Exception as exc:
            db.rollback()
            raise PersistenceError(f"Unable to update schedule: {exc}") from exc
        finally:
            db.close()

    def create_target(self, values: dict[str, Any]) -> ScheduleTargetRecord:
        db = self._session()
        try:
            row = ScheduleTargetModel(**values)
            db.add(row)
            db.commit()
            db.refresh(row)
            return self._target(row)
        except Exception as exc:
            db.rollback()
            if "uq_entity_schedule_targets" in str(exc):
                raise ConflictError("this entity is already a target of the schedule") from exc
            raise PersistenceError(f"Unable to create schedule target: {exc}") from exc
        finally:
            db.close()

    def get_target(
        self,
        organization_id: str,
        schedule_id: str,
        anchor_entity_id: str,
    ) -> ScheduleTargetRecord | None:
        db = self._session()
        try:
            row = db.query(ScheduleTargetModel).filter_by(
                organization_id=organization_id,
                schedule_id=schedule_id,
                anchor_entity_id=anchor_entity_id,
            ).first()
            return self._target(row) if row else None
        finally:
            db.close()

    def get_target_by_id(
        self, organization_id: str, schedule_id: str, target_id: str
    ) -> ScheduleTargetRecord | None:
        db = self._session()
        try:
            row = db.query(ScheduleTargetModel).filter_by(
                organization_id=organization_id,
                schedule_id=schedule_id,
                target_id=target_id,
            ).first()
            return self._target(row) if row else None
        finally:
            db.close()

    def delete_schedule(self, organization_id: str, schedule_id: str) -> bool:
        """Delete a schedule and its target subscriptions atomically."""
        db = self._session()
        try:
            schedule = db.query(ScheduleModel).filter_by(
                organization_id=organization_id, schedule_id=schedule_id
            ).first()
            if schedule is None:
                return False
            db.query(ScheduleTargetModel).filter_by(
                organization_id=organization_id, schedule_id=schedule_id
            ).delete(synchronize_session=False)
            db.delete(schedule)
            db.commit()
            return True
        except Exception as exc:
            db.rollback()
            raise PersistenceError(f"Unable to delete schedule: {exc}") from exc
        finally:
            db.close()

    def list_targets(self, organization_id: str, schedule_id: str) -> list[ScheduleTargetRecord]:
        db = self._session()
        try:
            rows = db.query(ScheduleTargetModel).filter_by(organization_id=organization_id, schedule_id=schedule_id).order_by(ScheduleTargetModel.created_at.asc()).all()
            return [self._target(row) for row in rows]
        finally:
            db.close()

    def list_due_targets(self, today: date, limit: int = 100) -> list[ScheduleTargetRecord]:
        db = self._session()
        try:
            rows = (
                db.query(ScheduleTargetModel)
                .join(ScheduleModel, ScheduleModel.schedule_id == ScheduleTargetModel.schedule_id)
                .filter(ScheduleTargetModel.is_enabled.is_(True))
                .filter(ScheduleModel.is_enabled.is_(True))
                .filter(ScheduleTargetModel.next_materialization_date <= today)
                .order_by(ScheduleTargetModel.next_materialization_date.asc())
                .limit(limit)
                .all()
            )
            return [self._target(row) for row in rows]
        finally:
            db.close()

    def advance_target(self, organization_id: str, target_id: str, *, due_date: date, materialization_date: date, run_id: str | None, result: str) -> None:
        db = self._session()
        try:
            row = db.query(ScheduleTargetModel).filter_by(organization_id=organization_id, target_id=target_id).first()
            if row is None:
                return
            row.next_due_date = due_date
            row.next_materialization_date = materialization_date
            row.last_action_run_id = run_id
            row.last_result = result
            db.commit()
        except Exception as exc:
            db.rollback()
            raise PersistenceError(f"Unable to advance schedule target: {exc}") from exc
        finally:
            db.close()

    def finish_once_target(
        self,
        organization_id: str,
        schedule_id: str,
        target_id: str,
        *,
        run_id: str | None,
        result: str,
    ) -> None:
        """Finish one target and complete the one-time schedule when none remain pending."""
        db = self._session()
        try:
            schedule = db.query(ScheduleModel).filter_by(
                organization_id=organization_id,
                schedule_id=schedule_id,
            ).with_for_update().first()
            if schedule is None:
                return
            target = db.query(ScheduleTargetModel).filter_by(
                organization_id=organization_id,
                schedule_id=schedule_id,
                target_id=target_id,
            ).first()
            if target is None:
                return
            target.is_enabled = False
            if run_id is not None:
                target.last_action_run_id = run_id
            target.last_result = result
            pending = db.query(ScheduleTargetModel).filter_by(
                organization_id=organization_id,
                schedule_id=schedule_id,
                last_result="queued_once",
            ).count()
            enabled = db.query(ScheduleTargetModel).filter_by(
                organization_id=organization_id,
                schedule_id=schedule_id,
                is_enabled=True,
            ).count()
            if pending == 0 and enabled == 0:
                schedule.is_enabled = False
                schedule.completed_at = func.now()
            db.commit()
        except Exception as exc:
            db.rollback()
            raise PersistenceError(f"Unable to finish one-time schedule target: {exc}") from exc
        finally:
            db.close()

    def finish_one_batch_target(
        self,
        organization_id: str,
        target_id: str,
        *,
        run_id: str | None,
    ) -> None:
        """Complete a one-batch invocation without completing its reusable schedule."""
        db = self._session()
        try:
            row = db.query(ScheduleTargetModel).filter_by(
                organization_id=organization_id,
                target_id=target_id,
            ).first()
            if row is None:
                return
            row.is_enabled = False
            row.last_action_run_id = run_id
            row.last_result = "queued_one_batch"
            db.commit()
        except Exception as exc:
            db.rollback()
            raise PersistenceError(f"Unable to finish schedule batch target: {exc}") from exc
        finally:
            db.close()

    def prepare_one_batch_target(self, organization_id: str, target_id: str) -> None:
        """Keep a one-batch target out of the automatic scheduler while its jobs queue."""
        db = self._session()
        try:
            row = db.query(ScheduleTargetModel).filter_by(
                organization_id=organization_id,
                target_id=target_id,
            ).first()
            if row is None:
                raise PersistenceError("Unable to prepare missing schedule batch target")
            row.is_enabled = False
            row.last_result = "one_batch_pending"
            db.commit()
        except PersistenceError:
            db.rollback()
            raise
        except Exception as exc:
            db.rollback()
            raise PersistenceError(f"Unable to prepare schedule batch target: {exc}") from exc
        finally:
            db.close()

    def complete_empty_once_schedule(self, organization_id: str, schedule_id: str) -> bool:
        """Complete an all-scope one-time schedule when its execution snapshot is empty."""
        db = self._session()
        try:
            schedule = db.query(ScheduleModel).filter_by(
                organization_id=organization_id,
                schedule_id=schedule_id,
                is_enabled=True,
            ).with_for_update().first()
            if schedule is None:
                return False
            target_count = db.query(ScheduleTargetModel).filter_by(
                organization_id=organization_id,
                schedule_id=schedule_id,
            ).count()
            if target_count:
                return False
            schedule.is_enabled = False
            schedule.completed_at = func.now()
            db.commit()
            return True
        except Exception as exc:
            db.rollback()
            raise PersistenceError(f"Unable to complete empty one-time schedule: {exc}") from exc
        finally:
            db.close()

    @staticmethod
    def _schedule(row: ScheduleModel) -> ScheduleRecord:
        return ScheduleRecord(
            schedule_id=row.schedule_id, organization_id=row.organization_id, machine_name=row.machine_name,
            name=row.name, description=row.description, anchor_entity_type_id=row.anchor_entity_type_id,
            target_entity_type_id=row.target_entity_type_id, relation_def_id=row.relation_def_id,
            target_scope=ScheduleTargetScope(row.target_scope),
            recurrence=RecurrenceRule.model_validate(row.recurrence_json),
            occurrences_per_batch=row.occurrences_per_batch, lead_days=row.lead_days,
            timezone=row.timezone, entity_data=dict(row.entity_data_json or {}), identifier_template=row.identifier_template,
            owner_id=row.owner_id, assignee_id=row.assignee_id,
            conditions=[ScheduleCondition.model_validate(item) for item in (row.conditions_json or [])],
            condition_mode=row.condition_mode, is_enabled=row.is_enabled, starts_on=row.starts_on,
            ends_on=row.ends_on, created_at=row.created_at, updated_at=row.updated_at,
            completed_at=row.completed_at,
        )

    @staticmethod
    def _target(row: ScheduleTargetModel) -> ScheduleTargetRecord:
        return ScheduleTargetRecord(
            target_id=row.target_id, organization_id=row.organization_id, schedule_id=row.schedule_id,
            anchor_entity_id=row.anchor_entity_id, next_due_date=row.next_due_date,
            next_materialization_date=row.next_materialization_date, assignee_id=row.assignee_id,
            is_enabled=row.is_enabled, last_action_run_id=row.last_action_run_id,
            last_result=row.last_result, created_at=row.created_at, updated_at=row.updated_at,
        )
