"""Persistence adapters for RBAC roles.

Owns Role, RolePermission, FieldPermission, UserRoleAssignment SQLAlchemy models.
Business rules and validation live in `roles/manager.py`.
"""

from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from permissions.db_models import PermissionsModelService

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Index, Integer, MetaData, String, Table, Text, UniqueConstraint
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, joinedload, relationship
from sqlalchemy.sql import func

from common.configuration import Configuration
from common.data_model import Enum
from common.enums import DefaultRole
from common.logger import logger
from common.protocols import EntityAccessCheck, EntityConditionSpec
from database.manager import Base
from exceptions import NotFoundError, PersistenceError, ValidationError
from permissions.models.interface import DEFAULT_PERMISSION_DEFINITIONS
from roles.models.interface import PermissionCheckResult
from roles.models.request import RoleCreateRequest, RoleDuplicateRequest, RoleUpdateRequest, UserRoleSetRequest


# ── Enums ──────────────────────────────────────────────────────────────────────

class PermissionAction(str, Enum):
    VIEW = "view"
    CREATE = "create"
    EDIT = "edit"
    DELETE = "delete"


# ── SQLAlchemy Models ──────────────────────────────────────────────────────────

class Role(Base):
    """A role defines a set of permissions within an organization."""

    __tablename__ = "roles"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(64), nullable=False)
    display_name = Column(String(128), nullable=False)
    description = Column(Text(), nullable=True)
    is_system = Column(Boolean(), nullable=False, default=False)
    priority = Column(Integer(), nullable=False, default=0)
    color = Column(String(32), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    archived_at = Column(DateTime(timezone=True), nullable=True)

    permissions = relationship("RolePermission", back_populates="role", cascade="all, delete-orphan")
    field_permissions = relationship("FieldPermission", back_populates="role", cascade="all, delete-orphan")
    transition_permissions = relationship("TransitionPermission", back_populates="role", cascade="all, delete-orphan")
    workflow_permissions = relationship("RoleWorkflowPermission", back_populates="role", cascade="all, delete-orphan")
    user_roles = relationship("UserRoleAssignment", back_populates="role", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_roles_org_name"),
    )


class RolePermission(Base):
    """Entity-level permission for a role."""

    __tablename__ = "role_permissions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    role_id = Column(String(36), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True)
    permission_key = Column(String(128), nullable=True, index=True)
    entity_type = Column(String(128), nullable=True)
    action = Column(String(32), nullable=True)
    allowed = Column(Boolean(), nullable=False, default=True)
    # Optional read-narrowing condition (entity field permission filter) — all four
    # nullable together; null across the board means unchanged, full-access behavior.
    entity_field = Column(String(128), nullable=True)
    operator = Column(String(32), nullable=True)
    value_source = Column(String(32), nullable=True)
    condition_value = Column(String(256), nullable=True)
    read_filter = Column(JSON(none_as_null=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    role = relationship("Role", back_populates="permissions")

    __table_args__ = ()


class FieldPermission(Base):
    """Field-level permission for a role."""

    __tablename__ = "field_permissions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    role_id = Column(String(36), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_type = Column(String(128), nullable=False)
    field_name = Column(String(128), nullable=False)
    can_view = Column(Boolean(), nullable=False, default=True)
    can_edit = Column(Boolean(), nullable=False, default=True)
    mask_value = Column(Boolean(), nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    role = relationship("Role", back_populates="field_permissions")

    __table_args__ = (
        UniqueConstraint("role_id", "entity_type", "field_name", name="uq_field_permissions_unique"),
    )


class TransitionPermission(Base):
    """Per-role transition allow-list entry."""

    __tablename__ = "transition_permissions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    role_id = Column(String(36), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True)
    machine_name = Column(String(128), nullable=False)
    transition_key = Column(String(128), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    role = relationship("Role", back_populates="transition_permissions")

    __table_args__ = (
        UniqueConstraint("role_id", "machine_name", "transition_key", name="uq_transition_permissions_unique"),
    )


class RoleWorkflowPermission(Base):
    """Workflow allow-list entry. No rows for a role means unrestricted access."""

    __tablename__ = "role_workflow_permissions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    role_id = Column(String(36), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True)
    machine_name = Column(String(128), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    role = relationship("Role", back_populates="workflow_permissions")

    __table_args__ = (
        UniqueConstraint("role_id", "machine_name", name="uq_role_workflow_permissions_unique"),
    )


class UserRoleAssignment(Base):
    """Links a user to a role within an organization."""

    __tablename__ = "user_roles"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id = Column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role_id = Column(String(36), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True)
    assigned_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    assigned_by = Column(String(36), nullable=True)

    role = relationship("Role", back_populates="user_roles")

    __table_args__ = (
        UniqueConstraint("user_id", "organization_id", "role_id", name="uq_user_roles_unique"),
        Index("ix_user_roles_user_org", "user_id", "organization_id"),
    )


# ── DB service ─────────────────────────────────────────────────────────────────

class RolesModelService:
    """DB operations for roles.

    Most methods still take `db: Session` supplied by the FastAPI request
    (existing convention for this module). Batched read methods added for
    manager-side composition (e.g. `get_workflow_access_rows`) self-manage
    their own session via `_db_session()`, matching every other module's
    db_models.py — first step of moving this file onto that same
    convention, not a full migration.
    """

    def __init__(
        self,
        database_service_manager: Any = None,
        permissions_model_service: PermissionsModelService | None = None,
    ) -> None:
        """Initialize the roles persistence service."""
        self.module_name = "roles"
        self._permissions_svc = permissions_model_service
        self._organizations_svc: Any = None
        self.database_service_manager = database_service_manager

    @contextmanager
    def _db_session(self):
        """Yield a session opened from this service's own connection pool."""
        session = self.database_service_manager.postgres_db_service().get_db_session()
        try:
            yield session
        finally:
            session.close()

    def register_organizations_service(self, organizations_model_service: Any) -> None:
        """Wire the organizations service in from main.py once it's constructed.

        roles is built before organizations during app startup, so this can't
        be a constructor argument — it's set once main.py finishes wiring.
        """
        self._organizations_svc = organizations_model_service

    # ── Permission evaluation ───────────────────────────────────────────────

    def _get_user_roles_for_org(self, db: Session, user_id: str, organization_id: str) -> list[Role]:
        """Load roles assigned to a user in an organization."""
        assignments = (
            db.query(UserRoleAssignment)
            .filter(
                UserRoleAssignment.user_id == user_id,
                UserRoleAssignment.organization_id == organization_id,
            )
            .all()
        )
        if not assignments:
            return []
        role_ids = [a.role_id for a in assignments]
        return db.query(Role).filter(Role.id.in_(role_ids), Role.archived_at.is_(None)).all()

    def _role_grants_permission(self, role: Role, permission_key: str) -> bool:
        """Return True if the role grants the given permission key."""
        if role.is_system:
            return True
        return any(
            perm.allowed and perm.permission_key == permission_key
            for perm in role.permissions
        )

    def check_permission(
        self, db: Session, user_id: str, organization_id: str, permission_key: str
    ) -> PermissionCheckResult:
        """Evaluate whether a user has a permission in an organization."""
        try:
            if self._permissions_svc is None:
                return PermissionCheckResult.deny(permission_key, "permissions service not configured")
            if not self._permissions_svc.get_by_key(db, permission_key):
                return PermissionCheckResult.deny(permission_key, "unknown permission key")

            roles = self._get_user_roles_for_org(db, user_id, organization_id)
            if not roles:
                return PermissionCheckResult.deny(permission_key, "user has no roles in this organization")

            if any(self._role_grants_permission(role, permission_key) for role in roles):
                return PermissionCheckResult.allow(permission_key)

            return PermissionCheckResult.deny(permission_key, "no role grants this permission")
        except SQLAlchemyError as exc:
            logger.exception(
                f"roles.db_models.check_permission failed (user_id={user_id} org_id={organization_id} key={permission_key}): {exc}"
            )
            raise PersistenceError(f"Unable to evaluate permission: {exc}")

    def check_permission_self_managed(
        self, user_id: str, organization_id: str, permission_key: str
    ) -> PermissionCheckResult:
        """Same evaluation as `check_permission`, self-managing its own
        session — for manager-side callers with no request-scoped session
        of their own (e.g. `enroll_entity_for_actor`'s internal permission
        check)."""
        with self._db_session() as db:
            return self.check_permission(db, user_id, organization_id, permission_key)

    # ── Role reads ──────────────────────────────────────────────────────────

    def list_roles(self, db: Session, organization_id: str) -> list[Role]:
        """List non-archived roles for an organization."""
        try:
            return (
                db.query(Role)
                .filter(Role.organization_id == organization_id, Role.archived_at.is_(None))
                .order_by(Role.priority.desc(), Role.name)
                .all()
            )
        except SQLAlchemyError as exc:
            logger.exception(f"roles.db_models.list_roles failed (organization_id={organization_id}): {exc}")
            raise PersistenceError(f"Unable to list roles: {exc}")

    def get_role(self, db: Session, role_id: str, organization_id: str) -> Role | None:
        """Get one non-archived role by id scoped to an organization."""
        try:
            return (
                db.query(Role)
                .filter(Role.id == role_id, Role.organization_id == organization_id, Role.archived_at.is_(None))
                .first()
            )
        except SQLAlchemyError as exc:
            logger.exception(
                f"roles.db_models.get_role failed (organization_id={organization_id} role_id={role_id}): {exc}"
            )
            raise PersistenceError(f"Unable to get role: {exc}")

    def get_role_by_id(self, db: Session, role_id: str) -> Role | None:
        """Get a non-archived role by id without org scope — for superadmin use only."""
        try:
            return db.query(Role).filter(Role.id == role_id, Role.archived_at.is_(None)).first()
        except SQLAlchemyError as exc:
            logger.exception(f"roles.db_models.get_role_by_id failed (role_id={role_id}): {exc}")
            raise PersistenceError(f"Unable to get role: {exc}")

    def get_role_by_name(self, db: Session, organization_id: str, name: str) -> Role | None:
        """Get one non-archived role by name scoped to an organization."""
        try:
            return (
                db.query(Role)
                .filter(Role.organization_id == organization_id, Role.name == name, Role.archived_at.is_(None))
                .first()
            )
        except SQLAlchemyError as exc:
            logger.exception(f"roles.db_models.get_role_by_name failed (organization_id={organization_id} name={name}): {exc}")
            raise PersistenceError(f"Unable to get role by name: {exc}")

    def count_role_assignments(self, db: Session, role_id: str, organization_id: str) -> int:
        """Count role assignments for a role in an organization."""
        try:
            return (
                db.query(UserRoleAssignment)
                .filter(
                    UserRoleAssignment.role_id == role_id,
                    UserRoleAssignment.organization_id == organization_id,
                )
                .count()
            )
        except SQLAlchemyError as exc:
            logger.exception(
                f"roles.db_models.count_role_assignments failed (organization_id={organization_id} role_id={role_id}): {exc}"
            )
            raise PersistenceError(f"Unable to count role assignments: {exc}")

    # ── Role mutations ──────────────────────────────────────────────────────

    def create_role(self, db: Session, organization_id: str, payload: RoleCreateRequest) -> Role:
        """Create a custom role and its permissions."""
        try:
            role = Role(
                id=str(uuid.uuid4()),
                organization_id=organization_id,
                name=payload.name,
                display_name=payload.display_name,
                description=payload.description,
                is_system=False,
                priority=int(payload.priority or 0),
                color=payload.color,
            )
            db.add(role)
            db.flush()

            for perm in payload.permissions:
                db.add(
                    RolePermission(
                        id=str(uuid.uuid4()),
                        role_id=role.id,
                        permission_key=perm.permission_key,
                        entity_type=None,
                        action=None,
                        allowed=True,
                    )
                )

            for ep in payload.entity_permissions or []:
                db.add(
                    RolePermission(
                        id=str(uuid.uuid4()),
                        role_id=role.id,
                        permission_key=None,
                        entity_type=ep.entity_type,
                        action=ep.action,
                        allowed=ep.allowed,
                        entity_field=ep.entity_field,
                        operator=ep.operator,
                        value_source=ep.value_source,
                        condition_value=ep.condition_value,
                        read_filter=ep.read_filter.model_dump() if ep.read_filter else None,
                    )
                )

            for fp in payload.field_permissions or []:
                db.add(
                    FieldPermission(
                        id=str(uuid.uuid4()),
                        role_id=role.id,
                        entity_type=fp.entity_type,
                        field_name=fp.field_name,
                        can_view=fp.can_view,
                        can_edit=fp.can_edit,
                        mask_value=fp.mask_value,
                    )
                )

            for tp in payload.transition_permissions or []:
                db.add(
                    TransitionPermission(
                        id=str(uuid.uuid4()),
                        role_id=role.id,
                        machine_name=tp.machine_name,
                        transition_key=tp.transition_key,
                    )
                )

            for wp in payload.workflow_permissions or []:
                db.add(
                    RoleWorkflowPermission(
                        id=str(uuid.uuid4()),
                        role_id=role.id,
                        machine_name=wp.machine_name,
                    )
                )

            db.commit()
            db.refresh(role)
            return role
        except IntegrityError as exc:
            logger.warning(
                f"roles.db_models.create_role conflict (organization_id={organization_id} name={payload.name}): {exc}"
            )
            db.rollback()
            raise ValidationError(f"Role with name '{payload.name}' already exists")
        except SQLAlchemyError as exc:
            logger.exception(f"roles.db_models.create_role failed (organization_id={organization_id} name={payload.name}): {exc}")
            db.rollback()
            raise PersistenceError(f"Unable to create role: {exc}")

    def update_role(self, db: Session, role: Role, payload: RoleUpdateRequest) -> Role:
        """Update role fields and optionally replace permissions."""
        try:
            if payload.name is not None:
                role.name = payload.name
            if payload.display_name is not None:
                role.display_name = payload.display_name
            if payload.description is not None:
                role.description = payload.description
            if payload.priority is not None:
                role.priority = int(payload.priority)
            if payload.color is not None:
                role.color = payload.color

            if payload.permissions is not None:
                db.query(RolePermission).filter(
                    RolePermission.role_id == role.id,
                    RolePermission.permission_key.isnot(None),
                ).delete()
                for perm in payload.permissions:
                    db.add(
                        RolePermission(
                            id=str(uuid.uuid4()),
                            role_id=role.id,
                            permission_key=perm.permission_key,
                            entity_type=None,
                            action=None,
                            allowed=True,
                        )
                    )

            if payload.entity_permissions is not None:
                db.query(RolePermission).filter(
                    RolePermission.role_id == role.id,
                    RolePermission.permission_key.is_(None),
                ).delete()
                for ep in payload.entity_permissions:
                    db.add(
                        RolePermission(
                            id=str(uuid.uuid4()),
                            role_id=role.id,
                            permission_key=None,
                            entity_type=ep.entity_type,
                            action=ep.action,
                            allowed=ep.allowed,
                            entity_field=ep.entity_field,
                            operator=ep.operator,
                            value_source=ep.value_source,
                            condition_value=ep.condition_value,
                            read_filter=ep.read_filter.model_dump() if ep.read_filter else None,
                        )
                    )

            if payload.field_permissions is not None:
                db.query(FieldPermission).filter(FieldPermission.role_id == role.id).delete()
                for fp in payload.field_permissions:
                    db.add(
                        FieldPermission(
                            id=str(uuid.uuid4()),
                            role_id=role.id,
                            entity_type=fp.entity_type,
                            field_name=fp.field_name,
                            can_view=fp.can_view,
                            can_edit=fp.can_edit,
                            mask_value=fp.mask_value,
                        )
                    )

            if payload.transition_permissions is not None:
                db.query(TransitionPermission).filter(TransitionPermission.role_id == role.id).delete()
                for tp in payload.transition_permissions:
                    db.add(
                        TransitionPermission(
                            id=str(uuid.uuid4()),
                            role_id=role.id,
                            machine_name=tp.machine_name,
                            transition_key=tp.transition_key,
                        )
                    )

            if payload.workflow_permissions is not None:
                db.query(RoleWorkflowPermission).filter(RoleWorkflowPermission.role_id == role.id).delete()
                allowed_workflows = {wp.machine_name for wp in payload.workflow_permissions}
                if allowed_workflows:
                    db.query(TransitionPermission).filter(
                        TransitionPermission.role_id == role.id,
                        TransitionPermission.machine_name.notin_(allowed_workflows),
                    ).delete(synchronize_session=False)
                for wp in payload.workflow_permissions:
                    db.add(
                        RoleWorkflowPermission(
                            id=str(uuid.uuid4()),
                            role_id=role.id,
                            machine_name=wp.machine_name,
                        )
                    )

            db.commit()
            db.refresh(role)
            return role
        except SQLAlchemyError as exc:
            logger.exception(
                f"roles.db_models.update_role failed (organization_id={role.organization_id} role_id={role.id}): {exc}"
            )
            db.rollback()
            raise PersistenceError(f"Unable to update role: {exc}")

    def delete_role(self, db: Session, role: Role) -> None:
        """Soft-delete a role and reassign affected users to the viewer role."""
        try:
            viewer_role = self.get_role_by_name(db, role.organization_id, DefaultRole.VIEWER.value)
            if viewer_role:
                assignments = (
                    db.query(UserRoleAssignment)
                    .filter(
                        UserRoleAssignment.role_id == role.id,
                        UserRoleAssignment.organization_id == role.organization_id,
                    )
                    .all()
                )
                for assignment in assignments:
                    assignment.role_id = viewer_role.id
            role.archived_at = datetime.now(UTC)
            db.commit()
        except SQLAlchemyError as exc:
            logger.exception(
                f"roles.db_models.delete_role failed (organization_id={role.organization_id} role_id={role.id}): {exc}"
            )
            db.rollback()
            raise PersistenceError(f"Unable to archive role: {exc}")

    def duplicate_role(self, db: Session, source: Role, organization_id: str, payload: RoleDuplicateRequest) -> Role:
        """Duplicate a role and copy permissions."""
        try:
            new_role = Role(
                id=str(uuid.uuid4()),
                organization_id=organization_id,
                name=payload.name,
                display_name=payload.display_name,
                description=source.description,
                is_system=False,
                priority=int(source.priority),
                color=source.color,
            )
            db.add(new_role)
            db.flush()

            for perm in source.permissions:
                db.add(
                    RolePermission(
                        id=str(uuid.uuid4()),
                        role_id=new_role.id,
                        permission_key=perm.permission_key,
                        entity_type=perm.entity_type,
                        action=perm.action,
                        allowed=perm.allowed,
                        entity_field=perm.entity_field,
                        operator=perm.operator,
                        value_source=perm.value_source,
                        condition_value=perm.condition_value,
                        read_filter=perm.read_filter,
                    )
                )

            for fp in source.field_permissions:
                db.add(
                    FieldPermission(
                        id=str(uuid.uuid4()),
                        role_id=new_role.id,
                        entity_type=fp.entity_type,
                        field_name=fp.field_name,
                        can_view=fp.can_view,
                        can_edit=fp.can_edit,
                        mask_value=fp.mask_value,
                    )
                )

            for tp in source.transition_permissions:
                db.add(
                    TransitionPermission(
                        id=str(uuid.uuid4()),
                        role_id=new_role.id,
                        machine_name=tp.machine_name,
                        transition_key=tp.transition_key,
                    )
                )

            for wp in source.workflow_permissions:
                db.add(
                    RoleWorkflowPermission(
                        id=str(uuid.uuid4()),
                        role_id=new_role.id,
                        machine_name=wp.machine_name,
                    )
                )

            db.commit()
            db.refresh(new_role)
            return new_role
        except IntegrityError as exc:
            logger.warning(
                f"roles.db_models.duplicate_role conflict (organization_id={organization_id} name={payload.name} source_role_id={source.id}): {exc}"
            )
            db.rollback()
            raise ValidationError(f"Role with name '{payload.name}' already exists")
        except SQLAlchemyError as exc:
            logger.exception(
                f"roles.db_models.duplicate_role failed (organization_id={organization_id} source_role_id={source.id}): {exc}"
            )
            db.rollback()
            raise PersistenceError(f"Unable to duplicate role: {exc}")

    # ── User role assignment ────────────────────────────────────────────────

    def get_user_roles(self, db: Session, user_id: str, organization_id: str) -> list[UserRoleAssignment]:
        """List role assignment rows for a user in an organization."""
        try:
            return (
                db.query(UserRoleAssignment)
                .filter(
                    UserRoleAssignment.user_id == user_id,
                    UserRoleAssignment.organization_id == organization_id,
                )
                .all()
            )
        except SQLAlchemyError as exc:
            logger.exception(
                f"roles.db_models.get_user_roles failed (organization_id={organization_id} user_id={user_id}): {exc}"
            )
            raise PersistenceError(f"Unable to list user role assignments: {exc}")

    def get_user_roles_with_permissions(self, db: Session, user_id: str, org_id: str) -> list[Role]:
        """Load roles with permissions eagerly for a user/org."""
        try:
            assignments = (
                db.query(UserRoleAssignment)
                .filter(
                    UserRoleAssignment.user_id == user_id,
                    UserRoleAssignment.organization_id == org_id,
                )
                .options(joinedload(UserRoleAssignment.role).joinedload(Role.permissions))
                .all()
            )
            return [a.role for a in assignments]
        except SQLAlchemyError as exc:
            logger.exception(
                f"roles.db_models.get_user_roles_with_permissions failed (org_id={org_id} user_id={user_id}): {exc}"
            )
            raise PersistenceError(f"Unable to get user roles with permissions: {exc}")

    def get_users_with_permission(self, db: Session, org_id: str, permission_key: str) -> list[str]:
        """Return user IDs of all users in org_id that have the given permission_key."""
        try:
            assignments = (
                db.query(UserRoleAssignment)
                .filter(UserRoleAssignment.organization_id == org_id)
                .options(joinedload(UserRoleAssignment.role).joinedload(Role.permissions))
                .all()
            )
            user_ids: list[str] = []
            for assignment in assignments:
                role = assignment.role
                if role is None:
                    continue
                if role.is_system:
                    user_ids.append(str(assignment.user_id))
                    continue
                for perm in role.permissions:
                    if perm.permission_key == permission_key and perm.allowed:
                        user_ids.append(str(assignment.user_id))
                        break
            return list(dict.fromkeys(user_ids))
        except SQLAlchemyError as exc:
            logger.exception(
                f"roles.db_models.get_users_with_permission failed (org_id={org_id} permission_key={permission_key}): {exc}"
            )
            raise PersistenceError(f"Unable to get users with permission: {exc}")

    def get_field_permissions_for_roles(
        self, db: Session, role_ids: list[str], entity_type: str
    ) -> list[FieldPermission]:
        """List field-permission rows for the given roles and entity type."""
        try:
            return (
                db.query(FieldPermission)
                .filter(FieldPermission.role_id.in_(role_ids), FieldPermission.entity_type == entity_type)
                .all()
            )
        except SQLAlchemyError as exc:
            logger.exception(
                f"roles.db_models.get_field_permissions_for_roles failed (entity_type={entity_type} role_ids={role_ids}): {exc}"
            )
            raise PersistenceError(f"Unable to get field permissions: {exc}")

    def get_field_permissions_for_roles_and_types(
        self, db: Session, role_ids: list[str], entity_types: set[str]
    ) -> list[FieldPermission]:
        """Load every field rule needed to compile one list-page policy set."""
        if not role_ids or not entity_types:
            return []
        try:
            return (
                db.query(FieldPermission)
                .filter(
                    FieldPermission.role_id.in_(role_ids),
                    FieldPermission.entity_type.in_(entity_types),
                )
                .all()
            )
        except SQLAlchemyError as exc:
            logger.exception("roles.db_models bulk field permission lookup failed")
            raise PersistenceError(f"Unable to get bulk field permissions: {exc}") from exc

    def check_transition_permission(
        self, user_id: str, org_id: str, machine_name: str, transition_key: str
    ) -> bool:
        """Per-role deny-by-default: system roles pass, no entries = denied, else must match.

        Self-manages its own session, like `get_workflow_access_rows`, so callers do not have to
        thread a request-scoped session down through the workflow manager.
        """
        with self._db_session() as db:
            return self._check_transition_permission(
                db, user_id, org_id, machine_name, transition_key
            )

    def _check_transition_permission(
        self, db: Session, user_id: str, org_id: str, machine_name: str, transition_key: str
    ) -> bool:
        """Evaluate the per-role transition permission rows on an open session."""
        try:
            roles = self._get_user_roles_for_org(db, user_id, org_id)
            if not roles:
                return False
            for role in roles:
                if role.is_system:
                    return True
                has_any = db.query(TransitionPermission).filter(TransitionPermission.role_id == role.id).count() > 0
                if not has_any:
                    continue
                match = db.query(TransitionPermission).filter(
                    TransitionPermission.role_id == role.id,
                    TransitionPermission.machine_name == machine_name,
                    TransitionPermission.transition_key == transition_key,
                ).first()
                if match:
                    return True
            return False
        except SQLAlchemyError as exc:
            logger.exception(f"roles.db_models.check_transition_permission failed (user={user_id} org={org_id}): {exc}")
            raise PersistenceError(f"Unable to evaluate transition permission: {exc}")

    def get_workflow_access_rows(
        self, user_id: str, org_id: str
    ) -> tuple[list[Role], list[RolePermission], list[RoleWorkflowPermission]]:
        """Batched read of everything needed to decide workflow access scope.

        Self-manages its own session (no `db` param) — 3 queries total
        regardless of how many roles the user holds: roles, then their
        catalog permission rows and workflow-scope rows in one batch each.
        The actual RBAC decision (is_system bypass, workflow:read grant,
        scope accumulation) is composed by `roles/manager.py`, not here."""
        with self._db_session() as db:
            try:
                roles = self._get_user_roles_for_org(db, user_id, org_id)
                role_ids = [role.id for role in roles]
                if not role_ids:
                    return roles, [], []
                permissions = (
                    db.query(RolePermission).filter(RolePermission.role_id.in_(role_ids)).all()
                )
                workflow_permissions = (
                    db.query(RoleWorkflowPermission)
                    .filter(RoleWorkflowPermission.role_id.in_(role_ids))
                    .all()
                )
                return roles, permissions, workflow_permissions
            except SQLAlchemyError as exc:
                logger.exception(
                    f"roles.db_models.get_workflow_access_rows failed (user={user_id} org={org_id}): {exc}"
                )
                raise PersistenceError(f"Unable to load workflow access rows: {exc}")

    def sync_transition_permissions_on_publish(
        self,
        org_id: str,
        machine_name: str,
        renames: list[tuple[str, str]],
        valid_keys: list[str],
    ) -> None:
        """Apply rename cascades and orphan removal for one workflow's transition permissions.

        Opens and commits its own session, like the other self-managed methods here. It
        previously took the caller's session and left the commit to them, but its only caller is
        the workflow publish endpoint, whose session comes from `get_db` and is closed without
        committing — so every cascade was silently rolled back and no permission ever moved.
        """
        with self._db_session() as db:
            try:
                role_ids = [
                    r.id for r in db.query(Role).filter(Role.organization_id == org_id).all()
                ]
                if not role_ids:
                    return
                base = db.query(TransitionPermission).filter(
                    TransitionPermission.role_id.in_(role_ids),
                    TransitionPermission.machine_name == machine_name,
                )
                for old_key, new_key in renames:
                    base.filter(TransitionPermission.transition_key == old_key).update(
                        {"transition_key": new_key}, synchronize_session=False
                    )
                base.filter(TransitionPermission.transition_key.notin_(valid_keys)).delete(
                    synchronize_session=False
                )
                db.commit()
            except SQLAlchemyError as exc:
                db.rollback()
                logger.exception(
                    f"roles.db_models.sync_transition_permissions_on_publish failed "
                    f"(org={org_id} machine={machine_name}): {exc}"
                )
                raise PersistenceError(
                    f"Unable to sync transition permissions on publish: {exc}"
                ) from exc

    def get_all_field_permissions_for_roles(
        self, db: Session, role_ids: list[str]
    ) -> list[FieldPermission]:
        """Return all field permissions across all entity types for the given roles."""
        try:
            return (
                db.query(FieldPermission)
                .filter(FieldPermission.role_id.in_(role_ids))
                .all()
            )
        except SQLAlchemyError as exc:
            logger.exception(f"roles.db_models.get_all_field_permissions_for_roles failed (role_ids={role_ids}): {exc}")
            raise PersistenceError(f"Unable to get all field permissions: {exc}")

    def ensure_superadmin_role_in_org(self, db: Session, user_id: str, org_id: str) -> None:
        """Ensure superadmin user has the superadmin role assigned in the target org."""
        existing = (
            db.query(UserRoleAssignment)
            .filter(
                UserRoleAssignment.user_id == user_id,
                UserRoleAssignment.organization_id == org_id,
            )
            .join(Role, UserRoleAssignment.role_id == Role.id)
            .filter(Role.name == DefaultRole.SUPERADMIN.value)
            .first()
        )
        if existing:
            return
        superadmin_role = (
            db.query(Role)
            .filter(Role.organization_id == org_id, Role.name == DefaultRole.SUPERADMIN.value)
            .first()
        )
        if superadmin_role is None:
            roles = self.ensure_default_roles(db, org_id)
            superadmin_role = next((r for r in roles if r.name == DefaultRole.SUPERADMIN.value), None)
        if superadmin_role is None:
            return
        self.assign_role_to_user(db, user_id, org_id, superadmin_role.id)


    def check_entity_permission(
        self, db: Session, user_id: str, org_id: str, entity_type: str, action: str
    ) -> bool:
        """Return True if user has permission to perform action on entity_type in org."""
        return self.evaluate_entity_access(db, user_id, org_id, entity_type, action).allowed

    def evaluate_entity_access(
        self, db: Session, user_id: str, org_id: str, entity_type: str, action: str
    ) -> EntityAccessCheck:
        """Return whether the user's roles grant `action` on `entity_type`, and any
        read-narrowing conditions attached to the granting role(s) (entity field
        permission filter). Most-permissive-role-wins: if any granting role is
        unconditional (`is_system`, or an entity permission row with no condition set),
        the result is unconditional even if another granting role has a condition."""
        try:
            assignments = (
                db.query(UserRoleAssignment)
                .filter(
                    UserRoleAssignment.user_id == user_id,
                    UserRoleAssignment.organization_id == org_id,
                )
                .all()
            )
            if not assignments:
                return EntityAccessCheck(allowed=False)
            role_ids = [a.role_id for a in assignments]
            roles = db.query(Role).filter(Role.id.in_(role_ids)).all()
            conditions: list[EntityConditionSpec] = []
            for role in roles:
                if role.is_system:
                    return EntityAccessCheck(allowed=True)
                for perm in role.permissions:
                    if (
                        perm.permission_key is None
                        and perm.entity_type == entity_type
                        and perm.action == action
                        and perm.allowed
                    ):
                        condition = EntityConditionSpec.from_permission(perm)
                        if condition is not None:
                            conditions.append(condition)
                        else:
                            return EntityAccessCheck(allowed=True)
            if conditions:
                return EntityAccessCheck(allowed=True, conditions=conditions)
            return EntityAccessCheck(allowed=False)
        except SQLAlchemyError as exc:
            logger.exception(
                f"roles.db_models.evaluate_entity_access failed (user={user_id} org={org_id} entity_type={entity_type} action={action}): {exc}"
            )
            raise PersistenceError(f"Unable to evaluate entity permission: {exc}")

    @staticmethod
    def _get_entity_types_table() -> Table:
        app_schema = Configuration()._configuration.postgresql_configuration.app_schema
        definitions_schema = f"{app_schema}_definitions"
        meta = MetaData(schema=definitions_schema)
        return Table(
            "entity_types",
            meta,
            Column("entity_type_id", String(36), primary_key=True),
            Column("organization_id", String(36)),
            Column("name", String(128)),
            Column("schema", JSON),
            Column("is_active", Boolean),
        )

    @staticmethod
    def _get_entity_type_schema_table() -> Table:
        app_schema = Configuration()._configuration.postgresql_configuration.app_schema
        definitions_schema = f"{app_schema}_definitions"
        meta = MetaData(schema=definitions_schema)
        return Table(
            "entity_type_schema",
            meta,
            Column("organization_id", String(36)),
            Column("entity_type", String(128)),
            Column("fields_json", JSON),
            Column("is_active", Boolean),
        )

    @staticmethod
    def _get_workflow_state_machines_table() -> Table:
        app_schema = Configuration()._configuration.postgresql_configuration.app_schema
        meta = MetaData(schema=app_schema)
        return Table(
            "workflow_state_machines",
            meta,
            Column("organization_id", String(36)),
            Column("entity_type", String(128)),
            Column("definition_json", Text),
            Column("is_active", Boolean),
            Column("archived_at", DateTime(timezone=True)),
        )

    def list_all_entity_types(self, db: Session) -> list[str]:
        """Return all active entity type names across all orgs."""
        try:
            t = self._get_entity_types_table()
            rows = db.execute(
                t.select().where(t.c.is_active.is_(True)).distinct(t.c.name)
            ).fetchall()
            return [row.name for row in rows]
        except SQLAlchemyError as exc:
            logger.exception(f"roles.db_models.list_all_entity_types failed: {exc}")
            raise PersistenceError(f"Unable to list entity types: {exc}")

    def entity_type_exists(self, db: Session, org_id: str, entity_type: str) -> bool:
        """Return True if entity_type exists and is active for the given org."""
        try:
            t = self._get_entity_types_table()
            result = db.execute(
                t.select()
                .where(t.c.organization_id == org_id)
                .where(t.c.name == entity_type)
                .where(t.c.is_active.is_(True))
                .limit(1)
            ).fetchone()
            return result is not None
        except SQLAlchemyError as exc:
            logger.exception(f"roles.db_models.entity_type_exists failed: {exc}")
            raise PersistenceError(f"Unable to check entity type existence: {exc}")

    def get_entity_type_schema_fields(
        self, db: Session, org_id: str, entity_type: str
    ) -> list[dict] | None:
        """Return the merged field list across every active form for this entity
        type (`entity_type_schema.fields_json`, forms module) — an entity type can
        have multiple forms, each contributing its own fields (including
        cross-entity reference fields), so this merges and de-duplicates by field
        key across all of them. Returns `None` only if the entity type itself
        doesn't exist/isn't active for this org; an existing entity type with no
        forms yet returns an empty list (a real, valid state, distinct from
        "doesn't exist").

        `entity_types.schema` is a *different*, largely-unpopulated field, kept
        in sync separately for RBAC field renames (see
        `entities/manager.py::_cascade_field_renames`) — not the real field
        source for this feature; corrected 2026-07-16 after confirming actual
        entity records are built from form-configured fields, not that column."""
        if not self.entity_type_exists(db, org_id, entity_type):
            return None
        try:
            t = self._get_entity_type_schema_table()
            rows = db.execute(
                t.select()
                .where(t.c.organization_id == org_id)
                .where(t.c.entity_type == entity_type)
                .where(t.c.is_active.is_(True))
            ).fetchall()
            merged: list[dict] = []
            seen_keys: set[str] = set()
            for row in rows:
                for field in row.fields_json or []:
                    key = field.get("field") or field.get("id") or field.get("name")
                    if key and key not in seen_keys:
                        seen_keys.add(key)
                        merged.append(field)
            # Method-Block-composed fields live on the workflow definition's
            # entity_schema, not on any form, yet their values sit in the same
            # `entities.data` the read condition is evaluated against
            # (common/protocols.py::resolve_and_compare) — so they are just as
            # filterable and must be offered/accepted here too.
            w = self._get_workflow_state_machines_table()
            workflow_rows = db.execute(
                w.select()
                .where(w.c.organization_id == org_id)
                .where(w.c.entity_type == entity_type)
                .where(w.c.is_active.is_(True))
                .where(w.c.archived_at.is_(None))
            ).fetchall()
            for row in workflow_rows:
                try:
                    definition = json.loads(row.definition_json or "{}")
                except (TypeError, ValueError):
                    continue
                schema = definition.get("entity_schema") or {}
                for field in schema.get("fields") or []:
                    if not isinstance(field, dict):
                        continue
                    key = field.get("field")
                    if key and key not in seen_keys:
                        seen_keys.add(key)
                        merged.append(field)
            return merged
        except SQLAlchemyError as exc:
            logger.exception(f"roles.db_models.get_entity_type_schema_fields failed: {exc}")
            raise PersistenceError(f"Unable to fetch entity type schema: {exc}")

    def entity_field_exists(self, db: Session, org_id: str, entity_type: str, field_name: str) -> bool:
        """Return True if field_name exists in entity_type's schema for the given org."""
        try:
            t = self._get_entity_type_schema_table()
            rows = db.execute(
                t.select()
                .where(t.c.organization_id == org_id)
                .where(t.c.entity_type == entity_type)
                .where(t.c.is_active.is_(True))
            ).fetchall()
            for row in rows:
                fields_json = row.fields_json or []
                for field in fields_json:
                    if field.get("id") == field_name or field.get("field") == field_name:
                        return True
            return False
        except SQLAlchemyError as exc:
            logger.exception(f"roles.db_models.entity_field_exists failed: {exc}")
            raise PersistenceError(f"Unable to check entity field existence: {exc}")

    def assign_role_to_user(
        self, db: Session, user_id: str, org_id: str, role_id: str, assigned_by: str | None = None
    ) -> UserRoleAssignment:
        """Assign a role to a user if not already assigned."""
        try:
            existing = (
                db.query(UserRoleAssignment)
                .filter(
                    UserRoleAssignment.user_id == user_id,
                    UserRoleAssignment.organization_id == org_id,
                    UserRoleAssignment.role_id == role_id,
                )
                .first()
            )
            if existing:
                return existing
            assignment = UserRoleAssignment(
                id=str(uuid.uuid4()),
                user_id=user_id,
                organization_id=org_id,
                role_id=role_id,
                assigned_by=assigned_by,
            )
            db.add(assignment)
            db.commit()
            return assignment
        except SQLAlchemyError as exc:
            logger.exception(
                f"roles.db_models.assign_role_to_user failed (org_id={org_id} user_id={user_id} role_id={role_id}): {exc}"
            )
            db.rollback()
            raise PersistenceError(f"Unable to assign role to user: {exc}")

    def set_user_role(
        self,
        db: Session,
        user_id: str,
        organization_id: str,
        payload: UserRoleSetRequest,
        *,
        assigned_by: str,
    ) -> UserRoleAssignment:
        """Replace all role assignments for a user with a single new role."""
        try:
            db.query(UserRoleAssignment).filter(
                UserRoleAssignment.user_id == user_id,
                UserRoleAssignment.organization_id == organization_id,
            ).delete()
            assignment = UserRoleAssignment(
                id=str(uuid.uuid4()),
                user_id=user_id,
                organization_id=organization_id,
                role_id=payload.role_id,
                assigned_by=assigned_by,
            )
            db.add(assignment)
            db.commit()
            return assignment
        except SQLAlchemyError as exc:
            logger.exception(
                f"roles.db_models.set_user_role failed (organization_id={organization_id} user_id={user_id} role_id={payload.role_id}): {exc}"
            )
            db.rollback()
            raise PersistenceError(f"Unable to set user role: {exc}")

    def remove_user_role(self, db: Session, user_id: str, organization_id: str, role_id: str) -> None:
        """Remove a specific role assignment for a user."""
        try:
            deleted = (
                db.query(UserRoleAssignment)
                .filter(
                    UserRoleAssignment.user_id == user_id,
                    UserRoleAssignment.organization_id == organization_id,
                    UserRoleAssignment.role_id == role_id,
                )
                .first()
            )
            if not deleted:
                raise NotFoundError("Role assignment not found")
            db.delete(deleted)
            db.commit()
        except NotFoundError as exc:
            logger.info(
                f"roles.db_models.remove_user_role not found (organization_id={organization_id} user_id={user_id} role_id={role_id}): {exc}"
            )
            raise
        except SQLAlchemyError as exc:
            logger.exception(
                f"roles.db_models.remove_user_role failed (organization_id={organization_id} user_id={user_id} role_id={role_id}): {exc}"
            )
            db.rollback()
            raise PersistenceError(f"Unable to remove user role: {exc}")

    def rename_entity_type_in_permissions(
        self, db: Session, org_id: str, old_name: str, new_name: str
    ) -> None:
        """Cascade entity type rename to role_permissions and field_permissions."""
        try:
            role_ids = [
                r.id for r in db.query(Role).filter(Role.organization_id == org_id).all()
            ]
            if not role_ids:
                return
            db.query(RolePermission).filter(
                RolePermission.role_id.in_(role_ids),
                RolePermission.entity_type == old_name,
            ).update({"entity_type": new_name}, synchronize_session=False)
            db.query(FieldPermission).filter(
                FieldPermission.role_id.in_(role_ids),
                FieldPermission.entity_type == old_name,
            ).update({"entity_type": new_name}, synchronize_session=False)
            db.commit()
        except SQLAlchemyError as exc:
            logger.exception(
                f"roles.db_models.rename_entity_type_in_permissions failed (org={org_id} old={old_name} new={new_name}): {exc}"
            )
            db.rollback()
            raise PersistenceError(f"Unable to cascade entity type rename to permissions: {exc}")

    def rename_field_in_permissions(
        self, db: Session, org_id: str, entity_type: str, old_field: str, new_field: str
    ) -> None:
        """Cascade field rename to field_permissions."""
        try:
            role_ids = [
                r.id for r in db.query(Role).filter(Role.organization_id == org_id).all()
            ]
            if not role_ids:
                return
            db.query(FieldPermission).filter(
                FieldPermission.role_id.in_(role_ids),
                FieldPermission.entity_type == entity_type,
                FieldPermission.field_name == old_field,
            ).update({"field_name": new_field}, synchronize_session=False)
            db.commit()
        except SQLAlchemyError as exc:
            logger.exception(
                f"roles.db_models.rename_field_in_permissions failed (org={org_id} entity={entity_type} old={old_field} new={new_field}): {exc}"
            )
            db.rollback()
            raise PersistenceError(f"Unable to cascade field rename to permissions: {exc}")

    def ensure_default_roles(self, db: Session, org_id: str) -> list[Role]:
        """Create default system roles for an org if they don't exist."""
        try:
            cfg = Configuration()._configuration.default_roles_configuration
            system_roles = [
                {
                    "name": DefaultRole.SUPERADMIN.value,
                    "display_name": cfg.superadmin_display_name,
                    "priority": cfg.superadmin_priority,
                    "color": cfg.superadmin_color,
                    "is_system": True,
                    "seed_permissions": True,
                },
                {
                    "name": DefaultRole.ADMIN.value,
                    "display_name": cfg.admin_display_name,
                    "priority": cfg.admin_priority,
                    "color": cfg.admin_color,
                    "is_system": True,
                    "seed_permissions": True,
                },
                {
                    "name": DefaultRole.VIEWER.value,
                    "display_name": cfg.viewer_display_name,
                    "priority": cfg.viewer_priority,
                    "color": cfg.viewer_color,
                    "is_system": False,
                    "seed_permissions": False,
                },
            ]
            created: list[Role] = []
            for role_def in system_roles:
                existing = (
                    db.query(Role)
                    .filter(Role.organization_id == org_id, Role.name == role_def["name"])
                    .first()
                )
                if existing:
                    created.append(existing)
                    continue
                role = Role(
                    id=str(uuid.uuid4()),
                    organization_id=org_id,
                    name=role_def["name"],
                    display_name=role_def["display_name"],
                    is_system=role_def["is_system"],
                    priority=role_def["priority"],
                    color=role_def["color"],
                )
                db.add(role)
                db.flush()
                if role_def["seed_permissions"]:
                    for perm_def in DEFAULT_PERMISSION_DEFINITIONS:
                        db.add(
                            RolePermission(
                                id=str(uuid.uuid4()),
                                role_id=role.id,
                                permission_key=perm_def["key"],
                                entity_type=None,
                                action=None,
                                allowed=True,
                            )
                        )
                created.append(role)
            db.commit()
            return created
        except SQLAlchemyError as exc:
            logger.exception(f"roles.db_models.ensure_default_roles failed (org_id={org_id}): {exc}")
            db.rollback()
            raise PersistenceError(f"Unable to ensure default roles: {exc}")

    # ── User / org helpers ──────────────────────────────────────────────────

    def get_user(self, db: Session, user_id: str):  # noqa: ANN201
        """Return a User ORM object by id, or None."""
        try:
            from user.db_models import User  # lazy to avoid circular import
            return db.query(User).filter(User.id == user_id).first()
        except SQLAlchemyError as exc:
            logger.exception(f"roles.db_models.get_user failed (user_id={user_id}): {exc}")
            raise PersistenceError(f"Unable to get user: {exc}")

    def get_user_org_membership(self, db: Session, user_id: str, organization_id: str):  # noqa: ANN201
        """Return the membership row for the user/org pair, or None."""
        if self._organizations_svc is None:
            return None
        return self._organizations_svc.get_membership(db, user_id=user_id, org_id=organization_id)

    def update_user_org_role(self, db: Session, user_id: str, organization_id: str, role_name: str) -> None:
        """Sync the membership row with a role grant: create it if missing, reactivate
        it if suspended/inactive, and keep its role label current either way."""
        if self._organizations_svc is None:
            return
        membership = self.get_user_org_membership(db, user_id, organization_id)
        if membership is None:
            self._organizations_svc.add_membership(
                db, user_id=user_id, org_id=organization_id, role=role_name, status="active"
            )
        else:
            membership.role = role_name
            membership.status = "active"
            db.commit()
