"""Response schemas for invitation."""

from __future__ import annotations

from datetime import datetime

from common.data_model import BaseModel as PydanticBaseModel


class InvitationResponse(PydanticBaseModel):
    """Full invitation details returned from management endpoints."""

    id: str
    organization_id: str
    email: str
    role: str
    status: str
    invited_by_user_id: str | None = None
    expires_at: datetime | None = None
    accepted_at: datetime | None = None
    created_at: datetime
    token:str


class InvitationValidationResponse(PydanticBaseModel):
    """Response for the public validate-token endpoint."""

    valid: bool
    error: str | None = None
    email: str | None = None
    role: str | None = None
    organization_name: str | None = None
    expires_at: str | None = None
    user_exists: bool = False


class AcceptInvitationResponse(PydanticBaseModel):
    """Response after successfully accepting an invitation."""

    message: str
    user_id: str
    already_member: bool = False
