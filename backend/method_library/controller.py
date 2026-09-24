"""Method library REST controller module.

Reads plus the write side: create, metadata edit, field-list replacement and
delete. Grid, search, clone and permissions are separate tickets.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from common.auth import require_permission
from common.logger import logger, tracer
from common.utils import raise_http_error
from method_library.db_models import DEFAULT_PAGE_LIMIT
from method_library.models.request import (
    MethodCategoryCreateRequest,
    MethodCategoryRenameRequest,
    MethodCloneRequest,
    MethodCreateRequest,
    MethodFieldListUpdateRequest,
    MethodFieldRepinRequest,
    MethodMetadataUpdateRequest,
)
from method_library.models.response import (
    MethodCategory,
    MethodCategoryListResponse,
    MethodIdentity,
    MethodLibraryStatusResponse,
    MethodListResponse,
    MethodVersionListResponse,
    MethodWithFields,
)

if TYPE_CHECKING:
    from fastapi.params import Depends as DependsParam

    from method_library.manager import MethodLibraryServiceManager

# The method library has its own permission scope, so access to it can be granted
# independently of Workflow Designer access. Existing roles were backfilled from
# their workflow:* grants, so nobody lost access when this moved off workflow:*.
MethodReadActor = Annotated[
    dict[str, object], Depends(require_permission("method_library", "read"))
]
MethodWriteActor = Annotated[
    dict[str, object], Depends(require_permission("method_library", "write"))
]

# Upper bound on a single page, matching the other list endpoints.
MAX_PAGE_LIMIT = 200


class MethodLibraryRestController:
    """Implements method library REST controller."""

    def __init__(self, method_library_service_manager: MethodLibraryServiceManager) -> None:
        self.method_library_service_manager = method_library_service_manager
        self.manager = method_library_service_manager

    @staticmethod
    def _route_dependencies(security: DependsParam | None) -> list[DependsParam] | None:
        return [security] if security else None

    @staticmethod
    def _error_context(request_id: str, operation: str) -> dict[str, str]:
        return {
            "request_id": request_id,
            "controller": "MethodLibraryRestController",
            "operation": operation,
        }

    def prepare(self, app: APIRouter, security: DependsParam | None = None) -> None:
        """Register the method library routes."""
        route_dependencies = self._route_dependencies(security)
        self._register_read_routes(app, route_dependencies)
        self._register_single_method_routes(app, route_dependencies)
        self._register_write_routes(app, route_dependencies)
        self._register_clone_route(app, route_dependencies)
        self._register_field_list_route(app, route_dependencies)
        self._register_field_repin_route(app, route_dependencies)
        self._register_delete_route(app, route_dependencies)
        self._register_archive_routes(app, route_dependencies)
        self._register_category_routes(app, route_dependencies)
        self._register_category_edit_routes(app, route_dependencies)

    def _register_read_routes(
        self, app: APIRouter, route_dependencies: list[DependsParam] | None
    ) -> None:
        """Status, the method list, and one resolved method."""

        @app.get(
            "/method-library/status",
            status_code=status.HTTP_200_OK,
            tags=["method_library"],
            response_model=MethodLibraryStatusResponse,
            dependencies=route_dependencies,
        )
        def status_endpoint(request: Request):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("MethodLibraryController.status"):
                try:
                    logger.info("method library status", extra={"request_id": request_id})
                    return self.method_library_service_manager.get_status()
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "status"))

        @app.get(
            "/method-library/methods",
            status_code=status.HTTP_200_OK,
            tags=["method_library"],
            response_model=MethodListResponse,
            dependencies=route_dependencies,
        )
        def list_methods_endpoint(
            request: Request,
            actor: MethodReadActor,
            include_archived: bool = Query(default=False),
            search: str | None = Query(default=None),
            entity_type: str | None = Query(default=None),
            limit: int = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
            offset: int = Query(default=0, ge=0),
        ):
            """A page of the actor's organization's methods, identities only.

            `search` partially matches a method's name or its category name,
            case insensitively. `entity_type` keeps only methods tagged for that
            entity type, which is how a workflow state picker asks for the
            methods it may offer. `total` counts every match, not just this page.
            """
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("MethodLibraryController.list_methods"):
                try:
                    items, total = self.method_library_service_manager.list_methods_for_actor(
                        actor,
                        include_archived=include_archived,
                        search=search,
                        entity_type=entity_type,
                        limit=limit,
                        offset=offset,
                    )
                    return MethodListResponse(
                        organization_id=str(actor.get("organization_id") or ""),
                        items=items,
                        total=total,
                        limit=limit,
                        offset=offset,
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "list_methods"))

    def _register_single_method_routes(
        self, app: APIRouter, route_dependencies: list[DependsParam] | None
    ) -> None:
        """Reading one method: its version history, and the resolved detail."""

        @app.get(
            "/method-library/methods/{method_id}/versions",
            status_code=status.HTTP_200_OK,
            tags=["method_library"],
            response_model=MethodVersionListResponse,
            dependencies=route_dependencies,
        )
        def list_method_versions_endpoint(
            request: Request,
            method_id: str,
            actor: MethodReadActor,
            limit: int = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
            offset: int = Query(default=0, ge=0),
        ):
            """A page of a method's version history, newest first.

            The detail endpoint resolves only the current version; this is how a
            caller sees what came before it.
            """
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("MethodLibraryController.list_versions"):
                try:
                    items, total = (
                        self.method_library_service_manager.list_method_versions_for_actor(
                            actor, method_id, limit=limit, offset=offset
                        )
                    )
                    return MethodVersionListResponse(
                        method_id=method_id, items=items, total=total, limit=limit, offset=offset
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "list_versions"))

        @app.get(
            "/method-library/methods/{method_id}",
            status_code=status.HTTP_200_OK,
            tags=["method_library"],
            response_model=MethodWithFields,
            dependencies=route_dependencies,
        )
        def get_method_endpoint(request: Request, method_id: str, actor: MethodReadActor):
            """One method resolved into its ordered field list.

            Each field carries the method's own label, placeholder, required flag
            and position, merged with the type and settings of the Field Library
            version it pins.
            """
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("MethodLibraryController.get_method"):
                try:
                    return self.method_library_service_manager.get_method_with_fields_for_actor(
                        actor, method_id
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "get_method"))

    def _register_write_routes(
        self, app: APIRouter, route_dependencies: list[DependsParam] | None
    ) -> None:
        """Creating a method and editing its metadata in place."""

        @app.post(
            "/method-library/methods",
            status_code=status.HTTP_201_CREATED,
            tags=["method_library"],
            response_model=MethodWithFields,
            dependencies=route_dependencies,
        )
        def create_method_endpoint(
            request: Request, payload: MethodCreateRequest, actor: MethodWriteActor
        ):
            """Create a method and its version 1.

            Each field is pinned to its current latest Field Library version.
            """
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("MethodLibraryController.create_method"):
                try:
                    logger.info("method library create", extra={"request_id": request_id})
                    return self.method_library_service_manager.create_method_for_actor(
                        actor, payload
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "create_method"))

        @app.patch(
            "/method-library/methods/{method_id}",
            status_code=status.HTTP_200_OK,
            tags=["method_library"],
            response_model=MethodIdentity,
            dependencies=route_dependencies,
        )
        def update_method_endpoint(
            request: Request,
            method_id: str,
            payload: MethodMetadataUpdateRequest,
            actor: MethodWriteActor,
        ):
            """Edit name, description or category in place, creating no version."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("MethodLibraryController.update_method"):
                try:
                    return (
                        self.method_library_service_manager
                        .update_method_metadata_for_actor(actor, method_id, payload)
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "update_method"))

    def _register_clone_route(
        self, app: APIRouter, route_dependencies: list[DependsParam] | None
    ) -> None:
        """Cloning a method, optionally from one of its historical versions."""

        @app.post(
            "/method-library/methods/{method_id}/clone",
            status_code=status.HTTP_201_CREATED,
            tags=["method_library"],
            response_model=MethodWithFields,
            dependencies=route_dependencies,
        )
        def clone_method_endpoint(
            request: Request,
            method_id: str,
            payload: MethodCloneRequest,
            actor: MethodWriteActor,
        ):
            """Copy a method's field list into a new, independent method.

            `source_version_id` picks which version to copy, defaulting to the
            source's current latest. The copy keeps that version's exact field
            pins, so cloning an old version reproduces it rather than upgrading
            it. Nothing links the two methods afterwards.
            """
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("MethodLibraryController.clone_method"):
                try:
                    return self.method_library_service_manager.clone_method_for_actor(
                        actor, method_id, payload
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "clone_method"))

    def _register_field_list_route(
        self, app: APIRouter, route_dependencies: list[DependsParam] | None
    ) -> None:
        """Replacing a method's field list, which is what produces a version."""

        @app.put(
            "/method-library/methods/{method_id}/fields",
            status_code=status.HTTP_200_OK,
            tags=["method_library"],
            response_model=MethodWithFields,
            dependencies=route_dependencies,
        )
        def replace_method_fields_endpoint(
            request: Request,
            method_id: str,
            payload: MethodFieldListUpdateRequest,
            actor: MethodWriteActor,
        ):
            """Replace the field list wholesale, producing a new version.

            The superseded version is kept, so anything pinned to it still
            resolves.
            """
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("MethodLibraryController.replace_fields"):
                try:
                    return (
                        self.method_library_service_manager
                        .replace_method_fields_for_actor(actor, method_id, payload)
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "replace_fields"))

    def _register_field_repin_route(
        self, app: APIRouter, route_dependencies: list[DependsParam] | None
    ) -> None:
        """Moving one field's pin to a different version of that field."""

        @app.patch(
            "/method-library/methods/{method_id}/fields/{link_id}/version",
            status_code=status.HTTP_200_OK,
            tags=["method_library"],
            response_model=MethodWithFields,
            dependencies=route_dependencies,
        )
        def repin_method_field_endpoint(
            request: Request,
            method_id: str,
            link_id: str,
            payload: MethodFieldRepinRequest,
            actor: MethodWriteActor,
        ):
            """Move one of a method's fields to a different version of that field."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("MethodLibraryController.repin_field"):
                try:
                    return self.method_library_service_manager.repin_method_field_for_actor(
                        actor, method_id, link_id, payload
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "repin_field"))

    def _register_delete_route(
        self, app: APIRouter, route_dependencies: list[DependsParam] | None
    ) -> None:
        """Deleting a method outright."""

        @app.delete(
            "/method-library/methods/{method_id}",
            status_code=status.HTTP_204_NO_CONTENT,
            tags=["method_library"],
            dependencies=route_dependencies,
        )
        def delete_method_endpoint(
            request: Request, method_id: str, actor: MethodWriteActor
        ):
            """Hard delete a method, taking its versions and version fields with it.

            Unconditional for now, and deliberately so: there is no way yet to
            check whether a workflow references the method. Once
            workflow-to-method linking exists this should refuse while anything
            points at it, rather than deleting it out from under a workflow.
            """
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("MethodLibraryController.delete_method"):
                try:
                    self.method_library_service_manager.delete_method_for_actor(
                        actor, method_id
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "delete_method"))

    def _register_archive_routes(
        self, app: APIRouter, route_dependencies: list[DependsParam] | None
    ) -> None:
        """Archiving a method and reversing it. Separate from delete."""

        @app.post(
            "/method-library/methods/{method_id}/archive",
            status_code=status.HTTP_200_OK,
            tags=["method_library"],
            response_model=MethodIdentity,
            dependencies=route_dependencies,
        )
        def archive_method_endpoint(
            request: Request, method_id: str, actor: MethodWriteActor
        ):
            """Archive a method. Reversible and hidden, not destructive."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("MethodLibraryController.archive_method"):
                try:
                    return self.method_library_service_manager.archive_method_for_actor(
                        actor, method_id
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "archive_method"))

        @app.post(
            "/method-library/methods/{method_id}/unarchive",
            status_code=status.HTTP_200_OK,
            tags=["method_library"],
            response_model=MethodIdentity,
            dependencies=route_dependencies,
        )
        def unarchive_method_endpoint(
            request: Request, method_id: str, actor: MethodWriteActor
        ):
            """Reverse an archive, making the method appear in default listings again."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("MethodLibraryController.unarchive_method"):
                try:
                    return self.method_library_service_manager.unarchive_method_for_actor(
                        actor, method_id
                    )
                except Exception as exc:
                    raise_http_error(
                        exc, self._error_context(request_id, "unarchive_method")
                    )

    def _register_category_routes(
        self, app: APIRouter, route_dependencies: list[DependsParam] | None
    ) -> None:
        """Creating a category and listing them, the pickers behind category_id."""

        @app.post(
            "/method-library/categories",
            status_code=status.HTTP_201_CREATED,
            tags=["method_library"],
            response_model=MethodCategory,
            dependencies=route_dependencies,
        )
        def create_category_endpoint(
            request: Request, payload: MethodCategoryCreateRequest, actor: MethodWriteActor
        ):
            """Create a category. Names are unique per organization, ignoring case."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("MethodLibraryController.create_category"):
                try:
                    return self.method_library_service_manager.create_category_for_actor(
                        actor, payload
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "create_category"))

        @app.get(
            "/method-library/categories",
            status_code=status.HTTP_200_OK,
            tags=["method_library"],
            response_model=MethodCategoryListResponse,
            dependencies=route_dependencies,
        )
        def list_categories_endpoint(request: Request, actor: MethodReadActor):
            """Every category in the actor's organization, ordered by name."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("MethodLibraryController.list_categories"):
                try:
                    items = self.method_library_service_manager.list_categories_for_actor(actor)
                    return MethodCategoryListResponse(
                        organization_id=str(actor.get("organization_id") or ""), items=items
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "list_categories"))

    def _register_category_edit_routes(
        self, app: APIRouter, route_dependencies: list[DependsParam] | None
    ) -> None:
        """Renaming and deleting a category."""

        @app.patch(
            "/method-library/categories/{category_id}",
            status_code=status.HTTP_200_OK,
            tags=["method_library"],
            response_model=MethodCategory,
            dependencies=route_dependencies,
        )
        def rename_category_endpoint(
            request: Request,
            category_id: str,
            payload: MethodCategoryRenameRequest,
            actor: MethodWriteActor,
        ):
            """Rename a category. Its methods stay filed under it."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("MethodLibraryController.rename_category"):
                try:
                    return self.method_library_service_manager.rename_category_for_actor(
                        actor, category_id, payload
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "rename_category"))

        @app.delete(
            "/method-library/categories/{category_id}",
            status_code=status.HTTP_204_NO_CONTENT,
            tags=["method_library"],
            dependencies=route_dependencies,
        )
        def delete_category_endpoint(
            request: Request, category_id: str, actor: MethodWriteActor
        ):
            """Delete a category. Refused while a method is still filed under it."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("MethodLibraryController.delete_category"):
                try:
                    self.method_library_service_manager.delete_category_for_actor(
                        actor, category_id
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "delete_category"))
