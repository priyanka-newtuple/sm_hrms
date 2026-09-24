"""Request models for invitation."""

from __future__ import annotations

from typing import Self

from pydantic import EmailStr, Field, model_validator

from common.data_model import BaseModel as PydanticBaseModel
from invitation.models.interface import validate_invitation_role


class InvitationCreateRequest(PydanticBaseModel):
    """Payload to send a new organization invitation."""

    email: EmailStr
    role: str = Field(..., min_length=1, max_length=32)


class InvitationAcceptRequest(PydanticBaseModel):
    """Payload to accept an invitation (public endpoint)."""

    token: str = Field(..., min_length=1)
    full_name: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, min_length=8)

    @model_validator(mode="after")
    def normalize_fields(self) -> Self:
        if self.full_name is not None:
            self.full_name = self.full_name.strip() or None
        return self
