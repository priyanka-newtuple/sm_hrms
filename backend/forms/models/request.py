"""Request models for forms."""

from __future__ import annotations

from typing import Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from common.data_model import BaseModel as PydanticBaseModel
from exceptions import ValidationError
from forms.models.interface import (
    FieldDefinition,
    PicklistOption,
    validate_picklist_id,
    validate_picklist_name,
)
from workflow.models.interface import EntityField


class UpsertEntityTypeRequest(PydanticBaseModel):
    model_config = ConfigDict(from_attributes=True)

    organization_id: str
    entity_type: str
    display_name: str
    allowed_states: list[str] = Field(default_factory=list)
    version: int = 1

    @field_validator("organization_id", "entity_type", "display_name", mode="before")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        normalized = str(v).strip()
        if not normalized:
            raise ValidationError(f"field must be a non-empty string, got: {v!r}")
        return normalized

    @field_validator("allowed_states", mode="before")
    @classmethod
    def _normalize_states(cls, v: object) -> list[str]:
        if not isinstance(v, list):
            raise ValidationError("allowed_states must be a list")
        seen: set[str] = set()
        states: list[str] = []
        for state in v:
            normalized = str(state).strip().upper()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            states.append(normalized)
        if not states:
            raise ValidationError("allowed_states must include at least one state")
        return states


class UpsertFormConfigRequest(PydanticBaseModel):
    model_config = ConfigDict(from_attributes=True)

    organization_id: str
    form_key: str
    fields: list[FieldDefinition] = Field(default_factory=list)
    version: int = 1

    @field_validator("organization_id", "form_key", mode="before")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        normalized = str(v).strip()
        if not normalized:
            raise ValidationError(f"field must be a non-empty string, got: {v!r}")
        return normalized

    @model_validator(mode="after")
    def _require_fields(self) -> Self:
        if not self.fields:
            raise ValidationError("fields must include at least one field")
        return self


class ResolveFunnelRequest(PydanticBaseModel):
    model_config = ConfigDict(from_attributes=True)

    organization_id: str
    entity_type: str
    lifecycle_key: str | None = None
    funnel_key: str | None = None

    @field_validator("organization_id", "entity_type", mode="before")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        normalized = str(v).strip()
        if not normalized:
            raise ValidationError(f"field must be a non-empty string, got: {v!r}")
        return normalized

    @field_validator("lifecycle_key", "funnel_key", mode="before")
    @classmethod
    def _optional_text(cls, v: object) -> str | None:
        if v is None:
            return None
        normalized = str(v).strip()
        return normalized or None

    @model_validator(mode="after")
    def _unify_funnel_key(self) -> Self:
        lifecycle_key = self.lifecycle_key or self.funnel_key
        self.lifecycle_key = lifecycle_key
        self.funnel_key = lifecycle_key
        return self

    def deprecated_field_names(self) -> list[str]:
        if self.funnel_key is not None and self.lifecycle_key is None:
            return ["funnel_key"]
        return []


class EntityTypeSchemaCreateRequest(PydanticBaseModel):
    model_config = ConfigDict(from_attributes=True)

    schema_key: str
    name: str
    description: str | None = None
    entity_type: str
    fields: list[EntityField] = Field(default_factory=list)
    is_active: bool = True
    display_order: int = 0

    @field_validator("schema_key", "name", "entity_type", mode="before")
    @classmethod
    def _schema_non_empty(cls, v: str) -> str:
        normalized = str(v).strip()
        if not normalized:
            raise ValidationError(f"field must be a non-empty string, got: {v!r}")
        return normalized

    @field_validator("description", mode="before")
    @classmethod
    def _optional_text(cls, v: object) -> str | None:
        if v is None:
            return None
        normalized = str(v).strip()
        return normalized or None


class EntityTypeSchemaUpdateRequest(PydanticBaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str | None = None
    description: str | None = None
    entity_type: str | None = None
    fields: list[EntityField] | None = None
    is_active: bool | None = None
    display_order: int | None = None

    @field_validator("name", "entity_type", mode="before")
    @classmethod
    def _optional_non_empty(cls, v: object) -> str | None:
        if v is None:
            return None
        normalized = str(v).strip()
        if not normalized:
            raise ValidationError("field must be a non-empty string")
        return normalized

    @field_validator("description", mode="before")
    @classmethod
    def _optional_description(cls, v: object) -> str | None:
        if v is None:
            return None
        normalized = str(v).strip()
        return normalized or None

    @model_validator(mode="after")
    def _require_updatable_field(self) -> Self:
        if (
            self.name is None
            and self.description is None
            and self.entity_type is None
            and self.fields is None
            and self.is_active is None
            and self.display_order is None
        ):
            raise ValidationError("at least one updatable field must be provided")
        return self


class PicklistCreateRequest(PydanticBaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    options: list[PicklistOption] = Field(default_factory=list)

    @model_validator(mode="after")
    def normalize_fields(self) -> Self:
        self.name = validate_picklist_name(str(self.name))
        return self


class PicklistUpdateRequest(PydanticBaseModel):
    name: str | None = Field(default=None, max_length=256)
    options: list[PicklistOption] | None = None

    @model_validator(mode="after")
    def normalize_fields(self) -> Self:
        if self.name is not None:
            self.name = validate_picklist_name(str(self.name))
        return self
