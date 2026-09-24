"""Request models for entities."""

from __future__ import annotations

from datetime import date
from typing import Any, Self

from pydantic import Field, model_validator

from common.data_model import BaseModel as PydanticBaseModel
from entities.models.interface import (
    ASSIGNMENT_MODE_CONFLICT_MESSAGE,
    FieldDefinition,
    RelationType,
)
from exceptions import ValidationError


def _non_empty(value: str, field_name: str) -> str:
    """Validator: reject empty/whitespace strings on required text fields."""
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized


def _optional_text(value: object | None) -> str | None:
    """Validator: collapse blank optional strings to None."""
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


class UpsertFormConfigRequest(PydanticBaseModel):
    organization_id: str = Field(..., min_length=1)
    form_key: str = Field(..., min_length=1)
    fields: list[FieldDefinition] = Field(default_factory=list)
    version: int = 1

    @model_validator(mode="after")
    def normalize_fields(self) -> Self:
        """Normalize whitespace and coerce blank optionals before validation."""
        self.organization_id = _non_empty(str(self.organization_id), "organization_id")
        self.form_key = _non_empty(str(self.form_key), "form_key")
        self.fields = list(self.fields or [])
        if not self.fields:
            raise ValueError("fields must include at least one field")
        self.version = int(self.version)
        return self

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> UpsertFormConfigRequest:
        """Build the request from a plain dict (typed model_validate wrapper)."""
        try:
            return cls.model_validate(payload)
        except Exception as exc:
            raise ValidationError(str(exc)) from exc


class EntityTypeCreateRequest(PydanticBaseModel):
    """Create payload for the canonical entity type registry.

    `organization_id` is optional in the wire payload; HTTP controllers derive
    it from the authenticated actor. Internal callers may still supply it.
    """

    organization_id: str | None = None
    name: str = Field(..., min_length=1)
    description: str | None = None
    schema_definition: dict[str, Any] = Field(default_factory=dict)
    version: int = 1
    is_active: bool = True

    @model_validator(mode="after")
    def normalize_fields(self) -> Self:
        """Normalize whitespace and coerce blank optionals before validation."""
        if self.organization_id is not None:
            self.organization_id = _non_empty(str(self.organization_id), "organization_id")
        self.name = _non_empty(str(self.name), "name")
        self.description = _optional_text(self.description)
        if self.version < 1:
            raise ValueError("version must be >= 1")
        self.schema_definition = dict(self.schema_definition or {})
        return self

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> EntityTypeCreateRequest:
        """Build the request from a plain dict (typed model_validate wrapper)."""
        try:
            return cls.model_validate(payload)
        except Exception as exc:
            raise ValidationError(str(exc)) from exc


class EntityTypeUpdateRequest(PydanticBaseModel):
    """Partial update for an existing entity type."""

    name: str | None = None
    description: str | None = None
    schema_definition: dict[str, Any] | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def normalize_fields(self) -> Self:
        """Normalize whitespace and coerce blank optionals before validation."""
        if self.name is not None:
            self.name = _non_empty(str(self.name), "name")
        if self.description is not None:
            self.description = _optional_text(self.description)
        if self.schema_definition is not None:
            self.schema_definition = dict(self.schema_definition)
        return self

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> EntityTypeUpdateRequest:
        """Build the request from a plain dict (typed model_validate wrapper)."""
        try:
            return cls.model_validate(payload)
        except Exception as exc:
            raise ValidationError(str(exc)) from exc


class EntityRelationInput(PydanticBaseModel):
    """Inline relation spec for atomic entity-create-with-relations requests.

    Allows callers to link the new entity to one or more existing entities
    in a single `POST /entity-records` call instead of a separate relation
    endpoint call after creation.
    """

    to_entity_id: str = Field(..., min_length=1)
    relation_type: str = Field(..., min_length=1)
    relation_metadata: dict[str, Any] | None = None

    @model_validator(mode="after")
    def normalize_fields(self) -> Self:
        self.to_entity_id = _non_empty(str(self.to_entity_id), "to_entity_id")
        self.relation_type = _non_empty(str(self.relation_type), "relation_type")
        if self.relation_metadata is not None:
            self.relation_metadata = dict(self.relation_metadata)
        return self

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> EntityRelationInput:
        try:
            return cls.model_validate(payload)
        except Exception as exc:
            raise ValidationError(str(exc)) from exc


class EntityTypeRelationCreateRequest(PydanticBaseModel):
    """Create payload for an entity type relation definition."""

    organization_id: str | None = None
    from_entity_type_id: str | None = None
    to_entity_type_id: str = Field(..., min_length=1)
    relation_name: str = Field(..., min_length=1)

    @model_validator(mode="after")
    def normalize_fields(self) -> Self:
        if self.organization_id is not None:
            self.organization_id = _non_empty(str(self.organization_id), "organization_id")
        if self.from_entity_type_id is not None:
            self.from_entity_type_id = _non_empty(
                str(self.from_entity_type_id), "from_entity_type_id"
            )
        self.to_entity_type_id = _non_empty(str(self.to_entity_type_id), "to_entity_type_id")
        self.relation_name = _non_empty(str(self.relation_name), "relation_name").upper()
        if (
            self.from_entity_type_id is not None
            and self.from_entity_type_id == self.to_entity_type_id
        ):
            raise ValueError("from_entity_type_id and to_entity_type_id must differ")
        return self

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> EntityTypeRelationCreateRequest:
        try:
            return cls.model_validate(payload)
        except Exception as exc:
            raise ValidationError(str(exc)) from exc


class EntityRelationDeclarationCreateRequest(PydanticBaseModel):
    """Create payload for a field-inheritance relation declaration."""

    organization_id: str | None = None
    from_entity_type_id: str | None = None
    to_entity_type_id: str = Field(..., min_length=1)
    relation_type: RelationType | None = None
    relation_metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def normalize_fields(self) -> Self:
        """Normalize whitespace and reject a type declaring a relation to itself."""
        if self.organization_id is not None:
            self.organization_id = _non_empty(str(self.organization_id), "organization_id")
        if self.from_entity_type_id is not None:
            self.from_entity_type_id = _non_empty(
                str(self.from_entity_type_id), "from_entity_type_id"
            )
        self.to_entity_type_id = _non_empty(str(self.to_entity_type_id), "to_entity_type_id")
        if self.from_entity_type_id == self.to_entity_type_id:
            raise ValueError("from_entity_type_id and to_entity_type_id must differ")
        self.relation_metadata = dict(self.relation_metadata or {})
        return self

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> EntityRelationDeclarationCreateRequest:
        """Build the request from a plain dict (typed model_validate wrapper)."""
        try:
            return cls.model_validate(payload)
        except Exception as exc:
            raise ValidationError(str(exc)) from exc


class EntityRelationDeclarationUpdateRequest(PydanticBaseModel):
    """Update payload for a relation declaration — only relation_metadata is mutable."""

    relation_metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def normalize_fields(self) -> Self:
        """Normalize the metadata mapping before validation."""
        self.relation_metadata = dict(self.relation_metadata or {})
        return self

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> EntityRelationDeclarationUpdateRequest:
        """Build the request from a plain dict (typed model_validate wrapper)."""
        try:
            return cls.model_validate(payload)
        except Exception as exc:
            raise ValidationError(str(exc)) from exc


class EntityRecordCreateRequest(PydanticBaseModel):
    """Create payload for a runtime entity instance.

    `organization_id` is optional in the wire payload; HTTP controllers derive
    it from the authenticated actor. `entity_id` is optional — server
    generates a UUID when omitted; legacy callers (workflow REST surface)
    pass through their own caller-controlled ids.

    `relations` is optional; when provided the listed edges are created
    atomically after the entity row is committed.

    `source_entity_ids` lists the provider records (if any) this record
    should link to on create — one per active declaration whose provider
    type matches that source's own type. Required for any active REFERENCE
    declaration targeting this entity type; optional for SNAPSHOT.

    `custom_form_data` seeds a dynamic method's answers at create time; the
    form's schema itself still resolves lazily on first read, same as elsewhere.
    """

    organization_id: str | None = None
    entity_id: str | None = None
    entity_type_id: str = Field(..., min_length=1)
    data: dict[str, Any] = Field(default_factory=dict)
    owner_id: str | None = None
    assignee_id: str | None = None
    due_date: date | None = None
    relations: list[EntityRelationInput] | None = None
    source_entity_ids: list[str] = Field(default_factory=list)
    custom_form_data: dict[str, Any] | None = None

    @model_validator(mode="after")
    def normalize_fields(self) -> Self:
        """Normalize whitespace and coerce blank optionals before validation."""
        if self.organization_id is not None:
            self.organization_id = _non_empty(str(self.organization_id), "organization_id")
        if self.entity_id is not None:
            self.entity_id = _non_empty(str(self.entity_id), "entity_id")
        self.entity_type_id = _non_empty(str(self.entity_type_id), "entity_type_id")
        self.data = dict(self.data or {})
        self.owner_id = _optional_text(self.owner_id)
        self.assignee_id = _optional_text(self.assignee_id)
        self.source_entity_ids = [
            _non_empty(str(sid), "source_entity_ids") for sid in (self.source_entity_ids or [])
        ]
        if self.custom_form_data is not None:
            self.custom_form_data = dict(self.custom_form_data)
        return self

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> EntityRecordCreateRequest:
        """Build the request from a plain dict (typed model_validate wrapper)."""
        try:
            return cls.model_validate(payload)
        except Exception as exc:
            raise ValidationError(str(exc)) from exc


class EntityRelationCreateRequest(PydanticBaseModel):
    """Create payload for an edge between two runtime entities.

    `organization_id` is optional in the wire payload; HTTP controllers derive
    it from the authenticated actor.
    """

    organization_id: str | None = None
    from_entity_id: str = Field(..., min_length=1)
    to_entity_id: str = Field(..., min_length=1)
    relation_type: str = Field(..., min_length=1)
    relation_metadata: dict[str, Any] | None = None

    @model_validator(mode="after")
    def normalize_fields(self) -> Self:
        """Normalize whitespace and coerce blank optionals before validation."""
        if self.organization_id is not None:
            self.organization_id = _non_empty(str(self.organization_id), "organization_id")
        self.from_entity_id = _non_empty(str(self.from_entity_id), "from_entity_id")
        self.to_entity_id = _non_empty(str(self.to_entity_id), "to_entity_id")
        self.relation_type = _non_empty(str(self.relation_type), "relation_type")
        if self.from_entity_id == self.to_entity_id:
            raise ValueError("from_entity_id and to_entity_id must differ")
        if self.relation_metadata is not None:
            self.relation_metadata = dict(self.relation_metadata)
        return self

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> EntityRelationCreateRequest:
        """Build the request from a plain dict (typed model_validate wrapper)."""
        try:
            return cls.model_validate(payload)
        except Exception as exc:
            raise ValidationError(str(exc)) from exc


class EntityRecordUpdateRequest(PydanticBaseModel):
    """Partial update for an existing entity instance.

    Assignment is handled separately via the dedicated assignee endpoint
    (`EntityAssigneeUpdateRequest`), not through this generic update.

    `source_entity_ids` links additional provider records after the fact —
    e.g. an entity created via an agent tool call has no source links yet,
    so a caller with that context (a create-form the user is still filling
    in) can attach them here once the entity already exists. Matched to
    active declarations the same way `EntityRecordCreateRequest` does; a
    declaration that already has a link for this entity is left untouched
    (no duplicate rows, no relinking) rather than erroring.
    """

    data: dict[str, Any] | None = None
    custom_form_data: dict[str, Any] | None = None
    owner_id: str | None = None
    due_date: date | None = None
    source_entity_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def normalize_fields(self) -> Self:
        """Normalize whitespace and coerce blank optionals before validation."""
        if self.data is not None:
            self.data = dict(self.data)
        if self.owner_id is not None:
            self.owner_id = _optional_text(self.owner_id)
        self.source_entity_ids = [
            _non_empty(str(sid), "source_entity_ids") for sid in (self.source_entity_ids or [])
        ]
        return self

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> EntityRecordUpdateRequest:
        """Build the request from a plain dict (typed model_validate wrapper)."""
        try:
            return cls.model_validate(payload)
        except Exception as exc:
            raise ValidationError(str(exc)) from exc


class EntityAssigneeUpdateRequest(PydanticBaseModel):
    """Set (or clear) the assignee on an entity.

    A blank/omitted `assignee_id` means "unassign" — unlike the generic record
    update, this dedicated endpoint always writes the field, so `None` clears it.

    `assign_to_originator` assigns the record to whoever originally created it.
    The client never supplies that user's id: the server resolves it from the
    record's creation history, so the two fields are mutually exclusive.
    """

    assignee_id: str | None = None
    assign_to_originator: bool = False

    @model_validator(mode="after")
    def normalize_fields(self) -> Self:
        """Coerce blank assignee to None, and reject both modes at once.

        Rejected here rather than in the manager so a contradictory request
        never reaches the permission check or the database.
        """
        self.assignee_id = _optional_text(self.assignee_id)
        if self.assign_to_originator and self.assignee_id is not None:
            raise ValueError(ASSIGNMENT_MODE_CONFLICT_MESSAGE)
        return self

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> EntityAssigneeUpdateRequest:
        """Build the request from a plain dict (typed model_validate wrapper)."""
        try:
            return cls.model_validate(payload)
        except Exception as exc:
            raise ValidationError(str(exc)) from exc
