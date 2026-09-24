"""Interface models and contracts for the invitation module."""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import ConfigDict

from common.data_model import BaseModel as PydanticBaseModel
from user.db_models import UserRole


class InvitationContract(PydanticBaseModel):
    """Frozen snapshot of an invitation — safe to pass across module boundaries."""

    model_config = ConfigDict(frozen=True, from_attributes=True)

    id: str
    organization_id: str
    email: str
    role: str
    status: str
    token: str


class InvitationLookupService(Protocol):
    """Read-only lookup contract for invitation records."""

    def get_by_token(self, db: Any, token: str) -> Any | None: ...
    def get_by_id(self, db: Any, invitation_id: str) -> Any | None: ...


def validate_invitation_role(role: str) -> str:
    normalized = role.strip().lower()
    if not normalized:
        raise ValueError("role must be a non-empty string")
    valid_roles = {r.value for r in UserRole}
    if normalized not in valid_roles:
        raise ValueError(
            f"Invalid role '{normalized}'. Must be one of: {', '.join(sorted(valid_roles))}"
        )
    return normalized
