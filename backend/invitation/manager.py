"""Business logic manager for the invitation module."""

from __future__ import annotations

import contextlib
import html
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from common.logger import logger
from common.security import hash_password
from exceptions import NotFoundError, ValidationError
from invitation.db_models import Invitation, InvitationStatus
from invitation.models.response import (
    AcceptInvitationResponse,
    InvitationResponse,
    InvitationValidationResponse,
)
from mail.manager import email_service
from user.db_models import User
from mail.models.interface import EmailActionKind

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from invitation.db_models import InvitationModelService
    from roles.manager import RolesServiceManager

# Action kind of the system email template seeded for invitations. Keep in sync
# with the seed migration (2026_08_09_0001_seed_invitation_email_template).
EMAIL_KIND_INVITATION = EmailActionKind.INVITATION.value


class InvitationServiceManager:
    """Stateless invitation management business logic.

    Instantiated once and injected into InvitationRestController.
    Each method receives the per-request DB session as a parameter.
    """

    def __init__(
        self,
        invitation_model_service: InvitationModelService,
        database_service_manager: Any = None,
        roles_service_manager : RolesServiceManager = None,
        config: Any = None,
    ) -> None:
        self.db_service = invitation_model_service
        self.config = config
        self.module_name = "invitation"
        self._started = False
        self.roles_service_manager = roles_service_manager
        # Back-linked in the composition root once the mail manager is built, so
        # the invitation email can render the seeded system template.
        self._mail_service_manager = None

    def start(self) -> None:
        self._started = True

    def stop(self) -> None:
        self._started = False

    # ── Queries ───────────────────────────────────────────────────────────────

    def list_invitations(
        self,
        db: Session,
        organization_id: str,
        status: str | None = None,
    ) -> list[InvitationResponse]:
        """List invitations for an organization.

        Args:
            db: Active SQLAlchemy session.
            organization_id: UUID of the organization.
            status: Optional status filter.

        Returns:
            List of InvitationResponse objects.
        """
        invitations = self.db_service.list_by_org(db, organization_id, status=status)
        logger.info(
            f"Listed {len(invitations)} invitations org_id={organization_id} status={status}"
        )
        return [InvitationResponse.model_validate(i) for i in invitations]

    def validate_token(self, db: Session, token: str) -> InvitationValidationResponse:
        """Validate an invitation token and return details.

        Args:
            db: Active SQLAlchemy session.
            token: URL-safe invitation token.

        Returns:
            InvitationValidationResponse with the valid flag, context, and
            user_exists — true when the email already has an account, in which
            case accepting only adds the organization and no name or password
            is used.
        """
        invitation = self.db_service.get_by_token(db, token)
        if not invitation:
            return InvitationValidationResponse(valid=False, error="Invitation not found")

        if invitation.status == InvitationStatus.REVOKED.value:
            return InvitationValidationResponse(
                valid=False, error="This invitation has been revoked"
            )

        if invitation.status == InvitationStatus.ACCEPTED.value:
            return InvitationValidationResponse(
                valid=False, error="This invitation has already been accepted"
            )

        now = datetime.now(UTC)
        if invitation.expires_at < now:
            if invitation.status != InvitationStatus.EXPIRED.value:
                self.db_service.set_status(db, invitation, InvitationStatus.EXPIRED.value)
            return InvitationValidationResponse(valid=False, error="This invitation has expired")

        org = self.db_service.get_organization(db, invitation.organization_id)
        return InvitationValidationResponse(
            valid=True,
            email=invitation.email,
            role=invitation.role,
            organization_name=org.name if org else "Unknown Organization",
            expires_at=invitation.expires_at.isoformat(),
            user_exists=self.db_service.get_user_by_email(db, invitation.email.lower()) is not None,
        )

    # ── Mutations ─────────────────────────────────────────────────────────────

    def create_invitation(
        self,
        db: Session,
        organization_id: str,
        email: str,
        role: str,
        invited_by_user_id: str,
    ) -> InvitationResponse:
        """Create and send an invitation.

        Args:
            db: Active SQLAlchemy session.
            organization_id: UUID of the inviting organization.
            email: Email address to invite.
            role: Role to assign on acceptance.
            invited_by_user_id: UUID of the user sending the invite.

        Returns:
            InvitationResponse for the new invitation.

        Raises:
            ValidationError: If user is already a member, invitation exists, or role is invalid.
        """
        email = email.lower().strip()

        # validate incoming role if it's part of the RBAC roles
        available_roles = [roleitem.name for roleitem in self.roles_service_manager.list_roles(db, organization_id)]
        if role not in available_roles:
            logger.warning(f"Invitation Not Created : {role} Does not exist in Database. Current available roles are {available_roles}")
            raise ValidationError(f"Invitation Rejected : {role} Does not exist in Database.")

        existing_user = self.db_service.get_user_by_email(db, email)
        if existing_user:
            membership = self.db_service.get_membership(db, existing_user.id, organization_id)
            if membership:
                raise ValidationError("User is already a member of this organization")

        if self.db_service.find_pending(db, organization_id, email):
            raise ValidationError("A pending invitation already exists for this email")

        invitation = self.db_service.create(
            db,
            organization_id=organization_id,
            email=email,
            role=role,
            invited_by_user_id=invited_by_user_id,
        )

        self._send_invitation_email(db, invitation)
        return InvitationResponse.model_validate(invitation)

    def accept_invitation(
        self,
        db: Session,
        token: str,
        full_name: str | None = None,
        password: str | None = None,
    ) -> AcceptInvitationResponse:
        """Accept an invitation and create or add the user.

        Args:
            db: Active SQLAlchemy session.
            token: URL-safe invitation token.
            full_name: Required for new users.
            password: Required for new users (min 8 chars).

        Returns:
            AcceptInvitationResponse with the user_id.

        Raises:
            NotFoundError: If invitation token is not found.
            ValidationError: If invitation is invalid/expired or fields are missing.
        """
        invitation = self.db_service.get_by_token(db, token)
        if not invitation:
            raise NotFoundError("Invitation not found")

        validation = self.validate_token(db, token)
        if not validation.valid:
            raise ValidationError(validation.error or "Invalid invitation")

        email = invitation.email.lower()
        existing_user = self.db_service.get_user_by_email(db, email)

        if existing_user:
            membership = self.db_service.get_membership(
                db, existing_user.id, invitation.organization_id
            )
            if membership:
                logger.info(
                    f"Invitation acceptance skipped: user_id={existing_user.id} "
                    f"is already a member of organization_id={invitation.organization_id}"
                )
                self.db_service.activate_membership(existing_user, membership)
                self.db_service.accept(db, invitation, existing_user.id)
                return AcceptInvitationResponse(
                    message="You're already a member of this organization",
                    user_id=existing_user.id,
                    already_member=True,
                )

            self.db_service.add_membership(
                db,
                existing_user,
                invitation.organization_id,
                invitation.role,
                set_as_active=True,
            )
            user = existing_user
        else:
            if not full_name or not password:
                raise ValidationError("Full name and password are required for new users")
            if len(password) < 8:
                raise ValidationError("Password must be at least 8 characters")
            user = self.db_service.create_user_and_membership(
                db,
                email=email,
                full_name=full_name.strip(),
                hashed_password=hash_password(password),
                role=invitation.role,
                organization_id=invitation.organization_id,
            )

        self.roles_service_manager.assign_role_by_name(
            db, user.id, invitation.organization_id, invitation.role
        )

        self.db_service.accept(db, invitation, user.id)
        logger.info(f"Invitation accepted id={invitation.id} user_id={user.id}")
        return AcceptInvitationResponse(message="Invitation accepted", user_id=user.id)

    def resend_invitation(
        self, db: Session, invitation_id: str, organization_id: str
    ) -> InvitationResponse:
        """Resend an invitation with a new token and extended expiry.

        Args:
            db: Active SQLAlchemy session.
            invitation_id: UUID of the invitation.
            organization_id: UUID of the requesting organization (ownership check).

        Returns:
            Updated InvitationResponse.

        Raises:
            NotFoundError: If invitation is not found or belongs to another org.
            ValidationError: If invitation is not pending.
        """
        invitation = self.db_service.get_by_id(db, invitation_id)
        if not invitation or invitation.organization_id != organization_id:
            raise NotFoundError("Invitation not found")

        if invitation.status != InvitationStatus.PENDING.value:
            raise ValidationError("Can only resend pending invitations")

        invitation = self.db_service.refresh_token(db, invitation)
        self._send_invitation_email(db, invitation)
        logger.info(f"Resent invitation id={invitation_id}")
        return InvitationResponse.model_validate(invitation)

    def revoke_invitation(
        self, db: Session, invitation_id: str, organization_id: str
    ) -> InvitationResponse:
        """Revoke a pending invitation.

        Args:
            db: Active SQLAlchemy session.
            invitation_id: UUID of the invitation.
            organization_id: UUID of the requesting organization (ownership check).

        Returns:
            Updated InvitationResponse.

        Raises:
            NotFoundError: If invitation is not found or belongs to another org.
            ValidationError: If invitation is not pending.
        """
        invitation = self.db_service.get_by_id(db, invitation_id)
        if not invitation or invitation.organization_id != organization_id:
            raise NotFoundError("Invitation not found")

        if invitation.status != InvitationStatus.PENDING.value:
            raise ValidationError("Can only revoke pending invitations")

        invitation = self.db_service.set_status(db, invitation, InvitationStatus.REVOKED.value)
        logger.info(f"Revoked invitation id={invitation_id}")
        return InvitationResponse.model_validate(invitation)

    # ── Internal ──────────────────────────────────────────────────────────────

    @staticmethod
    def _render_template(text: str, values: dict[str, str]) -> str:
        """Replace {{key}} placeholders in a stored email template."""
        for key, value in values.items():
            text = text.replace(f"{{{{{key}}}}}", value)
        return text

    def _send_invitation_email(self, db: Session, invitation: Invitation) -> None:
        """Send invitation email to the invitee.

        Args:
            db: Active SQLAlchemy session.
            invitation: Invitation instance to send email for.
        """
        org = self.db_service.get_organization(db, invitation.organization_id)
        org_name = org.name if org else "Newtuple"

        inviter = None
        if invitation.invited_by_user_id:
            with contextlib.suppress(Exception):
                inviter = db.query(User).filter(User.id == invitation.invited_by_user_id).first()
        inviter_name = inviter.full_name if inviter else "An administrator"

        frontend_url = ""
        if self.config:
            with contextlib.suppress(Exception):
                frontend_url = self.config._configuration.app_settings.frontend_url

        accept_url = f"{frontend_url.rstrip('/')}/accept-invite?token={invitation.token}"
        expires_date = invitation.expires_at.strftime("%B %d, %Y")
        role_display = invitation.role.replace("_", " ").title()

        values = {
            "inviter_name": html.escape(inviter_name),
            "org_name": html.escape(org_name),
            "role": html.escape(role_display),
            "expires": html.escape(expires_date),
            "accept_url": html.escape(accept_url, quote=True),
        }

        mail = self._mail_service_manager
        template = (
            mail.get_default_email_template_for_kind(
                db, invitation.organization_id, EMAIL_KIND_INVITATION
            )
            if mail
            else None
        )
        if template:
            subject = self._render_template(template["subject"], values)
            body_html = self._render_template(template["body_html"], values)
        else:
            # Defensive fallback if the system template is missing (unseeded env);
            # the seeded default normally supplies the full body.
            logger.warning("invitation email template '%s' not found; using minimal fallback", EMAIL_KIND_INVITATION)
            subject = f"You're invited to join {org_name}"
            body_html = (
                f'<p>{values["inviter_name"]} has invited you to join '
                f'<strong>{values["org_name"]}</strong> as a {values["role"]}.</p>'
                f'<p><a href="{values["accept_url"]}">Accept your invitation</a> '
                f"(expires {values['expires']}).</p>"
            )

        sender = mail or email_service
        result = sender.send_email(
            db=db,
            org_id=invitation.organization_id,
            to=invitation.email,
            subject=subject,
            body_html=body_html,
        )

        if result.success:
            logger.info(f"Invitation email sent to {invitation.email}")
        else:
            logger.warning(
                f"Failed to send invitation email to {invitation.email}: {result.message}"
            )
