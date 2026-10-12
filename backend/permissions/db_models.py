"""Persistence adapter for the global permission catalog.

Owns the Permission SQLAlchemy model and DB operations.
Role-scoped tables (role_permissions, field_permissions, user_roles) stay in roles/db_models.py.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import or_, Boolean, Column, DateTime, Index, String, Text, UniqueConstraint
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql import func

from common.logger import logger
from database.manager import Base
from exceptions import PersistenceError
from permissions.models.interface import DEFAULT_PERMISSION_DEFINITIONS

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


# ── SQLAlchemy model ───────────────────────────────────────────────────────────

class Permission(Base):
    """System permission catalog entry."""

    __tablename__ = "permissions"

    id          = Column(String(36),  primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), nullable=True, index=True)
    key         = Column(String(128), nullable=False, index=True)
    resource    = Column(String(64),  nullable=False, index=True)
    action      = Column(String(64),  nullable=False)
    description = Column(Text(),      nullable=True)
    is_system   = Column(Boolean(),   nullable=False, default=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at  = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("key", name="uq_permissions_key"),
        Index("ix_permissions_resource_action", "resource", "action"),
    )


# ── DB service ─────────────────────────────────────────────────────────────────

class PermissionsModelService:
    """DB operations for the global permission catalog."""

    def __init__(self, database_service_manager: Any = None) -> None:
        _ = database_service_manager
        self.module_name = "permissions"

    def ensure_default_permissions(self, db: Session) -> list[Permission]:
        """Idempotently seed the system permission catalog."""
        try:
            keys = [d["key"] for d in DEFAULT_PERMISSION_DEFINITIONS]
            existing = db.query(Permission).filter(Permission.key.in_(keys)).all()
            existing_by_key = {p.key: p for p in existing}
            created: list[Permission] = []
            for d in DEFAULT_PERMISSION_DEFINITIONS:
                if d["key"] in existing_by_key:
                    continue
                perm = Permission(
                    id=str(uuid.uuid4()),
                    key=d["key"],
                    resource=d["resource"],
                    action=d["action"],
                    description=d.get("description"),
                    is_system=True,
                )
                db.add(perm)
                created.append(perm)
            if created:
                db.commit()
            return (
                db.query(Permission)
                .filter(Permission.key.in_(keys))
                .order_by(Permission.resource, Permission.action, Permission.key)
                .all()
            )
        except SQLAlchemyError as exc:
            logger.exception(f"permissions.db_models.ensure_default_permissions failed: {exc}")
            db.rollback()
            raise PersistenceError(f"Unable to ensure default permissions: {exc}")

    def get_by_key(self, db: Session, key: str, organization_id: str | None = None) -> Permission | None:
        """Return a single permission by its key, or None if not found."""
        try:
            return db.query(Permission).filter(Permission.key == key, self._scope(organization_id)).first()
        except SQLAlchemyError as exc:
            logger.exception(f"permissions.db_models.get_by_key failed (key={key}): {exc}")
            raise PersistenceError(f"Unable to get permission by key: {exc}")

    def list_permissions(self, db: Session, organization_id: str | None = None) -> list[Permission]:
        """Return all system permissions ordered by resource and action."""
        try:
            return (
                db.query(Permission)
                .filter(self._scope(organization_id))
                .order_by(Permission.resource, Permission.action, Permission.key)
                .all()
            )
        except PersistenceError:
            raise
        except SQLAlchemyError as exc:
            logger.exception(f"permissions.db_models.list_permissions failed: {exc}")
            raise PersistenceError(f"Unable to list permissions: {exc}")

    @staticmethod
    def _scope(organization_id):
        return or_(Permission.organization_id.is_(None), Permission.organization_id == organization_id)

    def register(self, db, organization_id, payload):
        # Tenant in the key prevents accidental collisions or cross-tenant role grants.
        key = f"tenant.{organization_id}.{payload.namespace}.{payload.resource}:{payload.action}"
        # Serialize registrations with the same key; a retry keeps both identity and grants.
        from sqlalchemy import text
        if db.bind.dialect.name == 'postgresql':
            db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))'), {'key': key})
        try:
            row = self.get_by_key(db, key, organization_id)
            if row is None:
                row = Permission(key=key, organization_id=organization_id,
                                 resource=f"{payload.namespace}.{payload.resource}",
                                 action=payload.action, is_system=False)
                db.add(row)
            row.description = payload.description
            db.commit()
            db.refresh(row)
            return row
        except SQLAlchemyError as exc:
            db.rollback()
            raise PersistenceError('Unable to register tenant permission') from exc
