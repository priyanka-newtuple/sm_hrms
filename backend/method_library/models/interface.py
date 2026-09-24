"""Cross-module contracts for the method library.

A method is a named, categorised list of fields. Its name, description and
category are live editable state on the identity. Its field list is versioned,
so a workflow reading a method gets a stable ordered list that later edits to the
method cannot change underneath it.

Each listed field pins one Field Library version, so a method also sees a stable
field shape: the type and settings as they were when the method version was made.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from common.data_model import BaseModel as PydanticBaseModel

METHOD_NAME_MAX_LENGTH = 256
CATEGORY_NAME_MAX_LENGTH = 256
LABEL_MAX_LENGTH = 256
PLACEHOLDER_MAX_LENGTH = 256
# Matches workflow_state_machines.entity_type, the column tags are compared against.
ENTITY_TYPE_MAX_LENGTH = 128
# "<EntityTypeName>.<field>" — generous enough for the widest entity type name
# (128) plus the widest field key (128) plus the separator.
INHERIT_FROM_MAX_LENGTH = 300
# Holds any `workflow.models.interface.FieldOwnership` member ('owned',
# 'inherited') with headroom. The column is sized from this.
OWNERSHIP_MAX_LENGTH = 32


class MethodCategory(PydanticBaseModel):
    """A grouping for methods, unique by name within an organization.

    Uniqueness is case insensitive, so "Reagent Prep" and "reagent prep" are the
    same category to one organization and unrelated across two.
    """

    category_id: str
    organization_id: str
    name: str
    created_at: datetime | None = None


class MethodIdentity(PydanticBaseModel):
    """A method's live state.

    `method_code` is a per-organization sequence number assigned by the database
    at creation and never reused, so each organization counts 1, 2, 3 of its own.
    Name, description and category are edited in place and carry no versioning
    implication.
    """

    method_id: str
    organization_id: str
    method_code: int
    name: str
    description: str | None = None
    category_id: str | None = None
    category_name: str | None = None
    created_by: str | None = None
    is_archived: bool = False
    created_at: datetime | None = None
    # Entity types this method is offered on. Empty means offered nowhere.
    entity_types: list[str] = Field(default_factory=list)


class MethodVersion(PydanticBaseModel):
    """One version of a method's field list.

    Insert-only apart from `is_latest` moving when superseded, so a workflow
    pinned to a version keeps resolving the list it pinned.
    """

    version_id: str
    method_id: str
    organization_id: str
    version: int
    is_latest: bool = False
    # With no fields, makes this a dynamic method.
    connector_id: str | None = None
    created_by: str | None = None


class MethodVersionField(PydanticBaseModel):
    """One field inside a method version, merged with its Field Library shape.

    `label`, `placeholder`, `required` and `position` are the method's own view of
    the field. `field_key`, `field_type` and `settings` are resolved from the
    pinned `field_version_id`, so they describe the field as it was when this
    method version was created, not as it is now.
    """

    id: str
    method_version_id: str
    library_field_id: str
    field_version_id: str
    label: str | None = None
    placeholder: str | None = None
    required: bool = False
    position: int = 0
    # "<EntityTypeName>.<field>" this usage inherits its value from, or None
    # to enter it directly. Per-usage, like label/placeholder/required above.
    inherit_from: str | None = None
    field_key: str
    field_type: str
    settings: dict[str, object] = Field(default_factory=dict)
    # Optional source intent: entity type + field this field's value should
    # resolve from once the method is attached to a workflow state. Both set or
    # both None — see MethodFieldInput.
    source_entity_type: str | None = None
    source_field_key: str | None = None
    # The opt-in that makes the source intent above actually resolve. When
    # 'inherited', the pinned field is marked inherited on the workflow's
    # entity schema and its value is read from the related record named by
    # `source_entity_type`.`source_field_key`, only where this Method is in
    # use. None = not stated = behaves as today. A `FieldOwnership` value.
    ownership: str | None = None


class MethodWithFields(PydanticBaseModel):
    """A method's identity, the version being read, and its ordered field list."""

    identity: MethodIdentity
    version: MethodVersion
    fields: list[MethodVersionField] = Field(default_factory=list)
