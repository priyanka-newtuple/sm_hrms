"""Roles REST controller module."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from common.auth import actor_str, build_actor_context, require_permission
from common.deps import get_db
from common.logger import logger, tracer
from exceptions import (
    NotFoundError,
    PersistenceError,
    ServiceError,
    ValidationError,
)
from roles.manager import RolesServiceManager
from roles.models.request import RoleCreateRequest, RoleDuplicateRequest, RoleUpdateRequest, UserRoleSetRequest
from roles.models.response import PermissionsSummary, RoleListItem, RoleRead, UserRoleRead


AnyActor = Annotated[dict[str, object], Depends(build_actor_context)]
ReadActor = Annotated[dict[str, object], Depends(require_permission("role", "read"))]
AdminActor = Annotated[dict[str, object], Depends(require_permission("role", "write"))]
UserReadActor = Annotated[dict[str, object], Depends(require_permission("user", "read"))]
UserWriteActor = Annotated[dict[str, object], Depends(require_permission("user", "write"))]


class RolesRestController:
    """Roles REST controller — RBAC role management and assignment endpoints."""

    def __init__(
        self,
        roles_service_manager: RolesServiceManager,
        database_service_manager: Any = None,
        auth_service_manager: Any = None,
    ) -> None:
        """Description:
            Initialize the roles REST controller and bind the roles manager dependency.

        Args:
            roles_service_manager: Roles service manager instance (business orchestration layer).
            database_service_manager: Unused legacy/wiring parameter (kept for consistency with other modules).
            auth_service_manager: Unused legacy/wiring parameter (kept for consistency with other modules).

        Returns:
            None

        Raises:
            None
        """
        super().__init__()
        _ = database_service_manager, auth_service_manager
        self.manager = roles_service_manager

    def prepare(self, app: APIRouter) -> None:
        """Description:
            Register roles routes on the provided FastAPI router.

        Args:
            app: FastAPI router to attach routes to.

        Returns:
            None

        Raises:
            None
        """
        roles_router = APIRouter(prefix="/roles", tags=["roles"])

        # --- Role CRUD ---

        @roles_router.get("", response_model=list[RoleListItem])
        def list_roles(actor: ReadActor, db: Any = Depends(get_db)) -> list[RoleListItem]:
            """Description:
                List all roles for the current organization.

            Args:
                actor: Current authenticated actor (must have one of READ_ALLOWED_ROLES).
                db: SQLAlchemy session (FastAPI dependency).

            Returns:
                List of roles available in the organization.

            Raises:
                HTTPException: 500 when persistence/service errors occur.
            """
            org_id = actor_str(actor, "organization_id")
            try:
                with tracer.start_as_current_span("roles.list"):
                    return self.manager.list_roles(db, org_id)
            except (PersistenceError, ServiceError) as exc:
                logger.exception(f"roles.list failed (org_id={org_id}): {exc}")
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
            except Exception as exc:
                logger.exception(f"roles.list unexpected error (org_id={org_id}): {exc}")
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

        # --- Current user permissions ---

        @roles_router.get("/my-permissions", response_model=PermissionsSummary)
        def get_my_permissions(actor: AnyActor, db: Any = Depends(get_db)) -> PermissionsSummary:
            """Return the current user's effective permissions for their organization.

            Includes merged catalog permission keys, entity-level permissions,
            and field-level permissions across all assigned roles.
            """
            org_id = actor_str(actor, "organization_id")
            user_id = actor_str(actor, "user_id")
            actor_roles = list(actor.get("roles") or [])
            try:
                with tracer.start_as_current_span("roles.my_permissions"):
                    return self.manager.get_effective_permissions(db, user_id, org_id, user_id, org_id, actor_roles)
            except (PersistenceError, ServiceError) as exc:
                logger.exception(f"roles.my_permissions failed (org_id={org_id} user_id={user_id}): {exc}")
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
            except Exception as exc:
                logger.exception(f"roles.my_permissions unexpected error (org_id={org_id} user_id={user_id}): {exc}")
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

        @roles_router.get("/users/{user_id}/permissions", response_model=PermissionsSummary)
        def get_user_permissions(user_id: str, actor: AdminActor, db: Any = Depends(get_db)) -> PermissionsSummary:
            """Description:
                Return effective permission catalog keys for a specific user. Admin only.

            Args:
                user_id: Target user id.
                actor: Current authenticated actor (must have one of ADMIN_ALLOWED_ROLES).
                db: SQLAlchemy session (FastAPI dependency).

            Returns:
                PermissionsSummary for the target user.

            Raises:
                HTTPException: 403 if cross-org or insufficient permission.
                HTTPException: 404 if user not found.
                HTTPException: 500 when persistence/service errors occur.
            """
            org_id = actor_str(actor, "organization_id")
            actor_user_id = actor_str(actor, "user_id")
            actor_roles = list(actor.get("roles") or [])
            try:
                with tracer.start_as_current_span("roles.user_permissions"):
                    return self.manager.get_effective_permissions(db, user_id, org_id, actor_user_id, org_id, actor_roles)
            except NotFoundError as exc:
                logger.info(f"roles.user_permissions not found (org_id={org_id} user_id={user_id}): {exc}")
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
            except ValidationError as exc:
                logger.exception(f"roles.user_permissions forbidden (org_id={org_id} user_id={user_id}): {exc}")
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
            except (PersistenceError, ServiceError) as exc:
                logger.exception(f"roles.user_permissions failed (org_id={org_id} user_id={user_id}): {exc}")
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
            except Exception as exc:
                logger.exception(f"roles.user_permissions unexpected error (org_id={org_id} user_id={user_id}): {exc}")
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

        @roles_router.get("/{role_id}", response_model=RoleRead)
        def get_role(role_id: str, actor: ReadActor, db: Any = Depends(get_db)) -> RoleRead:
            """Description:
                Get a single role with its permissions within the actor's organization.

            Args:
                role_id: Role id.
                actor: Current authenticated actor (must have one of READ_ALLOWED_ROLES).
                db: SQLAlchemy session (FastAPI dependency).

            Returns:
                Role details including permissions and field permissions.

            Raises:
                HTTPException: 404 if the role is not found.
                HTTPException: 500 when persistence/service errors occur.
            """
            org_id = actor_str(actor, "organization_id")
            try:
                with tracer.start_as_current_span("roles.get"):
                    actor_roles = actor.get("roles", [])
                    return self.manager.get_role(db, role_id, org_id, actor_roles=actor_roles)
            except NotFoundError as exc:
                logger.info(f"roles.get not found (org_id={org_id} role_id={role_id}): {exc}")
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
            except (PersistenceError, ServiceError) as exc:
                logger.exception(f"roles.get failed (org_id={org_id} role_id={role_id}): {exc}")
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
            except Exception as exc:
                logger.exception(f"roles.get unexpected error (org_id={org_id} role_id={role_id}): {exc}")
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

        @roles_router.post("", response_model=RoleRead, status_code=201)
        def create_role(
            payload: RoleCreateRequest, actor: AdminActor, db: Any = Depends(get_db)
        ) -> RoleRead:
            """Description:
                Create a custom role for the current organization.

            Args:
                payload: Role creation request payload.
                actor: Current authenticated actor (must have one of ADMIN_ALLOWED_ROLES).
                db: SQLAlchemy session (FastAPI dependency).

            Returns:
                Newly created role details.

            Raises:
                HTTPException: 400 when the request is invalid (ValidationError).
                HTTPException: 500 when persistence/service errors occur.
            """
            org_id = actor_str(actor, "organization_id")
            try:
                with tracer.start_as_current_span("roles.create"):
                    return self.manager.create_role(db, org_id, payload)
            except ValidationError as exc:
                logger.exception(f"roles.create validation failed (org_id={org_id}): {exc}")
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
            except (PersistenceError, ServiceError) as exc:
                logger.exception(f"roles.create failed (org_id={org_id}): {exc}")
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
            except Exception as exc:
                logger.exception(f"roles.create unexpected error (org_id={org_id}): {exc}")
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

        @roles_router.put("/{role_id}", response_model=RoleRead)
        def update_role(
            role_id: str,
            payload: RoleUpdateRequest,
            actor: AdminActor,
            db: Any = Depends(get_db),
        ) -> RoleRead:
            """Description:
                Update a role's details and permissions.

            Args:
                role_id: Role id.
                payload: Role update request payload.
                actor: Current authenticated actor (must have one of ADMIN_ALLOWED_ROLES).
                db: SQLAlchemy session (FastAPI dependency).

            Returns:
                Updated role details.

            Raises:
                HTTPException: 404 if the role is not found.
                HTTPException: 400 when the request is invalid (ValidationError).
                HTTPException: 500 when persistence/service errors occur.
            """
            org_id = actor_str(actor, "organization_id")
            try:
                with tracer.start_as_current_span("roles.update"):
                    actor_roles = list(actor.get("roles") or [])
                    return self.manager.update_role(db, role_id, org_id, payload, actor_roles=actor_roles)
            except NotFoundError as exc:
                logger.info(f"roles.update not found (org_id={org_id} role_id={role_id}): {exc}")
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
            except ValidationError as exc:
                logger.exception(f"roles.update validation failed (org_id={org_id} role_id={role_id}): {exc}")
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
            except (PersistenceError, ServiceError) as exc:
                logger.exception(f"roles.update failed (org_id={org_id} role_id={role_id}): {exc}")
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
            except Exception as exc:
                logger.exception(f"roles.update unexpected error (org_id={org_id} role_id={role_id}): {exc}")
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

        @roles_router.delete("/{role_id}", status_code=204)
        def delete_role(role_id: str, actor: AdminActor, db: Any = Depends(get_db)) -> None:
            """Description:
                Delete a custom role if it has no assignments.

            Args:
                role_id: Role id.
                actor: Current authenticated actor (must have one of ADMIN_ALLOWED_ROLES).
                db: SQLAlchemy session (FastAPI dependency).

            Returns:
                None

            Raises:
                HTTPException: 404 if the role is not found.
                HTTPException: 400 when deletion is not allowed (ValidationError).
                HTTPException: 500 when persistence/service errors occur.
            """
            org_id = actor_str(actor, "organization_id")
            try:
                with tracer.start_as_current_span("roles.delete"):
                    self.manager.delete_role(db, role_id, org_id)
                return None
            except NotFoundError as exc:
                logger.info(f"roles.delete not found (org_id={org_id} role_id={role_id}): {exc}")
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
            except ValidationError as exc:
                logger.exception(f"roles.delete validation failed (org_id={org_id} role_id={role_id}): {exc}")
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
            except (PersistenceError, ServiceError) as exc:
                logger.exception(f"roles.delete failed (org_id={org_id} role_id={role_id}): {exc}")
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
            except Exception as exc:
                logger.exception(f"roles.delete unexpected error (org_id={org_id} role_id={role_id}): {exc}")
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

        @roles_router.post("/{role_id}/duplicate", response_model=RoleRead, status_code=201)
        def duplicate_role(
            role_id: str, payload: RoleDuplicateRequest, actor: AdminActor, db: Any = Depends(get_db)
        ) -> RoleRead:
            """Description:
                Duplicate an existing role under a new name.

            Args:
                role_id: Source role id.
                payload: Role duplication request payload.
                actor: Current authenticated actor (must have one of ADMIN_ALLOWED_ROLES).
                db: SQLAlchemy session (FastAPI dependency).

            Returns:
                Newly created duplicated role details.

            Raises:
                HTTPException: 404 if the source role is not found.
                HTTPException: 400 when duplication is invalid (ValidationError).
                HTTPException: 500 when persistence/service errors occur.
            """
            org_id = actor_str(actor, "organization_id")
            try:
                with tracer.start_as_current_span("roles.duplicate"):
                    return self.manager.duplicate_role(db, role_id, org_id, payload)
            except NotFoundError as exc:
                logger.info(f"roles.duplicate not found (org_id={org_id} role_id={role_id}): {exc}")
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
            except ValidationError as exc:
                logger.exception(f"roles.duplicate validation failed (org_id={org_id} role_id={role_id}): {exc}")
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
            except (PersistenceError, ServiceError) as exc:
                logger.exception(f"roles.duplicate failed (org_id={org_id} role_id={role_id}): {exc}")
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
            except Exception as exc:
                logger.exception(f"roles.duplicate unexpected error (org_id={org_id} role_id={role_id}): {exc}")
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

        # --- User role assignment ---

        @roles_router.get("/users/{user_id}/roles", response_model=list[UserRoleRead])
        def get_user_roles(
            user_id: str, actor: UserReadActor, db: Any = Depends(get_db)
        ) -> list[UserRoleRead]:
            """Description:
                List role assignments for a user in the current organization.

            Args:
                user_id: Target user id.
                actor: Current authenticated actor (must have one of READ_ALLOWED_ROLES).
                db: SQLAlchemy session (FastAPI dependency).

            Returns:
                List of role assignments for the user.

            Raises:
                HTTPException: 500 when persistence/service errors occur.
            """
            org_id = actor_str(actor, "organization_id")
            try:
                with tracer.start_as_current_span("roles.user_roles.list"):
                    return self.manager.get_user_roles(db, user_id, org_id)
            except (PersistenceError, ServiceError) as exc:
                logger.exception(f"roles.user_roles.list failed (org_id={org_id} user_id={user_id}): {exc}")
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
            except Exception as exc:
                logger.exception(f"roles.user_roles.list unexpected error (org_id={org_id} user_id={user_id}): {exc}")
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

        @roles_router.put("/users/{user_id}/role", response_model=UserRoleRead)
        def set_user_role(
            user_id: str, payload: UserRoleSetRequest, actor: UserWriteActor, db: Any = Depends(get_db)
        ) -> UserRoleRead:
            """Description:
                Set (replace) the user's roles to a single role in this organization.

            Args:
                user_id: Target user id.
                payload: Role assignment payload.
                actor: Current authenticated actor (must have one of ADMIN_ALLOWED_ROLES).
                db: SQLAlchemy session (FastAPI dependency).

            Returns:
                The created/updated role assignment.

            Raises:
                HTTPException: 404 if the user or role is not found.
                HTTPException: 400 when the request is invalid (ValidationError).
                HTTPException: 500 when persistence/service errors occur.
            """
            org_id = actor_str(actor, "organization_id")
            assigned_by = actor_str(actor, "user_id")
            try:
                with tracer.start_as_current_span("roles.user_roles.set"):
                    return self.manager.set_user_role(db, user_id, org_id, payload, assigned_by=assigned_by)
            except NotFoundError as exc:
                logger.info(
                    f"roles.user_roles.set not found (org_id={org_id} user_id={user_id} role_id={payload.role_id}): {exc}"
                )
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
            except ValidationError as exc:
                logger.exception(
                    f"roles.user_roles.set validation failed (org_id={org_id} user_id={user_id} role_id={payload.role_id}): {exc}"
                )
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
            except (PersistenceError, ServiceError) as exc:
                logger.exception(
                    f"roles.user_roles.set failed (org_id={org_id} user_id={user_id} role_id={payload.role_id}): {exc}"
                )
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
            except Exception as exc:
                logger.exception(
                    f"roles.user_roles.set unexpected error (org_id={org_id} user_id={user_id} role_id={payload.role_id}): {exc}"
                )
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

        @roles_router.post("/users/{user_id}/roles", response_model=UserRoleRead, status_code=201)
        def add_user_role(
            user_id: str, payload: UserRoleSetRequest, actor: UserWriteActor, db: Any = Depends(get_db)
        ) -> UserRoleRead:
            """Add a role to the user without removing the roles they already hold."""
            org_id = actor_str(actor, "organization_id")
            assigned_by = actor_str(actor, "user_id")
            try:
                with tracer.start_as_current_span("roles.user_roles.add"):
                    return self.manager.add_user_role(db, user_id, org_id, payload, assigned_by=assigned_by)
            except NotFoundError as exc:
                logger.info(
                    f"roles.user_roles.add not found (org_id={org_id} user_id={user_id} role_id={payload.role_id}): {exc}"
                )
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
            except ValidationError as exc:
                logger.exception(
                    f"roles.user_roles.add validation failed (org_id={org_id} user_id={user_id} role_id={payload.role_id}): {exc}"
                )
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
            except (PersistenceError, ServiceError) as exc:
                logger.exception(
                    f"roles.user_roles.add failed (org_id={org_id} user_id={user_id} role_id={payload.role_id}): {exc}"
                )
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
            except Exception as exc:
                logger.exception(
                    f"roles.user_roles.add unexpected error (org_id={org_id} user_id={user_id} role_id={payload.role_id}): {exc}"
                )
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

        @roles_router.delete("/users/{user_id}/roles/{role_id}", status_code=204)
        def remove_user_role(
            user_id: str, role_id: str, actor: UserWriteActor, db: Any = Depends(get_db)
        ) -> None:
            """Description:
                Remove a specific role assignment from a user.

            Args:
                user_id: Target user id.
                role_id: Role id to remove.
                actor: Current authenticated actor (must have one of ADMIN_ALLOWED_ROLES).
                db: SQLAlchemy session (FastAPI dependency).

            Returns:
                None

            Raises:
                HTTPException: 404 if the role assignment is not found.
                HTTPException: 500 when persistence/service errors occur.
            """
            org_id = actor_str(actor, "organization_id")
            try:
                with tracer.start_as_current_span("roles.user_roles.remove"):
                    self.manager.remove_user_role(db, user_id, org_id, role_id)
                return None
            except NotFoundError as exc:
                logger.info(
                    f"roles.user_roles.remove not found (org_id={org_id} user_id={user_id} role_id={role_id}): {exc}"
                )
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
            except (PersistenceError, ServiceError) as exc:
                logger.exception(
                    f"roles.user_roles.remove failed (org_id={org_id} user_id={user_id} role_id={role_id}): {exc}"
                )
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
            except Exception as exc:
                logger.exception(
                    f"roles.user_roles.remove unexpected error (org_id={org_id} user_id={user_id} role_id={role_id}): {exc}"
                )
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

        app.include_router(roles_router, tags=["roles"])
