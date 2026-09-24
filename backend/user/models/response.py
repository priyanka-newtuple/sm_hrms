"""Response schemas for the user module."""

from __future__ import annotations

from datetime import datetime

from common.data_model import BaseModel as PydanticBaseModel


class UserPublic(PydanticBaseModel):
    """Minimal user info embedded in token responses."""

    id: str
    email: str
    full_name: str
    avatar_url: str | None = None
    role: str
    status: str = "active"
    auth_type: str
    organization_id: str | None = None


class UserRead(PydanticBaseModel):
    """Full user info returned from /auth/me."""

    id: str
    email: str
    full_name: str
    avatar_url: str | None = None
    role: str
    status: str = "active"
    auth_type: str
    is_active: bool
    organization_id: str | None = None
    last_login_at: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None


class UserOrganizationRead(PydanticBaseModel):
    id: str | None = None
    organization_id: str
    organization_name: str
    organization_slug: str
    organization_domain: str | None = None
    organization_logo_url: str | None = None
    organization_status: str
    role: str
    status: str
    is_current: bool


class UserOrganizationsResponse(PydanticBaseModel):
    organizations: list[UserOrganizationRead]
    current_organization_id: str | None


class UserSearchResult(PydanticBaseModel):
    id: str
    email: str
    full_name: str
    avatar_url: str | None = None
    role: str | None = None

class UserStatsSummary(PydanticBaseModel):
    total: int
    by_status: dict[str, int]
    by_role: dict[str, int]


class UserResponse(PydanticBaseModel):
    """Full user info for user management endpoints."""

    id: str
    email: str
    full_name: str
    avatar_url: str | None = None
    role: str
    status: str
    auth_type: str
    is_active: bool
    organization_id: str | None = None
    last_login_at: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None
