"""Request models for the user module."""

from __future__ import annotations

from typing import Self

from pydantic import EmailStr, Field, model_validator

from common.data_model import BaseModel as PydanticBaseModel
from user.models.interface import validate_user_name


class UserCreate(PydanticBaseModel):
    """Register a new user. organization_name required only for public email domains."""

    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: str = Field(..., min_length=1, max_length=255)
    role: str = Field(default="viewer")
    organization_name: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def normalize_fields(self) -> Self:
        self.full_name = validate_user_name(str(self.full_name))
        if self.organization_name is not None:
            self.organization_name = self.organization_name.strip() or None
        self.role = self.role.strip().lower()
        return self


class UserCreateWithOrg(PydanticBaseModel):
    """Create a user + new organization together (deprecated — use UserCreate)."""

    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: str = Field(..., min_length=1, max_length=255)
    organization_name: str = Field(..., min_length=1, max_length=255)
    organization_slug: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def normalize_fields(self) -> Self:
        self.full_name = validate_user_name(str(self.full_name))
        self.organization_name = self.organization_name.strip()
        if self.organization_slug is not None:
            self.organization_slug = self.organization_slug.strip().lower() or None
        return self


class UpdateRoleRequest(PydanticBaseModel):
    role: str = Field(..., min_length=1)

    @model_validator(mode="after")
    def normalize_fields(self) -> Self:
        self.role = self.role.strip().lower()
        return self


class UpdateStatusRequest(PydanticBaseModel):
    status: str = Field(..., min_length=1)

    @model_validator(mode="after")
    def normalize_fields(self) -> Self:
        self.status = self.status.strip().lower()
        return self


class SwitchOrganizationRequest(PydanticBaseModel):
    organization_id: str

    @model_validator(mode="after")
    def normalize_fields(self) -> Self:
        self.organization_id = self.organization_id.strip()
        return self
