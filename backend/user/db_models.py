"""Persistence adapters for the user module — owns all user SQLAlchemy models."""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    Column,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    String,
    and_,
    case,
    or_,
)
from sqlalchemy.orm import aliased
from sqlalchemy.sql import func

from common.data_model import Enum
from common.logger import logger
from database.manager import Base

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

from exceptions import AuthorizationError, PersistenceError
from organizations.db_models import Organization, OrganizationStatus, UserOrganization, org_members_query
from roles.db_models import RolesModelService
from roles.models.request import UserRoleSetRequest

# ── Enums ─────────────────────────────────────────────────────────────────────


class AuthType(str, Enum):
    LOCAL = "local"
    GOOGLE = "google"
    MICROSOFT = "microsoft"


class UserRole(str, Enum):
    SUPERADMIN = "superadmin"
    ADMIN = "admin"
    RECRUITER = "recruiter"
    HIRING_MANAGER = "hiring_manager"
    VIEWER = "viewer"


class UserStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REJECTED = "rejected"


# ── SQLAlchemy Models ─────────────────────────────────────────────────────────


class User(Base):
    """Platform user."""

    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=True)  # null for Google-only users
    full_name = Column(String(255), nullable=False)
    avatar_url = Column(String(2048), nullable=True)
    role = Column(String(32), nullable=False, default=UserRole.VIEWER.value)
    status = Column(String(32), nullable=False, default=UserStatus.PENDING.value)
    auth_type = Column(String(16), nullable=False, default=AuthType.LOCAL.value)
    google_id = Column(String(255), nullable=True, unique=True, index=True)
    microsoft_id = Column(String(255), nullable=True, unique=True, index=True)
    # Computed by the database as (status == 'active'); read-only from the app.
    is_active = Column(
        Boolean, Computed("status = 'active'", persisted=True), nullable=False
    )
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    # Primary/current organization the user is working in
    organization_id = Column(
        String(36),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (Index("ix_users_auth_type", "auth_type"),)


class RefreshToken(Base):
    """Issued refresh tokens (revocable)."""

    __tablename__ = "refresh_tokens"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash = Column(String(255), nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (Index("ix_refresh_tokens_user_id", "user_id"),)


# ── RBAC models (owned by roles module) ───────────────────────────────────────
from roles.db_models import (  # noqa: E402
    FieldPermission,
    PermissionAction,
    Role,
    RolePermission,
    UserRoleAssignment,
)

__all__ = [
    "FieldPermission",
    "PermissionAction",
    "Role",
    "RolePermission",
    "UserRoleAssignment",
]


def attach_superadmins_to_org(db: Session, org_id: str) -> None:
    """Insert UserOrganization rows for every superadmin user, idempotent.

    Superadmin users are platform-level — they must be members of every org so
    `/users/me/organizations` returns the full org list and `switch_organization`
    succeeds without special-casing the role downstream.

    Safe to call multiple times: existing memberships are skipped via the uniq
    constraint on (user_id, organization_id). Failures are logged but do not
    block org creation — superadmin membership is recoverable via backfill.
    """
    try:
        superadmins = (
            db.query(User.id).filter(User.role == UserRole.SUPERADMIN.value).all()
        )
        if not superadmins:
            return
        for (user_id,) in superadmins:
            exists = (
                db.query(UserOrganization.id)
                .filter(
                    UserOrganization.user_id == user_id,
                    UserOrganization.organization_id == org_id,
                )
                .first()
            )
            if exists:
                continue
            db.add(
                UserOrganization(
                    user_id=user_id,
                    organization_id=org_id,
                    role=UserRole.SUPERADMIN.value,
                    status="active",
                )
            )
        db.commit()
    except Exception as exc:  # noqa: BLE001
        # Roll back the whole membership batch so we don't leave partial rows
        # in the current transaction if any insert/commit step fails.
        db.rollback()
        # Don't raise — org creation should not fail if superadmin attach fails.
        logger.warning(f"attach_superadmins_to_org failed for org_id={org_id}: {exc}")


# ── DB operations ─────────────────────────────────────────────────────────────


class UserModelService:
    """DB operations for user management.

    `get_*` methods take a per-request Session from the caller; `fetch_*`
    methods manage their own.
    """

    # Model handles for modules that receive this service via injection and
    # cannot import user.db_models at module level (circular dependency).
    user_model = User
    user_role = UserRole
    user_status = UserStatus
    role_model = Role
    user_role_assignment = UserRoleAssignment
    auth_type = AuthType

    def __init__(self, database_service_manager: Any = None) -> None:
        self.module_name = "user"
        self._db_manager = database_service_manager

    def attach_superadmins_to_org(self, db: Session, org_id: str) -> None:
        """Delegate to the module-level helper — injectable entry point."""
        attach_superadmins_to_org(db, org_id)

    @contextmanager
    def _db_session(self):
        """Open a short-lived session for self-contained reads."""
        if self._db_manager is None:
            raise RuntimeError("Database service manager unavailable")
        session = self._db_manager.postgres_db_service().get_db_session()
        try:
            yield session
        finally:
            session.close()

    def fetch_display_info(self, user_id: str) -> tuple[str | None, str | None]:
        """Return (full_name, role) for a user. Self-managed session, best-effort.

        Returns (None, None) when the user is not found, the DB is unavailable,
        or on any error. Failures are swallowed — this is audit enrichment only.
        """
        if not user_id:
            return None, None
        try:
            with self._db_session() as session:
                user = self.get_by_id(session, user_id)
                if user is None:
                    return None, None
                return getattr(user, "full_name", None), getattr(user, "role", None)
        except Exception as e:
            logger.warning("fetch_display_info failed", extra={"user_id": user_id, "error": str(e)}, exc_info=True)
            return None, None

    # ── Queries ───────────────────────────────────────────────────────────────

    def get_by_id(self, db: Session, user_id: str) -> User | None:
        try:
            return db.query(User).filter(User.id == user_id).first()
        except Exception as exc:
            raise PersistenceError(f"Unable to get user: {exc}") from exc

    def is_member_of_org(self, db: Session, user_id: str, org_id: str) -> bool:
        """Check whether a user belongs to an org: an explicit membership row,
        or the legacy primary users.organization_id fallback — mirrors the
        same membership rule org_members_query() uses for listing."""
        try:
            has_membership = (
                db.query(UserOrganization.id)
                .filter(UserOrganization.user_id == user_id, UserOrganization.organization_id == org_id)
                .first()
            )
            if has_membership:
                return True
            user = self.get_by_id(db, user_id)
            return bool(user and str(user.organization_id or "") == org_id)
        except Exception as exc:
            raise PersistenceError(f"Unable to check org membership: {exc}") from exc

    def get_membership(
        self, db: Session, user_id: str, org_id: str
    ) -> UserOrganization | None:
        """Return the user's membership row for one org, or None."""
        try:
            return (
                db.query(UserOrganization)
                .filter(
                    UserOrganization.user_id == user_id,
                    UserOrganization.organization_id == org_id,
                )
                .first()
            )
        except Exception as exc:
            raise PersistenceError(f"Unable to get membership: {exc}") from exc

    def fetch_user_with_membership(
        self, user_id: str, org_id: str
    ) -> tuple[User, UserOrganization | None] | None:
        """Return one user and their membership in one org, or None if no such user.

        A `None` membership means the user exists but has no membership row in
        this organization; a matching primary organization does not count.
        Returned records are detached, so lazy loading is unavailable.
        """
        with self._db_session() as db:
            try:
                user = self.get_by_id(db, user_id)
                if user is None:
                    return None
                return user, self.get_membership(db, user_id, org_id)
            except Exception as exc:
                logger.error(
                    "org member lookup failed: %s",
                    exc,
                    extra={"user_id": user_id, "organization_id": org_id},
                    exc_info=True,
                )
                raise

    def is_membership_active(self, db: Session, user_id: str, org_id: str) -> bool:
        """Return True if the user's membership in this org is active. A user with
        no membership row whose primary org is this org counts as active; a
        suspended membership returns False."""
        try:
            membership = self.get_membership(db, user_id, org_id)
            if membership is not None:
                return membership.status == UserStatus.ACTIVE.value
            user = self.get_by_id(db, user_id)
            return bool(user and str(user.organization_id or "") == org_id)
        except Exception as exc:
            raise PersistenceError(f"Unable to check membership status: {exc}") from exc

    def list_all(
        self,
        db: Session,
        organization_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[User]:
        try:
            if organization_id:
                # Scope the membership join to this org so `status` can filter on the
                # effective org-scoped status (account lifecycle until active, then the
                # per-org membership status) — the same value the response displays.
                # Legacy members (primary org set, no membership row) are still included.
                membership = aliased(UserOrganization)
                query = (
                    db.query(User)
                    .outerjoin(
                        membership,
                        and_(
                            membership.user_id == User.id,
                            membership.organization_id == organization_id,
                        ),
                    )
                    .filter(
                        or_(
                            membership.id.isnot(None),
                            User.organization_id == organization_id,
                        )
                    )
                    .distinct()
                )
                if status:
                    effective_status = case(
                        (User.status != UserStatus.ACTIVE.value, User.status),
                        else_=func.coalesce(membership.status, UserStatus.ACTIVE.value),
                    )
                    query = query.filter(effective_status == status)
            else:
                query = db.query(User)
                if status:
                    query = query.filter(User.status == status)
            return query.order_by(User.created_at.desc()).limit(limit).offset(offset).all()
        except Exception as exc:
            raise PersistenceError(f"Unable to list users: {exc}") from exc

    def list_pending(self, db: Session, organization_id: str | None = None) -> list[User]:
        return self.list_all(db, organization_id=organization_id, status=UserStatus.PENDING.value)

    # ── Mutations ─────────────────────────────────────────────────────────────

    def set_status(self, db: Session, user_id: str, status: str) -> User | None:
        try:
            user = self.get_by_id(db, user_id)
            if not user:
                return None
            user.status = status  # is_active is derived from status by the DB
            db.commit()
            db.refresh(user)
            return user
        except Exception as exc:
            db.rollback()
            raise PersistenceError(f"Unable to update user status: {exc}") from exc

    def set_role(self, db: Session, user_id: str, role: str) -> User | None:
        try:
            user = self.get_by_id(db, user_id)
            if not user:
                return None
            user.role = role
            db.commit()
            db.refresh(user)
            return user
        except Exception as exc:
            db.rollback()
            raise PersistenceError(f"Unable to update user role: {exc}") from exc

    def set_membership_status(
        self, db: Session, user_id: str, org_id: str, status: str
    ) -> bool:
        """Set the per-org membership status (e.g. active/suspended). Returns
        False if no membership row exists for this user+org."""
        try:
            membership = self.get_membership(db, user_id, org_id)
            if membership is None:
                return False
            membership.status = status
            db.commit()
            return True
        except Exception as exc:
            db.rollback()
            raise PersistenceError(f"Unable to update membership status: {exc}") from exc

    def get_organizations_for_user(
        self, db: Session, user_id: str
    ) -> list[tuple[UserOrganization, Organization]]:
        try:
            # Only return active memberships — keeps list output consistent with
            # `switch_organization`, which rejects non-active membership rows.
            # Inactive/legacy rows would otherwise surface in the switcher and
            # produce 400s on click.
            rows = (
                db.query(UserOrganization, Organization)
                .join(Organization, UserOrganization.organization_id == Organization.id)
                .filter(UserOrganization.user_id == user_id)
                .filter(UserOrganization.status == UserStatus.ACTIVE.value)
                .all()
            )
            return [(membership, org) for membership, org in rows]
        except Exception as exc:
            raise PersistenceError(f"Unable to get user organizations: {exc}") from exc

    def get_memberships_map(
        self, db: Session, org_id: str, user_ids: list[str]
    ) -> dict[str, UserOrganization]:
        """Map user_id -> membership row within the given org, in one query."""
        if not user_ids:
            return {}
        try:
            rows = (
                db.query(UserOrganization)
                .filter(
                    UserOrganization.organization_id == org_id,
                    UserOrganization.user_id.in_(user_ids),
                )
                .all()
            )
            return {str(r.user_id): r for r in rows}
        except Exception as exc:
            raise PersistenceError(f"Unable to fetch memberships: {exc}") from exc

    def set_membership_role(self, db: Session, user_id: str, org_id: str, role: str) -> None:
        """Update the membership role for a user in one org. No-op if no membership row."""
        try:
            membership = self.get_membership(db, user_id, org_id)
            if membership:
                membership.role = role
                db.commit()
        except Exception as exc:
            db.rollback()
            raise PersistenceError(f"Unable to update membership role: {exc}") from exc

    def switch_organization(self, db: Session, user: User, organization_id: str) -> User:
        try:
            membership = (
                db.query(UserOrganization)
                .filter(UserOrganization.user_id == user.id)
                .filter(UserOrganization.organization_id == organization_id)
                .filter(UserOrganization.status == UserStatus.ACTIVE.value)
                .first()
            )
            if not membership:
                raise AuthorizationError("You are not a member of this organization")
            org = db.query(Organization).filter(Organization.id == organization_id).first()
            if not org or org.status != OrganizationStatus.ACTIVE.value:
                raise AuthorizationError("This organization is not active")
            # Backfill a membership row for the org being left so it stays in the switcher.
            previous_org_id = user.organization_id
            if previous_org_id and previous_org_id != organization_id:
                has_previous = (
                    db.query(UserOrganization)
                    .filter(
                        UserOrganization.user_id == user.id,
                        UserOrganization.organization_id == previous_org_id,
                    )
                    .first()
                )
                if not has_previous:
                    db.add(
                        UserOrganization(
                            user_id=user.id,
                            organization_id=previous_org_id,
                            role=user.role or UserRole.VIEWER.value,
                            status=UserStatus.ACTIVE.value,
                        )
                    )
            user.organization_id = organization_id
            if user.role != UserRole.SUPERADMIN.value:
                user.role = membership.role
            db.commit()
            db.refresh(user)
            return user
        except (PersistenceError, AuthorizationError):
            raise
        except Exception as exc:
            db.rollback()
            raise PersistenceError(f"Unable to switch organization: {exc}") from exc

    def search_users(
        self, db: Session, query: str, organization_id: str, limit: int = 10
    ) -> list[User]:
        try:
            search = f"%{query}%"
            return (
                org_members_query(db, User, organization_id)
                .filter(User.status == UserStatus.ACTIVE.value)
                .filter(User.is_active == True)  # noqa: E712
                .filter(User.full_name.ilike(search) | User.email.ilike(search))
                .limit(limit)
                .all()
            )
        except Exception as exc:
            raise PersistenceError(f"Unable to search users: {exc}") from exc

    def get_stats(self, db: Session, organization_id: str) -> dict:
        try:
            users = self.list_all(db, organization_id=organization_id, limit=10000)
            status_counts = {s.value: 0 for s in UserStatus}
            role_counts = {r.value: 0 for r in UserRole}
            for u in users:
                if u.status in status_counts:
                    status_counts[u.status] += 1
                if u.role in role_counts:
                    role_counts[u.role] += 1
            return {"total": len(users), "by_status": status_counts, "by_role": role_counts}
        except Exception as exc:
            raise PersistenceError(f"Unable to get user stats: {exc}") from exc

    def get_organization_by_id(self, db: Session, org_id: str) -> Organization | None:
        return db.query(Organization).filter(Organization.id == org_id).first()

    def _roles_svc(self):
        return RolesModelService()

    def get_user_roles(self, db: Session, user_id: str, org_id: str) -> list[Role]:
        return self._roles_svc().get_user_roles_with_permissions(db, user_id, org_id)

    def get_field_permissions_for_roles(
        self, db: Session, role_ids: list[str], entity_type: str
    ) -> list[FieldPermission]:
        return self._roles_svc().get_field_permissions_for_roles(db, role_ids, entity_type)

    def get_all_field_permissions_for_roles(
        self, db: Session, role_ids: list[str]
    ) -> list[FieldPermission]:
        return self._roles_svc().get_all_field_permissions_for_roles(db, role_ids)

    def assign_role_to_user(
        self, db: Session, user_id: str, org_id: str, role_id: str, assigned_by: str | None = None
    ) -> UserRoleAssignment:
        return self._roles_svc().assign_role_to_user(db, user_id, org_id, role_id, assigned_by)

    def remove_role_from_user(self, db: Session, user_id: str, org_id: str, role_id: str) -> bool:
        try:
            RolesModelService().remove_user_role(db, user_id, org_id, role_id)
            return True
        except Exception:
            logger.error(
                "failed to remove role %s from user %s in org %s",
                role_id,
                user_id,
                org_id,
                exc_info=True,
            )
            return False

    def set_user_role(
        self, db: Session, user_id: str, org_id: str, role_id: str, assigned_by: str | None = None
    ) -> UserRoleAssignment:
        payload = UserRoleSetRequest(role_id=role_id)
        return self._roles_svc().set_user_role(
            db, user_id, org_id, payload, assigned_by=assigned_by or ""
        )

    def ensure_default_roles(self, db: Session, org_id: str) -> list[Role]:
        return self._roles_svc().ensure_default_roles(db, org_id)

    def get_role_by_name(self, db: Session, org_id: str, name: str) -> Role | None:
        return self._roles_svc().get_role_by_name(db, org_id, name)
