"""Persistence adapter for the invitation module.

Owns the Invitation SQLAlchemy model and provides the InvitationModelService with all
DB operations needed by the invitation manager.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import Column, DateTime, ForeignKey, Index, String
from sqlalchemy.sql import func

from common.data_model import Enum
from common.logger import logger
from database.manager import Base
from exceptions import PersistenceError
from organizations.db_models import Organization, UserOrganization
from user.db_models import AuthType, User, UserRole, UserStatus

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class InvitationStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    EXPIRED = "expired"
    REVOKED = "revoked"


def _generate_invitation_token() -> str:
    return secrets.token_urlsafe(48)


def _default_invitation_expiry() -> datetime:
    return datetime.now(UTC) + timedelta(days=7)


class Invitation(Base):
    """Organization invitation for user onboarding."""

    __tablename__ = "invitations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email = Column(String(255), nullable=False, index=True)
    role = Column(String(32), nullable=False)
    token = Column(
        String(64), nullable=False, unique=True, index=True, default=_generate_invitation_token
    )
    status = Column(String(32), nullable=False, default=InvitationStatus.PENDING.value)
    invited_by_user_id = Column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    expires_at = Column(DateTime(timezone=True), nullable=False, default=_default_invitation_expiry)
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    accepted_user_id = Column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index(
            "ix_invitations_org_email_pending",
            "organization_id",
            "email",
            postgresql_where="status = 'pending'",
        ),
    )


class InvitationModelService:
    """DB operations for invitation management.

    Receives a per-request Session — no session management of its own.
    """

    def __init__(self, database_service_manager: Any = None) -> None:
        self.module_name = "invitation"

    # ── Queries ───────────────────────────────────────────────────────────────

    def get_by_id(self, db: Session, invitation_id: str) -> Invitation | None:
        """Fetch a single invitation by primary key.

        Args:
            db: Active SQLAlchemy session.
            invitation_id: UUID string of the invitation.

        Returns:
            Invitation instance or None if not found.

        Raises:
            PersistenceError: On database error.
        """
        try:
            return db.query(Invitation).filter(Invitation.id == invitation_id).first()
        except Exception as exc:
            raise PersistenceError(f"Unable to get invitation: {exc}") from exc

    def get_by_token(self, db: Session, token: str) -> Invitation | None:
        """Fetch an invitation by its unique token.

        Args:
            db: Active SQLAlchemy session.
            token: URL-safe token string.

        Returns:
            Invitation instance or None if not found.

        Raises:
            PersistenceError: On database error.
        """
        try:
            return db.query(Invitation).filter(Invitation.token == token).first()
        except Exception as exc:
            raise PersistenceError(f"Unable to get invitation by token: {exc}") from exc

    def list_by_org(
        self,
        db: Session,
        organization_id: str,
        status: str | None = None,
    ) -> list[Invitation]:
        """List invitations for an organization, optionally filtered by status.

        Args:
            db: Active SQLAlchemy session.
            organization_id: UUID of the organization.
            status: Optional status filter (pending/accepted/expired/revoked).

        Returns:
            List of Invitation instances ordered by created_at desc.

        Raises:
            PersistenceError: On database error.
        """
        try:
            query = db.query(Invitation).filter(Invitation.organization_id == organization_id)
            if status:
                query = query.filter(Invitation.status == status)
            return query.order_by(Invitation.created_at.desc()).all()
        except Exception as exc:
            raise PersistenceError(f"Unable to list invitations: {exc}") from exc

    def find_pending(self, db: Session, organization_id: str, email: str) -> Invitation | None:
        """Find an existing pending invitation for email+org combo.

        Args:
            db: Active SQLAlchemy session.
            organization_id: UUID of the organization.
            email: Normalized (lowercase) email address.

        Returns:
            Pending Invitation or None.

        Raises:
            PersistenceError: On database error.
        """
        try:
            return (
                db.query(Invitation)
                .filter(
                    Invitation.organization_id == organization_id,
                    Invitation.email == email,
                    Invitation.status == InvitationStatus.PENDING.value,
                )
                .first()
            )
        except Exception as exc:
            raise PersistenceError(f"Unable to find pending invitation: {exc}") from exc

    def get_user_by_email(self, db: Session, email: str) -> User | None:
        """Look up a user by email address.

        Args:
            db: Active SQLAlchemy session.
            email: Normalized (lowercase) email.

        Returns:
            User instance or None.

        Raises:
            PersistenceError: On database error.
        """
        try:
            return db.query(User).filter(User.email == email).first()
        except Exception as exc:
            raise PersistenceError(f"Unable to get user by email: {exc}") from exc

    def get_membership(
        self, db: Session, user_id: str, organization_id: str
    ) -> UserOrganization | None:
        """Check if a user is already a member of the organization.

        Args:
            db: Active SQLAlchemy session.
            user_id: UUID of the user.
            organization_id: UUID of the organization.

        Returns:
            UserOrganization membership row or None.

        Raises:
            PersistenceError: On database error.
        """
        try:
            return (
                db.query(UserOrganization)
                .filter(
                    UserOrganization.user_id == user_id,
                    UserOrganization.organization_id == organization_id,
                )
                .first()
            )
        except Exception as exc:
            raise PersistenceError(f"Unable to get membership: {exc}") from exc

    def get_organization(self, db: Session, organization_id: str) -> Organization | None:
        """Fetch an organization by ID.

        Args:
            db: Active SQLAlchemy session.
            organization_id: UUID of the organization.

        Returns:
            Organization instance or None.

        Raises:
            PersistenceError: On database error.
        """
        try:
            return db.query(Organization).filter(Organization.id == organization_id).first()
        except Exception as exc:
            raise PersistenceError(f"Unable to get organization: {exc}") from exc

    # ── Mutations ─────────────────────────────────────────────────────────────

    def create(
        self,
        db: Session,
        organization_id: str,
        email: str,
        role: str,
        invited_by_user_id: str,
    ) -> Invitation:
        """Persist a new pending invitation.

        Args:
            db: Active SQLAlchemy session.
            organization_id: UUID of the organization.
            email: Normalized email to invite.
            role: Role string to assign on acceptance.
            invited_by_user_id: UUID of the inviting user.

        Returns:
            Newly created Invitation instance.

        Raises:
            PersistenceError: On database error.
        """
        try:
            invitation = Invitation(
                organization_id=organization_id,
                email=email,
                role=role,
                invited_by_user_id=invited_by_user_id,
            )
            db.add(invitation)
            db.commit()
            db.refresh(invitation)
            logger.info(
                f"Created invitation id={invitation.id} email={email} org_id={organization_id}"
            )
            return invitation
        except Exception as exc:
            db.rollback()
            raise PersistenceError(f"Unable to create invitation: {exc}") from exc

    def refresh_token(self, db: Session, invitation: Invitation) -> Invitation:
        """Regenerate token and extend expiry for an existing invitation.

        Args:
            db: Active SQLAlchemy session.
            invitation: Invitation instance to update.

        Returns:
            Updated Invitation instance.

        Raises:
            PersistenceError: On database error.
        """
        try:
            invitation.token = _generate_invitation_token()
            invitation.expires_at = _default_invitation_expiry()
            db.commit()
            db.refresh(invitation)
            return invitation
        except Exception as exc:
            db.rollback()
            raise PersistenceError(f"Unable to refresh invitation token: {exc}") from exc

    def set_status(self, db: Session, invitation: Invitation, status: str) -> Invitation:
        """Update the status of an invitation.

        Args:
            db: Active SQLAlchemy session.
            invitation: Invitation instance to update.
            status: New status value.

        Returns:
            Updated Invitation instance.

        Raises:
            PersistenceError: On database error.
        """
        try:
            invitation.status = status
            db.commit()
            db.refresh(invitation)
            return invitation
        except Exception as exc:
            db.rollback()
            raise PersistenceError(f"Unable to update invitation status: {exc}") from exc

    def accept(self, db: Session, invitation: Invitation, user_id: str) -> Invitation:
        """Mark invitation as accepted and record accepting user.

        Args:
            db: Active SQLAlchemy session.
            invitation: Invitation to accept.
            user_id: UUID of the user who accepted.

        Returns:
            Updated Invitation instance.

        Raises:
            PersistenceError: On database error.
        """
        try:
            invitation.status = InvitationStatus.ACCEPTED.value
            invitation.accepted_at = datetime.now(UTC)
            invitation.accepted_user_id = user_id
            db.commit()
            db.refresh(invitation)
            return invitation
        except Exception as exc:
            db.rollback()
            raise PersistenceError(f"Unable to accept invitation: {exc}") from exc

    def create_user_and_membership(
        self,
        db: Session,
        email: str,
        full_name: str,
        hashed_password: str,
        role: str,
        organization_id: str,
    ) -> User:
        """Create a new user and add them to the organization.

        Args:
            db: Active SQLAlchemy session.
            email: Normalized email address.
            full_name: Display name.
            hashed_password: Bcrypt-hashed password string.
            role: Role to assign.
            organization_id: UUID of the organization to join.

        Returns:
            Newly created User instance.

        Raises:
            PersistenceError: On database error.
        """
        try:
            user = User(
                email=email,
                full_name=full_name,
                hashed_password=hashed_password,
                role=role,
                status=UserStatus.ACTIVE.value,
                auth_type=AuthType.LOCAL.value,
                organization_id=organization_id,
            )
            db.add(user)
            db.flush()

            membership = UserOrganization(
                user_id=user.id,
                organization_id=organization_id,
                role=role,
                status=UserStatus.ACTIVE.value,
            )
            db.add(membership)
            db.commit()
            db.refresh(user)
            return user
        except Exception as exc:
            db.rollback()
            raise PersistenceError(f"Unable to create user from invitation: {exc}") from exc

    def add_membership(
        self,
        db: Session,
        user: User,
        organization_id: str,
        role: str,
        set_as_active: bool = False,
    ) -> None:
        """Add an existing user to an organization.

        Args:
            db: Active SQLAlchemy session.
            user: Existing User instance.
            organization_id: UUID of the organization to join.
            role: Role to assign.
            set_as_active: Whether to make this the user's active organization.

        Raises:
            PersistenceError: On database error.
        """
        try:
            membership = UserOrganization(
                user_id=user.id,
                organization_id=organization_id,
                role=role,
                status=UserStatus.ACTIVE.value,
            )
            db.add(membership)
            if set_as_active:
                user.organization_id = organization_id
                if user.role != UserRole.SUPERADMIN.value:
                    user.role = role
            elif not user.organization_id:
                user.organization_id = organization_id
            db.commit()
        except Exception as exc:
            db.rollback()
            raise PersistenceError(f"Unable to add user to organization: {exc}") from exc

    def activate_membership(self, user: User, membership: UserOrganization) -> None:
        """Stage an existing membership as the user's active organization."""
        user.organization_id = membership.organization_id
        if user.role != UserRole.SUPERADMIN.value:
            user.role = membership.role
