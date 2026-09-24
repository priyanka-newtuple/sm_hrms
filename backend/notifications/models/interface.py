"""Interface models and contracts for the notifications module."""

from __future__ import annotations

from typing import Any, Protocol, Self

from pydantic import ConfigDict, Field, model_validator

from common.data_model import BaseModel as PydanticBaseModel
from mail.models.interface import EmailActionKind

NOTIFICATION_TYPE_MENTION = "mention"
NOTIFICATION_TYPE_ASSIGNMENT = "assignment"
NOTIFICATION_TYPE_COMMENT = "comment"
NOTIFICATION_TYPE_REPLY = "reply"
NOTIFICATION_TYPE_LIKE = "like"
EMAIL_KIND_MENTION = EmailActionKind.MENTION.value
EMAIL_KIND_ASSIGNMENT = EmailActionKind.ASSIGNMENT.value
EMAIL_KIND_COMMENT = EmailActionKind.COMMENT.value
EMAIL_KIND_REPLY = EmailActionKind.REPLY.value
EMAIL_KIND_LIKE = EmailActionKind.LIKE.value
EMAIL_KIND_NEW_USER = EmailActionKind.NEW_USER.value
EMAIL_KIND_NEW_ORG = EmailActionKind.NEW_ORG.value
FEATURE_FLAG_SEND_ASSIGNMENT_EMAILS = "sendAssignmentEmails"
FEATURE_FLAG_SEND_COMMENT_EMAILS = "sendCommentEmails"
FEATURE_FLAG_SEND_REPLY_EMAILS = "sendReplyEmails"
FEATURE_FLAG_SEND_LIKE_EMAILS = "sendLikeEmails"
COMMENT_PREVIEW_LENGTH = 100
EMAIL_PREVIEW_LENGTH = 500


def validate_notification_text(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized


def validate_optional_notification_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


class NotificationContract(PydanticBaseModel):
    """Cross-module notification payload."""

    model_config = ConfigDict(frozen=True, from_attributes=True)

    id: str
    organization_id: str
    recipient_id: str
    notification_type: str
    entity_id: str
    entity_type: str
    title: str
    body: str | None = None
    link: str | None = None
    is_read: bool = False


class NotificationLookupService(Protocol):
    """Persistence contract for notification lookups."""

    def get_unread_count(self, *, db: Any = None, organization_id: str, recipient_id: str) -> int:
        """Return unread count for a recipient."""
        ...


class NotificationCreateContract(PydanticBaseModel):
    """Normalized payload for creating notifications."""

    organization_id: str = Field(..., min_length=1)
    recipient_id: str = Field(..., min_length=1)
    notification_type: str = Field(..., min_length=1)
    entity_id: str = Field(..., min_length=1)
    entity_type: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1, max_length=256)
    body: str | None = None
    link: str | None = None
    actor_id: str | None = None
    actor_name: str | None = None
    source_type: str | None = None
    source_id: str | None = None

    @model_validator(mode="after")
    def normalize_fields(self) -> Self:
        self.organization_id = validate_notification_text(
            str(self.organization_id), "organization_id"
        )
        self.recipient_id = validate_notification_text(str(self.recipient_id), "recipient_id")
        self.notification_type = validate_notification_text(
            str(self.notification_type), "notification_type"
        )
        self.entity_id = validate_notification_text(str(self.entity_id), "entity_id")
        self.entity_type = validate_notification_text(str(self.entity_type), "entity_type")
        self.title = validate_notification_text(str(self.title), "title")
        self.body = validate_optional_notification_text(self.body)
        self.link = validate_optional_notification_text(self.link)
        self.actor_id = validate_optional_notification_text(self.actor_id)
        self.actor_name = validate_optional_notification_text(self.actor_name)
        self.source_type = validate_optional_notification_text(self.source_type)
        self.source_id = validate_optional_notification_text(self.source_id)
        return self
