"""Response contracts for the field library module."""

from __future__ import annotations

from pydantic import Field

from common.data_model import BaseModel as PydanticBaseModel
from field_library.models.interface import (
    FieldIdentity,
    FieldTypeCatalogueEntry,
    FieldVersion,
    FieldWithVersion,
    FormFieldPlacement,
)


class FieldTypeOption(PydanticBaseModel):
    """One entry as offered to the field-type selector.

    `selectable` folds together engine availability and org enablement.
    Unavailable entries are still returned so the UI can grey them out.
    """

    code: str
    label: str
    engine_type: str | None = None
    config_kind: str
    selectable: bool
    unavailable_reason: str | None = None


class FieldTypeCatalogueResponse(PydanticBaseModel):
    """The field types offered to one organization, in display order."""

    organization_id: str
    items: list[FieldTypeOption] = Field(default_factory=list)


class FieldLibraryStatusResponse(PydanticBaseModel):
    """Module status, matching the shape every other module reports."""

    module: str
    status: str
    started: bool


class FieldListResponse(PydanticBaseModel):
    """A page of library fields, each with its current version.

    Carrying the version inline lets the grid show settings and description
    without a follow-up call per row. `total` counts every match, not just this
    page, so the caller can build page controls.
    """

    organization_id: str
    items: list[FieldWithVersion] = Field(default_factory=list)
    total: int = 0
    limit: int = 0
    offset: int = 0


class FieldVersionListResponse(PydanticBaseModel):
    """Every version of one field, oldest first, for a version picker."""

    library_field_id: str
    items: list[FieldVersion] = Field(default_factory=list)


class FormFieldListResponse(PydanticBaseModel):
    """Every field one form uses, in the order it shows them."""

    schema_id: str
    organization_id: str
    items: list[FormFieldPlacement] = Field(default_factory=list)


__all__ = [
    "FieldIdentity",
    "FieldLibraryStatusResponse",
    "FieldListResponse",
    "FieldTypeCatalogueEntry",
    "FieldTypeCatalogueResponse",
    "FieldTypeOption",
    "FieldVersion",
    "FieldVersionListResponse",
    "FieldWithVersion",
    "FormFieldListResponse",
    "FormFieldPlacement",
]
