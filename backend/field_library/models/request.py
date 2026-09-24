"""Request contracts for the field library module."""

from __future__ import annotations

from pydantic import Field

from common.data_model import BaseModel as PydanticBaseModel
from field_library.models.interface import (
    FIELD_KEY_MAX_LENGTH,
    FIELD_NAME_MAX_LENGTH,
    FIELD_TYPE_CODE_MAX_LENGTH,
)


class FieldCreateRequest(PydanticBaseModel):
    """Create a library field. The only request carrying field content, since a
    field is immutable once created.

    Bounds mirror the column widths so over-long input gets a 422, not a 500.
    """

    name: str = Field(min_length=1, max_length=FIELD_NAME_MAX_LENGTH)
    field_key: str = Field(min_length=1, max_length=FIELD_KEY_MAX_LENGTH)
    field_type: str = Field(min_length=1, max_length=FIELD_TYPE_CODE_MAX_LENGTH)
    description: str | None = None
    settings: dict[str, object] = Field(default_factory=dict)


class FieldRenameRequest(PydanticBaseModel):
    """Rename a field.

    Not a content edit: it updates the identity row and creates no version, so
    every existing reference keeps resolving unchanged.
    """

    name: str = Field(min_length=1, max_length=FIELD_NAME_MAX_LENGTH)


class FieldVersionCreateRequest(PydanticBaseModel):
    """Create the next version of an existing field.

    None for field_type means no type change, which is the common case. A value
    means this version also changes the type, and the identity is updated to
    match. field_key is absent because it can never change.
    """

    description: str | None = None
    settings: dict[str, object] = Field(default_factory=dict)
    field_type: str | None = Field(default=None, max_length=FIELD_TYPE_CODE_MAX_LENGTH)


class FieldDescriptionUpdateRequest(PydanticBaseModel):
    """Edit the current version's description in place.

    A lightweight edit, like rename is for name: it rewrites one column on the
    latest version and creates no new version.
    """

    description: str | None = None


class FormFieldLinkCreateRequest(PydanticBaseModel):
    """Put one Field Library field on one form.

    `version_id` omitted means "whatever this field's current version is now",
    resolved once at link time and then pinned. It is not re-resolved later: that
    is the whole point of pinning.
    """

    schema_id: str = Field(min_length=1)
    library_field_id: str = Field(min_length=1)
    version_id: str | None = None
    position: int = Field(default=0, ge=0)


class FormFieldLinkRepinRequest(PydanticBaseModel):
    """Move an existing link to a different version of the field it already uses."""

    version_id: str = Field(min_length=1)
