"""Response models for forms."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import ConfigDict, Field

from common.data_model import BaseModel as PydanticBaseModel
from workflow.models.interface import EntityField


class MetadataRegistryStatusResponse(PydanticBaseModel):
    model_config = ConfigDict(from_attributes=True)

    module: str
    status: str
    started: bool


class EntityTypeResponse(PydanticBaseModel):
    model_config = ConfigDict(from_attributes=True)

    organization_id: str
    entity_type: str
    display_name: str
    allowed_states: list[str] = Field(default_factory=list)
    version: int = 1


class FormConfigResponse(PydanticBaseModel):
    model_config = ConfigDict(from_attributes=True)

    organization_id: str
    form_key: str
    field_count: int
    version: int = 1


class FunnelResolutionResponse(PydanticBaseModel):
    model_config = ConfigDict(from_attributes=True)

    organization_id: str
    entity_type: str
    lifecycle_key: str
    states: list[str] = Field(default_factory=list)
    source: str = "fallback"
    funnel_key: str | None = None

    def model_post_init(self, __context: object) -> None:
        if self.funnel_key is None:
            self.funnel_key = self.lifecycle_key


class EntityTypeListResponse(PydanticBaseModel):
    model_config = ConfigDict(from_attributes=True)

    organization_id: str
    items: list[EntityTypeResponse] = Field(default_factory=list)


class EntityTypeSchemaResponse(PydanticBaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    schema_key: str
    name: str
    description: str | None = None
    entity_type: str
    fields: list[EntityField] = Field(default_factory=list)
    is_active: bool = True
    display_order: int = 0
    content_hash: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class EntityTypeSchemaListResponse(PydanticBaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[EntityTypeSchemaResponse] = Field(default_factory=list)
    total: int = 0


class PicklistResponse(PydanticBaseModel):
    id: str
    organization_id: str
    name: str
    options: list[Any] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PicklistListResponse(PydanticBaseModel):
    organization_id: str
    items: list[PicklistResponse] = Field(default_factory=list)
    total: int = 0
