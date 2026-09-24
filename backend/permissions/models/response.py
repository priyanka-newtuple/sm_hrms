"""Response schemas for the permissions module."""

from __future__ import annotations

from common.data_model import BaseModel as PydanticBaseModel


class PermissionRead(PydanticBaseModel):
    id: str
    key: str
    resource: str
    action: str
    description: str | None = None
    is_system: bool
