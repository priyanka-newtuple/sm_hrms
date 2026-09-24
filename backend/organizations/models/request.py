"""Request models for organizations."""

from __future__ import annotations

from typing import Any, Self

from pydantic import EmailStr, Field, model_validator

from common.data_model import BaseModel as PydanticBaseModel
from organizations.models.interface import validate_org_name, validate_slug


class OrganizationCreate(PydanticBaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    slug: str | None = Field(default=None, max_length=128)
    domain: str | None = Field(default=None, max_length=255)
    settings: dict[str, Any] | None = Field(default=None)
    logo_url: str | None = Field(default=None, max_length=512)

    @model_validator(mode="after")
    def normalize_fields(self) -> Self:
        self.name = validate_org_name(str(self.name))
        if self.slug is not None:
            self.slug = validate_slug(str(self.slug))
        if self.domain is not None:
            self.domain = self.domain.strip().lower() or None
        return self


class OrganizationUpdate(PydanticBaseModel):
    name: str | None = Field(default=None, max_length=255)
    domain: str | None = Field(default=None, max_length=255)
    settings: dict[str, Any] | None = None
    logo_url: str | None = Field(default=None, max_length=512)
    status: str | None = None

    @model_validator(mode="after")
    def normalize_fields(self) -> Self:
        if self.name is not None:
            self.name = validate_org_name(str(self.name))
        if self.domain is not None:
            self.domain = self.domain.strip().lower() or None
        if self.status is not None:
            self.status = self.status.strip().lower()
        return self


class BrandingUpdate(PydanticBaseModel):
    """Branding-only update an org admin may apply to their own organization.

    Restricted to appearance fields (theme settings and logo) so that org admins
    cannot change privileged fields such as name, domain, or status.
    """

    settings: dict[str, Any] | None = None
    logo_url: str | None = Field(default=None, max_length=512)


class OrgNameUpdate(PydanticBaseModel):
    """Name-only update that org admins can apply to their own organization."""

    name: str = Field(..., min_length=1, max_length=255)

    @model_validator(mode="after")
    def normalize_fields(self) -> Self:
        self.name = validate_org_name(str(self.name))
        return self


class PlatformUserCreate(PydanticBaseModel):
    """Create a user under an organization (super-admin only)."""

    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=255)
    role: str = Field(default="viewer")
    status: str = Field(default="active")

    @model_validator(mode="after")
    def normalize_fields(self) -> Self:
        self.full_name = self.full_name.strip()
        if not self.full_name:
            raise ValueError("full_name must be a non-empty string")
        self.role = self.role.strip().lower()
        self.status = self.status.strip().lower()
        return self
