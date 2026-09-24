"""Interface models and contracts for forms."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from pydantic import ConfigDict, Field, field_validator

from common.data_model import BaseModel as PydanticBaseModel
from exceptions import ValidationError
from workflow.models.interface import EntityField


class FieldDefinition(PydanticBaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    field_type: str
    required: bool = False
    options: tuple[str, ...] = ()

    @field_validator("name", "field_type", mode="before")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        normalized = str(v).strip()
        if not normalized:
            raise ValidationError(f"field must be a non-empty string, got: {v!r}")
        return normalized

    @field_validator("options", mode="before")
    @classmethod
    def _clean_options(cls, v: object) -> tuple[str, ...]:
        if v is None:
            return ()
        if not isinstance(v, (list, tuple)):
            raise ValidationError("options must be a list")
        return tuple(str(o).strip() for o in v if str(o).strip())


class EntityTypeContract(PydanticBaseModel):
    model_config = ConfigDict(frozen=True, from_attributes=True)

    organization_id: str
    entity_type: str
    display_name: str
    allowed_states: tuple[str, ...] = ()
    version: int = 1


class FormConfigContract(PydanticBaseModel):
    model_config = ConfigDict(from_attributes=True)

    organization_id: str
    form_key: str
    fields: list[FieldDefinition] = Field(default_factory=list)
    version: int = 1


class EntityTypeSchemaContract(PydanticBaseModel):
    """Reusable form schema bound to one entity type."""

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


class FunnelResolution(PydanticBaseModel):
    model_config = ConfigDict(frozen=True, from_attributes=True)

    organization_id: str
    entity_type: str
    lifecycle_key: str
    states: tuple[str, ...]
    source: str

    @property
    def funnel_key(self) -> str:
        return self.lifecycle_key


def validate_picklist_id(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("picklist id must be a non-empty string")
    return normalized


def validate_picklist_name(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("picklist name must be a non-empty string")
    return normalized


class PicklistOption(PydanticBaseModel):
    model_config = ConfigDict(frozen=True)

    value: str
    label: str


class PicklistContract(PydanticBaseModel):
    model_config = ConfigDict(frozen=True, from_attributes=True)

    id: str
    organization_id: str
    name: str
    options: list[Any] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class MetadataLookupPort(Protocol):
    """Read-only lookup contract for dependent managers."""

    def get_entity_type(self, organization_id: str, entity_type: str) -> EntityTypeContract | None:
        """Resolve entity type metadata."""

    def get_form_config(self, organization_id: str, form_key: str) -> FormConfigContract | None:
        """Resolve form metadata."""
