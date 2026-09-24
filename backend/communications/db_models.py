"""Persistence adapters for communications.

Owns:
  - In-memory comment/notification records (CommunicationsModelService)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from common.enums import NotificationChannel, NotificationStatus
from communications.models.interface import normalize_mentions
from exceptions import PersistenceError

if TYPE_CHECKING:
    from communications.models.request import (
        CommentCreateRequest,
        NotificationCreateRequest,
    )
    from database.manager import DatabaseServiceManager


# ── Helpers ───────────────────────────────────────────────────────────────────


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


# ── In-memory records ─────────────────────────────────────────────────────────


@dataclass
class CommentRecord:
    comment_id: str
    entity_id: str
    organization_id: str
    author_id: str
    body: str
    mentions: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=_utc_now)


@dataclass
class NotificationRecord:
    notification_id: str
    recipient_id: str
    organization_id: str
    template: str
    payload: dict[str, object] = field(default_factory=dict)
    status: str = NotificationStatus.QUEUED.value
    channel: str = NotificationChannel.IN_APP.value
    created_at: str = field(default_factory=_utc_now)


# ── In-memory service (comments, notifications) ───────────────────────────────


class CommunicationsModelService:
    """In-memory persistence service for communications artifacts."""

    def __init__(self, database_service_manager: DatabaseServiceManager | None) -> None:
        self.database_manager = database_service_manager
        self.database_service_manager = database_service_manager
        self.current_db = (
            self.database_manager.postgres_db_service()
            if self.database_manager and hasattr(self.database_manager, "postgres_db_service")
            else None
        )
        self.current_db_engine = getattr(self.current_db, "engine", None)
        self.module_name = "communications"
        self._comments_by_thread: dict[tuple[str, str], list[CommentRecord]] = {}
        self._notifications_by_org: dict[str, list[NotificationRecord]] = {}

    def create_comment(self, request: CommentCreateRequest) -> CommentRecord:
        try:
            record = CommentRecord(
                comment_id=str(uuid4()),
                entity_id=request.entity_id,
                organization_id=request.organization_id,
                author_id=request.author_id,
                body=request.body.strip(),
                mentions=normalize_mentions(request.mentions),
            )
            key = (request.organization_id, request.entity_id)
            self._comments_by_thread.setdefault(key, []).append(record)
            return record
        except Exception as exc:
            raise PersistenceError(f"Unable to create comment: {exc}") from exc

    def list_comments(self, organization_id: str, entity_id: str) -> list[CommentRecord]:
        return list(self._comments_by_thread.get((organization_id, entity_id), []))

    def create_notification(self, request: NotificationCreateRequest) -> NotificationRecord:
        try:
            record = NotificationRecord(
                notification_id=str(uuid4()),
                recipient_id=request.recipient_id,
                organization_id=request.organization_id,
                template=request.template,
                payload=dict(request.payload),
            )
            self._notifications_by_org.setdefault(request.organization_id, []).append(record)
            return record
        except Exception as exc:
            raise PersistenceError(f"Unable to create notification: {exc}") from exc

    def list_notifications(self, organization_id: str) -> list[NotificationRecord]:
        return list(self._notifications_by_org.get(organization_id, []))
