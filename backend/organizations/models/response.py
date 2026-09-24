"""Response schemas for the organizations module."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from common.data_model import BaseModel as PydanticBaseModel
from pydantic import Field

from user.models.response import UserRead


class OrganizationRead(PydanticBaseModel):
    id: str
    name: str
    slug: str
    logo_url: str | None = None
    domain: str | None = None
    settings: dict[str, Any] | None = None
    status: str | None = None
    requested_by_user_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class OrganizationWithRequester(OrganizationRead):
    requester_email: str | None = None
    requester_name: str | None = None


class OrganizationListResponse(PydanticBaseModel):
    items: list[OrganizationRead] = Field(default_factory=list)
    total: int = 0


class PendingOrganizationListResponse(PydanticBaseModel):
    items: list[OrganizationWithRequester] = Field(default_factory=list)
    total: int = 0


class OrganizationUserListResponse(PydanticBaseModel):
    items: list[UserRead] = Field(default_factory=list)
    total: int = 0


class ProvisionResult(PydanticBaseModel):
    organization_id: str = Field(..., description="Organization ID that was provisioned")
    success: bool = Field(..., description="Whether provisioning completed successfully")

    entity_types_created: int = 0
    entity_types_skipped: int = 0
    picklists_created: int = 0
    picklists_skipped: int = 0
    form_schemas_created: int = 0
    form_schemas_skipped: int = 0
    document_types_created: int = 0
    document_types_skipped: int = 0
    funnels_created: int = 0
    funnels_skipped: int = 0

    sample_job_created: bool = False

    view_definitions_created: int = 0
    view_definitions_skipped: int = 0
    agent_definitions_created: int = 0
    agent_definitions_skipped: int = 0
    rbac_roles_created: int = 0
    rbac_roles_skipped: int = 0

    errors: list[str] = Field(default_factory=list)
    provisioned_at: datetime | None = None


class ProvisionStatus(PydanticBaseModel):
    organization_id: str
    fully_provisioned: bool

    has_entity_types: bool
    has_picklists: bool
    has_form_schemas: bool
    has_document_types: bool
    has_funnels: bool
    has_view_definitions: bool = False
    has_agent_definitions: bool = False
    has_rbac_roles: bool = False

    entity_type_count: int = 0
    picklist_count: int = 0
    form_schema_count: int = 0
    document_type_count: int = 0
    funnel_count: int = 0

    expected_entity_types: int = 4
    expected_picklists: int = 6
    expected_form_schemas: int = 3
    expected_document_types: int = 6
    expected_funnels: int = 1
