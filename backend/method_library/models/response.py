"""Response contracts for the method library module."""

from __future__ import annotations

from pydantic import Field

from common.data_model import BaseModel as PydanticBaseModel
from method_library.models.interface import (
    MethodCategory,
    MethodIdentity,
    MethodVersion,
    MethodVersionField,
    MethodWithFields,
)


class MethodCategoryListResponse(PydanticBaseModel):
    """Every category in the organization, ordered by name.

    Not paginated: this is the lookup list behind a category picker, and an
    organization has a handful of categories rather than a growing history.
    """

    organization_id: str
    items: list[MethodCategory] = Field(default_factory=list)


class MethodLibraryStatusResponse(PydanticBaseModel):
    """Module status, matching the shape every other module reports."""

    module: str
    status: str
    started: bool


class MethodListResponse(PydanticBaseModel):
    """A page of the method grid: one entry per method, no field lists.

    Identities only, so listing stays cheap. Field lists are resolved by the
    detail endpoint. `total` counts every match, not just this page, so the
    caller can build page controls.
    """

    organization_id: str
    items: list[MethodIdentity] = Field(default_factory=list)
    total: int = 0
    limit: int = 0
    offset: int = 0


class MethodVersionListResponse(PydanticBaseModel):
    """A page of one method's version history, newest first.

    Paginated deliberately, unlike the field library's equivalent: a method's
    field list changes far more often than a field's own settings, so this
    history is expected to grow.
    """

    method_id: str
    items: list[MethodVersion] = Field(default_factory=list)
    total: int = 0
    limit: int = 0
    offset: int = 0


__all__ = [
    "MethodCategory",
    "MethodCategoryListResponse",
    "MethodIdentity",
    "MethodLibraryStatusResponse",
    "MethodListResponse",
    "MethodVersion",
    "MethodVersionField",
    "MethodVersionListResponse",
    "MethodWithFields",
]
