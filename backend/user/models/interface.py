"""Interface models and contracts for the user module."""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import ConfigDict

from common.data_model import BaseModel as PydanticBaseModel, ExtendedStrEnum


class UserContract(PydanticBaseModel):
    """Frozen snapshot of a user — safe to pass across module boundaries."""

    model_config = ConfigDict(frozen=True, from_attributes=True)

    id: str
    email: str
    full_name: str
    role: str
    status: str
    organization_id: str | None = None
    avatar_url: str | None = None


class OrgMembershipVerdict(ExtendedStrEnum):
    """Why a user may or may not be assigned work in a given organization.

    The user module decides the verdict; each consuming module phrases its own
    client-facing rejection, since the wording belongs to the endpoint the
    caller actually hit, not to user management.
    """

    ASSIGNABLE = "assignable"
    NOT_FOUND = "not_found"
    NOT_A_MEMBER = "not_a_member"
    # Per-org suspension: `user_organizations.status = 'suspended'`. This is the
    # only place suspension lives — `users.status` cannot hold it.
    SUSPENDED = "suspended"
    # Account lifecycle: `users.status` is 'pending' or 'rejected'. Kept distinct
    # from SUSPENDED so callers do not tell a never-approved user they were
    # suspended.
    INACTIVE_ACCOUNT = "inactive_account"


class OrgMemberAssignability(PydanticBaseModel):
    """Whether one user can be handed work in one organization.

    `full_name` is populated whenever the user row exists, so a caller can name
    the person in a rejection without a second lookup.
    """

    model_config = ConfigDict(frozen=True)

    user_id: str
    full_name: str
    verdict: OrgMembershipVerdict

    @property
    def is_assignable(self) -> bool:
        """True only when both the account and its org membership are active."""
        return self.verdict is OrgMembershipVerdict.ASSIGNABLE


class UserLookupService(Protocol):
    def get_by_id(self, db: Any, user_id: str) -> Any | None: ...


def validate_user_email(email: str) -> str:
    normalized = email.strip().lower()
    if not normalized:
        raise ValueError("email must be a non-empty string")
    return normalized


def validate_user_name(name: str) -> str:
    normalized = name.strip()
    if not normalized:
        raise ValueError("full_name must be a non-empty string")
    return normalized
