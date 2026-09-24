"""Request schemas for the roles module."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import Field, model_validator

from common.data_model import BaseModel as PydanticBaseModel
from roles.models.interface import EntityConditionOperator

PermissionAction = Literal["view", "create", "edit", "delete"]


MAX_ENTITY_READ_FILTER_CONDITIONS = 50


class RolePermissionCreate(PydanticBaseModel):
    permission_key: str


class EntityReadCondition(PydanticBaseModel):
    conjunction: Literal["AND", "OR"] = "AND"
    entity_field: str = Field(min_length=1, max_length=128)
    operator: EntityConditionOperator
    value_source: Literal["LITERAL"] = "LITERAL"
    condition_value: str = Field(min_length=1, max_length=256)


class EntityReadFilter(PydanticBaseModel):
    conditions: list[EntityReadCondition] = Field(
        min_length=1, max_length=MAX_ENTITY_READ_FILTER_CONDITIONS
    )

    @model_validator(mode="after")
    def normalize_first_conjunction(self) -> EntityReadFilter:
        if self.conditions:
            self.conditions[0].conjunction = "AND"
        return self


class EntityPermissionCreate(PydanticBaseModel):
    entity_type: str
    action: PermissionAction
    allowed: bool = True
    # Optional read-narrowing condition (entity field permission filter). All four fields
    # are validated together in roles/manager.py at save time — shape only, not
    # existence/support, is enforced here.
    entity_field: Optional[str] = None
    operator: Optional[str] = None
    value_source: Optional[str] = None
    condition_value: Optional[str] = None
    read_filter: EntityReadFilter | None = None


class FieldPermissionCreate(PydanticBaseModel):
    entity_type: str
    field_name: str
    can_view: bool
    can_edit: bool
    mask_value: bool

    @model_validator(mode="after")
    def validate_view_edit_consistency(self) -> FieldPermissionCreate:
        if not self.can_view and self.can_edit:
            raise ValueError("can_edit must be False when can_view is False")
        return self


class TransitionPermissionCreate(PydanticBaseModel):
    machine_name: str
    transition_key: str


class WorkflowPermissionCreate(PydanticBaseModel):
    machine_name: str


class RoleCreateRequest(PydanticBaseModel):
    name: str
    display_name: str
    description: Optional[str] = None
    priority: Optional[int] = None
    color: Optional[str] = None
    permissions: list[RolePermissionCreate] = []
    entity_permissions: list[EntityPermissionCreate] = []
    field_permissions: list[FieldPermissionCreate] = []
    transition_permissions: list[TransitionPermissionCreate] = []
    workflow_permissions: list[WorkflowPermissionCreate] = []


class RoleUpdateRequest(PydanticBaseModel):
    name: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[int] = None
    color: Optional[str] = None
    permissions: Optional[list[RolePermissionCreate]] = None
    entity_permissions: Optional[list[EntityPermissionCreate]] = None
    field_permissions: Optional[list[FieldPermissionCreate]] = None
    transition_permissions: Optional[list[TransitionPermissionCreate]] = None
    workflow_permissions: Optional[list[WorkflowPermissionCreate]] = None


class RoleDuplicateRequest(PydanticBaseModel):
    name: str
    display_name: str


class UserRoleSetRequest(PydanticBaseModel):
    role_id: str
