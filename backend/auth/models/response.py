"""Response schemas for the auth module."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from common.data_model import BaseModel as PydanticBaseModel
from user.models.response import UserPublic


class TokenResponse(PydanticBaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserPublic


class RegistrationResponse(PydanticBaseModel):
    """Returned (202) when registration requires approval before access."""

    message: str
    user_id: str
    organization_id: str
    organization_name: str
    approval_type: Literal["active", "pending_org_admin", "pending_platform"]
    is_new_organization: bool


class PendingOrgRegistrationResponse(PydanticBaseModel):
    """Returned when a user registers with a new (pending) organization."""

    message: str
    user_id: str
    organization_id: str
    organization_name: str
    status: str = "pending_org_approval"


class GoogleAuthUrl(PydanticBaseModel):
    url: str


class MicrosoftAuthUrl(PydanticBaseModel):
    url: str
    state: str


class MicrosoftTokenResponse(PydanticBaseModel):
    token_type: str = "bearer"
    id_token: str
    access_token: str | None = None
    expires_in: int | None = None
    user: UserPublic
    # App-issued JWTs for use with backend API calls
    app_access_token: str | None = None
    app_refresh_token: str | None = None


class MessageResponse(PydanticBaseModel):
    message: str


class AccessCheckResponse(PydanticBaseModel):
    allowed: bool
    evaluated_permission: str
    reason: str | None = None
    matched_roles: list[str] = Field(default_factory=list)


class TokenIntrospectionResponse(PydanticBaseModel):
    active: bool
    subject: str | None = None
    organization_id: str | None = None
    roles: list[str] = Field(default_factory=list)


class RoleGrantResponse(PydanticBaseModel):
    user_id: str
    organization_id: str
    role: str
    granted: bool = True


class IdentityAccessStatusResponse(PydanticBaseModel):
    module: str
    status: str
    started: bool
