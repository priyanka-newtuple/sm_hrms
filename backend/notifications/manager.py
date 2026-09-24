"""Business logic manager for notifications."""

from __future__ import annotations

import html
import os
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from comments.models.interface import render_mentions_as_text
from common.logger import logger
from exceptions import AuthorizationError, NotFoundError, ServiceError, ValidationError
from notifications.models.interface import (
    COMMENT_PREVIEW_LENGTH,
    EMAIL_KIND_ASSIGNMENT,
    EMAIL_KIND_COMMENT,
    EMAIL_KIND_LIKE,
    EMAIL_KIND_MENTION,
    EMAIL_KIND_NEW_ORG,
    EMAIL_KIND_NEW_USER,
    EMAIL_KIND_REPLY,
    EMAIL_PREVIEW_LENGTH,
    FEATURE_FLAG_SEND_ASSIGNMENT_EMAILS,
    FEATURE_FLAG_SEND_COMMENT_EMAILS,
    FEATURE_FLAG_SEND_LIKE_EMAILS,
    FEATURE_FLAG_SEND_REPLY_EMAILS,
    NOTIFICATION_TYPE_ASSIGNMENT,
    NOTIFICATION_TYPE_COMMENT,
    NOTIFICATION_TYPE_LIKE,
    NOTIFICATION_TYPE_MENTION,
    NOTIFICATION_TYPE_REPLY,
)
from notifications.models.request import NotificationCreateRequest
from notifications.models.response import (
    MarkAllReadResponse,
    NotificationListResponse,
    NotificationRead,
    UnreadCountResponse,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.orm import Session

    from common.protocols import BackgroundTaskScheduler
    from notifications.db_models import NotificationsModelService


class NotificationsServiceManager:
    """Notifications orchestration service."""

    def __init__(
        self,
        notifications_db_model_service: NotificationsModelService,
        database_service_manager: Any,
        config: Any,
        auth_service_manager: Any = None,
        mail_service_manager: Any = None,
        *dependencies: object,
        user_service_manager: Any = None,
        organizations_service_manager: Any = None,
    ) -> None:
        """Initialize the manager.

        Args:
            notifications_db_model_service: Persistence adapter.
            database_service_manager: Database service manager.
            config: Global configuration.
            auth_service_manager: Auth manager for RBAC (optional).
            dependencies: Optional dependencies.
            user_service_manager: Resolves recipient emails for notification emails.
            organizations_service_manager: Resolves the org's notification-email feature flag.
        """
        self.db_model_service = notifications_db_model_service
        self.notifications_db_model_service = notifications_db_model_service
        self.database_service_manager = database_service_manager
        self.config = config
        self.auth_service_manager = auth_service_manager
        self._mail_service_manager = mail_service_manager
        self.dependencies = list(dependencies)
        self.user_service_manager = user_service_manager
        self.organizations_service_manager = organizations_service_manager
        self._started = False
        self.module_name = "notifications"

    def start(self) -> None:
        """Start the manager.

        Returns:
            None.
        """
        self._started = True

    def stop(self) -> None:
        """Stop the manager.

        Returns:
            None.
        """
        self._started = False

    def list_notifications_for_actor(
        self,
        actor: dict[str, object],
        *,
        db: Session | None = None,
        is_read: bool | None,
        limit: int,
        offset: int,
    ) -> NotificationListResponse:
        """List notifications for the current actor.

        Args:
            actor: Actor context dict (user_id, organization_id, roles).
            is_read: Optional read filter.
            limit: Page size.
            offset: Page offset.

        Returns:
            NotificationListResponse.
        """
        recipient_id = self._require_actor_field(actor, "user_id")
        organization_id = self._require_actor_field(actor, "organization_id")
        self._authorize_actor_operation(
            actor, resource="notification", action="read", organization_id=organization_id
        )

        try:
            notifications = self.db_model_service.list_notifications(
                db=db,
                organization_id=organization_id,
                recipient_id=recipient_id,
                is_read=is_read,
                limit=limit,
                offset=offset,
            )
            unread_count = self.db_model_service.get_unread_count(
                db=db,
                organization_id=organization_id,
                recipient_id=recipient_id,
            )
            return NotificationListResponse(
                notifications=[NotificationRead.model_validate(item) for item in notifications],
                total=len(notifications),
                unread_count=unread_count,
            )
        except (AuthorizationError, NotFoundError, ValidationError) as exc:
            logger.exception(f"notifications.list_notifications_for_actor failed: {exc}")
            raise
        except Exception as exc:
            raise ServiceError(f"Unable to list notifications: {exc}") from exc

    def get_unread_count_for_actor(
        self, actor: dict[str, object], *, db: Session | None = None
    ) -> UnreadCountResponse:
        """Get unread notification count for the current actor.

        Args:
            actor: Actor context dict (user_id, organization_id, roles).
            db: Optional SQLAlchemy Session.

        Returns:
            UnreadCountResponse.

        Raises:
            AuthorizationError: When actor is not allowed.
            ValidationError: When actor context is incomplete.
            ServiceError: For unexpected failures.
        """
        recipient_id = self._require_actor_field(actor, "user_id")
        organization_id = self._require_actor_field(actor, "organization_id")
        self._authorize_actor_operation(
            actor, resource="notification", action="read", organization_id=organization_id
        )
        try:
            count = self.db_model_service.get_unread_count(
                db=db,
                organization_id=organization_id,
                recipient_id=recipient_id,
            )
            return UnreadCountResponse(count=count)
        except (AuthorizationError, ValidationError) as exc:
            logger.exception(f"notifications.get_unread_count_for_actor failed: {exc}")
            raise
        except Exception as exc:
            raise ServiceError(f"Unable to get unread count: {exc}") from exc

    def mark_as_read_for_actor(
        self,
        actor: dict[str, object],
        *,
        db: Session | None = None,
        notification_id: str,
    ) -> NotificationRead:
        """Mark one notification as read for the current actor.

        Args:
            actor: Actor context dict (user_id, organization_id, roles).
            db: Optional SQLAlchemy Session.
            notification_id: Notification id.

        Returns:
            Updated notification.

        Raises:
            NotFoundError: When the notification does not exist or is not owned by actor.
            AuthorizationError: When actor is not allowed.
            ValidationError: When inputs are invalid.
            ServiceError: For unexpected failures.
        """
        recipient_id = self._require_actor_field(actor, "user_id")
        organization_id = self._require_actor_field(actor, "organization_id")
        self._authorize_actor_operation(
            actor, resource="notification", action="write", organization_id=organization_id
        )
        try:
            notification = self.db_model_service.mark_as_read(
                db=db,
                organization_id=organization_id,
                recipient_id=recipient_id,
                notification_id=str(notification_id).strip(),
            )
            if notification is None:
                raise NotFoundError("Notification not found")
            return NotificationRead.model_validate(notification)
        except (AuthorizationError, NotFoundError, ValidationError) as exc:
            logger.exception(f"notifications.mark_as_read_for_actor failed: {exc}")
            raise
        except Exception as exc:
            raise ServiceError(f"Unable to mark notification as read: {exc}") from exc

    def mark_all_as_read_for_actor(
        self, actor: dict[str, object], *, db: Session | None = None
    ) -> MarkAllReadResponse:
        """Mark all notifications as read for the current actor.

        Args:
            actor: Actor context dict (user_id, organization_id, roles).
            db: Optional SQLAlchemy Session.

        Returns:
            MarkAllReadResponse.

        Raises:
            AuthorizationError: When actor is not allowed.
            ValidationError: When actor context is incomplete.
            ServiceError: For unexpected failures.
        """
        recipient_id = self._require_actor_field(actor, "user_id")
        organization_id = self._require_actor_field(actor, "organization_id")
        self._authorize_actor_operation(
            actor, resource="notification", action="write", organization_id=organization_id
        )
        try:
            updated = self.db_model_service.mark_all_as_read(
                db=db,
                organization_id=organization_id,
                recipient_id=recipient_id,
            )
            return MarkAllReadResponse(updated=updated)
        except (AuthorizationError, ValidationError) as exc:
            logger.exception(f"notifications.mark_all_as_read_for_actor failed: {exc}")
            raise
        except Exception as exc:
            raise ServiceError(f"Unable to mark all notifications as read: {exc}") from exc

    def delete_notification_for_actor(
        self,
        actor: dict[str, object],
        *,
        db: Session | None = None,
        notification_id: str,
    ) -> None:
        """Delete one notification for the current actor.

        Args:
            actor: Actor context dict (user_id, organization_id, roles).
            db: Optional SQLAlchemy Session.
            notification_id: Notification id.

        Returns:
            None.

        Raises:
            NotFoundError: When the notification does not exist or is not owned by actor.
            AuthorizationError: When actor is not allowed.
            ValidationError: When inputs are invalid.
            ServiceError: For unexpected failures.
        """
        recipient_id = self._require_actor_field(actor, "user_id")
        organization_id = self._require_actor_field(actor, "organization_id")
        self._authorize_actor_operation(
            actor, resource="notification", action="write", organization_id=organization_id
        )
        try:
            deleted = self.db_model_service.delete_notification(
                db=db,
                organization_id=organization_id,
                recipient_id=recipient_id,
                notification_id=str(notification_id).strip(),
            )
            if not deleted:
                raise NotFoundError("Notification not found")
        except (AuthorizationError, NotFoundError, ValidationError) as exc:
            logger.exception(f"notifications.delete_notification_for_actor failed: {exc}")
            raise
        except Exception as exc:
            raise ServiceError(f"Unable to delete notification: {exc}") from exc

    def create_notification(
        self,
        *,
        db: Session | None = None,
        organization_id: str,
        recipient_id: str,
        notification_type: str,
        entity_id: str,
        entity_type: str,
        title: str,
        body: str | None = None,
        link: str | None = None,
        actor_id: str | None = None,
        actor_name: str | None = None,
        source_type: str | None = None,
        source_id: str | None = None,
    ) -> NotificationRead:
        """Create a notification record.

        Args:
            db: SQLAlchemy session.
            organization_id: Organization id.
            recipient_id: Recipient user id.
            notification_type: Notification type (e.g. "mention", "assignment", "system").
            entity_id: Related entity id.
            entity_type: Related entity type.
            title: Notification title.
            body: Optional body text.
            link: Optional frontend link.
            actor_id: Optional triggering user id.
            actor_name: Optional triggering user name.
            source_type: Optional source type (e.g. "comment").
            source_id: Optional source id.

        Returns:
            NotificationRead.

        Raises:
            ServiceError: For unexpected failures.
        """
        try:
            payload = NotificationCreateRequest(
                organization_id=organization_id,
                recipient_id=recipient_id,
                notification_type=notification_type,
                entity_id=entity_id,
                entity_type=entity_type,
                title=title,
                body=body,
                link=link,
                actor_id=actor_id,
                actor_name=actor_name,
                source_type=source_type,
                source_id=source_id,
            )
            notification = self.db_model_service.create_notification(
                db=db,
                organization_id=payload.organization_id,
                recipient_id=payload.recipient_id,
                notification_type=payload.notification_type,
                entity_id=payload.entity_id,
                entity_type=payload.entity_type,
                title=payload.title,
                body=payload.body,
                link=payload.link,
                actor_id=payload.actor_id,
                actor_name=payload.actor_name,
                source_type=payload.source_type,
                source_id=payload.source_id,
            )
            return NotificationRead.model_validate(notification)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        except Exception as exc:
            raise ServiceError(f"Unable to create notification: {exc}") from exc

    def _email_notifications_enabled(
        self, db: Session | None, organization_id: str, flag_key: str
    ) -> bool:
        """Whether Settings → Display has turned on the given per-org email flag
        ("sendAssignmentEmails" or "sendCommentEmails")."""
        if self.organizations_service_manager is None or db is None:
            return False
        try:
            org = self.organizations_service_manager.get_current(db, organization_id)
        except Exception as exc:
            logger.warning(
                f"_email_notifications_enabled lookup failed for org {organization_id}: {exc}"
            )
            return False
        flags = dict(org.settings or {}).get("featureFlags")
        return isinstance(flags, dict) and flags.get(flag_key) is True

    def _resolve_recipient_email(
        self, db: Session | None, organization_id: str, recipient_id: str
    ) -> str | None:
        if self.user_service_manager is None or db is None:
            return None
        try:
            return self.user_service_manager.get_user(db, recipient_id, organization_id).email
        except Exception as exc:
            logger.warning(f"_resolve_recipient_email lookup failed for user {recipient_id}: {exc}")
            return None

    def _maybe_send_notification_email(
        self,
        *,
        db: Session | None,
        organization_id: str,
        recipient_id: str,
        flag_key: str,
        send_fn: Callable[[str], None],
    ) -> None:
        """Resolve the recipient's email and call `send_fn(recipient_email)`,
        but only if the org has this notification type's email flag enabled.
        The in-app notification always fires regardless — this only gates
        whether an email additionally goes out."""
        if not self._email_notifications_enabled(db, organization_id, flag_key):
            return
        recipient_email = self._resolve_recipient_email(db, organization_id, recipient_id)
        if recipient_email:
            send_fn(recipient_email)

    @contextmanager
    def _fresh_db_session(self):
        """Open a brand-new session against the shared pool, independent of any
        request-scoped session. Only used inside a deferred (background) email
        send by the time that callback runs, the request's own `db` (from
        `Depends(get_db)`) may already be closed by FastAPI's dependency
        teardown."""
        if self.database_service_manager is None:
            raise ServiceError("database_service_manager is not configured")
        session = self.database_service_manager.postgres_db_service().get_db_session()
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _dispatch_send_email(
        self,
        *,
        background_tasks: BackgroundTaskScheduler | None,
        db: Session | None,
        organization_id: str,
        to: str | list[str],
        subject: str,
        body_html: str,
    ) -> None:
        """Send a fully-prepared email (subject/body already rendered from a
        template by the caller)."""
        if background_tasks is None:
            try:
                self._mail_service_manager.send_email(
                    db=db, org_id=organization_id, to=to, subject=subject, body_html=body_html
                )
            except Exception as exc:
                logger.error(f"send_email failed org={organization_id} to={to}: {exc}")
            return

        def _deferred() -> None:
            try:
                with self._fresh_db_session() as fresh_db:
                    self._mail_service_manager.send_email(
                        db=fresh_db,
                        org_id=organization_id,
                        to=to,
                        subject=subject,
                        body_html=body_html,
                    )
            except Exception as exc:
                logger.error(f"deferred send_email failed org={organization_id} to={to}: {exc}")

        background_tasks.add_task(_deferred)

    def create_mention_notification(
        self,
        *,
        db: Session | None = None,
        organization_id: str,
        recipient_id: str,
        entity_id: str,
        entity_type: str,
        entity_label: str = "",
        comment_id: str,
        comment_text: str,
        actor_id: str,
        actor_name: str = "",
        link: str | None = None,
        background_tasks: BackgroundTaskScheduler | None = None,
    ) -> NotificationRead:
        """Create a mention notification and, if enabled in Settings → Display,
        email the mentioned user.

        Args:
            db: SQLAlchemy session.
            organization_id: Organization id.
            recipient_id: User id of the mentioned user.
            entity_id: Entity the comment belongs to.
            entity_type: Entity type.
            comment_id: Comment id containing the mention.
            comment_text: Full comment text (used for email preview).
            actor_id: User id who wrote the comment.
            actor_name: Display name of the user who wrote the comment.
            link: Optional frontend route to the entity.
            background_tasks: When given, defers the email's network send to
                run after the HTTP response (see `_dispatch_send_email`).

        Returns:
            NotificationRead.

        Raises:
            ServiceError: For unexpected failures.
        """
        comment_text = render_mentions_as_text(comment_text)
        preview = (
            comment_text[:COMMENT_PREVIEW_LENGTH] + "..."
            if len(comment_text) > COMMENT_PREVIEW_LENGTH
            else comment_text
        )
        notification = self.create_notification(
            db=db,
            organization_id=organization_id,
            recipient_id=recipient_id,
            notification_type=NOTIFICATION_TYPE_MENTION,
            entity_id=entity_id,
            entity_type=entity_type,
            title=f"{actor_name} mentioned you in a comment"
            if actor_name
            else "You were mentioned in a comment",
            body=preview,
            link=link,
            actor_id=actor_id,
            actor_name=actor_name,
            source_type="comment",
            source_id=comment_id,
        )
        self._maybe_send_notification_email(
            db=db,
            organization_id=organization_id,
            recipient_id=recipient_id,
            flag_key=FEATURE_FLAG_SEND_COMMENT_EMAILS,
            send_fn=lambda recipient_email: self._send_mention_email(
                db=db,
                organization_id=organization_id,
                recipient_email=recipient_email,
                actor_name=actor_name,
                entity_label=entity_label or entity_type,
                comment_text=comment_text,
                link=link,
                background_tasks=background_tasks,
            ),
        )
        return notification

    def delete_notifications_for_source(
        self,
        *,
        db: Session | None = None,
        source_type: str,
        source_id: str,
    ) -> int:
        """Delete all notifications tied to a source (e.g. when a comment is deleted).

        Args:
            db: SQLAlchemy session.
            source_type: Source type (e.g. "comment").
            source_id: Source id.

        Returns:
            Number of notifications deleted.

        Raises:
            ServiceError: For unexpected failures.
        """
        try:
            return self.db_model_service.delete_notifications_for_source(
                db=db,
                source_type=source_type,
                source_id=source_id,
            )
        except Exception as exc:
            raise ServiceError(f"Unable to delete notifications for source: {exc}") from exc

    def notify_admins_new_user(
        self,
        *,
        db: Session | None = None,
        organization_id: str,
        new_user_email: str,
        new_user_name: str,
        admin_emails: list[str],
        background_tasks: BackgroundTaskScheduler | None = None,
    ) -> None:
        """Send email to org admins when a new user registers.

        Args:
            db: SQLAlchemy session.
            organization_id: Organization id.
            new_user_email: Email of the new registrant.
            new_user_name: Name of the new registrant.
            admin_emails: List of admin email addresses to notify.
            background_tasks: When given, defers the email's network send to
                run after the HTTP response (see `_dispatch_send_email`).
        """
        if self._mail_service_manager is None:
            logger.warning("notify_admins_new_user: mail service not available, skipping email")
            return
        if not admin_emails:
            logger.warning("notify_admins_new_user: no admin emails provided, skipping")
            return
        try:
            frontend_url = os.environ.get("FRONTEND_URL", "").rstrip("/")
            approval_url = f"{frontend_url}/settings?tab=users"
            values = {
                "new_user_name": html.escape(new_user_name),
                "new_user_email": html.escape(new_user_email),
                "approval_url": approval_url,
            }
            template = self._mail_service_manager.get_default_email_template_for_kind(
                db, organization_id, EMAIL_KIND_NEW_USER
            )
            if template is None:
                logger.warning(
                    "notify_admins_new_user: no notification.new_user template found, skipping email"
                )
                return
            subject = self._render_template(template["subject"], values)
            body_html = self._render_template(template["body_html"], values)
            self._dispatch_send_email(
                background_tasks=background_tasks,
                db=db,
                organization_id=organization_id,
                to=admin_emails,
                subject=subject,
                body_html=body_html,
            )
        except Exception as exc:
            logger.warning(f"notify_admins_new_user failed: {exc}")

    def notify_superadmins_new_org(
        self,
        *,
        db: Session | None = None,
        org_name: str,
        requester_email: str,
        requester_name: str,
        superadmin_emails: list[str],
        platform_org_id: str,
        background_tasks: BackgroundTaskScheduler | None = None,
    ) -> None:
        """Send email to superadmins when a new organization is requested.

        Args:
            db: SQLAlchemy session.
            org_name: Name of the requested organization.
            requester_email: Email of the requester.
            requester_name: Name of the requester.
            superadmin_emails: List of superadmin email addresses to notify.
            platform_org_id: Platform org id (used to resolve mail config).
            background_tasks: When given, defers the email's network send to
                run after the HTTP response (see `_dispatch_send_email`).
        """
        if self._mail_service_manager is None:
            logger.warning("notify_superadmins_new_org: mail service not available, skipping email")
            return
        if not superadmin_emails:
            logger.warning("notify_superadmins_new_org: no superadmin emails provided, skipping")
            return
        try:
            frontend_url = os.environ.get("FRONTEND_URL", "").rstrip("/")
            approval_url = f"{frontend_url}/settings?tab=organizations"
            values = {
                "org_name": html.escape(org_name),
                "requester_name": html.escape(requester_name),
                "requester_email": html.escape(requester_email),
                "approval_url": approval_url,
            }
            template = self._mail_service_manager.get_default_email_template_for_kind(
                db, platform_org_id, EMAIL_KIND_NEW_ORG
            )
            if template is None:
                logger.warning(
                    "notify_superadmins_new_org: no notification.new_org template found, skipping email"
                )
                return
            subject = self._render_template(template["subject"], values)
            body_html = self._render_template(template["body_html"], values)
            self._dispatch_send_email(
                background_tasks=background_tasks,
                db=db,
                organization_id=platform_org_id,
                to=superadmin_emails,
                subject=subject,
                body_html=body_html,
            )
        except Exception as exc:
            logger.warning(f"notify_superadmins_new_org failed: {exc}")

    @staticmethod
    def _render_template(text: str, values: dict[str, str]) -> str:
        """Replace {{key}} placeholders in a stored email template."""
        for key, value in values.items():
            text = text.replace(f"{{{{{key}}}}}", value)
        return text

    @staticmethod
    def _email_preview(comment_text: str) -> str:
        """Comment text as an email-safe preview: mentions readable, truncated, escaped."""
        readable_text = render_mentions_as_text(comment_text)
        truncated = (
            readable_text[:EMAIL_PREVIEW_LENGTH] + "..."
            if len(readable_text) > EMAIL_PREVIEW_LENGTH
            else readable_text
        )
        return html.escape(truncated)

    def _send_mention_email(
        self,
        *,
        db: Session | None,
        organization_id: str,
        recipient_email: str,
        actor_name: str,
        entity_label: str,
        comment_text: str,
        link: str | None,
        background_tasks: BackgroundTaskScheduler | None = None,
    ) -> None:
        """Send an email for an @mention notification.

        Args:
            db: SQLAlchemy session.
            organization_id: Organization id.
            recipient_email: Email address of the mentioned user.
            actor_name: Name of the user who mentioned.
            comment_text: Full comment text.
            link: Optional frontend route.
            background_tasks: When given, defers the email's network send to
                run after the HTTP response (see `_dispatch_send_email`).
        """
        if self._mail_service_manager is None:
            logger.warning("_send_mention_email: mail service not available, skipping email")
            return
        template = self._mail_service_manager.get_default_email_template_for_kind(
            db, organization_id, EMAIL_KIND_MENTION
        )
        if template is None:
            logger.warning(
                "_send_mention_email: no notification.mention template found, skipping email"
            )
            return
        try:
            frontend_url = os.environ.get("FRONTEND_URL", "").rstrip("/")
            full_url = f"{frontend_url}{link}" if link else ""
            preview = self._email_preview(comment_text)
            values = {
                "actor_name": html.escape(actor_name or "Someone"),
                "entity_label": html.escape(entity_label or "a record"),
                "comment_text": preview,
                "link": full_url,
            }
            subject = self._render_template(template["subject"], values)
            body_html = self._render_template(template["body_html"], values)
            self._dispatch_send_email(
                background_tasks=background_tasks,
                db=db,
                organization_id=organization_id,
                to=recipient_email,
                subject=subject,
                body_html=body_html,
            )
        except Exception as exc:
            logger.warning(
                f"_send_mention_email failed org={organization_id} to={recipient_email}: {exc}"
            )

    def create_assignment_notification(
        self,
        *,
        db: Session | None = None,
        organization_id: str,
        recipient_id: str,
        entity_id: str,
        entity_type: str,
        entity_label: str,
        actor_id: str | None = None,
        actor_name: str = "",
        link: str | None = None,
        background_tasks: BackgroundTaskScheduler | None = None,
    ) -> NotificationRead:
        """Create an assignment notification and, if enabled in Settings → Display,
        email the newly assigned user."""
        notification = self.create_notification(
            db=db,
            organization_id=organization_id,
            recipient_id=recipient_id,
            notification_type=NOTIFICATION_TYPE_ASSIGNMENT,
            entity_id=entity_id,
            entity_type=entity_type,
            title=f"You were assigned {entity_label}",
            body=f"You are now the assignee for {entity_label}.",
            link=link,
            actor_id=actor_id,
            actor_name=actor_name,
        )
        recipient_email = (
            self._resolve_recipient_email(db, organization_id, recipient_id)
            if self._email_notifications_enabled(
                db, organization_id, FEATURE_FLAG_SEND_ASSIGNMENT_EMAILS
            )
            else None
        )
        if recipient_email:
            self._send_assignment_email(
                db=db,
                organization_id=organization_id,
                recipient_email=recipient_email,
                actor_name=actor_name,
                entity_label=entity_label,
                link=link,
                background_tasks=background_tasks,
            )
        return notification

    def _send_assignment_email(
        self,
        *,
        db: Session | None,
        organization_id: str,
        recipient_email: str,
        actor_name: str,
        entity_label: str,
        link: str | None,
        background_tasks: BackgroundTaskScheduler | None = None,
    ) -> None:
        """Send an email for an assignment notification."""
        if self._mail_service_manager is None:
            logger.warning("_send_assignment_email: mail service not available, skipping email")
            return
        template = self._mail_service_manager.get_default_email_template_for_kind(
            db, organization_id, EMAIL_KIND_ASSIGNMENT
        )
        if template is None:
            logger.warning(
                "_send_assignment_email: no notification.assignment template found, skipping email"
            )
            return
        try:
            frontend_url = os.environ.get("FRONTEND_URL", "").rstrip("/")
            full_url = f"{frontend_url}{link}" if link else ""
            values = {
                "entity_label": html.escape(entity_label),
                "actor_name": html.escape(actor_name or "a teammate"),
                "link": full_url,
            }
            subject = self._render_template(template["subject"], values)
            body_html = self._render_template(template["body_html"], values)
            self._dispatch_send_email(
                background_tasks=background_tasks,
                db=db,
                organization_id=organization_id,
                to=recipient_email,
                subject=subject,
                body_html=body_html,
            )
        except Exception as exc:
            logger.warning(f"_send_assignment_email failed: {exc}")

    def create_comment_notification(
        self,
        *,
        db: Session | None = None,
        organization_id: str,
        recipient_id: str,
        entity_id: str,
        entity_type: str,
        entity_label: str,
        comment_id: str,
        comment_text: str,
        actor_id: str,
        actor_name: str = "",
        link: str | None = None,
        background_tasks: BackgroundTaskScheduler | None = None,
    ) -> NotificationRead:
        """Create a comment notification for the entity's assignee and, if enabled
        in Settings → Display, email them. Distinct from @mention notifications."""
        comment_text = render_mentions_as_text(comment_text)
        notification = self.create_notification(
            db=db,
            organization_id=organization_id,
            recipient_id=recipient_id,
            notification_type=NOTIFICATION_TYPE_COMMENT,
            entity_id=entity_id,
            entity_type=entity_type,
            title=f"{actor_name} commented on {entity_label}"
            if actor_name
            else f"New comment on {entity_label}",
            body=(
                comment_text[:COMMENT_PREVIEW_LENGTH] + "..."
                if len(comment_text) > COMMENT_PREVIEW_LENGTH
                else comment_text
            ),
            link=link,
            actor_id=actor_id,
            actor_name=actor_name,
            source_type="comment",
            source_id=comment_id,
        )
        self._maybe_send_notification_email(
            db=db,
            organization_id=organization_id,
            recipient_id=recipient_id,
            flag_key=FEATURE_FLAG_SEND_COMMENT_EMAILS,
            send_fn=lambda recipient_email: self._send_comment_email(
                db=db,
                organization_id=organization_id,
                recipient_email=recipient_email,
                actor_name=actor_name,
                entity_label=entity_label,
                comment_text=comment_text,
                link=link,
                background_tasks=background_tasks,
            ),
        )
        return notification

    def _send_comment_email(
        self,
        *,
        db: Session | None,
        organization_id: str,
        recipient_email: str,
        actor_name: str,
        entity_label: str,
        comment_text: str,
        link: str | None,
        background_tasks: BackgroundTaskScheduler | None = None,
    ) -> None:
        """Send an email telling an entity's assignee that a comment was made on it."""
        if self._mail_service_manager is None:
            logger.warning("_send_comment_email: mail service not available, skipping email")
            return
        template = self._mail_service_manager.get_default_email_template_for_kind(
            db, organization_id, EMAIL_KIND_COMMENT
        )
        if template is None:
            logger.warning(
                "_send_comment_email: no notification.comment template found, skipping email"
            )
            return
        try:
            frontend_url = os.environ.get("FRONTEND_URL", "").rstrip("/")
            full_url = f"{frontend_url}{link}" if link else ""
            preview = self._email_preview(comment_text)
            values = {
                "entity_label": html.escape(entity_label),
                "actor_name": html.escape(actor_name or "Someone"),
                "comment_text": preview,
                "link": full_url,
            }
            subject = self._render_template(template["subject"], values)
            body_html = self._render_template(template["body_html"], values)
            self._dispatch_send_email(
                background_tasks=background_tasks,
                db=db,
                organization_id=organization_id,
                to=recipient_email,
                subject=subject,
                body_html=body_html,
            )
        except Exception as exc:
            logger.warning(
                f"_send_comment_email failed org={organization_id} to={recipient_email}: {exc}"
            )

    def create_reply_notification(
        self,
        *,
        db: Session | None = None,
        organization_id: str,
        recipient_id: str,
        entity_id: str,
        entity_type: str,
        comment_id: str,
        parent_comment_text: str,
        reply_text: str,
        actor_id: str,
        actor_name: str = "",
        link: str | None = None,
        background_tasks: BackgroundTaskScheduler | None = None,
    ) -> NotificationRead:
        """Create a notification for the parent comment's author when someone
        replies to it and, if enabled in Settings → Display, email them."""
        parent_comment_text = render_mentions_as_text(parent_comment_text)
        reply_text = render_mentions_as_text(reply_text)
        preview = (
            reply_text[:COMMENT_PREVIEW_LENGTH] + "..."
            if len(reply_text) > COMMENT_PREVIEW_LENGTH
            else reply_text
        )
        notification = self.create_notification(
            db=db,
            organization_id=organization_id,
            recipient_id=recipient_id,
            notification_type=NOTIFICATION_TYPE_REPLY,
            entity_id=entity_id,
            entity_type=entity_type,
            title=f"{actor_name} replied to your comment"
            if actor_name
            else "Someone replied to your comment",
            body=preview,
            link=link,
            actor_id=actor_id,
            actor_name=actor_name,
            source_type="comment",
            source_id=comment_id,
        )
        self._maybe_send_notification_email(
            db=db,
            organization_id=organization_id,
            recipient_id=recipient_id,
            flag_key=FEATURE_FLAG_SEND_REPLY_EMAILS,
            send_fn=lambda recipient_email: self._send_reply_email(
                db=db,
                organization_id=organization_id,
                recipient_email=recipient_email,
                actor_name=actor_name,
                parent_comment_text=parent_comment_text,
                reply_text=reply_text,
                link=link,
                background_tasks=background_tasks,
            ),
        )
        return notification

    def _send_reply_email(
        self,
        *,
        db: Session | None,
        organization_id: str,
        recipient_email: str,
        actor_name: str,
        parent_comment_text: str,
        reply_text: str,
        link: str | None,
        background_tasks: BackgroundTaskScheduler | None = None,
    ) -> None:
        """Send an email telling a comment's author that someone replied to it."""
        if self._mail_service_manager is None:
            logger.warning("_send_reply_email: mail service not available, skipping email")
            return
        template = self._mail_service_manager.get_default_email_template_for_kind(
            db, organization_id, EMAIL_KIND_REPLY
        )
        if template is None:
            logger.warning(
                "_send_reply_email: no notification.reply template found, skipping email"
            )
            return
        try:
            frontend_url = os.environ.get("FRONTEND_URL", "").rstrip("/")
            full_url = f"{frontend_url}{link}" if link else ""
            values = {
                "actor_name": html.escape(actor_name or "Someone"),
                "comment_text": html.escape(
                    parent_comment_text[:EMAIL_PREVIEW_LENGTH] + "..."
                    if len(parent_comment_text) > EMAIL_PREVIEW_LENGTH
                    else parent_comment_text
                ),
                "reply_text": html.escape(
                    reply_text[:EMAIL_PREVIEW_LENGTH] + "..."
                    if len(reply_text) > EMAIL_PREVIEW_LENGTH
                    else reply_text
                ),
                "link": full_url,
            }
            subject = self._render_template(template["subject"], values)
            body_html = self._render_template(template["body_html"], values)
            self._dispatch_send_email(
                background_tasks=background_tasks,
                db=db,
                organization_id=organization_id,
                to=recipient_email,
                subject=subject,
                body_html=body_html,
            )
        except Exception as exc:
            logger.warning(
                f"_send_reply_email failed org={organization_id} to={recipient_email}: {exc}"
            )

    def create_like_notification(
        self,
        *,
        db: Session | None = None,
        organization_id: str,
        recipient_id: str,
        entity_id: str,
        entity_type: str,
        comment_id: str,
        comment_text: str,
        actor_id: str,
        actor_name: str = "",
        link: str | None = None,
        background_tasks: BackgroundTaskScheduler | None = None,
    ) -> NotificationRead:
        """Create a notification for a comment's author when someone likes it
        and, if enabled in Settings → Display, email them. Off by default —
        likes are high-frequency/low-signal, so this flag defaults to False
        until an org admin opts in."""
        comment_text = render_mentions_as_text(comment_text)
        notification = self.create_notification(
            db=db,
            organization_id=organization_id,
            recipient_id=recipient_id,
            notification_type=NOTIFICATION_TYPE_LIKE,
            entity_id=entity_id,
            entity_type=entity_type,
            title=f"{actor_name} liked your comment"
            if actor_name
            else "Someone liked your comment",
            body=(
                comment_text[:COMMENT_PREVIEW_LENGTH] + "..."
                if len(comment_text) > COMMENT_PREVIEW_LENGTH
                else comment_text
            ),
            link=link,
            actor_id=actor_id,
            actor_name=actor_name,
            source_type="comment",
            source_id=comment_id,
        )
        self._maybe_send_notification_email(
            db=db,
            organization_id=organization_id,
            recipient_id=recipient_id,
            flag_key=FEATURE_FLAG_SEND_LIKE_EMAILS,
            send_fn=lambda recipient_email: self._send_like_email(
                db=db,
                organization_id=organization_id,
                recipient_email=recipient_email,
                actor_name=actor_name,
                comment_text=comment_text,
                link=link,
                background_tasks=background_tasks,
            ),
        )
        return notification

    def _send_like_email(
        self,
        *,
        db: Session | None,
        organization_id: str,
        recipient_email: str,
        actor_name: str,
        comment_text: str,
        link: str | None,
        background_tasks: BackgroundTaskScheduler | None = None,
    ) -> None:
        """Send an email telling a comment's author that someone liked it."""
        if self._mail_service_manager is None:
            logger.warning("_send_like_email: mail service not available, skipping email")
            return
        template = self._mail_service_manager.get_default_email_template_for_kind(
            db, organization_id, EMAIL_KIND_LIKE
        )
        if template is None:
            logger.warning("_send_like_email: no notification.like template found, skipping email")
            return
        try:
            frontend_url = os.environ.get("FRONTEND_URL", "").rstrip("/")
            full_url = f"{frontend_url}{link}" if link else ""
            preview = html.escape(
                comment_text[:EMAIL_PREVIEW_LENGTH] + "..."
                if len(comment_text) > EMAIL_PREVIEW_LENGTH
                else comment_text
            )
            values = {
                "actor_name": html.escape(actor_name or "Someone"),
                "comment_text": preview,
                "link": full_url,
            }
            subject = self._render_template(template["subject"], values)
            body_html = self._render_template(template["body_html"], values)
            self._dispatch_send_email(
                background_tasks=background_tasks,
                db=db,
                organization_id=organization_id,
                to=recipient_email,
                subject=subject,
                body_html=body_html,
            )
        except Exception as exc:
            logger.warning(
                f"_send_like_email failed org={organization_id} to={recipient_email}: {exc}"
            )

    def _authorize_actor_operation(
        self,
        actor: dict[str, object],
        *,
        resource: str,
        action: str,
        organization_id: str,
    ) -> None:
        """Authorize an operation for an actor within an organization scope.

        Args:
            actor: Actor context dict.
            resource: Resource name (RBAC matrix key).
            action: Action name (RBAC matrix key).
            organization_id: Organization id being accessed.

        Returns:
            None.

        Raises:
            AuthorizationError: When forbidden by org scope or RBAC.
            ValidationError: When actor context is invalid.
        """
        actor_org_id = self._require_actor_field(actor, "organization_id")
        if organization_id != actor_org_id:
            raise AuthorizationError("Forbidden organization scope")

    @staticmethod
    def _require_actor_field(actor: dict[str, object], field_name: str) -> str:
        """Require and normalize a string field from actor context.

        Args:
            actor: Actor context dict.
            field_name: Required field name.

        Returns:
            Normalized string value.

        Raises:
            ValidationError: When the field is missing or empty.
        """
        value = str(actor.get(field_name) or "").strip()
        if not value:
            raise ValidationError(f"actor.{field_name} is required")
        return value

    def notify_connector_auth_error(
        self,
        *,
        db: Session | None = None,
        organization_id: str,
        connector_id: str,
        connector_name: str,
        user_ids: list[str],
    ) -> None:
        """Notify all users with connector:write that a connector's credentials have expired.

        Called by the HTTP webhook executor when an external API returns 401/403.
        """
        if not user_ids:
            return
        frontend_url = os.environ.get("FRONTEND_URL", "").rstrip("/")
        link = f"{frontend_url}/settings?tab=connectors"
        for user_id in user_ids:
            try:
                self.create_notification(
                    db=db,
                    organization_id=organization_id,
                    recipient_id=user_id,
                    notification_type="system",
                    entity_id=connector_id,
                    entity_type="connector",
                    title=f"Connector credentials expired: {connector_name}",
                    body="The connector returned an authentication error (401/403). Please rotate the credentials in Settings → Connectors.",
                    link=link,
                )
            except Exception as exc:
                logger.warning(
                    f"notify_connector_auth_error: failed for user={user_id} connector={connector_id}: {exc}"
                )
