"""Organizations REST controller module."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, status

from common.auth import (
    actor_str,
    build_actor_context,
    require_permission,
    require_platform_permission,
)
from common.deps import get_db
from common.logger import logger, tracer
from common.utils import raise_http_error
from exceptions import NotFoundError, ValidationError

from auth.db_models import DEFAULT_ORG_ID, PLATFORM_ORG_ID
from organizations.models.request import (
    BrandingUpdate,
    OrgNameUpdate,
    OrganizationCreate,
    OrganizationUpdate,
    PlatformUserCreate,
)
from organizations.models.response import (
    OrganizationListResponse,
    OrganizationRead,
    OrganizationUserListResponse,
    PendingOrganizationListResponse,
    ProvisionResult,
    ProvisionStatus,
)
from user.models.response import UserRead

if TYPE_CHECKING:
    from fastapi.params import Depends as DependsParam

    from auth.manager import AuthServiceManager
    from database.manager import DatabaseServiceManager
    from organizations.manager import OrganizationsServiceManager
    from roles.manager import RolesServiceManager


AnyActor = Annotated[dict[str, object], Depends(build_actor_context)]

# Platform-wide actions (span organizations) — authorized against the
# caller's role within the dedicated platform organization, never against
# the caller's own organization_id. A tenant org's own "superadmin" role
# (any org can grant this to any of its own users) must never satisfy these.
PlatformOrgCreateActor = Annotated[dict[str, object], Depends(require_platform_permission("platform_organization", "create"))]
PlatformOrgReadActor = Annotated[dict[str, object], Depends(require_platform_permission("platform_organization", "read"))]
PlatformOrgWriteActor = Annotated[dict[str, object], Depends(require_platform_permission("platform_organization", "write"))]
PlatformOrgApproveActor = Annotated[dict[str, object], Depends(require_platform_permission("platform_organization", "approve"))]
PlatformOrgRejectActor = Annotated[dict[str, object], Depends(require_platform_permission("platform_organization", "reject"))]
PlatformOrgDeleteActor = Annotated[dict[str, object], Depends(require_platform_permission("platform_organization", "delete"))]
PlatformOrgProvisionActor = Annotated[dict[str, object], Depends(require_platform_permission("platform_organization", "provision"))]
PlatformUserReadActor = Annotated[dict[str, object], Depends(require_platform_permission("platform_user", "read"))]
PlatformUserWriteActor = Annotated[dict[str, object], Depends(require_platform_permission("platform_user", "write"))]

# Tenant-scoped actions — authorized against the caller's own organization_id.
BrandingActor = Annotated[dict[str, object], Depends(require_permission("organization", "branding"))]
RenameActor = Annotated[dict[str, object], Depends(require_permission("organization", "rename"))]


class OrganizationsRestController:
    """Organizations REST controller — current organization endpoint."""

    def __init__(
        self,
        organizations_service_manager: OrganizationsServiceManager,
        database_service_manager: DatabaseServiceManager | None = None,
        auth_service_manager: AuthServiceManager | None = None,
        roles_service_manager: RolesServiceManager | None = None,
    ) -> None:
        _ = database_service_manager, auth_service_manager
        self.manager = organizations_service_manager
        self.roles_manager = roles_service_manager

    @staticmethod
    def _route_dependencies(security: DependsParam | None) -> list[DependsParam] | None:
        return [security] if security else None

    @staticmethod
    def _error_context(request_id: str, operation: str) -> dict[str, str]:
        return {
            "request_id": request_id,
            "controller": "OrganizationsRestController",
            "operation": operation,
        }

    def prepare(self, app: APIRouter, security: DependsParam | None = None) -> None:
        """Register all organization routes on the given router."""
        route_dependencies = self._route_dependencies(security)

        @app.post(
            "/organizations",
            response_model=OrganizationRead,
            status_code=status.HTTP_201_CREATED,
            tags=["organizations"],
            dependencies=route_dependencies,
        )
        def create_organization(
            request: Request,
            payload: OrganizationCreate,
            actor: PlatformOrgCreateActor,
            db: Any = Depends(get_db),
        ) -> OrganizationRead:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("OrganizationsController.create"):
                try:
                    logger.info("organizations.create", extra={"request_id": request_id})
                    return self.manager.create_organization(
                        db,
                        name=payload.name,
                        slug=payload.slug,
                        domain=payload.domain,
                        settings=payload.settings,
                        logo_url=payload.logo_url,
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "create"))

        @app.get(
            "/organizations",
            response_model=OrganizationListResponse,
            tags=["organizations"],
            dependencies=route_dependencies,
        )
        def list_organizations(
            request: Request,
            actor: PlatformOrgReadActor,
            status_filter: str | None = Query(default=None, alias="status"),
            limit: int = Query(default=100, ge=1, le=1000),
            offset: int = Query(default=0, ge=0),
            db: Any = Depends(get_db),
        ) -> OrganizationListResponse:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("OrganizationsController.list"):
                try:
                    logger.info("organizations.list", extra={"request_id": request_id})
                    return self.manager.list_organizations(
                        db,
                        status=status_filter,
                        limit=limit,
                        offset=offset,
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "list"))

        @app.get(
            "/organizations/current",
            response_model=OrganizationRead,
            tags=["organizations"],
            dependencies=route_dependencies,
        )
        def get_current_organization(
            request: Request,
            actor: AnyActor,
            db: Any = Depends(get_db),
        ) -> OrganizationRead:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("OrganizationsController.current"):
                try:
                    logger.info("organizations.current", extra={"request_id": request_id})
                    org_id = actor_str(actor, "organization_id")
                    if not org_id:
                        raise NotFoundError("User has no organization")
                    return self.manager.get_current(db, org_id)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "current"))

        @app.put(
            "/organizations/current/branding",
            response_model=OrganizationRead,
            tags=["organizations"],
            dependencies=route_dependencies,
        )
        def update_current_branding(
            request: Request,
            payload: BrandingUpdate,
            actor: BrandingActor,
            db: Any = Depends(get_db),
        ) -> OrganizationRead:
            # Org admins/owners may update only their own organization's
            # appearance (theme settings + logo). The org is taken from the
            # actor's context, never the request body, so this cannot reach
            # another tenant, and only branding fields are forwarded.
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("OrganizationsController.update_branding"):
                try:
                    logger.info("organizations.update_branding", extra={"request_id": request_id})
                    org_id = actor_str(actor, "organization_id")
                    if not org_id:
                        raise NotFoundError("User has no organization")
                    return self.manager.update_organization(
                        db,
                        org_id,
                        settings=payload.settings,
                        logo_url=payload.logo_url,
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "update_branding"))

        @app.put(
            "/organizations/current/name",
            response_model=OrganizationRead,
            tags=["organizations"],
            dependencies=route_dependencies,
        )
        def rename_current_organization(
            request: Request,
            payload: OrgNameUpdate,
            actor: RenameActor,
            db: Any = Depends(get_db),
        ) -> OrganizationRead:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("OrganizationsController.rename_current"):
                try:
                    logger.info("organizations.rename_current", extra={"request_id": request_id})
                    org_id = actor_str(actor, "organization_id")
                    if not org_id:
                        raise NotFoundError("User has no organization")
                    return self.manager.rename_current_org(db, org_id, name=payload.name)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "rename_current"))

        @app.get(
            "/organizations/pending",
            response_model=PendingOrganizationListResponse,
            tags=["organizations"],
            dependencies=route_dependencies,
        )
        def list_pending_organizations(
            request: Request,
            actor: PlatformOrgReadActor,
            limit: int = Query(default=100, ge=1, le=1000),
            offset: int = Query(default=0, ge=0),
            db: Any = Depends(get_db),
        ) -> PendingOrganizationListResponse:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("OrganizationsController.pending"):
                try:
                    logger.info("organizations.list_pending", extra={"request_id": request_id})
                    return self.manager.list_pending(db, limit=limit, offset=offset)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "list_pending"))

        @app.get(
            "/organizations/{org_id}",
            response_model=OrganizationRead,
            tags=["organizations"],
            dependencies=route_dependencies,
        )
        def get_organization(
            request: Request,
            org_id: str,
            actor: PlatformOrgReadActor,
            db: Any = Depends(get_db),
        ) -> OrganizationRead:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("OrganizationsController.get"):
                try:
                    logger.info("organizations.get", extra={"request_id": request_id})
                    return self.manager.get_organization(db, org_id)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "get"))

        @app.put(
            "/organizations/{org_id}",
            response_model=OrganizationRead,
            tags=["organizations"],
            dependencies=route_dependencies,
        )
        def update_organization(
            request: Request,
            org_id: str,
            payload: OrganizationUpdate,
            actor: PlatformOrgWriteActor,
            db: Any = Depends(get_db),
        ) -> OrganizationRead:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("OrganizationsController.update"):
                try:
                    logger.info("organizations.update", extra={"request_id": request_id})
                    return self.manager.update_organization(
                        db,
                        org_id,
                        name=payload.name,
                        domain=payload.domain,
                        settings=payload.settings,
                        logo_url=payload.logo_url,
                        status=payload.status,
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "update"))

        @app.post(
            "/organizations/{org_id}/approve",
            response_model=OrganizationRead,
            tags=["organizations"],
            dependencies=route_dependencies,
        )
        def approve_organization(
            request: Request,
            org_id: str,
            actor: PlatformOrgApproveActor,
            db: Any = Depends(get_db),
        ) -> OrganizationRead:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("OrganizationsController.approve"):
                try:
                    logger.info("organizations.approve", extra={"request_id": request_id})
                    return self.manager.approve_organization(db, org_id)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "approve"))

        @app.post(
            "/organizations/{org_id}/reject",
            response_model=OrganizationRead,
            tags=["organizations"],
            dependencies=route_dependencies,
        )
        def reject_organization(
            request: Request,
            org_id: str,
            actor: PlatformOrgRejectActor,
            db: Any = Depends(get_db),
        ) -> OrganizationRead:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("OrganizationsController.reject"):
                try:
                    logger.info("organizations.reject", extra={"request_id": request_id})
                    return self.manager.reject_organization(db, org_id)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "reject"))

        @app.delete(
            "/organizations/{org_id}",
            status_code=status.HTTP_204_NO_CONTENT,
            tags=["organizations"],
            dependencies=route_dependencies,
        )
        def delete_organization(
            request: Request,
            org_id: str,
            actor: PlatformOrgDeleteActor,
            db: Any = Depends(get_db),
        ) -> None:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("OrganizationsController.delete"):
                try:
                    logger.info("organizations.delete", extra={"request_id": request_id})
                    protected = {PLATFORM_ORG_ID, DEFAULT_ORG_ID}
                    self.manager.delete_organization(db, org_id, protected_ids=protected)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "delete"))

        @app.post(
            "/organizations/{org_id}/provision",
            response_model=ProvisionResult,
            tags=["organizations"],
            dependencies=route_dependencies,
        )
        def provision_organization(
            request: Request,
            org_id: str,
            actor: PlatformOrgProvisionActor,
            create_sample_job: bool = Query(default=False),
            db: Any = Depends(get_db),
        ) -> ProvisionResult:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("OrganizationsController.provision"):
                try:
                    logger.info("organizations.provision", extra={"request_id": request_id})
                    return self.manager.provision_tenant(
                        db,
                        org_id=org_id,
                        create_sample_job=create_sample_job,
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "provision"))

        @app.get(
            "/organizations/{org_id}/provision-status",
            response_model=ProvisionStatus,
            tags=["organizations"],
            dependencies=route_dependencies,
        )
        def get_provision_status(
            request: Request,
            org_id: str,
            actor: PlatformOrgReadActor,
            db: Any = Depends(get_db),
        ) -> ProvisionStatus:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("OrganizationsController.provision_status"):
                try:
                    logger.info("organizations.provision_status", extra={"request_id": request_id})
                    return self.manager.get_provision_status(db, org_id=org_id)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "provision_status"))

        @app.get(
            "/organizations/{org_id}/users",
            response_model=OrganizationUserListResponse,
            tags=["organizations"],
            dependencies=route_dependencies,
        )
        def list_organization_users(
            request: Request,
            org_id: str,
            actor: PlatformUserReadActor,
            status_filter: str | None = Query(default=None, alias="status"),
            limit: int = Query(default=100, ge=1, le=1000),
            offset: int = Query(default=0, ge=0),
            db: Any = Depends(get_db),
        ) -> OrganizationUserListResponse:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("OrganizationsController.list_users"):
                try:
                    logger.info("organizations.list_users", extra={"request_id": request_id})
                    return self.manager.list_org_users(
                        db,
                        org_id=org_id,
                        status_filter=status_filter,
                        limit=limit,
                        offset=offset,
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "list_users"))

        @app.post(
            "/organizations/{org_id}/users",
            response_model=UserRead,
            status_code=status.HTTP_201_CREATED,
            tags=["organizations"],
            dependencies=route_dependencies,
        )
        def create_organization_user(
            request: Request,
            org_id: str,
            payload: PlatformUserCreate,
            actor: PlatformUserWriteActor,
            db: Any = Depends(get_db),
        ) -> UserRead:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("OrganizationsController.create_user"):
                try:
                    logger.info("organizations.create_user", extra={"request_id": request_id})
                    return self.manager.create_org_user(db, org_id=org_id, payload=payload)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "create_user"))

        @app.delete(
            "/organizations/{org_id}/users/{user_id}",
            status_code=status.HTTP_204_NO_CONTENT,
            tags=["organizations"],
            dependencies=route_dependencies,
        )
        def delete_organization_user(
            request: Request,
            org_id: str,
            user_id: str,
            actor: PlatformUserWriteActor,
            db: Any = Depends(get_db),
        ) -> None:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("OrganizationsController.delete_user"):
                try:
                    logger.info("organizations.delete_user", extra={"request_id": request_id})
                    actor_user_id = actor_str(actor, "user_id")
                    if actor_user_id and actor_user_id == str(user_id):
                        raise ValidationError("Cannot delete yourself")
                    self.manager.delete_org_user(db, org_id=org_id, user_id=user_id)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "delete_user"))
