"""Persistence adapters for the unified audit_events table."""

from __future__ import annotations

import os
import uuid
from contextlib import contextmanager
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import func

from common.logger import logger
from common.enums import AuditMetadataType
from common.protocols import EntityAccessCheck, RolesServiceProtocol
from database.manager import Base
from audit.models.interface import AuditEventRecord
from exceptions import PersistenceError

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _audit_schema() -> str:
    """Return the Postgres schema that holds append-only audit tables."""
    app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
    return f"{app_schema}_audit"


class AuditEventModel(Base):
    """Unified audit event row. Lives in the `_audit` schema.

    Captures all system events going forward — entity events, transition
    attempts, auth events, comments, actions. Dual-written from existing
    legacy writers; the legacy per-domain audit tables (entity_events,
    transition_attempts, auth_events) remain untouched.
    """

    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_org_id", "organization_id"),
        Index("ix_audit_events_entity_id_ts", "entity_id", "event_timestamp"),
        Index("ix_audit_events_org_type", "organization_id", "metadata_type"),
        Index("ix_audit_events_event_type", "event_type"),
        {"schema": _audit_schema()},
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), nullable=False)
    metadata_type = Column(String(64), nullable=False)
    entity_type = Column(String(128), nullable=True)
    entity_id = Column(String(256), nullable=True)
    user_id = Column(String(36), nullable=True)
    event_type = Column(String(128), nullable=False)
    actor_type = Column(String(32), nullable=False)
    actor_id = Column(String(128), nullable=True)
    actor_name = Column(String(255), nullable=True)
    actor_role = Column(String(64), nullable=True)
    correlation_id = Column(String(36), nullable=True)
    idempotency_key = Column(String(128), nullable=True)
    source = Column(String(64), nullable=True)  # api | worker | system_job
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(512), nullable=True)
    before_state = Column(String(256), nullable=True)
    after_state = Column(String(256), nullable=True)
    event_metadata = Column("metadata", JSONB, nullable=True)
    event_timestamp = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


def _apply_equality_filters(query, **filters):
    """Apply equality filters to a query, skipping any that are None.

    A list/tuple value becomes an IN; an empty list means "no filter" rather
    than "match nothing", matching how the manager treats an empty list.
    """
    for column_name, value in filters.items():
        if value is None:
            continue
        column = getattr(AuditEventModel, column_name)
        if isinstance(value, (list, tuple)):
            if value:
                query = query.filter(column.in_(list(value)))
        else:
            query = query.filter(column == value)
    return query


class AuditEventsModelService:
    """Persistence service for the unified audit_events table.

    Audit writes are best-effort: a write failure here must never break the
    caller's main operation. The `emit_audit_event` method returns `None` on
    failure and logs a warning rather than raising.
    """

    audit_event_model = AuditEventModel

    def __init__(self, database_service_manager) -> None:
        self.database_service_manager = database_service_manager
        self.current_db = (
            database_service_manager.postgres_db_service()
            if database_service_manager and hasattr(database_service_manager, "postgres_db_service")
            else None
        )

    @contextmanager
    def _db_session(self):
        if self.current_db is None:
            raise RuntimeError("Database service manager unavailable")
        session = self.current_db.get_db_session()
        try:
            yield session
        finally:
            session.close()

    def check_entity_view_permission(
        self,
        *,
        roles_manager: RolesServiceProtocol,
        user_id: str,
        organization_id: str,
        entity_type_name: str,
        action: str,
    ) -> EntityAccessCheck:
        """Open a session and delegate to `roles_manager.evaluate_entity_access`.

        Returns allowed/denied plus any read-narrowing condition(s) on the granting
        role(s) (entity field permission filter) — the caller evaluates the
        condition(s) against the specific entity being read, the same way
        `entities/manager.py::guard_read` does, so an entity a role can't view
        directly can't be seen via its audit trail either.

        Session handling for cross-module `RolesServiceProtocol` calls lives
        here, in this module's own db_models, rather than in `manager.py`.
        """
        with self._db_session() as session:
            return roles_manager.evaluate_entity_access(
                session, user_id, organization_id, entity_type_name, action
            )

    def get_visible_and_masked_fields(
        self,
        *,
        roles_manager: RolesServiceProtocol,
        user_id: str,
        organization_id: str,
        entity_type_name: str,
    ) -> tuple[list[str] | None, list[str]]:
        """Open a session and delegate to `roles_manager.get_visible_fields`/`get_masked_fields`.

        Both calls share one session so callers get a consistent snapshot.
        """
        with self._db_session() as session:
            visible = roles_manager.get_visible_fields(session, user_id, organization_id, entity_type_name)
            masked = roles_manager.get_masked_fields(session, user_id, organization_id, entity_type_name)
            return visible, masked

    def emit_audit_event(
        self,
        *,
        organization_id: str,
        metadata_type: AuditMetadataType,
        event_type: str,
        actor_type: str,
        entity_type: str | None = None,
        entity_id: str | None = None,
        user_id: str | None = None,
        actor_id: str | None = None,
        actor_name: str | None = None,
        actor_role: str | None = None,
        correlation_id: str | None = None,
        idempotency_key: str | None = None,
        source: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        before_state: str | None = None,
        after_state: str | None = None,
        event_metadata: dict | None = None,
    ) -> AuditEventRecord | None:
        """Append a row to the unified audit_events table.

        Returns the persisted record, or None on failure. Idempotent on
        (organization_id, metadata_type, idempotency_key) when idempotency_key
        is set.
        """
        with self._db_session() as session:
            try:
                if idempotency_key is not None:
                    existing = (
                        session.query(AuditEventModel)
                        .filter_by(
                            organization_id=organization_id,
                            metadata_type=metadata_type,
                            idempotency_key=idempotency_key,
                        )
                        .first()
                    )
                    if existing is not None:
                        return self._convert_audit_model_to_record(existing)
                model = AuditEventModel(
                    id=str(uuid.uuid4()),
                    organization_id=organization_id,
                    metadata_type=metadata_type,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    user_id=user_id,
                    event_type=event_type,
                    actor_type=actor_type,
                    actor_id=actor_id,
                    actor_name=actor_name,
                    actor_role=actor_role,
                    correlation_id=correlation_id,
                    idempotency_key=idempotency_key,
                    source=source,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    before_state=before_state,
                    after_state=after_state,
                    event_metadata=dict(event_metadata or {}),
                )
                session.add(model)
                session.commit()
                session.refresh(model)
                return self._convert_audit_model_to_record(model)
            except IntegrityError as exc:
                session.rollback()
                logger.info("emit_audit_event IntegrityError (idempotency race): %s", exc)
                if idempotency_key is not None:
                    existing = (
                        session.query(AuditEventModel)
                        .filter_by(
                            organization_id=organization_id,
                            metadata_type=metadata_type,
                            idempotency_key=idempotency_key,
                        )
                        .first()
                    )
                    if existing is not None:
                        return self._convert_audit_model_to_record(existing)
                logger.info("emit_audit_event idempotency conflict, no existing record found")
                return None
            except Exception:
                session.rollback()
                logger.exception("emit_audit_event failed")
                return None

    def list_for_entity_paginated(
        self,
        *,
        organization_id: str,
        entity_id: str,
        metadata_type: str | list[str] | None = None,
        event_type: str | list[str] | None = None,
        user_id: str | None = None,
        date_from=None,
        date_to=None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AuditEventRecord], int]:
        """List audit events for an entity with DB-level pagination. Returns (items, total).

        ``metadata_type`` accepts either a single value or a list of values.
        Ordered newest-first (desc), same as `list_for_org_paginated`.
        """
        with self._db_session() as session:
            try:
                base = _apply_equality_filters(
                    session.query(AuditEventModel).filter_by(
                        organization_id=organization_id, entity_id=entity_id
                    ),
                    metadata_type=metadata_type,
                    event_type=event_type,
                    user_id=user_id,
                )
                if date_from is not None:
                    base = base.filter(AuditEventModel.event_timestamp >= date_from)
                if date_to is not None:
                    base = base.filter(AuditEventModel.event_timestamp < date_to)
                total = base.count()
                rows = (
                    base.order_by(AuditEventModel.event_timestamp.desc())
                    .offset(offset)
                    .limit(limit)
                    .all()
                )
                return [self._convert_audit_model_to_record(row) for row in rows], total
            except Exception as exc:
                logger.debug("list_for_entity_paginated failed: %s", exc)
                return [], 0

    def list_for_org_paginated(
        self,
        *,
        organization_id: str,
        metadata_type: str | list[str] | None = None,
        event_type: str | list[str] | None = None,
        user_id: str | None = None,
        actor_type: str | None = None,
        entity_ids: list[str] | None = None,
        date_from=None,
        date_to=None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AuditEventRecord], int]:
        """List org-wide audit events, newest first, with DB-level pagination.

        ``date_from``/``date_to`` (datetimes) bound ``event_timestamp`` to
        [date_from, date_to). Returns (items, total).
        """
        with self._db_session() as session:
            try:
                base = _apply_equality_filters(
                    session.query(AuditEventModel).filter_by(
                        organization_id=organization_id
                    ),
                    metadata_type=metadata_type,
                    event_type=event_type,
                    user_id=user_id,
                    actor_type=actor_type,
                    entity_id=entity_ids,
                )
                if date_from is not None:
                    base = base.filter(AuditEventModel.event_timestamp >= date_from)
                if date_to is not None:
                    base = base.filter(AuditEventModel.event_timestamp < date_to)
                total = base.count()
                rows = (
                    base.order_by(AuditEventModel.event_timestamp.desc())
                    .offset(offset)
                    .limit(limit)
                    .all()
                )
                return [self._convert_audit_model_to_record(row) for row in rows], total
            except Exception as exc:
                logger.debug("list_for_org_paginated failed: %s", exc)
                return [], 0

    def list_transitions_for_entity(
        self,
        *,
        organization_id: str,
        entity_id: str,
        workflow_id: str | None = None,
        status: str | None = None,
        limit: int | None = None,
    ) -> list[AuditEventRecord]:
        """List transition audit events with DB-level JSONB filtering on workflow_id and status."""
        with self._db_session() as session:
            try:
                base = session.query(AuditEventModel).filter_by(
                    organization_id=organization_id,
                    entity_id=entity_id,
                    metadata_type=AuditMetadataType.TRANSITION,
                )
                if workflow_id:
                    base = base.filter(
                        AuditEventModel.event_metadata["workflow_id"].as_string() == workflow_id
                    )
                if status:
                    base = base.filter(
                        AuditEventModel.event_metadata["status"].as_string() == status
                    )
                base = base.order_by(AuditEventModel.event_timestamp.asc())
                if limit:
                    base = base.limit(limit)
                return [self._convert_audit_model_to_record(row) for row in base.all()]
            except Exception as exc:
                logger.debug("list_transitions_for_entity failed: %s", exc)
                return []

    def find_by_idempotency_key(
        self,
        *,
        organization_id: str,
        metadata_type: AuditMetadataType,
        idempotency_key: str,
    ) -> AuditEventRecord | None:
        with self._db_session() as session:
            try:
                model = (
                    session.query(AuditEventModel)
                    .filter_by(
                        organization_id=organization_id,
                        metadata_type=metadata_type,
                        idempotency_key=idempotency_key,
                    )
                    .first()
                )
                return self._convert_audit_model_to_record(model) if model else None
            except Exception as exc:
                logger.debug("find_by_idempotency_key failed: %s", exc)
                return None

    def find_earliest_event_actor_id(
        self,
        *,
        organization_id: str,
        entity_id: str,
        event_type: str,
        actor_type: str,
    ) -> str | None:
        """Return the `actor_id` of the earliest matching event, or None if there is none.

        Ordered by timestamp then id, so events sharing a timestamp resolve to a
        stable answer. Raises on a read failure rather than returning None.
        """
        with self._db_session() as session:
            try:
                row = (
                    session.query(AuditEventModel.actor_id)
                    .filter(
                        AuditEventModel.organization_id == organization_id,
                        AuditEventModel.entity_id == entity_id,
                        AuditEventModel.event_type == event_type,
                        AuditEventModel.actor_type == actor_type,
                        AuditEventModel.actor_id.isnot(None),
                    )
                    .order_by(
                        AuditEventModel.event_timestamp.asc(),
                        AuditEventModel.id.asc(),
                    )
                    .first()
                )
            except Exception as exc:
                logger.error(
                    "earliest audit actor lookup failed: %s",
                    exc,
                    extra={
                        "organization_id": organization_id,
                        "entity_id": entity_id,
                        "event_type": event_type,
                        "actor_type": actor_type,
                    },
                    exc_info=True,
                )
                raise PersistenceError(
                    f"Unable to look up earliest audit actor: {exc}"
                ) from exc
        return row[0] if row else None

    def list_for_entity(
        self,
        *,
        organization_id: str,
        entity_id: str,
        metadata_type: AuditMetadataType | None = None,
        event_type: str | None = None,
        limit: int | None = None,
    ) -> list[AuditEventRecord]:
        with self._db_session() as session:
            try:
                query = session.query(AuditEventModel).filter_by(
                    organization_id=organization_id, entity_id=entity_id
                )
                if metadata_type is not None:
                    query = query.filter_by(metadata_type=metadata_type)
                if event_type is not None:
                    query = query.filter_by(event_type=event_type)
                query = query.order_by(AuditEventModel.event_timestamp.desc())
                if limit is not None and limit > 0:
                    query = query.limit(limit)
                return [self._convert_audit_model_to_record(row) for row in query.all()]
            except Exception as exc:
                logger.debug("list_for_entity failed: %s", exc)
                return []

    @staticmethod
    def _convert_audit_model_to_record(model: AuditEventModel) -> AuditEventRecord:
        return AuditEventRecord(
            id=model.id,
            organization_id=model.organization_id,
            metadata_type=AuditMetadataType(model.metadata_type),
            entity_type=model.entity_type,
            entity_id=model.entity_id,
            user_id=model.user_id,
            event_type=model.event_type,
            actor_type=model.actor_type,
            actor_id=model.actor_id,
            actor_name=model.actor_name,
            actor_role=model.actor_role,
            correlation_id=model.correlation_id,
            idempotency_key=model.idempotency_key,
            source=model.source,
            ip_address=model.ip_address,
            user_agent=model.user_agent,
            before_state=model.before_state,
            after_state=model.after_state,
            metadata=dict(model.event_metadata or {}),
            event_timestamp=model.event_timestamp,
        )
