"""Request schemas for the auth module."""

from __future__ import annotations

from typing import Self

from pydantic import EmailStr, Field, model_validator

from auth.models.interface import ActorContext
from common.data_model import BaseModel as PydanticBaseModel
from common.utils import ensure_non_empty


class UserLogin(PydanticBaseModel):
    email: EmailStr
    password: str


class TokenRefresh(PydanticBaseModel):
    refresh_token: str


class GoogleAuthCallback(PydanticBaseModel):
    code: str
    redirect_uri: str | None = None


class MicrosoftAuthCallback(PydanticBaseModel):
    code: str
    state: str
    redirect_uri: str | None = None


class MicrosoftIdTokenLogin(PydanticBaseModel):
    """Login using a Microsoft ID token obtained elsewhere (e.g. a client
    app's own, already-completed Microsoft sign-in) instead of running our
    own separate authorization-code round trip."""

    id_token: str


class ForgotPasswordRequest(PydanticBaseModel):
    email: EmailStr


class ResetPasswordRequest(PydanticBaseModel):
    token: str
    new_password: str = Field(..., min_length=8)


class AccessCheckRequest(PydanticBaseModel):
    actor: ActorContext
    resource: str = Field(..., min_length=1)
    action: str = Field(..., min_length=1)
    organization_id: str | None = None

    @model_validator(mode="after")
    def normalize_fields(self) -> Self:
        self.resource = ensure_non_empty(str(self.resource), "resource")
        self.action = ensure_non_empty(str(self.action), "action")
        self.organization_id = str(self.organization_id).strip() if self.organization_id else None
        return self
