"""Shared actor-context dependency helpers for modular backend controllers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional, Protocol

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session

from common.configuration import get_configuration
from common.deps import get_db
from common.enums import DefaultRole
from common.logger import logger
from common.security import decode_token

if TYPE_CHECKING:
    from collections.abc import Callable

_bearer_scheme = HTTPBearer(auto_error=False)

# Injected by main.py after roles module is wired — used by require_permission
_roles_db_service: Any = None

class MembershipStatusChecker(Protocol):
    """Reports whether a user's membership in an organization is currently active."""

    def is_membership_active(self, db: Session, user_id: str, org_id: str) -> bool:
        ...


# Injected by main.py after the user module is wired — used by require_permission
# to enforce per-org membership status (a suspended membership must be denied).
_membership_db_service: MembershipStatusChecker | None = None


def register_roles_db_service(service: Any) -> None:
    """Register the RolesModelService instance for use in require_permission."""
    global _roles_db_service
    _roles_db_service = service


def register_membership_db_service(service: MembershipStatusChecker) -> None:
    """Set the membership checker that `require_permission` uses to enforce per-org access."""
    global _membership_db_service
    _membership_db_service = service


def _auth_bypass_enabled() -> bool:
    raw = get_configuration().auth_configuration.bypass_auth
    if raw is None:
        return False
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _build_bypass_actor(request: Request) -> dict[str, object]:
    """Build the `BYPASS_AUTH` dev-convenience actor, optionally overridden via headers.

    Explicit, env-gated local-dev path only — never reached unless
    `BYPASS_AUTH` is deliberately enabled. Left functionally unchanged by the
    header-trust removal in `_build_token_actor`.
    """
    user_id = (request.headers.get("x-user-id") or "").strip()
    organization_id = (request.headers.get("x-org-id") or "").strip()
    roles_header = request.headers.get("x-user-roles") or ""
    actor_roles = [token.strip().lower() for token in roles_header.split(",") if token.strip()]
    return {
        "user_id": user_id or "modular-dev-user",
        "organization_id": organization_id or "11111111-1111-1111-1111-111111111111",
        "roles": actor_roles or [DefaultRole.ADMIN.value],
        "request_id": getattr(request.state, "request_id", None),
    }


def _build_token_actor(request: Request) -> dict[str, object]:
    """Build the actor from a verified `Authorization: Bearer` token; 401 if missing/invalid.

    A missing `roles` claim defaults to `[]` rather than rejecting the token —
    `create_access_token` omits it when a user has no roles yet, which is a
    valid identity; what that actor can *do* is decided later, live, by
    `require_permission`/`require_platform_permission`.
    """
    auth_header = (request.headers.get("authorization") or "").strip()
    if auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
        if token:
            payload = decode_token(token)
            if payload and payload.get("type") == "access":
                token_user_id = (payload.get("sub") or "").strip()
                token_org_id = (payload.get("organization_id") or "").strip()
                token_roles = payload.get("roles") if isinstance(payload, dict) else None
                if token_roles is None:
                    token_roles = []
                if token_user_id and token_org_id and isinstance(token_roles, list):
                    roles = [str(r).strip().lower() for r in token_roles if str(r).strip()]
                    return {
                        "user_id": token_user_id,
                        "organization_id": token_org_id,
                        "roles": roles,
                        "request_id": getattr(request.state, "request_id", None),
                    }

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing or invalid access token",
    )


def build_actor_context(
    request: Request, _: None = Depends(_bearer_scheme)
) -> dict[str, object]:
    """Build actor context from a cryptographically verified access token.

    Thin dispatcher — see `_build_bypass_actor` (dev-only) and
    `_build_token_actor` (the real, security-relevant path) for the actual
    identity-resolution logic.

    The `_bearer_scheme` dependency is unused at runtime (the token is read from
    the request headers) but registers the HTTPBearer security scheme in OpenAPI,
    so Swagger shows the lock and sends the Authorization header on these routes.
    """
    if _auth_bypass_enabled():
        return _build_bypass_actor(request)
    return _build_token_actor(request)


def get_current_actor_with_roles(
    roles: list[str] | None = None,
) -> Callable[[Request], dict[str, object]]:
    """Create an actor dependency with optional role filtering."""

    required_roles = {str(role).strip().lower() for role in (roles or []) if str(role).strip()}

    def dep(request: Request, _: None = Depends(_bearer_scheme)) -> dict[str, object]:
        actor = build_actor_context(request)
        if required_roles:
            actor_roles = set(actor["roles"])  # type: ignore[arg-type]
            if actor_roles.isdisjoint(required_roles):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        return actor

    return dep


READ_ALLOWED_ROLES = [
    DefaultRole.SUPERADMIN.value,
    DefaultRole.VIEWER.value,
    DefaultRole.ADMIN.value,
    DefaultRole.OWNER.value,
]
WRITE_ALLOWED_ROLES = [
    DefaultRole.SUPERADMIN.value,
    DefaultRole.RECRUITER.value,
    DefaultRole.ADMIN.value,
    DefaultRole.OWNER.value,
]
ADMIN_ALLOWED_ROLES = [
    DefaultRole.SUPERADMIN.value,
    DefaultRole.ADMIN.value,
    DefaultRole.OWNER.value,
]
SUPERADMIN_ALLOWED_ROLES = [DefaultRole.SUPERADMIN.value]


def read_actor_dependency():
    return Depends(get_current_actor_with_roles(READ_ALLOWED_ROLES))


def write_actor_dependency():
    return Depends(get_current_actor_with_roles(WRITE_ALLOWED_ROLES))


def admin_actor_dependency():
    return Depends(get_current_actor_with_roles(ADMIN_ALLOWED_ROLES))


def actor_str(actor: dict[str, object], key: str, default: str = "") -> str:
    """Safely extract a stripped string field from an actor dict."""
    return str(actor.get(key) or default).strip()


def build_system_actor(organization_id: str, source: str = "system") -> dict[str, object]:
    """Build a system actor context for background workers, agents, and schedulers.

    Pass the returned dict as the `actor` argument to any `_for_actor` method.
    The `source` field distinguishes caller origin in the audit log without
    changing the actor model — use "worker", "agent", or "scheduler".
    """
    return {
        "user_id": None,
        "organization_id": organization_id,
        "roles": ["system"],
        "actor_type": "system",
        "actor_name": "System",
        "actor_role": "SYSTEM",
        "source": source,
    }


def _require_roles_service_ready(
    permission_key: str,
    actor: dict[str, object],
    organization_id: str,
    db: Optional[Session],
) -> None:
    """Raise 503 if the DB-backed permission check cannot be evaluated.

    A permission that can't be evaluated must deny access, not grant it —
    the previous behavior (silently allowing the request through) meant an
    unavailable roles service or DB session fully bypassed authorization.
    """
    if _roles_db_service is None or db is None:
        logger.warning(
            "Permission check unavailable: roles service or DB session not ready (%s)",
            permission_key,
            extra={"user_id": actor.get("user_id"), "organization_id": organization_id, "permission_key": permission_key},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Permission service unavailable",
        )


def _require_active_membership(
    permission_key: str,
    user_id: str,
    organization_id: str,
    db: Optional[Session],
) -> None:
    """Raise 403 if the user's membership in this organization is not active
    (e.g. suspended), or 503 if the check cannot be performed."""
    if _auth_bypass_enabled():
        # Dev bypass synthesizes the actor (no real membership row); skip the check.
        return
    if _membership_db_service is None or db is None:
        logger.warning(
            "Membership check unavailable: user service or DB session not ready (%s)",
            permission_key,
            extra={"user_id": user_id, "organization_id": organization_id, "permission_key": permission_key},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Permission service unavailable",
        )
    if not _membership_db_service.is_membership_active(db, user_id, organization_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your access to this organization is suspended",
        )


def require_permission(resource: str, action: str) -> Callable:
    """Create a FastAPI dependency that checks a DB-backed permission within the caller's own org.

    Usage:
        actor: Annotated[dict, Depends(require_permission("role", "write"))]

    Fails closed (`503`) if the roles service or DB session is unavailable —
    an unevaluable permission must never be treated as a granted one.
    """
    permission_key = f"{resource}:{action}"

    def dep(
        request: Request,
        db: Optional[Session] = Depends(get_db),
        _: None = Depends(_bearer_scheme),
    ) -> dict[str, object]:
        """Authenticate actor and verify a DB permission scoped to their own organization."""
        actor = build_actor_context(request)
        organization_id = str(actor.get("organization_id") or "")
        user_id = str(actor.get("user_id") or "")
        _require_roles_service_ready(permission_key, actor, organization_id, db)
        _require_active_membership(permission_key, user_id, organization_id, db)

        result = _roles_db_service.check_permission(
            db,
            user_id,
            organization_id,
            permission_key,
        )
        if not result.allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=result.reason,
            )
        return actor

    return dep


def require_platform_permission(resource: str, action: str) -> Callable:
    """Create a FastAPI dependency that checks a DB-backed permission within the platform organization.

    Like `require_permission`, but checked against `PLATFORM_ORG_ID` instead
    of the caller's own org, and requires the `superadmin` role there
    specifically (see Misc Project Conventions in `jarvis_map.md` for why the
    permission check alone isn't enough). Fails closed (`503`) if the roles
    service or DB session is unavailable.

    Usage:
        actor: Annotated[dict, Depends(require_platform_permission("platform_organization", "delete"))]
    """
    permission_key = f"{resource}:{action}"
    platform_org_id = get_configuration().auth_configuration.platform_org_id

    def dep(
        request: Request,
        db: Optional[Session] = Depends(get_db),
        _: None = Depends(_bearer_scheme),
    ) -> dict[str, object]:
        """Authenticate actor and verify the platform superadmin role and permission."""
        actor = build_actor_context(request)
        user_id = str(actor.get("user_id") or "")
        _require_roles_service_ready(permission_key, actor, platform_org_id, db)
        _require_active_membership(permission_key, user_id, platform_org_id, db)

        platform_roles = _roles_db_service.get_user_roles_with_permissions(
            db, user_id, platform_org_id
        )
        if not any(role.name == DefaultRole.SUPERADMIN.value for role in platform_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Requires the platform superadmin role",
            )

        result = _roles_db_service.check_permission(
            db,
            user_id,
            platform_org_id,
            permission_key,
        )
        if not result.allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=result.reason,
            )
        return actor

    return dep
