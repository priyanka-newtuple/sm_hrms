"""Response models for notifications."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from common.data_model import BaseModel as PydanticBaseModel


class NotificationRead(PydanticBaseModel):
    """Schema for reading a notification."""

    id: str
    organization_id: str
    recipient_id: str
    notification_type: str
    source_type: str | None = None
    source_id: str | None = None
    entity_id: str
    entity_type: str
    actor_id: str | None = None
    actor_name: str | None = None
    title: str
    body: str | None = None
    link: str | None = None
    is_read: bool
    read_at: datetime | None = None
    created_at: datetime


class NotificationListResponse(PydanticBaseModel):
    """Response schema for listing notifications."""

    notifications: list[NotificationRead] = Field(default_factory=list)
    total: int
    unread_count: int


class UnreadCountResponse(PydanticBaseModel):
    """Response schema for unread notification count."""

    count: int


class MarkAllReadResponse(PydanticBaseModel):
    """Response schema for marking all notifications as read."""

    updated: int
