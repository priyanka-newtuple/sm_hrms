"""Response models for unified audit events."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from common.data_model import BaseModel as PydanticBaseModel


class AuditEventResponse(PydanticBaseModel):
    """Schema for reading a single audit event."""

    id: str
    organization_id: str
    metadata_type: str
    entity_type: str | None = None
    entity_id: str | None = None
    entity_identifier: str | None = None
    entity_archived: bool = False
    user_id: str | None = None
    event_type: str
    actor_type: str
    actor_id: str | None = None
    actor_name: str | None = None
    actor_role: str | None = None
    correlation_id: str | None = None
    source: str | None = None
    before_state: str | None = None
    after_state: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    event_timestamp: datetime | None = None


class AuditEventListResponse(PydanticBaseModel):
    """Response schema for listing audit events."""

    items: list[AuditEventResponse] = Field(default_factory=list)
    total: int
    entity_id: str | None = None


class AuditConstantsResponse(PydanticBaseModel):
    """Response schema for valid metadata_type and event_type values."""

    metadata_types: list[str]
    event_types: dict[str, list[str]]
