"""User REST controller — user management endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any

from fastapi import APIRouter, Depends, Query, Request

from common.auth import (
    actor_str,
    build_actor_context,
    require_permission,
)
from common.deps import get_db
from common.logger import logger, tracer
from common.utils import raise_http_error
from user.models.request import SwitchOrganizationRequest, UpdateRoleRequest
from user.models.response import (
    UserOrganizationsResponse,
    UserResponse,
    UserSearchResult,
    UserStatsSummary,
)

if TYPE_CHECKING:
    from fastapi.params import Depends as DependsParam

    from auth.manager import AuthServiceManager
    from database.manager import DatabaseServiceManager
    from user.manager import UserServiceManager


AnyActor = Annotated[dict[str, object], Depends(build_actor_context)]
UserReadActor = Annotated[dict[str, object], Depends(require_permission("user", "read"))]
UserWriteActor = Annotated[dict[str, object], Depends(require_permission("user", "write"))]


class UserRestController:
    def __init__(
        self,
        user_service_manager: UserServiceManager,
        database_service_manager: DatabaseServiceManager | None = None,
        auth_service_manager: AuthServiceManager | None = None,
    ) -> None:
        _ = database_service_manager, auth_service_manager
        self.manager = user_service_manager

    @staticmethod
    def _route_dependencies(security: DependsParam | None) -> list[DependsParam] | None:
        return [security] if security else None

    @staticmethod
    def _error_context(request_id: str, operation: str) -> dict[str, str]:
        return {
            "request_id": request_id,
            "controller": "UserRestController",
            "operation": operation,
        }

    def prepare(self, app: APIRouter, security: DependsParam | None = None) -> None:
        route_dependencies = self._route_dependencies(security)

        # ── Me / Orgs ─────────────────────────────────────────────────────────

        @app.get(
            "/users/me/organizations",
            response_model=UserOrganizationsResponse,
            tags=["users"],
            dependencies=route_dependencies,
        )
        def get_my_organizations(
            request: Request,
            actor: AnyActor,
            db: Any = Depends(get_db),
        ) -> UserOrganizationsResponse:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("UserController.get_my_organizations"):
                try:
                    logger.info("user.get_my_organizations", extra={"request_id": request_id})
                    user_id = actor_str(actor, "user_id")
                    return self.manager.get_my_organizations_by_id(db, user_id, actor)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "get_my_organizations"))

        @app.post(
            "/users/me/organizations/switch",
            tags=["users"],
            dependencies=route_dependencies,
        )
        def switch_organization(
            request: Request,
            payload: SwitchOrganizationRequest,
            actor: AnyActor,
            db: Any = Depends(get_db),
        ) -> dict:
            """Switch the current user's active organization."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("UserController.switch_organization"):
                try:
                    logger.info("user.switch_organization", extra={"request_id": request_id})
                    user_id = actor_str(actor, "user_id")
                    current_user = self.manager.db_service.get_by_id(db, user_id)
                    if not current_user:
                        raise ValueError("User not found")
                    org_name, access_token = self.manager.switch_organization(
                        db, current_user, payload.organization_id
                    )
                    return {
                        "message": f"Switched to organization: {org_name}",
                        "access_token": access_token,
                        "token_type": "bearer",
                        "organization_id": payload.organization_id,
                        "organization_name": org_name,
                    }
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "switch_organization"))

        # ── Search ────────────────────────────────────────────────────────────

        @app.get(
            "/users/search",
            response_model=list[UserSearchResult],
            tags=["users"],
            dependencies=route_dependencies,
        )
        def search_users(
            request: Request,
            actor: UserReadActor,
            q: str = Query(..., min_length=1),
            limit: int = Query(10, le=50),
            db: Any = Depends(get_db),
        ) -> list[UserSearchResult]:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("UserController.search"):
                try:
                    logger.info("user.search", extra={"request_id": request_id})
                    org_id = actor_str(actor, "organization_id")
                    return self.manager.search_users(
                        db, query=q, organization_id=org_id, limit=limit
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "search"))

        # ── Stats ─────────────────────────────────────────────────────────────

        @app.get(
            "/users/stats/summary",
            response_model=UserStatsSummary,
            tags=["users"],
            dependencies=route_dependencies,
        )
        def get_stats(
            request: Request,
            actor: UserReadActor,
            db: Any = Depends(get_db),
        ) -> UserStatsSummary:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("UserController.stats"):
                try:
                    logger.info("user.stats", extra={"request_id": request_id})
                    org_id = actor_str(actor, "organization_id")
                    return self.manager.get_stats(db, org_id)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "stats"))

        # ── List ──────────────────────────────────────────────────────────────

        @app.get(
            "/users",
            response_model=list[UserResponse],
            tags=["users"],
            dependencies=route_dependencies,
        )
        def list_users(
            request: Request,
            actor: UserReadActor,
            status_filter: str | None = Query(None, alias="status"),
            limit: int = Query(50, ge=1, le=200),
            offset: int = Query(0, ge=0),
            db: Any = Depends(get_db),
        ) -> list[UserResponse]:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("UserController.list"):
                try:
                    logger.info("user.list", extra={"request_id": request_id})
                    org_id = actor_str(actor, "organization_id")
                    return self.manager.list_users(
                        db,
                        organization_id=org_id,
                        status=status_filter,
                        limit=limit,
                        offset=offset,
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "list"))

        @app.get(
            "/users/pending",
            response_model=list[UserResponse],
            tags=["users"],
            dependencies=route_dependencies,
        )
        def list_pending_users(
            request: Request,
            actor: UserReadActor,
            db: Any = Depends(get_db),
        ) -> list[UserResponse]:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("UserController.list_pending"):
                try:
                    logger.info("user.list_pending", extra={"request_id": request_id})
                    org_id = actor_str(actor, "organization_id")
                    return self.manager.list_pending(db, organization_id=org_id)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "list_pending"))

        @app.get(
            "/users/{user_id}",
            response_model=UserResponse,
            tags=["users"],
            dependencies=route_dependencies,
        )
        def get_user(
            request: Request,
            user_id: str,
            actor: UserWriteActor,
            db: Any = Depends(get_db),
        ) -> UserResponse:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("UserController.get"):
                try:
                    logger.info("user.get", extra={"request_id": request_id})
                    org_id = actor_str(actor, "organization_id")
                    return self.manager.get_user(db, user_id, organization_id=org_id)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "get"))

        # ── Approve / Reject ──────────────────────────────────────────────────

        @app.post(
            "/users/{user_id}/approve",
            response_model=UserResponse,
            tags=["users"],
            dependencies=route_dependencies,
        )
        def approve_user(
            request: Request,
            user_id: str,
            actor: UserWriteActor,
            db: Any = Depends(get_db),
        ) -> UserResponse:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("UserController.approve"):
                try:
                    logger.info("user.approve", extra={"request_id": request_id})
                    org_id = actor_str(actor, "organization_id")
                    return self.manager.approve_user(db, user_id, organization_id=org_id)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "approve"))

        @app.post(
            "/users/{user_id}/reject",
            response_model=UserResponse,
            tags=["users"],
            dependencies=route_dependencies,
        )
        def reject_user(
            request: Request,
            user_id: str,
            actor: UserWriteActor,
            db: Any = Depends(get_db),
        ) -> UserResponse:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("UserController.reject"):
                try:
                    logger.info("user.reject", extra={"request_id": request_id})
                    org_id = actor_str(actor, "organization_id")
                    return self.manager.reject_user(db, user_id, organization_id=org_id)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "reject"))

        # ── Suspend / Reactivate ──────────────────────────────────────────────

        @app.post(
            "/users/{user_id}/suspend",
            response_model=UserResponse,
            tags=["users"],
            dependencies=route_dependencies,
        )
        def suspend_user(
            request: Request,
            user_id: str,
            actor: UserWriteActor,
            db: Any = Depends(get_db),
        ) -> UserResponse:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("UserController.suspend"):
                try:
                    logger.info("user.suspend", extra={"request_id": request_id})
                    actor_user_id = actor_str(actor, "user_id")
                    org_id = actor_str(actor, "organization_id")
                    return self.manager.suspend_user(db, user_id, actor_user_id, organization_id=org_id)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "suspend"))

        @app.post(
            "/users/{user_id}/reactivate",
            response_model=UserResponse,
            tags=["users"],
            dependencies=route_dependencies,
        )
        def reactivate_user(
            request: Request,
            user_id: str,
            actor: UserWriteActor,
            db: Any = Depends(get_db),
        ) -> UserResponse:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("UserController.reactivate"):
                try:
                    logger.info("user.reactivate", extra={"request_id": request_id})
                    org_id = actor_str(actor, "organization_id")
                    return self.manager.reactivate_user(db, user_id, organization_id=org_id)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "reactivate"))

        # ── Update role ───────────────────────────────────────────────────────

        @app.put(
            "/users/{user_id}/role",
            response_model=UserResponse,
            tags=["users"],
            dependencies=route_dependencies,
        )
        def update_role(
            request: Request,
            user_id: str,
            payload: UpdateRoleRequest,
            actor: UserWriteActor,
            db: Any = Depends(get_db),
        ) -> UserResponse:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("UserController.update_role"):
                try:
                    logger.info("user.update_role", extra={"request_id": request_id})
                    org_id = actor_str(actor, "organization_id")
                    caller_user_id = actor_str(actor, "user_id")
                    return self.manager.update_role(
                        db, user_id, payload.role, organization_id=org_id, caller_user_id=caller_user_id
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "update_role"))
