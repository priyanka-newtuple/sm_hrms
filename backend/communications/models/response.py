"""Response models for communications."""

from __future__ import annotations

from pydantic import Field

from common.data_model import BaseModel as PydanticBaseModel
from common.enums import NotificationChannel, NotificationStatus


class CollaborationStatusResponse(PydanticBaseModel):
    module: str
    status: str
    started: bool


class CommentCreateResponse(PydanticBaseModel):
    comment_id: str
    entity_id: str
    organization_id: str
    author_id: str
    body: str
    mentions: list[str] = Field(default_factory=list)
    mention_count: int = 0
    created_at: str = ""


class NotificationCreateResponse(PydanticBaseModel):
    notification_id: str
    recipient_id: str
    organization_id: str
    template: str
    status: NotificationStatus = NotificationStatus.QUEUED
    channel: NotificationChannel = NotificationChannel.IN_APP


class CommentListResponse(PydanticBaseModel):
    organization_id: str
    entity_id: str
    comments: list[dict[str, object]] = Field(default_factory=list)
