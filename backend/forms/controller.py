"""Forms REST controller module."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Body, Depends, Request, status
from sqlalchemy.orm import Session

from common.auth import require_permission
from common.deps import get_db
from common.logger import logger, tracer
from common.utils import raise_http_error
from forms.models.request import (
    EntityTypeSchemaCreateRequest,
    EntityTypeSchemaUpdateRequest,
    PicklistCreateRequest,
    PicklistUpdateRequest,
)
from forms.models.response import (
    EntityTypeSchemaListResponse,
    EntityTypeSchemaResponse,
    MetadataRegistryStatusResponse,
    PicklistListResponse,
    PicklistResponse,
)

if TYPE_CHECKING:
    from fastapi.params import Depends as DependsParam

    from auth.manager import AuthServiceManager
    from database.manager import DatabaseServiceManager
    from forms.manager import FormsServiceManager

FormReadActor = Annotated[dict[str, object], Depends(require_permission("form", "read"))]
FormWriteActor = Annotated[dict[str, object], Depends(require_permission("form", "write"))]


class FormsRestController:
    """Implements forms REST controller."""

    def __init__(
        self,
        forms_service_manager: FormsServiceManager,
        database_service_manager: DatabaseServiceManager | None = None,
        auth_service_manager: AuthServiceManager | None = None,
    ) -> None:
        """Store the service manager; unused dependencies accepted for interface compatibility."""
        _ = database_service_manager, auth_service_manager
        self.forms_service_manager = forms_service_manager
        self.manager = forms_service_manager

    @staticmethod
    def _route_dependencies(security: DependsParam | None) -> list[DependsParam] | None:
        """Wrap the security dependency in a list, or return None if no security is provided."""
        return [security] if security else None

    @staticmethod
    def _error_context(request_id: str, operation: str) -> dict[str, str]:
        """Build a structured error context dict for consistent error reporting."""
        return {
            "request_id": request_id,
            "controller": "FormsRestController",
            "operation": operation,
        }

    def prepare(self, app: APIRouter, security: DependsParam | None = None) -> None:
        """Prepare the forms REST controller."""
        route_dependencies = self._route_dependencies(security)

        @app.get(
            "/forms/status",
            status_code=status.HTTP_200_OK,
            tags=["forms"],
            response_model=MetadataRegistryStatusResponse,
            dependencies=route_dependencies,
        )
        def status_endpoint(request: Request):
            """Return the current operational status of the forms module."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("FormsController.status"):
                try:
                    logger.info("forms status requested", extra={"request_id": request_id})
                    return self.forms_service_manager.get_status()
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "status"))

        # ── Entity Type Schema endpoints ───────────────────────────────────────

        @app.get(
            "/forms/config",
            status_code=status.HTTP_200_OK,
            tags=["forms"],
            response_model=EntityTypeSchemaListResponse,
            dependencies=route_dependencies,
        )
        def list_form_entity_schemas_endpoint(
            request: Request,
            actor: FormReadActor,
            entity_type: str | None = None,
        ):
            """Return all entity type schemas for the actor's organization, optionally filtered by entity_type."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("FormsController.list_entity_schemas"):
                try:
                    logger.info("forms list_entity_schemas", extra={"request_id": request_id})
                    return self.forms_service_manager.list_form_entity_schemas_for_actor(
                        actor, entity_type=entity_type
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "list_entity_schemas"))

        @app.post(
            "/forms/config",
            status_code=status.HTTP_201_CREATED,
            tags=["forms"],
            response_model=EntityTypeSchemaResponse,
            dependencies=route_dependencies,
        )
        def create_form_entity_schema_endpoint(
            request: Request,
            payload: EntityTypeSchemaCreateRequest,
            actor: FormWriteActor,
            db: Session = Depends(get_db),
        ):
            """Create a new entity type schema for the actor's organization."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("FormsController.create_entity_schema"):
                try:
                    logger.info("forms create_entity_schema", extra={"request_id": request_id})
                    return self.forms_service_manager.create_form_entity_schema_for_actor(
                        actor, payload, db
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "create_entity_schema"))

        @app.get(
            "/forms/config/{schema_key}",
            status_code=status.HTTP_200_OK,
            tags=["forms"],
            response_model=EntityTypeSchemaResponse,
            dependencies=route_dependencies,
        )
        def get_form_entity_schema_endpoint(
            request: Request,
            schema_key: str,
            actor: FormReadActor,
            db: Session = Depends(get_db),
        ):
            """Return a single entity type schema by its key."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("FormsController.get_entity_schema"):
                try:
                    logger.info("forms get_entity_schema", extra={"request_id": request_id})
                    return self.forms_service_manager.get_form_entity_schema_for_actor(
                        actor, db, schema_key
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "get_entity_schema"))

        @app.put(
            "/forms/config/{schema_key}",
            status_code=status.HTTP_200_OK,
            tags=["forms"],
            response_model=EntityTypeSchemaResponse,
            dependencies=route_dependencies,
        )
        def update_form_entity_schema_endpoint(
            request: Request,
            schema_key: str,
            payload: EntityTypeSchemaUpdateRequest,
            actor: FormWriteActor,
            db: Session = Depends(get_db),
        ):
            """Update an existing entity type schema with the provided fields."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("FormsController.update_entity_schema"):
                try:
                    logger.info("forms update_entity_schema", extra={"request_id": request_id})
                    return self.forms_service_manager.update_form_entity_schema_for_actor(
                        actor, db, schema_key, payload
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "update_entity_schema"))

        @app.delete(
            "/forms/config/{schema_key}",
            status_code=status.HTTP_204_NO_CONTENT,
            tags=["forms"],
            dependencies=route_dependencies,
        )
        def delete_form_entity_schema_endpoint(
            request: Request,
            schema_key: str,
            actor: FormWriteActor,
            db: Session = Depends(get_db),
        ):
            """Delete an entity type schema by its key."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("FormsController.delete_entity_schema"):
                try:
                    logger.info("forms delete_entity_schema", extra={"request_id": request_id})
                    self.forms_service_manager.delete_form_entity_schema_for_actor(
                        actor, db, schema_key
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "delete_entity_schema"))

        # ── Picklist endpoints ─────────────────────────────────────────────────

        @app.get(
            "/config/picklists",
            status_code=status.HTTP_200_OK,
            tags=["forms"],
            response_model=PicklistListResponse,
            dependencies=route_dependencies,
        )
        def list_picklists_endpoint(
            request: Request,
            actor: FormReadActor,
            db: Session = Depends(get_db),
        ):
            """Return all picklists for the actor's organization."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("FormsController.list_picklists"):
                try:
                    logger.info("forms list_picklists", extra={"request_id": request_id})
                    return self.forms_service_manager.list_picklists_for_actor(db, actor)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "list_picklists"))

        @app.post(
            "/config/picklists",
            status_code=status.HTTP_201_CREATED,
            tags=["forms"],
            response_model=PicklistResponse,
            dependencies=route_dependencies,
        )
        def create_picklist_endpoint(
            request: Request,
            payload: PicklistCreateRequest,
            actor: FormWriteActor,
            db: Session = Depends(get_db),
        ):
            """Create a new picklist for the actor's organization."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("FormsController.create_picklist"):
                try:
                    logger.info("forms create_picklist", extra={"request_id": request_id})
                    return self.forms_service_manager.create_picklist_for_actor(db, actor, payload)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "create_picklist"))

        @app.get(
            "/config/picklists/{picklist_id}",
            status_code=status.HTTP_200_OK,
            tags=["forms"],
            response_model=PicklistResponse,
            dependencies=route_dependencies,
        )
        def get_picklist_endpoint(
            request: Request,
            picklist_id: str,
            actor: FormReadActor,
            db: Session = Depends(get_db),
        ):
            """Return a single picklist by its ID."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("FormsController.get_picklist"):
                try:
                    logger.info("forms get_picklist", extra={"request_id": request_id})
                    return self.forms_service_manager.get_picklist_for_actor(db, actor, picklist_id)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "get_picklist"))

        @app.put(
            "/config/picklists/{picklist_id}",
            status_code=status.HTTP_200_OK,
            tags=["forms"],
            response_model=PicklistResponse,
            dependencies=route_dependencies,
        )
        def update_picklist_endpoint(
            request: Request,
            picklist_id: str,
            payload: PicklistUpdateRequest,
            actor: FormWriteActor,
            db: Session = Depends(get_db),
        ):
            """Update an existing picklist with the provided options."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("FormsController.update_picklist"):
                try:
                    logger.info("forms update_picklist", extra={"request_id": request_id})
                    return self.forms_service_manager.update_picklist_for_actor(
                        db, actor, picklist_id, payload
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "update_picklist"))

        @app.delete(
            "/config/picklists/{picklist_id}",
            status_code=status.HTTP_204_NO_CONTENT,
            tags=["forms"],
            dependencies=route_dependencies,
        )
        def delete_picklist_endpoint(
            request: Request,
            picklist_id: str,
            actor: FormWriteActor,
            db: Session = Depends(get_db),
        ):
            """Delete a picklist by its ID."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("FormsController.delete_picklist"):
                try:
                    logger.info("forms delete_picklist", extra={"request_id": request_id})
                    self.forms_service_manager.delete_picklist_for_actor(db, actor, picklist_id)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "delete_picklist"))

        @app.post(
            "/forms/public/submit",
            status_code=status.HTTP_200_OK,
            tags=["forms"],
        )
        def submit_public_form_by_token_endpoint(
            request: Request,
            payload: dict = Body(default={}),
            db: Session = Depends(get_db),
        ):
            """Accept a public form submission via signed token."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("FormsController.submit_public_form_by_token"):
                try:
                    token = str(payload.get("token") or "").strip()
                    fields = payload.get("fields") or {}
                    return self.forms_service_manager.submit_public_form_by_token(db, token, fields)
                except Exception as exc:
                    raise_http_error(
                        exc, self._error_context(request_id, "submit_public_form_by_token")
                    )

        @app.get(
            "/forms/public/{token}",
            status_code=status.HTTP_200_OK,
            tags=["forms"],
        )
        def get_public_form_by_token_endpoint(
            request: Request, token: str, db: Session = Depends(get_db)
        ):
            """Return the public form data for a signed form token."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("FormsController.get_public_form_by_token"):
                try:
                    return self.forms_service_manager.get_public_form_by_token(db, token)
                except Exception as exc:
                    raise_http_error(
                        exc, self._error_context(request_id, "get_public_form_by_token")
                    )

        @app.get(
            "/forms/public/entity/{entity_id}",
            status_code=status.HTTP_200_OK,
            tags=["forms"],
        )
        def get_public_form_endpoint(
            request: Request, entity_id: str, db: Session = Depends(get_db)
        ):
            """Return the public form data for an entity's pending receive_data run."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("FormsController.get_public_form"):
                try:
                    logger.info("forms get_public_form", extra={"request_id": request_id})
                    return self.forms_service_manager.get_public_form_by_entity(db, entity_id)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "get_public_form"))

        @app.post(
            "/forms/public/entity/{entity_id}/submit",
            status_code=status.HTTP_200_OK,
            tags=["forms"],
        )
        def submit_public_form_endpoint(
            request: Request,
            entity_id: str,
            payload: dict = Body(default={}),
            db: Session = Depends(get_db),
        ):
            """Accept a public form submission and advance the workflow via the configured trigger."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("FormsController.submit_public_form"):
                try:
                    logger.info("forms submit_public_form", extra={"request_id": request_id})
                    fields = payload.get("fields") or {}
                    return self.forms_service_manager.submit_public_form_by_entity(
                        db, entity_id, fields
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "submit_public_form"))
