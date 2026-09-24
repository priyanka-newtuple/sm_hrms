"""Interface models and contracts for the organizations module."""

from __future__ import annotations

import re
from typing import Any, Protocol

from pydantic import ConfigDict, Field

from common.data_model import BaseModel as PydanticBaseModel


class OrganizationContract(PydanticBaseModel):
    """Frozen snapshot of an organization — safe to pass across module boundaries."""

    model_config = ConfigDict(frozen=True, from_attributes=True)

    id: str
    name: str
    slug: str
    status: str
    domain: str | None = None
    logo_url: str | None = None
    settings: dict[str, Any] = Field(default_factory=dict)


class OrganizationMembershipContract(PydanticBaseModel):
    """Frozen user-organization membership record."""

    model_config = ConfigDict(frozen=True, from_attributes=True)

    user_id: str
    organization_id: str
    role: str
    status: str


class TenantContext(PydanticBaseModel):
    """Tenant boundary context — org identity used for scoping cross-module operations."""

    model_config = ConfigDict(frozen=True)

    organization_id: str = Field(..., min_length=1)
    organization_slug: str | None = None
    is_platform: bool = False


class OrganizationLookupService(Protocol):
    """Minimal contract for modules that need to verify org existence."""

    def get_by_id(self, db: Any, org_id: str) -> Any | None:
        """Return an organization ORM object or None."""
        ...

    def get_by_slug(self, db: Any, slug: str) -> Any | None:
        """Return an organization ORM object or None."""
        ...


class TenantProvisioningService(Protocol):
    """Contract for modules that trigger tenant provisioning."""

    def provision_tenant(self, db: Any, *, org_id: str) -> Any:
        """Provision default resources for a tenant. Returns a ProvisionResult."""
        ...


def validate_slug(slug: str) -> str:
    """Normalize and validate an organization slug."""
    normalized = slug.strip().lower()
    if not normalized:
        raise ValueError("slug must be a non-empty string")
    if not re.match(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", normalized):
        raise ValueError("slug may only contain lowercase letters, digits, and hyphens")
    return normalized


def validate_org_name(name: str) -> str:
    """Validate an organization name is non-empty."""
    normalized = name.strip()
    if not normalized:
        raise ValueError("organization name must be a non-empty string")
    return normalized
