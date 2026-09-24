"""Interface models and contracts for the auth module."""

from __future__ import annotations

from typing import Protocol, Self

from pydantic import Field, model_validator

from common.data_model import BaseModel as PydanticBaseModel
from common.utils import ensure_non_empty

INVITE_PENDING_MESSAGE = "Invite has already been sent"


class ActorContext(PydanticBaseModel):
    """Identity and tenancy context for permission checks."""

    user_id: str = Field(..., min_length=1)
    organization_id: str = Field(..., min_length=1)
    roles: list[str] = Field(default_factory=list)
    request_id: str | None = None

    @model_validator(mode="after")
    def validate_actor(self) -> Self:
        self.user_id = ensure_non_empty(str(self.user_id), "user_id")
        self.organization_id = ensure_non_empty(str(self.organization_id), "organization_id")
        self.roles = [str(role).strip() for role in (self.roles or []) if str(role).strip()]
        self.request_id = str(self.request_id).strip() if self.request_id else None
        return self

    def normalized_roles(self) -> set[str]:
        return {role.lower() for role in self.roles if role.strip()}


class PermissionSpec(PydanticBaseModel):
    """Permission key evaluated against actor roles."""

    resource: str = Field(..., min_length=1)
    action: str = Field(..., min_length=1)
    requires_org_scope: bool = True

    @model_validator(mode="after")
    def validate_permission(self) -> Self:
        self.resource = ensure_non_empty(str(self.resource), "resource")
        self.action = ensure_non_empty(str(self.action), "action")
        return self

    def key(self) -> str:
        return f"{self.resource}:{self.action}"


class AccessDecision(PydanticBaseModel):
    """Result of a permission check."""

    allowed: bool
    reason: str | None = None
    matched_roles: tuple[str, ...] = ()


class IdentityAccessEvaluator(Protocol):
    """Minimal manager contract for authorization decisions."""

    def evaluate(self, actor: ActorContext, permission: PermissionSpec) -> AccessDecision:
        """Return access decision for actor/permission pair."""
        ...


class TenantGuard(Protocol):
    """Contract for tenancy boundary checks."""

    def validate_actor_org(
        self, actor: ActorContext, organization_id: str | None
    ) -> AccessDecision:
        """Return decision for actor organization scope."""
        ...
