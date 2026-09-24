"""Response schemas for the roles module."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from common.data_model import BaseModel as PydanticBaseModel

from roles.models.request import EntityReadFilter

PermissionAction = Literal["view", "create", "edit", "delete"]


class RolePermissionRead(PydanticBaseModel):
    permission_key: str


class EntityPermissionRead(PydanticBaseModel):
    id: str
    entity_type: str
    action: str
    allowed: bool
    entity_field: Optional[str] = None
    operator: Optional[str] = None
    value_source: Optional[str] = None
    condition_value: Optional[str] = None
    read_filter: EntityReadFilter | None = None


class FieldPermissionRead(PydanticBaseModel):
    id: str
    entity_type: str
    field_name: str
    can_view: bool
    can_edit: bool
    mask_value: bool


class TransitionPermissionRead(PydanticBaseModel):
    id: str
    machine_name: str
    transition_key: str


class WorkflowPermissionRead(PydanticBaseModel):
    id: str
    machine_name: str


class RoleRead(PydanticBaseModel):
    id: str
    organization_id: str
    name: str
    display_name: str
    description: Optional[str] = None
    is_system: bool
    priority: int
    color: Optional[str] = None
    permissions: list[RolePermissionRead] = []
    entity_permissions: list[EntityPermissionRead] = []
    field_permissions: list[FieldPermissionRead] = []
    transition_permissions: list[TransitionPermissionRead] = []
    workflow_permissions: list[WorkflowPermissionRead] = []
    user_count: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class RoleListItem(PydanticBaseModel):
    id: str
    name: str
    display_name: str
    description: Optional[str] = None
    is_system: bool
    priority: int
    color: Optional[str] = None
    user_count: int
    created_at: datetime


class UserRoleRead(PydanticBaseModel):
    id: str
    user_id: str
    organization_id: str
    role_id: str
    role_name: str
    role_display_name: str
    role_color: Optional[str] = None
    role_is_system: bool
    assigned_at: datetime
    assigned_by: Optional[str] = None


class FieldPermissionSummary(PydanticBaseModel):
    can_view: bool
    can_edit: bool
    mask_value: bool


class RoleSummary(PydanticBaseModel):
    id: str
    name: str
    display_name: str
    priority: int
    color: Optional[str] = None
    is_system: bool


class PermissionsSummary(PydanticBaseModel):
    user_id: Optional[str] = None
    organization_id: Optional[str] = None
    roles: list[RoleSummary]
    permissions: list[str] = []
    entity_permissions: list[EntityPermissionRead] = []
    field_permissions: list[FieldPermissionRead] = []
    transition_permissions: list[TransitionPermissionRead] = []
