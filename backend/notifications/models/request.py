"""Request models for notifications."""

from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from common.data_model import BaseModel as PydanticBaseModel
from notifications.models.interface import (
    validate_notification_text,
    validate_optional_notification_text,
)


class NotificationListRequest(PydanticBaseModel):
    is_read: bool | None = None
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class NotificationActionRequest(PydanticBaseModel):
    notification_id: str = Field(..., min_length=1)

    @model_validator(mode="after")
    def normalize_fields(self) -> Self:
        self.notification_id = validate_notification_text(
            str(self.notification_id), "notification_id"
        )
        return self


class NotificationCreateRequest(PydanticBaseModel):
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
