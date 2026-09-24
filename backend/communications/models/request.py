"""Request models for communications."""

from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from common.data_model import BaseModel as PydanticBaseModel
from communications.models.interface import normalize_mentions


def _non_empty(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized


class CommentCreateRequest(PydanticBaseModel):
    entity_id: str = Field(..., min_length=1)
    organization_id: str = Field(..., min_length=1)
    author_id: str = Field(..., min_length=1)
    body: str = Field(..., min_length=1)
    mentions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def normalize_fields(self) -> Self:
        self.entity_id = _non_empty(str(self.entity_id), "entity_id")
        self.organization_id = _non_empty(str(self.organization_id), "organization_id")
        self.author_id = _non_empty(str(self.author_id), "author_id")
        self.body = _non_empty(str(self.body), "body")
        self.mentions = normalize_mentions([str(item) for item in (self.mentions or [])])
        return self


class NotificationCreateRequest(PydanticBaseModel):
    recipient_id: str = Field(..., min_length=1)
    organization_id: str = Field(..., min_length=1)
    template: str = Field(..., min_length=1)
    payload: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def normalize_fields(self) -> Self:
        self.recipient_id = _non_empty(str(self.recipient_id), "recipient_id")
        self.organization_id = _non_empty(str(self.organization_id), "organization_id")
        self.template = _non_empty(str(self.template), "template")
        if not isinstance(self.payload, dict):
            raise ValueError("payload must be a dictionary")
        self.payload = dict(self.payload)
        return self
