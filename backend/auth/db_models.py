"""Persistence adapters for auth.

SQLAlchemy models live in user/db_models.py — auth imports from there.
This module owns:
  - In-memory RBAC helpers (AuthModelService)
  - Auth-specific DB operations (AuthDBOperations)
  - Auth enums and dataclasses (AuthEventType, ApprovalType, UserCreationResult)
  - Org helper functions
  - Core auth service (AuthService)
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from http import HTTPStatus
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

import httpx
from sqlalchemy import or_

from common.configuration import get_configuration
from common.enums import AuditMetadataType, DefaultRole
from common.logger import logger
from common.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from entities.db_models import AuthEventAuditModel
from exceptions import PersistenceError, ValidationError
from invitation.db_models import Invitation, InvitationStatus
from organizations.db_models import (
    Organization,
    OrganizationStatus,
    UserOrganization,
)
from user.db_models import AuthType, RefreshToken, User, UserRole, UserStatus, attach_superadmins_to_org
from user.db_models import UserModelService as _UserModelService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# ── Module-level singletons ───────────────────────────────────────────────────

_user_model_service = _UserModelService()

# ── Constants ─────────────────────────────────────────────────────────────────

_auth_cfg = get_configuration().auth_configuration
DEFAULT_ORG_ID = _auth_cfg.default_org_id
PLATFORM_ORG_ID = _auth_cfg.platform_org_id
PUBLIC_EMAIL_DOMAINS = frozenset(_auth_cfg.public_email_domains)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _add_membership_row(db: Session, user_id: str, organization_id: str, role: str) -> None:
    """Stage an active UserOrganization row alongside a new user (caller commits)."""
    db.add(
        UserOrganization(
            user_id=user_id,
            organization_id=organization_id,
            role=role,
            status=UserStatus.ACTIVE.value,
        )
    )


# ── Enums / dataclasses ───────────────────────────────────────────────────────


class AuthEventType(StrEnum):
    LOGIN_SUCCESS = "AUTH_LOGIN_SUCCESS"
    LOGIN_FAILED = "AUTH_LOGIN_FAILED"
    REGISTER = "AUTH_REGISTER"
    LOGOUT = "AUTH_LOGOUT"
    GOOGLE_LOGIN = "AUTH_GOOGLE_LOGIN"
    GOOGLE_LOGIN_FAILED = "AUTH_GOOGLE_LOGIN_FAILED"
    GOOGLE_ACCOUNT_LINKED = "AUTH_GOOGLE_ACCOUNT_LINKED"
    PASSWORD_CHANGED = "AUTH_PASSWORD_CHANGED"
    PASSWORD_RESET_REQUESTED = "AUTH_PASSWORD_RESET_REQUESTED"
    ACCOUNT_DEACTIVATED = "AUTH_ACCOUNT_DEACTIVATED"
    ACCOUNT_REACTIVATED = "AUTH_ACCOUNT_REACTIVATED"
    USER_APPROVED = "AUTH_USER_APPROVED"
    USER_REJECTED = "AUTH_USER_REJECTED"
    USER_SUSPENDED = "AUTH_USER_SUSPENDED"


class ApprovalType(StrEnum):
    ACTIVE = "active"
    PENDING_ORG_ADMIN = "pending_org_admin"
    PENDING_PLATFORM = "pending_platform"


@dataclass
class UserCreationResult:
    user: User
    organization: Organization
    is_new_org: bool
    approval_type: ApprovalType


# ── In-memory RBAC helpers ────────────────────────────────────────────────────


def _role_key(role: str) -> str:
    """Hash a role tuple to its dedupe key."""
    return role.strip().lower()


@dataclass(frozen=True)
class UserRoleRecord:
    user_id: str
    organization_id: str
    role: str


@dataclass
class UserTokenRecord:
    token: str
    user_id: str
    organization_id: str
    roles: list[str]
    active: bool = True


class AuthModelService:
    """In-memory RBAC role and token registry."""

    def __init__(self, database_service_manager: Any = None) -> None:
        """Initialize the in-memory store / DB-backed service."""
        self.module_name = "auth"
        self._roles_by_org_user: dict[tuple[str, str], set[str]] = {}
        self._token_registry: dict[str, UserTokenRecord] = {}

    def add_role(self, user_id: str, organization_id: str, role: str) -> UserRoleRecord:
        """Register a role for `(organization_id, user_id)`."""
        try:
            key = (organization_id, user_id)
            normalized = _role_key(role)
            self._roles_by_org_user.setdefault(key, set()).add(normalized)
            return UserRoleRecord(user_id=user_id, organization_id=organization_id, role=normalized)
        except Exception as exc:
            logger.debug(
                f"Failed to add role {role} for user {user_id} in org {organization_id}: {exc}"
            )
            raise PersistenceError(f"Unable to add role: {exc}") from exc

    def list_roles(self, user_id: str, organization_id: str) -> list[str]:
        """Return all registered roles for `(organization_id, user_id)`."""
        key = (organization_id, user_id)
        return sorted(self._roles_by_org_user.get(key, set()))

    def has_role(self, user_id: str, organization_id: str, role: str) -> bool:
        """Predicate: does the user hold the given role in the org."""
        key = (organization_id, user_id)
        return _role_key(role) in self._roles_by_org_user.get(key, set())

    def set_token(
        self, token: str, user_id: str, organization_id: str, roles: list[str], active: bool = True
    ) -> UserTokenRecord:
        """Cache an access token → user identity mapping (test/in-memory aid)."""
        try:
            record = UserTokenRecord(
                token=token,
                user_id=user_id,
                organization_id=organization_id,
                roles=sorted({_role_key(r) for r in roles}),
                active=active,
            )
            self._token_registry[token] = record
            return record
        except Exception as exc:
            logger.debug(f"Failed to set token for user {user_id} in org {organization_id}: {exc}")
            raise PersistenceError(f"Unable to set token: {exc}") from exc

    def introspect_token(self, token: str) -> UserTokenRecord | None:
        """Reverse the token cache to recover the user identity."""
        return self._token_registry.get(token)


# ── Org helpers ───────────────────────────────────────────────────────────────


class OrgModelService:
    """Static helpers for organization lookups and creation."""

    @staticmethod
    def slugify(name: str) -> str:
        """Lowercase + ascii-hyphenate a free-text name."""
        slug = re.sub(r"[^\w\s-]", "", name.lower())
        return re.sub(r"[-\s]+", "-", slug).strip("-")

    @staticmethod
    def _domain_to_org_name(domain: str) -> str:
        """Derive a default org display name from an email domain."""
        name = domain.split(".")[0]
        return name.replace("-", " ").replace("_", " ").title()

    @staticmethod
    def get_organization(db: Session, org_id: str) -> Organization | None:
        """Fetch an organization by id."""
        return db.query(Organization).filter(Organization.id == org_id).first()

    @staticmethod
    def get_organization_by_slug(db: Session, slug: str) -> Organization | None:
        """Fetch an organization by its url-safe slug."""
        return db.query(Organization).filter(Organization.slug == slug).first()

    @staticmethod
    def get_organization_by_domain(db: Session, domain: str) -> Organization | None:
        """Fetch an organization registered for the given email domain."""
        return db.query(Organization).filter(Organization.domain == domain).first()

    @staticmethod
    def get_organization_for_email(db: Session, email: str) -> Organization | None:
        """Resolve the organization that owns the email's domain (if any)."""
        if "@" not in email:
            return None
        domain = email.split("@")[1].lower()
        return OrgModelService.get_organization_by_domain(db, domain)

    @staticmethod
    def is_public_email_domain(email: str) -> bool:
        """Predicate: is this a public/free email provider (gmail, etc.)."""
        if "@" not in email:
            return False
        return email.split("@")[1].lower() in PUBLIC_EMAIL_DOMAINS

    @staticmethod
    def _create_organization(
        db: Session,
        name: str,
        slug: str | None = None,
        domain: str | None = None,
        status: OrganizationStatus = OrganizationStatus.PENDING,
        requested_by_user_id: str | None = None,
    ) -> Organization:
        """Insert a new organization row from name/domain inputs."""
        try:
            if slug is None:
                slug = OrgModelService.slugify(name)
            base_slug, counter = slug, 1
            while OrgModelService.get_organization_by_slug(db, slug) is not None:
                slug = f"{base_slug}-{counter}"
                counter += 1

            org = Organization(
                name=name,
                slug=slug,
                domain=domain,
                settings={},
                status=status.value,
                requested_by_user_id=requested_by_user_id,
            )
            db.add(org)
            db.commit()
            db.refresh(org)

            if org.status == OrganizationStatus.ACTIVE.value:
                try:
                    _user_model_service.ensure_default_roles(db, org.id)
                except Exception as exc:
                    logger.debug(f"Failed to seed default roles for org {org.id}: {exc}")

            attach_superadmins_to_org(db, str(org.id))
            return org
        except Exception as exc:
            db.rollback()
            raise PersistenceError(f"Unable to create organization: {exc}") from exc

    @staticmethod
    def get_or_create_organization_for_email(
        db: Session,
        email: str,
        organization_name: str | None = None,
        requested_by_user_id: str | None = None,
    ) -> tuple[Organization, bool]:
        """Idempotent: return existing org for email's domain or create one."""
        if "@" not in email:
            raise ValueError("Invalid email address")

        domain = email.split("@")[1].lower()
        existing = OrgModelService.get_organization_by_domain(db, domain)
        if existing:
            return existing, False

        if domain in PUBLIC_EMAIL_DOMAINS:
            if not organization_name:
                raise ValueError(
                    "Organization name is required for public email domains like gmail.com"
                )
            org = OrgModelService._create_organization(
                db,
                name=organization_name,
                domain=None,
                status=OrganizationStatus.PENDING,
                requested_by_user_id=requested_by_user_id,
            )
            return org, True

        org_name = organization_name or OrgModelService._domain_to_org_name(domain)
        org = OrgModelService._create_organization(
            db,
            name=org_name,
            domain=domain,
            status=OrganizationStatus.PENDING,
            requested_by_user_id=requested_by_user_id,
        )
        return org, True


# ── DB operations ─────────────────────────────────────────────────────────────


class AuthDBOperations:
    """DB persistence helpers for the auth module."""

    @staticmethod
    def create_pending_org_with_admin(
        db: Session,
        org_name: str,
        slug: str,
        email: str,
        hashed_password: str,
        full_name: str,
    ) -> tuple[Organization, User]:
        """Create a pending Organization and its initial ADMIN User atomically."""
        try:
            org = Organization(
                id=str(uuid.uuid4()),
                name=org_name,
                slug=slug,
                settings={},
                status=OrganizationStatus.PENDING.value,
                requested_by_user_id=None,
            )
            db.add(org)
            db.flush()

            user = User(
                id=str(uuid.uuid4()),
                email=email.lower(),
                hashed_password=hashed_password,
                full_name=full_name,
                role=UserRole.ADMIN.value,
                status=UserStatus.PENDING.value,
                auth_type=AuthType.LOCAL.value,
                organization_id=org.id,
            )
            db.add(user)
            db.flush()

            _add_membership_row(db, user.id, org.id, UserRole.ADMIN.value)

            org.requested_by_user_id = user.id
            db.commit()
            db.refresh(user)
            db.refresh(org)
            attach_superadmins_to_org(db, str(org.id))
            return org, user
        except Exception as exc:
            db.rollback()
            raise PersistenceError(f"Unable to create pending organization with admin: {exc}") from exc

    @staticmethod
    def find_pending_invitation(db: Session, email: str) -> Invitation | None:
        """Return the newest unexpired pending Invitation for *email*, or None.

        Ordered so that an address invited by two organizations resolves to the
        most recent invitation rather than whatever the database returns first.
        """
        now = datetime.now(UTC)
        return (
            db.query(Invitation)
            .filter(
                Invitation.email == email.lower(),
                Invitation.status == InvitationStatus.PENDING.value,
                Invitation.expires_at > now,
            )
            .order_by(Invitation.created_at.desc())
            .first()
        )

    @staticmethod
    def update_user_password(db: Session, user: User, hashed_password: str) -> None:
        """Overwrite the user's hashed password and commit."""
        user.hashed_password = hashed_password
        db.commit()

    @staticmethod
    def get_user_by_id(db: Session, user_id: str) -> User | None:
        """Fetch a user by id (org-scoped)."""
        return db.query(User).filter(User.id == user_id).first()

    @staticmethod
    def get_user_by_email(db: Session, email: str) -> User | None:
        """Fetch a user by email (case-insensitive)."""
        return db.query(User).filter(User.email == email.lower()).first()

    @staticmethod
    def get_user_by_microsoft_id(db: Session, microsoft_id: str) -> User | None:
        """Fetch a user by Microsoft OAuth subject id."""
        return db.query(User).filter(User.microsoft_id == microsoft_id).first()

    @staticmethod
    def get_organization(db: Session, organization_id: str) -> Organization | None:
        """Fetch an organization by id."""
        return db.query(Organization).filter(Organization.id == organization_id).first()

    @staticmethod
    def count_users_in_org(db: Session, organization_id: str) -> int:
        """Count users belonging to the given organization."""
        return db.query(User).filter(User.organization_id == organization_id).count()

    @staticmethod
    def create_microsoft_user(
        db: Session,
        email: str,
        full_name: str,
        microsoft_id: str,
        avatar_url: str | None,
        role: str,
        status: str,
        organization_id: str,
    ) -> User:
        """Insert a user record from a Microsoft OAuth callback."""
        user = User(
            id=str(uuid.uuid4()),
            email=email.lower(),
            full_name=full_name,
            microsoft_id=microsoft_id,
            avatar_url=avatar_url,
            role=role,
            status=status,
            auth_type=AuthType.MICROSOFT.value,
            organization_id=organization_id,
        )
        db.add(user)
        db.flush()
        _add_membership_row(db, user.id, organization_id, role)
        return user


# ── Core auth service ─────────────────────────────────────────────────────────


class AuthService:
    """Core authentication operations (user lookups, token ops, local + Google auth)."""

    def __init__(
        self,
        db: Session,
        config: Any = None,
        roles_db_service: Any = None,
        audit_events_service: Any = None,
    ):
        """Initialize the in-memory store / DB-backed service."""
        self.db = db
        self.config = config
        self.roles_db_service = roles_db_service
        self.audit_events_service = audit_events_service

    # ── Audit logging ─────────────────────────────────────────────────────────

    def log_auth_event(
        self,
        event_type: AuthEventType,
        user_id: str | None = None,
        email: str | None = None,
        payload: dict | None = None,
        organization_id: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        """Append an authentication audit row to the unified audit_events table."""
        if not organization_id or self.audit_events_service is None:
            return None
        try:
            metadata = dict(payload) if payload else {}
            if email:
                metadata.setdefault("email", email)
            self.audit_events_service.emit_audit_event(
                organization_id=organization_id,
                metadata_type=AuditMetadataType.AUTH,
                user_id=user_id,
                event_type=event_type.value,
                actor_type="system",
                actor_id="auth_service",
                correlation_id=correlation_id,
                source="api",
                event_metadata=metadata,
            )
        except Exception as exc:
            logger.debug(f"Could not log auth event: {exc}")

    # ── User lookups ──────────────────────────────────────────────────────────

    def get_user_by_email(self, email: str) -> User | None:
        """Fetch a user by email (case-insensitive)."""
        return self.db.query(User).filter(User.email == email).first()

    def get_user_by_id(self, user_id: str) -> User | None:
        """Fetch a user by id (org-scoped)."""
        return self.db.query(User).filter(User.id == user_id).first()

    def get_user_by_google_id(self, google_id: str) -> User | None:
        """Fetch a user by Google OAuth subject id."""
        return self.db.query(User).filter(User.google_id == google_id).first()

    def is_first_user_in_org(self, organization_id: str) -> bool:
        """Predicate: is this the first user provisioned in the org."""
        return self.db.query(User).filter(User.organization_id == organization_id).count() == 0

    def _assign_admin_role_to_first_user(self, user_id: str, org_id: str) -> None:
        """Assign the dynamic admin role to the first user in an org via user_roles."""
        if self.roles_db_service is None:
            return
        try:
            self.roles_db_service.ensure_default_roles(self.db, org_id)
            admin_role = self.roles_db_service.get_role_by_name(self.db, org_id, "admin")
            if admin_role:
                self.roles_db_service.assign_role_to_user(self.db, user_id, org_id, admin_role.id)
        except Exception as exc:
            logger.error(f"Failed to assign dynamic admin role to first user {user_id} in org {org_id}: {exc}", exc_info=True)

    # ── Token ops ─────────────────────────────────────────────────────────────

    def _primary_membership_active(self, user: User, org_id: str) -> bool:
        """Return True if the user's membership in this org is active, delegating the
        rule to UserModelService.is_membership_active. An empty org_id returns False."""
        # Empty org_id -> not active, so create_tokens searches other memberships.
        if not org_id:
            return False
        return _user_model_service.is_membership_active(self.db, str(user.id), org_id)

    def create_tokens(self, user: User) -> tuple[str, str]:
        """Issue an (access, refresh) token pair scoped to an organization the user
        is active in: their primary org if active there, otherwise any active
        membership. Raises if the user has no active membership."""
        org_id = user.organization_id or ""
        if not self._primary_membership_active(user, org_id):
            # Land in another active membership. Per-org suspension means the
            # primary may be suspended even though the account can authenticate.
            # order_by makes the choice deterministic when more than one active
            # membership qualifies. updated_at is nullable with no DB default on
            # the live schema (most rows are NULL there), and Postgres sorts NULL
            # first on DESC, so nullslast() plus created_at (always populated) and
            # id as a final tiebreaker keep this deterministic regardless of how
            # sparsely updated_at is populated.
            membership = (
                self.db.query(UserOrganization)
                .join(Organization, Organization.id == UserOrganization.organization_id)
                .filter(
                    UserOrganization.user_id == user.id,
                    UserOrganization.status == UserStatus.ACTIVE.value,
                    Organization.status == OrganizationStatus.ACTIVE.value,
                )
                .order_by(
                    UserOrganization.updated_at.desc().nullslast(),
                    UserOrganization.created_at.desc(),
                    UserOrganization.id.desc(),
                )
                .first()
            )
            org_id = str(membership.organization_id) if membership else ""

        if not org_id:
            exc = ValidationError("No active organization access. Please contact an administrator.")
            exc.status_code = HTTPStatus.FORBIDDEN
            raise exc

        roles: list[str] = []
        if self.roles_db_service is not None and org_id:
            try:
                assigned_roles = self.roles_db_service.get_user_roles_with_permissions(
                    self.db, user.id, org_id
                )
                if assigned_roles:
                    roles = [r.name for r in assigned_roles]
            except PersistenceError as exc:
                logger.warning(f"Dynamic role enrichment failed for user {user.id}: {exc}")

        access_token = create_access_token(
            subject=user.id,
            organization_id=org_id,
            roles=roles,
        )
        refresh_token = create_refresh_token(subject=user.id)
        token_record = RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(refresh_token),
            expires_at=datetime.now(UTC)
            + timedelta(
                days=self.config._configuration.app_settings.refresh_token_expire_days
                if self.config
                else 7
            ),
        )
        self.db.add(token_record)
        self.db.commit()
        return access_token, refresh_token

    def refresh_access_token(self, refresh_token: str) -> tuple[str, str, User] | None:
        """Mint a new access token from a valid refresh token."""
        payload = decode_token(refresh_token)
        if not payload or payload.get("type") != "refresh":
            return None
        user_id = payload.get("sub")
        if not user_id:
            return None
        token_hash = hash_refresh_token(refresh_token)
        token_record = (
            self.db.query(RefreshToken)
            .filter(
                RefreshToken.token_hash == token_hash,
                RefreshToken.revoked == False,  # noqa: E712
                RefreshToken.expires_at > datetime.now(UTC),
            )
            .first()
        )
        if not token_record:
            return None
        user = self.get_user_by_id(user_id)
        if not user or not user.is_active:
            return None
        token_record.revoked = True
        self.db.commit()
        new_access, new_refresh = self.create_tokens(user)
        return new_access, new_refresh, user

    def revoke_refresh_token(self, refresh_token: str) -> bool:
        """Mark a refresh token as revoked so it can no longer mint access tokens."""
        token_hash = hash_refresh_token(refresh_token)
        record = self.db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()
        if record:
            record.revoked = True
            self.db.commit()
            return True
        return False

    def revoke_all_user_tokens(self, user_id: str) -> int:
        """Bulk-revoke every refresh token for a user (logout-everywhere)."""
        result = (
            self.db.query(RefreshToken)
            .filter(RefreshToken.user_id == user_id, RefreshToken.revoked == False)  # noqa: E712
            .update({"revoked": True})
        )
        self.db.commit()
        return result

    def update_last_login(self, user: User) -> None:
        """Stamp the user's last_login_at to now."""
        user.last_login_at = datetime.now(UTC)
        self.db.commit()

    # ── Local auth ────────────────────────────────────────────────────────────

    def authenticate_local(self, email: str, password: str) -> tuple[User | None, str | None]:
        """Verify email + password against the local user store."""
        user = self.get_user_by_email(email)
        if not user:
            return None, "not_found"
        if user.auth_type != AuthType.LOCAL.value:
            return None, "wrong_auth_type"
        if not user.hashed_password or not verify_password(password, user.hashed_password):
            return None, "invalid_password"
        if hasattr(user, "status") and user.status:
            if user.status == UserStatus.PENDING.value:
                return None, "pending_approval"
            if user.status == UserStatus.SUSPENDED.value:
                return None, "suspended"
            if user.status == UserStatus.REJECTED.value:
                return None, "rejected"
        if not user.is_active:
            return None, "inactive"
        return user, None

    # ── User creation ─────────────────────────────────────────────────────────

    def create_local_user(
        self,
        email: str,
        password: str,
        full_name: str,
        role: str = UserRole.VIEWER.value,
        organization_id: str | None = None,
        organization_name: str | None = None,
    ) -> UserCreationResult:
        """Provision a local (password) user, hashing the password."""
        is_new_org = False
        org: Organization | None = None

        if organization_id is None:
            org, is_new_org = OrgModelService.get_or_create_organization_for_email(
                self.db, email, organization_name=organization_name
            )
            organization_id = org.id
        else:
            org = OrgModelService.get_organization(self.db, organization_id)

        assert organization_id is not None  # narrowed by branches above
        is_first = self.is_first_user_in_org(organization_id)
        org_is_pending = org and org.status == OrganizationStatus.PENDING.value

        if org_is_pending:
            status = UserStatus.PENDING.value
            if is_first:
                role = UserRole.ADMIN.value
            approval_type = ApprovalType.PENDING_PLATFORM
        elif is_first:
            role = UserRole.ADMIN.value
            status = UserStatus.ACTIVE.value
            approval_type = ApprovalType.ACTIVE
        else:
            status = UserStatus.PENDING.value
            approval_type = ApprovalType.PENDING_ORG_ADMIN

        user = User(
            email=email,
            hashed_password=hash_password(password),
            full_name=full_name,
            role=role,
            status=status,
            auth_type=AuthType.LOCAL.value,
            organization_id=organization_id,
        )
        self.db.add(user)
        self.db.flush()
        _add_membership_row(self.db, user.id, organization_id, role)
        if is_new_org and org:
            org.requested_by_user_id = user.id
        self.db.commit()
        self.db.refresh(user)
        if org:
            self.db.refresh(org)
        if is_first:
            self._assign_admin_role_to_first_user(user.id, organization_id)
        return UserCreationResult(
            user=user, organization=org, is_new_org=is_new_org, approval_type=approval_type
        )

    def create_google_user(
        self,
        email: str,
        full_name: str,
        google_id: str,
        avatar_url: str | None = None,
        role: str = UserRole.VIEWER.value,
        organization_id: str | None = None,
        organization_name: str | None = None,
    ) -> UserCreationResult:
        """Insert a user record from a Google OAuth callback."""
        is_new_org = False
        org: Organization | None = None

        if organization_id is None:
            if OrgModelService.is_public_email_domain(email):
                existing_org = OrgModelService.get_organization_for_email(self.db, email)
                if existing_org:
                    org = existing_org
                    organization_id = org.id
                elif organization_name:
                    org, is_new_org = OrgModelService.get_or_create_organization_for_email(
                        self.db, email, organization_name=organization_name
                    )
                    organization_id = org.id
                else:
                    raise ValueError(
                        "Google sign-in with public email domains requires an organization. "
                        "Please sign up with your company email or request an invitation."
                    )
            else:
                org, is_new_org = OrgModelService.get_or_create_organization_for_email(
                    self.db, email, organization_name=organization_name
                )
                organization_id = org.id
        else:
            org = OrgModelService.get_organization(self.db, organization_id)

        assert organization_id is not None  # narrowed by branches above
        is_first = self.is_first_user_in_org(organization_id)
        org_is_pending = org and org.status == OrganizationStatus.PENDING.value

        if org_is_pending:
            status = UserStatus.PENDING.value
            if is_first:
                role = UserRole.ADMIN.value
            approval_type = ApprovalType.PENDING_PLATFORM
        elif is_first:
            role = UserRole.ADMIN.value
            status = UserStatus.ACTIVE.value
            approval_type = ApprovalType.ACTIVE
        else:
            status = UserStatus.PENDING.value
            approval_type = ApprovalType.PENDING_ORG_ADMIN

        user = User(
            email=email,
            full_name=full_name,
            google_id=google_id,
            avatar_url=avatar_url,
            role=role,
            status=status,
            auth_type=AuthType.GOOGLE.value,
            organization_id=organization_id,
        )
        self.db.add(user)
        self.db.flush()
        _add_membership_row(self.db, user.id, organization_id, role)
        if is_new_org and org:
            org.requested_by_user_id = user.id
        self.db.commit()
        self.db.refresh(user)
        if org:
            self.db.refresh(org)
        if is_first:
            self._assign_admin_role_to_first_user(user.id, organization_id)
        return UserCreationResult(
            user=user, organization=org, is_new_org=is_new_org, approval_type=approval_type
        )

    # ── Google OAuth ──────────────────────────────────────────────────────────

    def get_google_auth_url(self, redirect_uri: str | None = None) -> str:
        """Build the Google OAuth consent URL with the right scopes/state."""
        google_oauth_config = (
            self.config._configuration.google_oauth_configuration if self.config else None
        )
        if not (google_oauth_config and google_oauth_config.client_id):
            raise ValueError("Google OAuth is not configured")
        params = {
            "client_id": google_oauth_config.client_id,
            "redirect_uri": redirect_uri or google_oauth_config.redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "access_type": "offline",
            "prompt": "select_account",
        }
        return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"

    async def authenticate_google(
        self, code: str, redirect_uri: str | None = None
    ) -> UserCreationResult | None:
        """Exchange a Google OAuth code for a session and provision a user."""
        google_oauth_config = (
            self.config._configuration.google_oauth_configuration if self.config else None
        )
        _google_client_id = google_oauth_config.client_id if google_oauth_config else ""
        _google_client_secret = google_oauth_config.client_secret if google_oauth_config else ""
        if not _google_client_id or not _google_client_secret:
            raise ValueError("Google OAuth is not configured")

        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": _google_client_id,
                    "client_secret": _google_client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri
                    or (google_oauth_config.redirect_uri if google_oauth_config else ""),
                },
            )
            if token_response.status_code != 200:
                logger.warning(
                    f"Google token exchange failed: {token_response.status_code} - {token_response.text}"
                )
                return None
            tokens = token_response.json()

            userinfo_response = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {tokens['access_token']}"},
            )
            if userinfo_response.status_code != 200:
                logger.warning(f"Google userinfo fetch failed: {userinfo_response.status_code}")
                return None
            userinfo = userinfo_response.json()

        email = userinfo.get("email")
        google_id = userinfo.get("id")
        full_name = userinfo.get("name", email.split("@")[0] if email else "")
        avatar_url = userinfo.get("picture")

        if not email or not google_id:
            return None

        _allowed_domain = google_oauth_config.allowed_domain if google_oauth_config else ""
        if _allowed_domain and email.split("@")[1] != _allowed_domain:
            return None

        user = self.get_user_by_google_id(google_id)
        if user:
            user.full_name = full_name
            user.avatar_url = avatar_url
            self.db.commit()
            org = (
                OrgModelService.get_organization(self.db, user.organization_id)
                if user.organization_id
                else None
            )
            if not user.is_active:
                approval_type = (
                    ApprovalType.PENDING_PLATFORM
                    if (org and org.status == "pending")
                    else ApprovalType.PENDING_ORG_ADMIN
                )
            else:
                approval_type = ApprovalType.ACTIVE
            return UserCreationResult(
                user=user, organization=org, is_new_org=False, approval_type=approval_type
            )

        existing_user = self.get_user_by_email(email)
        if existing_user:
            existing_user.google_id = google_id
            existing_user.avatar_url = avatar_url
            self.db.commit()
            org = (
                OrgModelService.get_organization(self.db, existing_user.organization_id)
                if existing_user.organization_id
                else None
            )
            if not existing_user.is_active:
                approval_type = (
                    ApprovalType.PENDING_PLATFORM
                    if (org and org.status == "pending")
                    else ApprovalType.PENDING_ORG_ADMIN
                )
            else:
                approval_type = ApprovalType.ACTIVE
            return UserCreationResult(
                user=existing_user, organization=org, is_new_org=False, approval_type=approval_type
            )

        return self.create_google_user(
            email=email, full_name=full_name, google_id=google_id, avatar_url=avatar_url
        )

    # ── Misc ──────────────────────────────────────────────────────────────────

    def cleanup_expired_tokens(self) -> int:
        """Sweep expired refresh tokens out of the store."""
        result = (
            self.db.query(RefreshToken)
            .filter(
                or_(
                    RefreshToken.expires_at < datetime.now(UTC),
                    RefreshToken.revoked == True,  # noqa: E712
                )
            )
            .delete()
        )
        self.db.commit()
        return result
