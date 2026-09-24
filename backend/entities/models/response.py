"""Response models for entities."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import Field

from common.data_model import BaseModel as PydanticBaseModel
from entities.models.interface import (
    EntityArchivedPayload,
    EntityAssigneeChangedPayload,
    EntityCreatedPayload,
    EntityRestoredPayload,
    EntityUpdatedPayload,
    RelationType,
)


class MetadataRegistryStatusResponse(PydanticBaseModel):
    module: str
    status: str
    started: bool

    def to_dict(self) -> dict[str, object]:
        """Serialize the response as a JSON-friendly dict."""
        return self.model_dump(mode="json")


class FormConfigResponse(PydanticBaseModel):
    organization_id: str
    form_key: str
    field_count: int
    version: int = 1

    def to_dict(self) -> dict[str, object]:
        """Serialize the response as a JSON-friendly dict."""
        return self.model_dump(mode="json")


class EntityTypeRecordResponse(PydanticBaseModel):
    """Response model for a single canonical entity type record."""

    entity_type_id: str
    organization_id: str
    name: str
    description: str | None = None
    schema_definition: dict[str, Any] = Field(default_factory=dict)
    version: int = 1
    is_active: bool = True
    archived_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def to_dict(self) -> dict[str, object]:
        """Serialize the response as a JSON-friendly dict."""
        return self.model_dump(mode="json")


class EntityTypeRecordListResponse(PydanticBaseModel):
    organization_id: str
    items: list[EntityTypeRecordResponse] = Field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        """Serialize the response as a JSON-friendly dict."""
        return {
            "organization_id": self.organization_id,
            "items": [item.to_dict() for item in self.items],
        }


class EntityTypeRelationResponse(PydanticBaseModel):
    """Response for a single entity type relation definition."""

    relation_def_id: str
    organization_id: str
    from_entity_type_id: str
    to_entity_type_id: str
    relation_name: str | None = None
    relation_type: RelationType = RelationType.SNAPSHOT
    relation_metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None

    def to_dict(self) -> dict[str, object]:
        return self.model_dump(mode="json")


class EntityTypeRelationDeleteResponse(PydanticBaseModel):
    """Response for a soft-deleted relation declaration."""

    relation_def_id: str
    deleted_at: datetime | None = None

    def to_dict(self) -> dict[str, object]:
        return self.model_dump(mode="json")


class InheritedFieldResponse(PydanticBaseModel):
    """One inherited field available on an entity type (a relation-declaration target).

    Merged into entity data at read time, so a connector on this type can reference
    it as ``$entity.<field>`` for both REFERENCE and SNAPSHOT.
    """

    field: str
    source_entity_type_id: str
    relation_type: RelationType = RelationType.SNAPSHOT

    def to_dict(self) -> dict[str, object]:
        return self.model_dump(mode="json")


class EntityTypeRelationListResponse(PydanticBaseModel):
    organization_id: str
    items: list[EntityTypeRelationResponse] = Field(default_factory=list)
    # Fields this type inherits from parents (auto `<parent>_id` + mapped fields).
    inherited_fields: list[InheritedFieldResponse] = Field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "organization_id": self.organization_id,
            "items": [i.to_dict() for i in self.items],
            "inherited_fields": [i.to_dict() for i in self.inherited_fields],
        }


class EntityRecordResponse(PydanticBaseModel):
    """Response for a single runtime entity instance."""

    entity_id: str
    organization_id: str
    entity_type_id: str
    data: dict[str, Any] = Field(default_factory=dict)
    custom_form_schema: dict[str, Any] = Field(default_factory=dict)
    custom_form_data: dict[str, Any] = Field(default_factory=dict)
    owner_id: str | None = None
    assignee_id: str | None = None
    due_date: date | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    archived_at: datetime | None = None

    def to_dict(self) -> dict[str, object]:
        """Serialize the response as a JSON-friendly dict."""
        return self.model_dump(mode="json")


class EntityRelationResponse(PydanticBaseModel):
    """Response for a single directed entity relation."""

    relation_id: str
    organization_id: str
    from_entity_id: str
    to_entity_id: str
    relation_type: str
    relation_metadata: dict[str, Any] | None = None
    created_at: datetime | None = None

    def to_dict(self) -> dict[str, object]:
        """Serialize the response as a JSON-friendly dict."""
        return self.model_dump(mode="json")


class EntityRelationListResponse(PydanticBaseModel):
    organization_id: str
    entity_id: str
    items: list[EntityRelationResponse] = Field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        """Serialize the response as a JSON-friendly dict."""
        return {
            "organization_id": self.organization_id,
            "entity_id": self.entity_id,
            "items": [item.to_dict() for item in self.items],
        }


class EntityStateResponse(PydanticBaseModel):
    """Response for a single (entity, workflow) state row."""

    state_id: str
    organization_id: str
    entity_id: str
    workflow_id: str
    current_state: str
    state_version: int = 0
    state_entered_at: datetime | None = None
    last_transition_at: datetime | None = None
    sla_due_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def to_dict(self) -> dict[str, object]:
        """Serialize the response as a JSON-friendly dict."""
        return self.model_dump(mode="json")


class RelatedEntityFileResponse(PydanticBaseModel):
    file_id: str
    type_id: str
    filename: str
    content_type: str
    size_bytes: int
    storage_key: str
    status: str
    uploaded_by: str
    owner_entity_id: str | None = None
    owner_entity_type: str | None = None
    storage_provider: str = "local"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str
    relation_type: RelationType
    relation_def_id: str
    source_entity_id: str
    source_entity_type_id: str
    source_entity_label: str


class RelatedEntityFileGroupResponse(PydanticBaseModel):
    source_entity_id: str
    source_entity_type_id: str
    source_entity_label: str
    relation_type: RelationType
    relation_def_id: str
    files: list[RelatedEntityFileResponse] = Field(default_factory=list)


class RelatedEntityFileListResponse(PydanticBaseModel):
    organization_id: str
    entity_id: str
    configured: bool = False
    count: int = 0
    groups: list[RelatedEntityFileGroupResponse] = Field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return self.model_dump(mode="json")


class EntityStateListResponse(PydanticBaseModel):
    organization_id: str
    entity_id: str
    items: list[EntityStateResponse] = Field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        """Serialize the response as a JSON-friendly dict."""
        return {
            "organization_id": self.organization_id,
            "entity_id": self.entity_id,
            "items": [item.to_dict() for item in self.items],
        }


EntityEventPayload = (
    EntityCreatedPayload
    | EntityUpdatedPayload
    | EntityAssigneeChangedPayload
    | EntityArchivedPayload
    | EntityRestoredPayload
    | dict[str, Any]
)


class EntityEventResponse(PydanticBaseModel):
    """Response for one row in `audit.entity_events`."""

    event_id: str
    organization_id: str
    entity_id: str
    event_type: str
    actor_type: str
    actor_id: str | None = None
    actor_name: str | None = None
    actor_role: str | None = None
    correlation_id: str | None = None
    idempotency_key: str | None = None
    payload: EntityEventPayload = Field(default_factory=dict)
    occurred_at: datetime | None = None

    def to_dict(self) -> dict[str, object]:
        """Serialize the response as a JSON-friendly dict."""
        return self.model_dump(mode="json")


class EntityEventListResponse(PydanticBaseModel):
    organization_id: str
    entity_id: str
    total: int = 0
    items: list[EntityEventResponse] = Field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        """Serialize the response as a JSON-friendly dict."""
        return {
            "organization_id": self.organization_id,
            "entity_id": self.entity_id,
            "total": self.total,
            "items": [item.to_dict() for item in self.items],
        }


class EntityRecordListResponse(PydanticBaseModel):
    organization_id: str
    items: list[EntityRecordResponse] = Field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        """Serialize the response as a JSON-friendly dict."""
        return {
            "organization_id": self.organization_id,
            "items": [item.to_dict() for item in self.items],
        }


class EntityRecordSummaryResponse(PydanticBaseModel):
    """Compact entity row used by records browsers."""

    entity_id: str
    organization_id: str
    entity_type_id: str
    entity_type: str
    display_name: str
    summary_fields: dict[str, object] = Field(default_factory=dict)
    owner_id: str | None = None
    assignee_id: str | None = None
    due_date: date | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    archived_at: datetime | None = None


class EntityRecordSummaryPage(PydanticBaseModel):
    items: list[EntityRecordSummaryResponse] = Field(default_factory=list)
    next_cursor: str | None = None
    has_more: bool = False


class EntityThumbnailUrlResponse(PydanticBaseModel):
    """Response for a single resolved attachment URL."""

    url: str | None = None


class EntityWithStatesResponse(PydanticBaseModel):
    """Combined view: a runtime entity plus every workflow it is enrolled in.

    `entity` carries the canonical record (data, owner, archive timestamps);
    `states` lists one row per `(entity, workflow)` pairing so a single
    entity can sit in multiple workflows simultaneously."""

    entity: EntityRecordResponse
    states: list[EntityStateResponse] = Field(default_factory=list)
    originator_id: str | None = None
    """The user who created this record, or None when no human created it.

    Resolved from the audit log rather than stored on the record — `owner_id`
    is backfilled at enrollment and is not the creator. None is a normal
    answer: system- and agent-created records have no human originator."""

    def to_dict(self) -> dict[str, object]:
        """Serialize the response as a JSON-friendly dict."""
        return {
            "entity": self.entity.to_dict(),
            "states": [state.to_dict() for state in self.states],
            "originator_id": self.originator_id,
        }
