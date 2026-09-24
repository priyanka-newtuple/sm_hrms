"""Interface models and contracts for entities."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Literal, Protocol, Self

from pydantic import ConfigDict, Field, model_validator

from common.data_model import BaseModel as PydanticBaseModel, ExtendedStrEnum
from exceptions import ValidationError

# Key for the per-entity-type unique identifier stored in entity `data`.
IDENTIFIER_FIELD_KEY = "identifier"

# Tried in order, after the identifier, when naming a record for display. Named here because two
# modules depend on the same order: this module resolves the name, and the workflow board has to
# request these fields for it to have anything to resolve from.
DISPLAY_NAME_FIELD_KEYS = ("name", "title", "full_name")

# Identifier-template config limits (spec §3, §7).
IDENTIFIER_LABEL_MAX = 64
IDENTIFIER_TEMPLATE_MAX = 256
IDENTIFIER_ERROR_MESSAGE_MAX = 200

# Hard cap on the `limit` a caller can request from
# `list_entity_records_by_type_name_for_actor` — a client-requested limit above
# this is silently clamped down, never rejected.
ENTITY_RECORDS_BY_TYPE_NAME_LIMIT_MAX = 100

# ponytail: fixed candidate prefilter cap for `list_entity_records_by_type_name_for_actor`
# — used whenever a search or limit is requested, since the DB-layer fetch is only a
# candidate prefilter and the authoritative match/filter runs after. Revisit if
# searches (or heavily-conditioned roles) with heavy field-masking start
# under-filling the requested limit.
ENTITY_RECORDS_BY_TYPE_NAME_PREFILTER_CAP = 200

DOCUMENT_FIELD_TYPE = "document"
EXTENSIONS_KEY = "extensions"
EXTENSION_FIELDS_KEY = "fields"


class RelationType(ExtendedStrEnum):
    """Field-inheritance mode declared on an entity_type_relations row."""

    REFERENCE = "REFERENCE"
    SNAPSHOT = "SNAPSHOT"


class IdentifierAllowedFieldType(ExtendedStrEnum):
    """Field types eligible to be used as a `{{token}}` in an identifier template
    (spec §3, §7). Anything not in this set can't be referenced by an
    identifier_template, even if the field exists on the schema."""

    TEXT = "text"
    TEXTAREA = "textarea"
    STRING = "string"
    EMAIL = "email"
    PHONE = "phone"
    URL = "url"
    SELECT = "select"
    ENUM = "enum"
    INTEGER = "integer"
    NUMBER = "number"
    INT = "int"
    DATE = "date"
    DATETIME = "datetime"
    AUTO_NUMBER = "auto_number"
    REFERENCE = "reference"


def local_field_name(dotted_field_key: str) -> str:
    """Strip the `EntityType.` prefix off a relation_metadata key/value.

    Shared between `manager.py` and `db_models.py` — both interpret the same
    `relation_metadata` dotted-key format, so the parsing rule lives here as
    the single source of truth rather than duplicated per layer.
    """
    return dotted_field_key.split(".", 1)[1] if "." in dotted_field_key else dotted_field_key


def parent_id_field_name(entity_type_name: str) -> str:
    """Auto field name that carries a linked parent's record id.

    e.g. ``client`` → ``client_id``, ``job`` → ``job_id``, ``ATS.Candidate`` →
    ``candidate_id``. Whenever an entity inherits fields from a parent type, the
    parent's own ``entity_id`` is exposed under this name automatically — no
    mapping needed — so a connector can use it as ``$entity.<name>``.
    """
    base = entity_type_name.split(".")[-1]
    base = re.sub(r"[^0-9a-zA-Z_]", "_", base).strip("_").lower()
    return f"{base}_id"


class ChangedFieldDiff(PydanticBaseModel):
    """Before/after diff for a single field inside an ENTITY_UPDATED payload."""

    model_config = ConfigDict(extra="forbid")

    before: Any
    after: Any


class EntityCreatedPayload(PydanticBaseModel):
    """Payload for ENTITY_CREATED events."""

    model_config = ConfigDict(extra="forbid")

    entity_type_name: str | None = None
    identifier: str | None = None
    owner_id: str | None = None


class EntityUpdatedPayload(PydanticBaseModel):
    """Payload for ENTITY_UPDATED events.

    `changed_fields` is keyed by field_key; value is the before/after diff.
    """

    model_config = ConfigDict(extra="forbid")

    changed_fields: dict[str, ChangedFieldDiff] = Field(default_factory=dict)


class EntityAssigneeChangedPayload(PydanticBaseModel):
    """Payload for ENTITY_ASSIGNEE_CHANGED events.

    `assignment_mode`/`assignment_source` explain how the assignee was chosen,
    so the timeline can distinguish "someone picked this person" from "the
    record was routed back to its creator by a workflow". Both are optional:
    rows written before these were recorded carry neither, and the payload union
    would otherwise stop parsing historical events as this type.

    `action_run_id` is present only when a workflow action made the change.
    """

    model_config = ConfigDict(extra="forbid")

    previous_assignee_id: str | None = None
    new_assignee_id: str | None = None
    assignment_mode: str | None = None
    assignment_source: str | None = None
    action_run_id: str | None = None


class EntityArchivedPayload(PydanticBaseModel):
    """Payload for ENTITY_ARCHIVED events — no extra fields."""

    model_config = ConfigDict(extra="forbid")


class EntityRestoredPayload(PydanticBaseModel):
    """Payload for ENTITY_RESTORED events — no extra fields."""

    model_config = ConfigDict(extra="forbid")


class EntityAuditEventType(ExtendedStrEnum):
    """Event type values written to audit_events for entity CRUD operations.

    Values must match the catalog registered in audit/models/interface.py
    under AuditMetadataType.ENTITY.
    """

    CREATED = "ENTITY_CREATED"
    UPDATED = "ENTITY_UPDATED"
    ASSIGNEE_CHANGED = "ENTITY_ASSIGNEE_CHANGED"
    ARCHIVED = "ENTITY_ARCHIVED"
    RESTORED = "ENTITY_RESTORED"


class ActorType(ExtendedStrEnum):
    """Actor type recorded on an emitted audit event's `actor_type` field."""

    USER = "user"
    SYSTEM = "system"


class AuditEventSource(ExtendedStrEnum):
    """Origin of an emitted audit event, passed to `emit_audit_event`."""

    API = "api"


class AssignmentMode(ExtendedStrEnum):
    """How the assignee on an `ENTITY_ASSIGNEE_CHANGED` event was chosen.

    Recorded in the audit payload so the record's history explains *why* a
    given user was selected, not just that the assignee moved.
    """

    MANUAL = "manual"
    ORIGINATOR = "originator"


class AssignmentSource(ExtendedStrEnum):
    """What drove an assignment — a human request or a workflow action."""

    API = "api"
    WORKFLOW_ACTION = "workflow_action"


class AssignmentRejection(ExtendedStrEnum):
    """Machine-readable `code` carried on an assignment `ValidationError`.

    Lets a non-HTTP caller — the workflow action executor — tell a suspended
    target from a missing one without parsing the client-facing message, which
    is free to be reworded. Does not affect the HTTP status: every one of these
    is a 400.
    """

    ORIGINATOR_NOT_FOUND = "originator_not_found"
    ORIGINATOR_USER_MISSING = "originator_user_missing"
    ORIGINATOR_NOT_A_MEMBER = "originator_not_a_member"
    ORIGINATOR_SUSPENDED = "originator_suspended"
    ORIGINATOR_INACTIVE_ACCOUNT = "originator_inactive_account"


class AssignmentAuditKey(ExtendedStrEnum):
    """Keys in the `ENTITY_ASSIGNEE_CHANGED` audit payload.

    A read contract: the activity timeline renders from these, so renaming one
    changes what already-written history means.
    """

    PREVIOUS_ASSIGNEE_ID = "previous_assignee_id"
    NEW_ASSIGNEE_ID = "new_assignee_id"
    ASSIGNMENT_MODE = "assignment_mode"
    ASSIGNMENT_SOURCE = "assignment_source"
    ACTION_RUN_ID = "action_run_id"


# Client-facing rejection messages for the assignee endpoint. Contract, not
# diagnostics: the UI surfaces these verbatim, so they name the person where a
# person is involved and never leak a user id.
ASSIGNMENT_MODE_CONFLICT_MESSAGE = (
    "Provide either an assignee or the assign-to-originator flag, not both."
)
ORIGINATOR_NOT_FOUND_MESSAGE = (
    "This record has no original creator to assign it to. It may have been "
    "created automatically rather than by a person."
)
ORIGINATOR_NOT_A_MEMBER_MESSAGE = (
    "The user who created this record is no longer a member of this organization."
)
ORIGINATOR_USER_MISSING_MESSAGE = "The user who created this record no longer exists."


def originator_suspended_message(full_name: str) -> str:
    """Rejection text naming the suspended originator, per the spec's example.

    Suspension is per-organization (`user_organizations.status`) — the only
    place the database can represent it.
    """
    return f"{full_name} cannot be assigned because the user is suspended."


def originator_inactive_account_message(full_name: str) -> str:
    """Rejection text for an account that is pending approval or was rejected.

    Distinct from suspension: `users.status` can only be pending/active/rejected,
    so telling a never-approved user they were suspended would be wrong.
    """
    return f"{full_name} cannot be assigned because their account is not active."


def _non_empty(value: str, field_name: str) -> str:
    """Pydantic validator: reject empty/whitespace-only strings."""
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized


class FieldDefinition(PydanticBaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    field_type: str
    required: bool = False
    options: tuple[str, ...] = ()

    @model_validator(mode="after")
    def normalize_fields(self) -> Self:
        """Strip empty optional fields and coerce blanks before model construction."""
        self.name = _non_empty(str(self.name), "name")
        self.field_type = _non_empty(str(self.field_type), "field_type")
        raw_options = self.options
        if not isinstance(raw_options, (list, tuple)):
            raise ValueError("options must be a list")
        self.options = tuple(str(option).strip() for option in raw_options if str(option).strip())
        return self

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> FieldDefinition:
        """Build the contract from a dict (typed wrapper around model_validate)."""
        try:
            return cls.model_validate(payload)
        except Exception as exc:
            raise ValidationError(str(exc)) from exc


class FormConfigContract(PydanticBaseModel):
    organization_id: str
    form_key: str
    fields: list[FieldDefinition] = Field(default_factory=list)
    version: int = 1


class EntityType(PydanticBaseModel):
    """Canonical entity type — schema registry record."""

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


class EntityRecord(PydanticBaseModel):
    """Canonical entity instance — runtime data record."""

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


class EntityRelation(PydanticBaseModel):
    """Directed edge between two runtime entities."""

    relation_id: str
    organization_id: str
    from_entity_id: str
    to_entity_id: str
    relation_type: str
    relation_metadata: dict[str, Any] | None = None
    created_at: datetime | None = None


class EntityStateRecord(PydanticBaseModel):
    """One workflow enrollment for a runtime entity.

    Multiple rows are allowed per `entity_id` — one per workflow. Identity is
    a synthetic `state_id`, distinct from the entity id, so the same entity
    can hold many concurrent state pointers.
    """

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


class EntityEventRecord(PydanticBaseModel):
    """One row in the per-entity append-only timeline (`audit.entity_events`)."""

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
    payload: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime | None = None


class EntityTypeRelation(PydanticBaseModel):
    """Declared relation between two entity types, including field-inheritance config."""

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


class MetadataLookupPort(Protocol):
    """Read-only lookup contract for dependent managers."""

    def get_form_config(self, organization_id: str, form_key: str) -> FormConfigContract | None:
        """Resolve form metadata."""
