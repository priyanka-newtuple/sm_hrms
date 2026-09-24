"""Persistence adapters for the notifications module."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.sql import func

from common.logger import logger
from database.manager import Base
from exceptions import PersistenceError

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class Notification(Base):
    """In-app notification for a user.

    Mirrors the legacy `app.models.notification.Notification` schema so the modular
    backend can operate without importing from `backend/app/`.
    """

    __tablename__ = "notifications"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    organization_id = Column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    recipient_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    notification_type = Column(String(32), nullable=False)
    source_type = Column(String(64), nullable=True)
    source_id = Column(String(36), nullable=True)

    entity_id = Column(String(36), nullable=False, index=True)
    entity_type = Column(String(128), nullable=False)

    actor_id = Column(String(36), nullable=True)
    actor_name = Column(String(256), nullable=True)

    title = Column(String(256), nullable=False)
    body = Column(Text, nullable=True)
    link = Column(String(512), nullable=True)

    is_read = Column(Boolean, nullable=False, default=False)
    read_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_notifications_recipient_unread", "recipient_id", "is_read"),
        Index("ix_notifications_created_at", "created_at"),
        Index("ix_notifications_org_recipient", "organization_id", "recipient_id"),
    )


def _utc_now() -> datetime:
    """Return the current UTC time.

    Returns:
        Current timezone-aware datetime in UTC.
    """
    return datetime.now(UTC)


@dataclass
class NotificationRecord:
    """In-memory fallback record for tests and local usage without DB."""

    id: str
    organization_id: str
    recipient_id: str
    notification_type: str
    entity_id: str
    entity_type: str
    title: str
    body: str | None = None
    link: str | None = None
    source_type: str | None = None
    source_id: str | None = None
    actor_id: str | None = None
    actor_name: str | None = None
    is_read: bool = False
    read_at: datetime | None = None
    created_at: datetime = field(default_factory=_utc_now)


class NotificationsModelService:
    """Notification persistence service.

    Accepts an injected SQLAlchemy Session per call (preferred). Falls back to an
    in-memory store when no DB session is provided (unit tests).
    """

    def __init__(self, database_service_manager: Any = None) -> None:
        """Initialize the persistence service.

        Args:
            database_service_manager: Database service manager (may be None in tests).
        """
        self.database_service_manager = database_service_manager
        self.module_name = "notifications"
        self._records_by_org: dict[str, list[NotificationRecord]] = {}

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
    ) -> Notification | NotificationRecord:
        """Create a notification record.

        Args:
            organization_id: Organization id.
            recipient_id: Recipient user id.
            notification_type: Notification type ("mention", "system", etc.).
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
            Created notification (ORM model when DB is configured; otherwise a record).

        Raises:
            PersistenceError: When persistence fails.
        """
        if db is None:
            record = NotificationRecord(
                id=str(uuid4()),
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
            self._records_by_org.setdefault(organization_id, []).append(record)
            return record

        try:
            notification = Notification(
                organization_id=organization_id,
                recipient_id=recipient_id,
                notification_type=notification_type,
                source_type=source_type,
                source_id=source_id,
                entity_id=entity_id,
                entity_type=entity_type,
                actor_id=actor_id,
                actor_name=actor_name,
                title=title,
                body=body,
                link=link,
                is_read=False,
                read_at=None,
            )
            db.add(notification)
            db.commit()
            db.refresh(notification)
            return notification
        except Exception as exc:
            db.rollback()
            raise PersistenceError(f"Unable to create notification: {exc}") from exc

    def list_notifications(
        self,
        *,
        db: Session | None = None,
        organization_id: str,
        recipient_id: str,
        is_read: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Notification | NotificationRecord]:
        """List notifications for a recipient within an organization.

        Args:
            organization_id: Organization id.
            recipient_id: Recipient user id.
            is_read: Optional read filter.
            limit: Page size (max 100 enforced at controller layer).
            offset: Page offset.

        Returns:
            List of notifications ordered by creation time (newest first).

        Raises:
            PersistenceError: When the query fails.
        """
        if db is None:
            records = [
                record
                for record in self._records_by_org.get(organization_id, [])
                if record.recipient_id == recipient_id
                and (is_read is None or record.is_read == is_read)
            ]
            records.sort(key=lambda r: r.created_at, reverse=True)
            return records[offset : offset + limit]

        try:
            query = db.query(Notification).filter(
                Notification.organization_id == organization_id,
                Notification.recipient_id == recipient_id,
            )
            if is_read is not None:
                query = query.filter(Notification.is_read == is_read)
            return query.order_by(Notification.created_at.desc()).offset(offset).limit(limit).all()
        except Exception as exc:
            raise PersistenceError(f"Unable to list notifications: {exc}") from exc

    def get_unread_count(
        self, *, db: Session | None = None, organization_id: str, recipient_id: str
    ) -> int:
        """Return the unread count for a recipient in an organization.

        Args:
            db: Optional SQLAlchemy Session.
            organization_id: Organization id.
            recipient_id: Recipient user id.

        Returns:
            Number of unread notifications.

        Raises:
            PersistenceError: When the query fails.
        """
        if db is None:
            return sum(
                1
                for record in self._records_by_org.get(organization_id, [])
                if record.recipient_id == recipient_id and not record.is_read
            )

        try:
            return (
                db.query(Notification)
                .filter(
                    Notification.organization_id == organization_id,
                    Notification.recipient_id == recipient_id,
                    Notification.is_read == False,  # noqa: E712
                )
                .count()
            )
        except Exception as exc:
            raise PersistenceError(f"Unable to get unread count: {exc}") from exc

    def mark_as_read(
        self,
        *,
        db: Session | None = None,
        organization_id: str,
        recipient_id: str,
        notification_id: str,
    ) -> Notification | NotificationRecord | None:
        """Mark a notification as read.

        Args:
            organization_id: Organization id.
            recipient_id: Recipient user id.
            notification_id: Notification id.

        Returns:
            Updated notification, or None when not found / not owned by the recipient.

        Raises:
            PersistenceError: When the update fails.
        """
        if db is None:
            for record in self._records_by_org.get(organization_id, []):
                if record.id == notification_id and record.recipient_id == recipient_id:
                    if not record.is_read:
                        record.is_read = True
                        record.read_at = _utc_now()
                    return record
            return None

        try:
            notification = (
                db.query(Notification)
                .filter(
                    Notification.id == notification_id,
                    Notification.organization_id == organization_id,
                    Notification.recipient_id == recipient_id,
                )
                .first()
            )
            if notification is None:
                return None
            if not notification.is_read:
                notification.is_read = True
                notification.read_at = _utc_now()
                db.commit()
                db.refresh(notification)
            return notification
        except Exception as exc:
            db.rollback()
            raise PersistenceError(f"Unable to mark notification as read: {exc}") from exc

    def mark_all_as_read(
        self, *, db: Session | None = None, organization_id: str, recipient_id: str
    ) -> int:
        """Mark all notifications as read for the recipient in the organization.

        Args:
            db: Optional SQLAlchemy Session.
            organization_id: Organization id.
            recipient_id: Recipient user id.

        Returns:
            Number of notifications updated.

        Raises:
            PersistenceError: When the update fails.
        """
        if db is None:
            updated = 0
            now = _utc_now()
            for record in self._records_by_org.get(organization_id, []):
                if record.recipient_id == recipient_id and not record.is_read:
                    record.is_read = True
                    record.read_at = now
                    updated += 1
            return updated

        try:
            now = _utc_now()
            result = (
                db.query(Notification)
                .filter(
                    Notification.organization_id == organization_id,
                    Notification.recipient_id == recipient_id,
                    Notification.is_read == False,  # noqa: E712
                )
                .update({"is_read": True, "read_at": now}, synchronize_session=False)
            )
            db.commit()
            return int(result or 0)
        except Exception as exc:
            db.rollback()
            raise PersistenceError(f"Unable to mark all notifications as read: {exc}") from exc

    def delete_notification(
        self,
        *,
        db: Session | None = None,
        organization_id: str,
        recipient_id: str,
        notification_id: str,
    ) -> bool:
        """Delete a notification.

        Args:
            organization_id: Organization id.
            recipient_id: Recipient user id.
            notification_id: Notification id.

        Returns:
            True if deleted, False if not found / not owned by the recipient.

        Raises:
            PersistenceError: When the delete fails.
        """
        if db is None:
            records = self._records_by_org.get(organization_id, [])
            for idx, record in enumerate(list(records)):
                if record.id == notification_id and record.recipient_id == recipient_id:
                    del records[idx]
                    return True
            return False

        try:
            notification = (
                db.query(Notification)
                .filter(
                    Notification.id == notification_id,
                    Notification.organization_id == organization_id,
                    Notification.recipient_id == recipient_id,
                )
                .first()
            )
            if notification is None:
                return False
            db.delete(notification)
            db.commit()
            return True
        except Exception as exc:
            db.rollback()
            raise PersistenceError(f"Unable to delete notification: {exc}") from exc

    def delete_notifications_for_source(
        self,
        *,
        db: Session | None = None,
        source_type: str,
        source_id: str,
    ) -> int:
        """Delete all notifications tied to a source (e.g. when a comment is deleted).

        Args:
            source_type: Source type (e.g. "comment").
            source_id: Source id.

        Returns:
            Number of notifications deleted.

        Raises:
            PersistenceError: When the delete fails.
        """
        if db is None:
            deleted = 0
            for records in self._records_by_org.values():
                to_remove = [
                    r for r in records if r.source_type == source_type and r.source_id == source_id
                ]
                for r in to_remove:
                    records.remove(r)
                    deleted += 1
            return deleted

        try:
            result = (
                db.query(Notification)
                .filter(
                    Notification.source_type == source_type,
                    Notification.source_id == source_id,
                )
                .delete(synchronize_session=False)
            )
            db.commit()
            return result
        except Exception as exc:
            db.rollback()
            raise PersistenceError(f"Unable to delete notifications for source: {exc}") from exc

    def debug_dump_records(self) -> dict[str, list[NotificationRecord]]:
        """Return the in-memory records map (test helper).

        Returns:
            Map of organization id -> list of in-memory notification records.
        """
        logger.debug(
            f"Dumping in-memory notifications records org_count={len(self._records_by_org)}"
        )
        return self._records_by_org
