"""Persistence adapters for the organizations module.

Owns Organization and membership SQLAlchemy models, plus DB operations.
"""

from __future__ import annotations

import re
import uuid
from typing import TYPE_CHECKING, Any

from common.data_model import Enum
from common.logger import logger
from database.manager import Base
from exceptions import PersistenceError
from sqlalchemy import Column, DateTime, ForeignKey, Index, String, UniqueConstraint, or_
from sqlalchemy.sql import func
from sqlalchemy.types import JSON

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


# ── Enums ─────────────────────────────────────────────────────────────────────

class OrganizationStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    ARCHIVED = "archived"
    REJECTED = "rejected"


# ── SQLAlchemy Models ─────────────────────────────────────────────────────────

class Organization(Base):
    """Organization (tenant) for multi-tenancy."""

    __tablename__ = "organizations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    slug = Column(String(128), unique=True, nullable=False, index=True)
    domain = Column(String(255), nullable=True, unique=True, index=True)
    settings = Column(JSON, nullable=False, default=dict)
    status = Column(String(32), nullable=False, default=OrganizationStatus.ACTIVE.value)
    logo_url = Column(String(512), nullable=True)
    requested_by_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (Index("ix_organizations_status", "status"),)


class UserOrganization(Base):
    """Junction table — user membership across organizations."""

    __tablename__ = "user_organizations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id = Column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Keep defaults string-based to avoid importing user.db_models (circular import risk).
    role = Column(String(32), nullable=False, default="viewer")
    status = Column(String(32), nullable=False, default="active")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "organization_id", name="uq_user_organization"),
        Index("ix_user_organizations_user_org", "user_id", "organization_id"),
    )


def org_members_query(db: Session, user_model: Any, org_id: str):
    """Query users belonging to an org via user_organizations membership rows.

    Includes a primary-org fallback so legacy users (created before membership
    rows were written consistently) stay visible in their own org."""
    return (
        db.query(user_model)
        .outerjoin(UserOrganization, UserOrganization.user_id == user_model.id)
        .filter(
            or_(
                UserOrganization.organization_id == org_id,
                user_model.organization_id == org_id,
            )
        )
        .distinct()
    )


class OrganizationsModelService:

    """DB operations for organizations.

    Receives a per-request Session — no session management of its own.
    """

    module_name = "organizations"

    def __init__(self, database_service_manager: Any = None, user_model_service: Any = None) -> None:
        self.module_name = "organizations"
        # UserModelService injected from main.py — organizations ↔ user have a
        # module-level circular dependency, so user models are reached through it.
        self.user_svc = user_model_service
        self.User: Any = getattr(user_model_service, "user_model", None)
        self.UserRole: Any = getattr(user_model_service, "user_role", None)
        self.UserStatus: Any = getattr(user_model_service, "user_status", None)
        self.Role: Any = getattr(user_model_service, "role_model", None)
        self.UserRoleAssignment: Any = getattr(user_model_service, "user_role_assignment", None)
        self.AuthType: Any = getattr(user_model_service, "auth_type", None)

    # ── Internal helpers (reuse within same open session) ─────────────────────

    @staticmethod
    def _get_by_id(db: Session, org_id: str) -> Organization | None:
        return db.query(Organization).filter(Organization.id == org_id).first()

    @staticmethod
    def _get_by_slug(db: Session, slug: str) -> Organization | None:
        return db.query(Organization).filter(Organization.slug == slug).first()

    def _get_user(self, db: Session, user_id: str) -> Any | None:
        return self.user_svc.get_by_id(db, user_id)

    # ── Public API ────────────────────────────────────────────────────────────

    def get_by_id(self, db: Session, org_id: str) -> Organization | None:
        try:
            return self._get_by_id(db, org_id)
        except Exception as exc:  # noqa: BLE001
            raise PersistenceError(f"Unable to get organization: {exc}") from exc

    def get_by_slug(self, db: Session, slug: str) -> Organization | None:
        try:
            return self._get_by_slug(db, slug)
        except Exception as exc:  # noqa: BLE001
            raise PersistenceError(f"Unable to get organization by slug: {exc}") from exc

    def get_by_domain(self, db: Session, domain: str) -> Organization | None:
        try:
            return db.query(Organization).filter(Organization.domain == domain).first()
        except Exception as exc:  # noqa: BLE001
            raise PersistenceError(f"Unable to get organization by domain: {exc}") from exc

    def get_by_name(self, db: Session, name: str) -> Organization | None:
        try:
            return db.query(Organization).filter(Organization.name == name).first()
        except Exception as exc:  # noqa: BLE001
            raise PersistenceError(f"Unable to get organization by name: {exc}") from exc

    @staticmethod
    def slugify(name: str) -> str:
        slug = re.sub(r"[^\w\s-]", "", str(name or "").lower())
        slug = re.sub(r"[-\s]+", "-", slug).strip("-")
        return slug

    def create(
        self,
        db: Session,
        *,
        name: str,
        slug: str | None = None,
        domain: str | None = None,
        settings: dict[str, Any] | None = None,
        logo_url: str | None = None,
        status: OrganizationStatus | None = None,
        requested_by_user_id: str | None = None,
    ) -> Organization:
        try:
            used_slug = slug or self.slugify(name)
            base_slug = used_slug
            counter = 1
            while self._get_by_slug(db, used_slug) is not None:
                used_slug = f"{base_slug}-{counter}"
                counter += 1

            org = Organization(
                name=name,
                slug=used_slug,
                domain=domain,
                settings=settings or {},
                logo_url=logo_url,
                status=(status or OrganizationStatus.ACTIVE).value,
                requested_by_user_id=requested_by_user_id,
            )
            db.add(org)
            db.commit()
            db.refresh(org)
            self.user_svc.attach_superadmins_to_org(db, str(org.id))
            return org
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            raise PersistenceError(f"Unable to create organization: {exc}") from exc

    def update(
        self,
        db: Session,
        org_id: str,
        *,
        name: str | None = None,
        domain: str | None = None,
        settings: dict[str, Any] | None = None,
        logo_url: str | None = None,
        status: OrganizationStatus | None = None,
    ) -> Organization | None:
        try:
            org = self._get_by_id(db, org_id)
            if not org:
                return None

            if name is not None:
                org.name = name
            if domain is not None:
                org.domain = domain
            if settings is not None:
                org.settings = {**(org.settings or {}), **settings}
            if logo_url is not None:
                org.logo_url = logo_url
            if status is not None:
                org.status = status.value

            db.commit()
            db.refresh(org)
            return org
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            raise PersistenceError(f"Unable to update organization: {exc}") from exc

    def list(
        self,
        db: Session,
        *,
        status: OrganizationStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Organization]:
        try:
            query = db.query(Organization)
            if status is not None:
                query = query.filter(Organization.status == status.value)
            return (
                query.order_by(Organization.created_at.desc())
                .offset(int(offset))
                .limit(int(limit))
                .all()
            )
        except Exception as exc:  # noqa: BLE001
            raise PersistenceError(f"Unable to list organizations: {exc}") from exc

    def list_pending(
        self,
        db: Session,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Organization]:
        try:
            return (
                db.query(Organization)
                .filter(Organization.status == OrganizationStatus.PENDING.value)
                .order_by(Organization.created_at.desc())
                .offset(int(offset))
                .limit(int(limit))
                .all()
            )
        except Exception as exc:  # noqa: BLE001
            raise PersistenceError(f"Unable to list pending organizations: {exc}") from exc

    def delete(self, db: Session, org_id: str) -> None:
        try:
            org = self._get_by_id(db, org_id)
            if org:
                db.delete(org)
                db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            raise PersistenceError(f"Unable to delete organization: {exc}") from exc

    def approve_org(self, db: Session, org_id: str) -> Organization | None:
        """Approve a pending org: activate org, requester, and pending users."""
        try:
            org = self._get_by_id(db, org_id)
            if not org:
                return None

            org.status = OrganizationStatus.ACTIVE.value

            requester_id = getattr(org, "requested_by_user_id", None)
            if requester_id:
                requester = self._get_user(db, str(requester_id))
                if requester:
                    requester.status = self.UserStatus.ACTIVE.value
                    requester.role = self.UserRole.ADMIN.value

            pending_users = (
                db.query(self.User)
                .filter(
                    self.User.organization_id == org.id,
                    self.User.status == self.UserStatus.PENDING.value,
                )
                .all()
            )
            for user in pending_users:
                if requester_id and str(user.id) == str(requester_id):
                    continue
                user.status = self.UserStatus.ACTIVE.value

            db.commit()
            db.refresh(org)


            return org
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            raise PersistenceError(f"Unable to approve organization: {exc}") from exc

    def reject_org(self, db: Session, org_id: str) -> Organization | None:
        try:
            org = self._get_by_id(db, org_id)
            if not org:
                return None
            org.status = OrganizationStatus.REJECTED.value
            db.commit()
            db.refresh(org)
            return org
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            raise PersistenceError(f"Unable to reject organization: {exc}") from exc

    def delete_with_users(self, db: Session, org_id: str) -> None:
        """Delete org and all its users in one transaction."""
        try:
            db.query(self.User).filter(self.User.organization_id == org_id).delete()
            org = self._get_by_id(db, org_id)
            if org:
                db.delete(org)
            db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            raise PersistenceError(f"Unable to delete organization with users: {exc}") from exc

    def has_rbac_roles(self, db: Session, org_id: str) -> bool:
        try:
            return db.query(self.Role).filter(self.Role.organization_id == org_id).count() > 0
        except Exception:  # noqa: BLE001
            return False

    def ensure_roles(self, db: Session, org_id: str) -> int:
        """Role seeding is handled by OrganizationsServiceManager via injected RolesServiceManager."""
        return 0

    def list_users(
        self,
        db: Session,
        *,
        org_id: str,
        status_filter: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Any], int]:
        try:
            query = org_members_query(db, self.User, org_id)
            if status_filter:
                query = query.filter(self.User.status == status_filter)
            total = query.count()
            users = (
                query.order_by(self.User.created_at.asc())
                .offset(int(offset))
                .limit(int(limit))
                .all()
            )
            return users, int(total)
        except Exception as exc:  # noqa: BLE001
            raise PersistenceError(f"Unable to list organization users: {exc}") from exc

    def get_user_by_email(self, db: Session, email: str) -> Any | None:
        try:
            return db.query(self.User).filter(self.User.email == email).first()
        except Exception as exc:  # noqa: BLE001
            raise PersistenceError(f"Unable to resolve user by email: {exc}") from exc

    def get_user(self, db: Session, user_id: str) -> Any | None:
        try:
            return self._get_user(db, user_id)
        except Exception as exc:  # noqa: BLE001
            raise PersistenceError(f"Unable to resolve user: {exc}") from exc

    def get_membership(self, db: Session, *, user_id: str, org_id: str) -> UserOrganization | None:
        try:
            return (
                db.query(UserOrganization)
                .filter(
                    UserOrganization.user_id == user_id,
                    UserOrganization.organization_id == org_id,
                )
                .first()
            )
        except Exception as exc:  # noqa: BLE001
            raise PersistenceError(f"Unable to resolve organization membership: {exc}") from exc

    def add_membership(
        self,
        db: Session,
        *,
        user_id: str,
        org_id: str,
        role: str,
        status: str,
    ) -> UserOrganization:
        try:
            membership = UserOrganization(
                user_id=user_id,
                organization_id=org_id,
                role=role,
                status=status,
            )
            db.add(membership)
            db.commit()
            db.refresh(membership)
            return membership
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            raise PersistenceError(f"Unable to add user membership: {exc}") from exc

    def remove_user_org_roles(self, db: Session, *, user_id: str, org_id: str) -> None:
        """Delete the user's RBAC role assignments scoped to this organization."""
        try:
            db.query(self.UserRoleAssignment).filter(
                self.UserRoleAssignment.user_id == user_id,
                self.UserRoleAssignment.organization_id == org_id,
            ).delete()
            db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            raise PersistenceError(f"Unable to remove user role assignments: {exc}") from exc

    def create_user(
        self,
        db: Session,
        *,
        email: str,
        full_name: str,
        role: str,
        status: str,
        organization_id: str,
        hashed_password: str,
    ) -> Any:
        try:
            user = self.User(
                email=email,
                full_name=full_name,
                role=role,
                status=status,
                auth_type=self.AuthType.LOCAL.value,
                organization_id=organization_id,
                hashed_password=hashed_password,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            return user
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            raise PersistenceError(f"Unable to create user: {exc}") from exc

    def remove_membership(self, db: Session, *, user_id: str, org_id: str) -> None:
        try:
            db.query(UserOrganization).filter(
                UserOrganization.user_id == user_id,
                UserOrganization.organization_id == org_id,
            ).delete()
            db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            raise PersistenceError(f"Unable to remove user membership: {exc}") from exc

    def delete_user(self, db: Session, *, user_id: str) -> None:
        try:
            db.query(UserOrganization).filter(UserOrganization.user_id == user_id).delete()
            user = db.query(self.User).filter(self.User.id == user_id).first()
            if user:
                db.delete(user)
            db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            raise PersistenceError(f"Unable to delete user: {exc}") from exc
