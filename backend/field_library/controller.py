"""Field library REST controller module."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from common.auth import require_permission
from common.logger import logger, tracer
from common.utils import raise_http_error
from field_library.db_models import DEFAULT_PAGE_LIMIT
from field_library.models.request import (
    FieldCreateRequest,
    FieldDescriptionUpdateRequest,
    FieldRenameRequest,
    FieldVersionCreateRequest,
    FormFieldLinkCreateRequest,
    FormFieldLinkRepinRequest,
)
from field_library.models.response import (
    FieldIdentity,
    FieldLibraryStatusResponse,
    FieldListResponse,
    FieldTypeCatalogueResponse,
    FieldVersion,
    FieldVersionListResponse,
    FieldWithVersion,
    FormFieldListResponse,
    FormFieldPlacement,
)

if TYPE_CHECKING:
    from fastapi.params import Depends as DependsParam

    from field_library.manager import FieldLibraryServiceManager

# The library has its own permission scope, so access to it can be granted
# independently of Forms access. Existing roles were backfilled from their form:*
# grants, so nobody lost access when this moved off form:*. One coarse write
# permission covers every write: create, rename, description edit, new version,
# archive and hard delete.
FieldTypeReadActor = Annotated[
    dict[str, object], Depends(require_permission("field_library", "read"))
]
FieldReadActor = Annotated[
    dict[str, object], Depends(require_permission("field_library", "read"))
]
FieldWriteActor = Annotated[
    dict[str, object], Depends(require_permission("field_library", "write"))
]

# Upper bound on a single page, matching the other list endpoints.
MAX_PAGE_LIMIT = 200


class FieldLibraryRestController:
    """Implements field library REST controller."""

    def __init__(self, field_library_service_manager: FieldLibraryServiceManager) -> None:
        self.field_library_service_manager = field_library_service_manager
        self.manager = field_library_service_manager

    @staticmethod
    def _route_dependencies(security: DependsParam | None) -> list[DependsParam] | None:
        return [security] if security else None

    @staticmethod
    def _error_context(request_id: str, operation: str) -> dict[str, str]:
        return {
            "request_id": request_id,
            "controller": "FieldLibraryRestController",
            "operation": operation,
        }

    def prepare(self, app: APIRouter, security: DependsParam | None = None) -> None:
        """Register the field library routes."""
        route_dependencies = self._route_dependencies(security)
        self._register_catalogue_routes(app, route_dependencies)
        self._register_field_routes(app, route_dependencies)
        self._register_field_edit_routes(app, route_dependencies)
        self._register_version_routes(app, route_dependencies)
        self._register_removal_routes(app, route_dependencies)
        self._register_form_link_routes(app, route_dependencies)
        self._register_form_link_edit_routes(app, route_dependencies)

    def _register_catalogue_routes(
        self, app: APIRouter, route_dependencies: list[DependsParam] | None
    ) -> None:
        """Module status and the read-only field-type catalogue."""

        @app.get(
            "/field-library/status",
            status_code=status.HTTP_200_OK,
            tags=["field_library"],
            response_model=FieldLibraryStatusResponse,
            dependencies=route_dependencies,
        )
        def status_endpoint(request: Request):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("FieldLibraryController.status"):
                try:
                    logger.info("field library status requested", extra={"request_id": request_id})
                    return self.field_library_service_manager.get_status()
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "status"))

        @app.get(
            "/field-library/field-types",
            status_code=status.HTTP_200_OK,
            tags=["field_library"],
            response_model=FieldTypeCatalogueResponse,
            dependencies=route_dependencies,
        )
        def list_field_types_endpoint(request: Request, actor: FieldTypeReadActor):
            """Return the field types the actor's organization may pick from."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("FieldLibraryController.list_field_types"):
                try:
                    logger.info("field library list_field_types", extra={"request_id": request_id})
                    return self.field_library_service_manager.list_field_types_for_actor(actor)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "list_field_types"))

    def _register_field_routes(
        self, app: APIRouter, route_dependencies: list[DependsParam] | None
    ) -> None:
        """Listing, creating and reading library fields."""

        @app.get(
            "/field-library/fields",
            status_code=status.HTTP_200_OK,
            tags=["field_library"],
            response_model=FieldListResponse,
            dependencies=route_dependencies,
        )
        def list_fields_endpoint(
            request: Request,
            actor: FieldReadActor,
            include_archived: bool = Query(default=False),
            search: str | None = Query(default=None),
            field_type: str | None = Query(default=None),
            limit: int = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
            offset: int = Query(default=0, ge=0),
        ):
            """A page of the actor's organization's library fields.

            Each item carries its current version. Archived fields are excluded
            unless `include_archived` is set, so a field `get` still returns can
            legitimately be absent here.
            """
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("FieldLibraryController.list_fields"):
                try:
                    items, total = self.field_library_service_manager.list_fields_for_actor(
                        actor,
                        include_archived=include_archived,
                        search=search,
                        field_type=field_type,
                        limit=limit,
                        offset=offset,
                    )
                    return FieldListResponse(
                        organization_id=str(actor.get("organization_id") or ""),
                        items=items,
                        total=total,
                        limit=limit,
                        offset=offset,
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "list_fields"))

        @app.post(
            "/field-library/fields",
            status_code=status.HTTP_201_CREATED,
            tags=["field_library"],
            response_model=FieldWithVersion,
            dependencies=route_dependencies,
        )
        def create_field_endpoint(
            request: Request, payload: FieldCreateRequest, actor: FieldWriteActor
        ):
            """Create a field and its version 1."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("FieldLibraryController.create_field"):
                try:
                    return self.field_library_service_manager.create_field_for_actor(
                        actor, payload
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "create_field"))

        @app.get(
            "/field-library/fields/{library_field_id}",
            status_code=status.HTTP_200_OK,
            tags=["field_library"],
            response_model=FieldWithVersion,
            dependencies=route_dependencies,
        )
        def get_field_endpoint(request: Request, library_field_id: str, actor: FieldReadActor):
            """Fetch one field with its current version."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("FieldLibraryController.get_field"):
                try:
                    return self.field_library_service_manager.get_field_for_actor(
                        actor, library_field_id
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "get_field"))

    def _register_field_edit_routes(
        self, app: APIRouter, route_dependencies: list[DependsParam] | None
    ) -> None:
        """In-place edits that create no version: rename and reword."""

        @app.patch(
            "/field-library/fields/{library_field_id}/name",
            status_code=status.HTTP_200_OK,
            tags=["field_library"],
            response_model=FieldIdentity,
            dependencies=route_dependencies,
        )
        def rename_field_endpoint(
            request: Request,
            library_field_id: str,
            payload: FieldRenameRequest,
            actor: FieldWriteActor,
        ):
            """Rename a field. Its own route, since a rename creates no version."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("FieldLibraryController.rename_field"):
                try:
                    return self.field_library_service_manager.rename_field_for_actor(
                        actor, library_field_id, payload
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "rename_field"))

        @app.patch(
            "/field-library/fields/{library_field_id}/description",
            status_code=status.HTTP_200_OK,
            tags=["field_library"],
            response_model=FieldVersion,
            dependencies=route_dependencies,
        )
        def update_description_endpoint(
            request: Request,
            library_field_id: str,
            payload: FieldDescriptionUpdateRequest,
            actor: FieldWriteActor,
        ):
            """Edit the current version's description in place, creating no version.

            The counterpart to rename. Real content changes go through
            POST /versions, which still accepts a description of its own.
            """
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("FieldLibraryController.update_description"):
                try:
                    return self.field_library_service_manager.update_description_for_actor(
                        actor, library_field_id, payload
                    )
                except Exception as exc:
                    raise_http_error(
                        exc, self._error_context(request_id, "update_description")
                    )

    def _register_version_routes(
        self, app: APIRouter, route_dependencies: list[DependsParam] | None
    ) -> None:
        """Reading a field's history and adding to it."""

        @app.get(
            "/field-library/fields/{library_field_id}/versions",
            status_code=status.HTTP_200_OK,
            tags=["field_library"],
            response_model=FieldVersionListResponse,
            dependencies=route_dependencies,
        )
        def list_versions_endpoint(
            request: Request, library_field_id: str, actor: FieldReadActor
        ):
            """List every version of one field, so a form can pick one to pin to."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("FieldLibraryController.list_versions"):
                try:
                    items = self.field_library_service_manager.list_versions_for_actor(
                        actor, library_field_id
                    )
                    return FieldVersionListResponse(
                        library_field_id=library_field_id, items=items
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "list_versions"))

        @app.post(
            "/field-library/fields/{library_field_id}/versions",
            status_code=status.HTTP_201_CREATED,
            tags=["field_library"],
            response_model=FieldVersion,
            dependencies=route_dependencies,
        )
        def create_version_endpoint(
            request: Request,
            library_field_id: str,
            payload: FieldVersionCreateRequest,
            actor: FieldWriteActor,
        ):
            """Create the next version. POST, since an edit inserts a new row."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("FieldLibraryController.create_version"):
                try:
                    return self.field_library_service_manager.create_version_for_actor(
                        actor, library_field_id, payload
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "create_version"))

    def _register_removal_routes(
        self, app: APIRouter, route_dependencies: list[DependsParam] | None
    ) -> None:
        """The two ways to remove a field: archive it, or delete it outright."""

        @app.delete(
            "/field-library/fields/{library_field_id}/hard",
            status_code=status.HTTP_204_NO_CONTENT,
            tags=["field_library"],
            dependencies=route_dependencies,
        )
        def hard_delete_field_endpoint(
            request: Request, library_field_id: str, actor: FieldWriteActor
        ):
            """Delete a field outright, refusing while any form still uses it.

            Archiving is the unconditional path; this one is only for fields that
            were never adopted.
            """
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("FieldLibraryController.hard_delete_field"):
                try:
                    self.field_library_service_manager.hard_delete_field_for_actor(
                        actor, library_field_id
                    )
                except Exception as exc:
                    raise_http_error(
                        exc, self._error_context(request_id, "hard_delete_field")
                    )

        @app.delete(
            "/field-library/fields/{library_field_id}",
            status_code=status.HTTP_200_OK,
            tags=["field_library"],
            response_model=FieldIdentity,
            dependencies=route_dependencies,
        )
        def archive_field_endpoint(
            request: Request, library_field_id: str, actor: FieldWriteActor
        ):
            """Archive a field. Nothing is deleted, so existing references survive."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("FieldLibraryController.archive_field"):
                try:
                    return self.field_library_service_manager.archive_field_for_actor(
                        actor, library_field_id
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "archive_field"))

    def _register_form_link_routes(
        self, app: APIRouter, route_dependencies: list[DependsParam] | None
    ) -> None:
        """Putting a field on a form, and reading what a form uses."""

        @app.post(
            "/field-library/form-fields",
            status_code=status.HTTP_201_CREATED,
            tags=["field_library"],
            response_model=FormFieldPlacement,
            dependencies=route_dependencies,
        )
        def create_form_field_endpoint(
            request: Request, payload: FormFieldLinkCreateRequest, actor: FieldWriteActor
        ):
            """Put a field on a form, pinned to one of its versions.

            Omit `version_id` to pin the field's current version as it stands
            now. The pin does not move on its own afterwards.
            """
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("FieldLibraryController.create_form_field"):
                try:
                    return self.field_library_service_manager.create_link_for_actor(
                        actor, payload
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "create_form_field"))

        @app.get(
            "/field-library/form-fields/{schema_id}",
            status_code=status.HTTP_200_OK,
            tags=["field_library"],
            response_model=FormFieldListResponse,
            dependencies=route_dependencies,
        )
        def list_form_fields_endpoint(request: Request, schema_id: str, actor: FieldReadActor):
            """Every field one form uses, in position order, each with its version."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("FieldLibraryController.list_form_fields"):
                try:
                    items = self.field_library_service_manager.list_links_for_actor(
                        actor, schema_id
                    )
                    return FormFieldListResponse(
                        schema_id=schema_id,
                        organization_id=str(actor.get("organization_id") or ""),
                        items=items,
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "list_form_fields"))

    def _register_form_link_edit_routes(
        self, app: APIRouter, route_dependencies: list[DependsParam] | None
    ) -> None:
        """Repinning a form's field to another version, and taking it off."""

        @app.patch(
            "/field-library/form-fields/{link_id}",
            status_code=status.HTTP_200_OK,
            tags=["field_library"],
            response_model=FormFieldPlacement,
            dependencies=route_dependencies,
        )
        def repin_form_field_endpoint(
            request: Request,
            link_id: str,
            payload: FormFieldLinkRepinRequest,
            actor: FieldWriteActor,
        ):
            """Move this form onto a different version of the same field."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("FieldLibraryController.repin_form_field"):
                try:
                    return self.field_library_service_manager.repin_link_for_actor(
                        actor, link_id, payload
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "repin_form_field"))

        @app.delete(
            "/field-library/form-fields/{link_id}",
            status_code=status.HTTP_204_NO_CONTENT,
            tags=["field_library"],
            dependencies=route_dependencies,
        )
        def delete_form_field_endpoint(request: Request, link_id: str, actor: FieldWriteActor):
            """Take a field off a form. The field and its versions are untouched."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("FieldLibraryController.delete_form_field"):
                try:
                    self.field_library_service_manager.delete_link_for_actor(actor, link_id)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "delete_form_field"))
