"""workflow request models."""

from __future__ import annotations

from typing import Any

from pydantic import Field, model_validator

from common.data_model import BaseModel as PydanticBaseModel
from common.data_model import ExtendedStrEnum
from workflow.models.interface import (
    RUN_FACTS_ENTITY_ID_CAP,
    SERVICE_NAME_MAX_LENGTH,
    EntityField,
    EntityState,
    StateMachineDefinition,
    _non_empty,
    _optional_non_empty,
)


class StateMachineCreateRequest(PydanticBaseModel):
    """Create workflow version request."""

    machine_name: str
    version: int = Field(..., ge=0)
    is_active: bool = False
    definition: StateMachineDefinition

    @model_validator(mode="after")
    def validate_model(self) -> "StateMachineCreateRequest":
        """Normalize names."""
        self.machine_name = _non_empty(self.machine_name, "machine_name")
        return self


class WorkflowDraftCreateRequest(PydanticBaseModel):
    """Create one empty workflow draft."""

    name: str | None = None
    description: str | None = None

    @model_validator(mode="after")
    def validate_model(self) -> "WorkflowDraftCreateRequest":
        """Normalize optional draft fields."""
        self.name = _optional_non_empty(self.name)
        self.description = _optional_non_empty(self.description)
        return self


class WorkflowDraftUpdateRequest(PydanticBaseModel):
    """Save one in-progress workflow definition without validation."""

    definition: dict[str, Any] = Field(default_factory=dict)
    canvas_metadata: dict[str, Any] | None = None


MAX_BOARD_DISPLAY_FIELDS = 3


class WorkflowBoardDisplayFieldsUpdateRequest(PydanticBaseModel):
    """Replace the extra entity fields shown on one workflow's Kanban cards."""

    machine_name: str
    fields: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_model(self) -> "WorkflowBoardDisplayFieldsUpdateRequest":
        """Normalize the machine name and enforce the max-3 field cap."""
        self.machine_name = _non_empty(self.machine_name, "machine_name")
        deduped = list(dict.fromkeys(_non_empty(f, "fields") for f in self.fields))
        if len(deduped) > MAX_BOARD_DISPLAY_FIELDS:
            raise ValueError(
                f"fields cannot contain more than {MAX_BOARD_DISPLAY_FIELDS} entries"
            )
        self.fields = deduped
        return self


class WorkflowDraftSeedRequest(PydanticBaseModel):
    """Seed a version-0 draft for an existing published workflow family.

    Used when a published workflow has no draft row yet and the user wants
    to start editing. The machine_name is taken from the URL path; this body
    carries the optional starting definition and canvas state.
    """

    definition: dict[str, Any] | None = None
    canvas_metadata: dict[str, Any] | None = None


class WorkflowPublishRequest(PydanticBaseModel):
    """Publish an existing workflow draft row by row ID."""

    definition: StateMachineDefinition
    canvas_metadata: dict[str, Any] | None = None


class WorkflowServiceCreateRequest(PydanticBaseModel):
    """Create a service. Name only: a service is nothing but its name."""

    name: str = Field(min_length=1, max_length=SERVICE_NAME_MAX_LENGTH)


class WorkflowServiceRenameRequest(PydanticBaseModel):
    """Rename a service in place.

    Workflows filed under it keep pointing at the same id, so a rename never
    moves a workflow out of its service.
    """

    name: str = Field(min_length=1, max_length=SERVICE_NAME_MAX_LENGTH)


class WorkflowScope(ExtendedStrEnum):
    """Supported state machine list scopes."""

    PUBLISHED = "published"
    DRAFT = "draft"
    ALL = "all"


class WorkflowRowLookupRequest(PydanticBaseModel):
    """Resolve one exact workflow row by row ID."""

    row_id: str

    @model_validator(mode="after")
    def validate_model(self) -> "WorkflowRowLookupRequest":
        self.row_id = _non_empty(self.row_id, "row_id")
        return self


class WorkflowListScopeRequest(PydanticBaseModel):
    """List scope request for workflow state machines."""

    scope: WorkflowScope = WorkflowScope.PUBLISHED
    machine_name: str | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_scope(cls, data):  # noqa: ANN001
        if isinstance(data, dict):
            raw_scope = data.get("scope")
            data["scope"] = str(raw_scope or WorkflowScope.PUBLISHED).strip().lower()
        return data

    @model_validator(mode="after")
    def validate_model(self) -> "WorkflowListScopeRequest":
        if self.machine_name is not None:
            self.machine_name = _non_empty(self.machine_name, "machine_name")
        return self




class StateMachineValidateRequest(PydanticBaseModel):
    """Validate one candidate workflow definition without persisting it."""

    machine_name: str
    base_version: int | None = Field(default=None, ge=0)
    definition: StateMachineDefinition

    @model_validator(mode="before")
    @classmethod
    def normalize_raw_definition(cls, data):  # noqa: ANN001
        """Allow callers to send either a wrapped payload or the raw definition."""
        if isinstance(data, dict) and "definition" not in data and "machine_key" in data:
            return {
                "machine_name": data.get("machine_key"),
                "definition": data,
            }
        return data

    @model_validator(mode="after")
    def validate_model(self) -> "StateMachineValidateRequest":
        """Normalize names."""
        self.machine_name = _non_empty(self.machine_name, "machine_name")
        return self


class StateMachinePublishRequest(PydanticBaseModel):
    """Publish one workflow definition as a new persisted version."""

    machine_name: str
    base_version: int | None = Field(default=None, ge=0)
    definition: StateMachineDefinition

    @model_validator(mode="before")
    @classmethod
    def normalize_raw_definition(cls, data):  # noqa: ANN001
        """Allow callers to send either a wrapped payload or the raw definition."""
        if isinstance(data, dict) and "definition" not in data and "machine_key" in data:
            return {
                "machine_name": data.get("machine_key"),
                "definition": data,
            }
        return data

    @model_validator(mode="after")
    def validate_model(self) -> "StateMachinePublishRequest":
        """Normalize names."""
        self.machine_name = _non_empty(self.machine_name, "machine_name")
        return self


class EntityDryRunRequest(PydanticBaseModel):
    """Dry-run one entity snapshot."""

    entity_type: str
    current_state: str
    data: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_model(self) -> "EntityDryRunRequest":
        """Normalize names."""
        self.entity_type = _non_empty(self.entity_type, "entity_type")
        self.current_state = _non_empty(self.current_state, "current_state")
        return self




class WorkflowEnrollmentRequest(PydanticBaseModel):
    """Enroll an existing entity in the active version of a workflow.

    Caller must have already created the entity record (via
    `POST /entity-records`). This route only writes to
    `runtime.entity_state` and emits the corresponding audit event."""

    entity_id: str

    @model_validator(mode="after")
    def validate_model(self) -> "WorkflowEnrollmentRequest":
        """Normalize and require entity_id."""
        self.entity_id = _non_empty(self.entity_id, "entity_id")
        return self


class TransitionExecuteRequest(PydanticBaseModel):
    """Transition execute request."""

    entity_id: str
    workflow_id: str | None = None
    trigger: str
    idempotency_key: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_model(self) -> "TransitionExecuteRequest":
        """Normalize names."""
        self.entity_id = _non_empty(self.entity_id, "entity_id")
        if self.workflow_id is not None:
            self.workflow_id = _non_empty(self.workflow_id, "workflow_id")
        self.trigger = _non_empty(self.trigger, "trigger")
        if self.idempotency_key is not None:
            self.idempotency_key = _non_empty(self.idempotency_key, "idempotency_key")
        return self


class EntitySchemaPicklistCreateRequest(PydanticBaseModel):
    """Create one reusable entity-schema picklist."""

    schema_key: str
    name: str
    description: str | None = None
    entity_type: str
    fields: list[EntityField] = Field(default_factory=list)
    is_active: bool = True

    @model_validator(mode="after")
    def validate_model(self) -> "EntitySchemaPicklistCreateRequest":
        """Normalize picklist schema request values."""
        self.schema_key = _non_empty(self.schema_key, "schema_key")
        self.name = _non_empty(self.name, "name")
        self.entity_type = _non_empty(self.entity_type, "entity_type")
        return self


class EntitySchemaPicklistUpdateRequest(PydanticBaseModel):
    """Update one reusable entity-schema picklist."""

    name: str | None = None
    description: str | None = None
    entity_type: str | None = None
    fields: list[EntityField] | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def validate_model(self) -> "EntitySchemaPicklistUpdateRequest":
        """Normalize optional update fields."""
        if self.name is not None:
            self.name = _non_empty(self.name, "name")
        if self.entity_type is not None:
            self.entity_type = _non_empty(self.entity_type, "entity_type")
        if (
            self.name is None
            and self.description is None
            and self.entity_type is None
            and self.fields is None
            and self.is_active is None
        ):
            raise ValueError("at least one updatable field must be provided")
        return self


class StateActionRerunRequest(PydanticBaseModel):
    """Optional body for a manual state-action re-run."""

    action_index: int | None = Field(default=None, ge=0)



class RunFactsRequest(PydanticBaseModel):
    """Batched read: run facts for a caller-supplied set of entity ids."""

    entity_ids: list[str] = Field(..., min_length=1, max_length=RUN_FACTS_ENTITY_ID_CAP)

    @model_validator(mode="after")
    def validate_model(self) -> "RunFactsRequest":
        """Normalize and de-duplicate entity_ids, preserving first-seen order."""
        normalized = [_non_empty(e, "entity_ids") for e in self.entity_ids]
        self.entity_ids = list(dict.fromkeys(normalized))
        return self
