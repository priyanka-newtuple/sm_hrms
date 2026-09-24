"""Entities REST controller module."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, status

from common.auth import build_actor_context, require_permission
from common.logger import logger, tracer
from common.utils import raise_http_error
from entities.models.request import (
    EntityAssigneeUpdateRequest,
    EntityRecordCreateRequest,
    EntityRecordUpdateRequest,
    EntityRelationCreateRequest,
    EntityRelationDeclarationCreateRequest,
    EntityRelationDeclarationUpdateRequest,
    EntityTypeCreateRequest,
    EntityTypeRelationCreateRequest,
    EntityTypeUpdateRequest,
)
from entities.models.response import (
    EntityRecordListResponse,
    EntityRecordResponse,
    EntityRecordSummaryPage,
    EntityRelationListResponse,
    EntityRelationResponse,
    EntityThumbnailUrlResponse,
    EntityTypeRecordListResponse,
    EntityTypeRecordResponse,
    EntityTypeRelationDeleteResponse,
    EntityTypeRelationListResponse,
    EntityTypeRelationResponse,
    EntityWithStatesResponse,
    MetadataRegistryStatusResponse,
    RelatedEntityFileListResponse,
)

from blob_storage.service import BlobStorageService

if TYPE_CHECKING:
    from fastapi.params import Depends as DependsParam

    from auth.manager import AuthServiceManager
    from database.manager import DatabaseServiceManager
    from entities.manager import EntitiesServiceManager

EntityReadActor = Annotated[dict[str, object], Depends(build_actor_context)]
EntityWriteActor = Annotated[dict[str, object], Depends(require_permission("entity_record", "write"))]


class EntitiesRestController:
    """Implements entities REST controller."""

    def __init__(
        self,
        entities_service_manager: EntitiesServiceManager,
        database_service_manager: DatabaseServiceManager | None = None,
        auth_service_manager: AuthServiceManager | None = None,
        blob_storage_service: BlobStorageService | None = None,
    ) -> None:
        _ = database_service_manager, auth_service_manager
        self.manager = entities_service_manager
        self.blob_storage = blob_storage_service if blob_storage_service is not None else BlobStorageService()

    @staticmethod
    def _route_dependencies(security: DependsParam | None) -> list[DependsParam] | None:
        """Build the FastAPI dependency tuple for protected routes."""
        return [security] if security else None

    @staticmethod
    def _error_context(request_id: str, operation: str) -> dict[str, str]:
        return {
            "request_id": request_id,
            "controller": "EntitiesRestController",
            "operation": operation,
        }

    def prepare(self, app: APIRouter, security: DependsParam | None = None) -> None:
        """Prepare the entities REST controller."""
        route_dependencies = self._route_dependencies(security)
        @app.get(
            "/entities/status",
            status_code=status.HTTP_200_OK,
            tags=["entities"],
            response_model=MetadataRegistryStatusResponse,
            dependencies=route_dependencies,
        )
        def status_endpoint(request: Request):
            """GET /entities/status — module health probe."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("EntitiesController.status"):
                try:
                    logger.info("entities status requested", extra={"request_id": request_id})
                    return self.manager.get_status()
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "status"))

        @app.get(
            "/metadata_registry/status",
            status_code=status.HTTP_200_OK,
            tags=["metadata_registry"],
            response_model=MetadataRegistryStatusResponse,
            dependencies=route_dependencies,
        )
        def legacy_status_endpoint(request: Request):
            """GET /metadata/status — legacy alias kept for older clients."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("EntitiesController.legacy_status"):
                try:
                    logger.info(
                        "metadata_registry status requested", extra={"request_id": request_id}
                    )
                    return self.manager.get_status()
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "legacy_status"))

        # ── /entity-types (canonical entity type registry) ──────────────────

        @app.post(
            "/entity-types",
            status_code=status.HTTP_201_CREATED,
            tags=["entity-types"],
            response_model=EntityTypeRecordResponse,
            dependencies=route_dependencies,
        )
        def create_entity_type_endpoint(
            request: Request,
            payload: EntityTypeCreateRequest,
            actor: EntityWriteActor,
        ):
            """POST /entity-types — register a new entity type."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("EntitiesController.create_entity_type"):
                try:
                    logger.info("entity_types create", extra={"request_id": request_id})
                    return self.manager.create_entity_type_for_actor(actor, payload)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "create_entity_type"))

        @app.get(
            "/entity-types",
            status_code=status.HTTP_200_OK,
            tags=["entity-types"],
            response_model=EntityTypeRecordListResponse,
            dependencies=route_dependencies,
        )
        def list_entity_types_endpoint(
            request: Request,
            actor: EntityReadActor,
        ):
            """GET /entity-types — list entity types in the actor's org."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("EntitiesController.list_entity_types"):
                try:
                    logger.info("entity_types list", extra={"request_id": request_id})
                    return self.manager.list_entity_type_records_for_actor(actor)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "list_entity_types"))

        @app.get(
            "/entity-types/{name}",
            status_code=status.HTTP_200_OK,
            tags=["entity-types"],
            response_model=EntityTypeRecordResponse,
            dependencies=route_dependencies,
        )
        def get_entity_type_endpoint(
            request: Request,
            name: str,
            actor: EntityReadActor,
        ):
            """GET /entity-types/{name} — fetch the latest version of an entity type."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("EntitiesController.get_entity_type"):
                try:
                    logger.info("entity_types get", extra={"request_id": request_id})
                    return self.manager.get_entity_type_record_for_actor(actor, name)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "get_entity_type"))

        @app.put(
            "/entity-types/{name}",
            status_code=status.HTTP_200_OK,
            tags=["entity-types"],
            response_model=EntityTypeRecordResponse,
            dependencies=route_dependencies,
        )
        def update_entity_type_endpoint(
            request: Request,
            name: str,
            payload: EntityTypeUpdateRequest,
            actor: EntityWriteActor,
        ):
            """PATCH /entity-types/{name} — update mutable fields on an entity type."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("EntitiesController.update_entity_type"):
                try:
                    logger.info("entity_types update", extra={"request_id": request_id})
                    return self.manager.update_entity_type_for_actor(actor, name, payload)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "update_entity_type"))

        @app.delete(
            "/entity-types/{name}",
            status_code=status.HTTP_200_OK,
            tags=["entity-types"],
            response_model=EntityTypeRecordResponse,
            dependencies=route_dependencies,
        )
        def archive_entity_type_endpoint(
            request: Request,
            name: str,
            actor: EntityWriteActor,
        ):
            """DELETE /entity-types/{name} — soft-delete (is_active=False)."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("EntitiesController.archive_entity_type"):
                try:
                    logger.info("entity_types archive", extra={"request_id": request_id})
                    return self.manager.archive_entity_type_for_actor(actor, name)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "archive_entity_type"))

        @app.patch(
            "/entity-types/{entity_type_id}/toggle",
            status_code=status.HTTP_200_OK,
            tags=["entity-types"],
            response_model=EntityTypeRecordResponse,
            dependencies=route_dependencies,
        )
        def toggle_entity_type_endpoint(
            request: Request,
            entity_type_id: str,
            actor: EntityWriteActor,
        ):
            """POST /entity-types/{entity_type_id}/toggle — flip is_active between True and False."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("EntitiesController.toggle_entity_type"):
                try:
                    logger.info("entity_types toggle", extra={"request_id": request_id})
                    return self.manager.toggle_entity_type_for_actor(actor, entity_type_id)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "toggle_entity_type"))

        @app.get(
            "/entity-types/{name}/auto-number-preview",
            status_code=status.HTTP_200_OK,
            tags=["entity-types"],
            dependencies=route_dependencies,
        )
        def auto_number_preview_endpoint(
            request: Request,
            name: str,
            actor: EntityReadActor,
        ):
            """GET /entity-types/{name}/auto-number-preview — next formatted value per auto_number field."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("EntitiesController.auto_number_preview"):
                try:
                    return self.manager.get_auto_number_previews_for_actor(actor, name)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "auto_number_preview"))

        # ── /entity-types/{entity_type_id}/relations ────────────────────────

        @app.post(
            "/entity-types/{entity_type_id}/relations",
            status_code=status.HTTP_201_CREATED,
            tags=["entity-types"],
            response_model=EntityTypeRelationResponse,
            dependencies=route_dependencies,
        )
        def create_entity_type_relation_endpoint(
            request: Request,
            entity_type_id: str,
            payload: EntityTypeRelationCreateRequest,
            actor: EntityWriteActor,
        ):
            """POST /entity-types/{entity_type_id}/relations — define a new allowed relation."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("EntitiesController.create_entity_type_relation"):
                try:
                    logger.info("entity_type_relations create", extra={"request_id": request_id})
                    normalized = EntityTypeRelationCreateRequest(
                        from_entity_type_id=entity_type_id,
                        to_entity_type_id=payload.to_entity_type_id,
                        relation_name=payload.relation_name,
                    )
                    return self.manager.create_entity_type_relation_for_actor(actor, normalized)
                except Exception as exc:
                    raise_http_error(
                        exc, self._error_context(request_id, "create_entity_type_relation")
                    )

        @app.get(
            "/entity-types/{entity_type_id}/relations",
            status_code=status.HTTP_200_OK,
            tags=["entity-types"],
            response_model=EntityTypeRelationListResponse,
            dependencies=route_dependencies,
        )
        def list_entity_type_relations_endpoint(
            request: Request,
            entity_type_id: str,
            actor: EntityReadActor,
        ):
            """GET /entity-types/{entity_type_id}/relations — list allowed relations for a type."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("EntitiesController.list_entity_type_relations"):
                try:
                    logger.info("entity_type_relations list", extra={"request_id": request_id})
                    return self.manager.list_entity_type_relations_for_actor(
                        actor, from_entity_type_id=entity_type_id
                    )
                except Exception as exc:
                    raise_http_error(
                        exc, self._error_context(request_id, "list_entity_type_relations")
                    )

        @app.delete(
            "/entity-types/{entity_type_id}/relations/{relation_def_id}",
            status_code=status.HTTP_204_NO_CONTENT,
            tags=["entity-types"],
            dependencies=route_dependencies,
        )
        def delete_entity_type_relation_endpoint(
            request: Request,
            entity_type_id: str,
            relation_def_id: str,
            actor: EntityWriteActor,
        ):
            """DELETE /entity-types/{entity_type_id}/relations/{relation_def_id} — remove a relation definition."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("EntitiesController.delete_entity_type_relation"):
                try:
                    logger.info("entity_type_relations delete", extra={"request_id": request_id})
                    self.manager.delete_entity_type_relation_for_actor(actor, relation_def_id)
                except Exception as exc:
                    raise_http_error(
                        exc, self._error_context(request_id, "delete_entity_type_relation")
                    )

        # ── /entity-types/{entity_type_id}/relation-declarations ────────────
        # Field-inheritance relation declarations (REFERENCE/SNAPSHOT). Kept
        # distinct from the legacy named-relation endpoints above.

        @app.post(
            "/entity-types/{entity_type_id}/relation-declarations",
            status_code=status.HTTP_201_CREATED,
            tags=["entity-types"],
            response_model=EntityTypeRelationResponse,
            dependencies=route_dependencies,
        )
        def create_entity_relation_declaration_endpoint(
            request: Request,
            entity_type_id: str,
            payload: EntityRelationDeclarationCreateRequest,
            actor: EntityWriteActor,
        ):
            """POST /entity-types/{entity_type_id}/relation-declarations — declare a
            field-inheritance relation from `entity_type_id` to another entity type.

            Use: schema-design time call by an admin wiring up REFERENCE/SNAPSHOT
            field inheritance between two entity types.
            Args: `entity_type_id` (source type, path), payload (to_entity_type_id,
            relation_type, relation_metadata), actor (write-authorized).
            Raises: 400 if either entity type doesn't exist, 409 if an active
            declaration already exists for this type pair.
            Returns: the persisted declaration.
            """
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("EntitiesController.create_entity_relation_declaration"):
                try:
                    logger.info("relation_declarations create", extra={"request_id": request_id})
                    normalized = EntityRelationDeclarationCreateRequest(
                        from_entity_type_id=entity_type_id,
                        to_entity_type_id=payload.to_entity_type_id,
                        relation_type=payload.relation_type,
                        relation_metadata=payload.relation_metadata,
                    )
                    return self.manager.create_entity_relation_declaration_for_actor(
                        actor, normalized
                    )
                except Exception as exc:
                    raise_http_error(
                        exc, self._error_context(request_id, "create_entity_relation_declaration")
                    )

        @app.get(
            "/entity-types/{entity_type_id}/relation-declarations",
            status_code=status.HTTP_200_OK,
            tags=["entity-types"],
            response_model=EntityTypeRelationListResponse,
            dependencies=route_dependencies,
        )
        def list_entity_relation_declarations_endpoint(
            request: Request,
            entity_type_id: str,
            actor: EntityReadActor,
            direction: str = "from",
        ):
            """GET /entity-types/{entity_type_id}/relation-declarations — list active
            declarations involving this type.

            Use: settings UI lists a type's relations (`direction=both`); the form
            builder and record-create flows list providers for a target (`direction=to`).
            Args: `entity_type_id` (path), `direction` query — one of from|to|both.
            Raises: 400 on an invalid direction.
            Returns: active declarations, oldest first.
            """
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("EntitiesController.list_entity_relation_declarations"):
                try:
                    logger.info("relation_declarations list", extra={"request_id": request_id})
                    return self.manager.list_entity_relation_declarations_for_actor(
                        actor, entity_type_id, direction=direction
                    )
                except Exception as exc:
                    raise_http_error(
                        exc, self._error_context(request_id, "list_entity_relation_declarations")
                    )

        @app.get(
            "/entity-types/{from_entity_type_id}/relation-declarations/{to_entity_type_id}",
            status_code=status.HTTP_200_OK,
            tags=["entity-types"],
            response_model=EntityTypeRelationResponse,
            dependencies=route_dependencies,
        )
        def get_entity_relation_declaration_endpoint(
            request: Request,
            from_entity_type_id: str,
            to_entity_type_id: str,
            actor: EntityReadActor,
        ):
            """GET /entity-types/{from_entity_type_id}/relation-declarations/{to_entity_type_id}
            — fetch the single active declaration for this type pair, if one exists.

            Use: look up whether a declaration already exists for a type pair before
            deciding to POST (create) or PATCH (update) — avoids relying on locally
            cached state that can drift from the backend.
            Args: `from_entity_type_id`, `to_entity_type_id` (path), actor (read-authorized).
            Raises: 404 if no active declaration exists for this pair.
            Returns: the active declaration.
            """
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("EntitiesController.get_entity_relation_declaration"):
                try:
                    logger.info("relation_declarations get", extra={"request_id": request_id})
                    return self.manager.get_entity_relation_declaration_for_actor(
                        actor, from_entity_type_id, to_entity_type_id
                    )
                except Exception as exc:
                    raise_http_error(
                        exc, self._error_context(request_id, "get_entity_relation_declaration")
                    )

        @app.patch(
            "/entity-types/relation-declarations/{relation_def_id}",
            status_code=status.HTTP_200_OK,
            tags=["entity-types"],
            response_model=EntityTypeRelationResponse,
            dependencies=route_dependencies,
        )
        def update_entity_relation_declaration_endpoint(
            request: Request,
            relation_def_id: str,
            payload: EntityRelationDeclarationUpdateRequest,
            actor: EntityWriteActor,
        ):
            """PATCH /entity-types/relation-declarations/{relation_def_id} — update
            the field mappings on an active relation declaration.

            Use: admin edits which fields are inherited after schema design time.
            Args: `relation_def_id` (path), payload (relation_metadata), actor.
            Raises: 404 if not found/already deleted.
            Returns: the updated declaration.
            """
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("EntitiesController.update_entity_relation_declaration"):
                try:
                    logger.info("relation_declarations update", extra={"request_id": request_id})
                    return self.manager.update_entity_relation_declaration_for_actor(
                        actor, relation_def_id, payload
                    )
                except Exception as exc:
                    raise_http_error(
                        exc, self._error_context(request_id, "update_entity_relation_declaration")
                    )

        @app.delete(
            "/entity-types/relation-declarations/{relation_def_id}",
            status_code=status.HTTP_200_OK,
            tags=["entity-types"],
            response_model=EntityTypeRelationDeleteResponse,
            dependencies=route_dependencies,
        )
        def delete_entity_relation_declaration_endpoint(
            request: Request,
            relation_def_id: str,
            actor: EntityWriteActor,
        ):
            """DELETE /entity-types/relation-declarations/{relation_def_id} — soft-delete
            an active relation declaration.

            Use: admin retires a field-inheritance relation. Existing links in
            `entity_relations` are left in place but stop resolving.
            Args: `relation_def_id` (path), actor (write-authorized).
            Raises: 404 if not found or already deleted.
            Returns: `{relation_def_id, deleted_at}`.
            """
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("EntitiesController.delete_entity_relation_declaration"):
                try:
                    logger.info("relation_declarations delete", extra={"request_id": request_id})
                    return self.manager.delete_entity_relation_declaration_for_actor(
                        actor, relation_def_id
                    )
                except Exception as exc:
                    raise_http_error(
                        exc, self._error_context(request_id, "delete_entity_relation_declaration")
                    )

        # ── /entity-records (runtime entity instances) ──────────────────────

        @app.post(
            "/entity-records",
            status_code=status.HTTP_201_CREATED,
            tags=["entity-records"],
            response_model=EntityRecordResponse,
            dependencies=route_dependencies,
        )
        def create_entity_record_endpoint(
            request: Request,
            payload: EntityRecordCreateRequest,
            actor: EntityWriteActor,
        ):
            """POST /entity-records — create a runtime entity instance."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("EntitiesController.create_entity_record"):
                try:
                    logger.info("entity_records create", extra={"request_id": request_id})
                    return self.manager.create_entity_record_for_actor(actor, payload)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "create_entity_record"))

        @app.get(
            "/entity-records",
            status_code=status.HTTP_200_OK,
            tags=["entity-records"],
            response_model=EntityRecordListResponse,
            dependencies=route_dependencies,
        )
        def list_entity_records_endpoint(
            request: Request,
            actor: EntityReadActor,
            entity_type_id: str | None = None,
            entity_type_name: str | None = None,
            include_archived: bool = False,
            search: str | None = None,
            limit: int | None = None,
        ):
            """GET /entity-records — paginated list of entity records.
            Scoped to the actor's organization.
            Supports filtering by `entity_type_id` (UUID) or `entity_type_name` (string).
            When `entity_type_name` is provided it takes precedence over `entity_type_id`;
            `search` (substring over record data) and `limit` (max 100) apply on the
            `entity_type_name` path."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("EntitiesController.list_entity_records"):
                try:
                    logger.info("entity_records list", extra={"request_id": request_id})
                    if entity_type_name:
                        return self.manager.list_entity_records_by_type_name_for_actor(
                            actor,
                            entity_type_name,
                            include_archived=include_archived,
                            search=search,
                            limit=limit,
                        )
                    return self.manager.list_entity_records_for_actor(
                        actor,
                        entity_type_id=entity_type_id,
                        include_archived=include_archived,
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "list_entity_records"))

        @app.get(
            "/entity-records/summary",
            status_code=status.HTTP_200_OK,
            tags=["entity-records"],
            response_model=EntityRecordSummaryPage,
            dependencies=route_dependencies,
        )
        def list_entity_record_summaries_endpoint(
            request: Request,
            actor: EntityReadActor,
            entity_type_id: str | None = Query(default=None),
            entity_type_name: str | None = Query(default=None),
            include_archived: bool = Query(default=False),
            anchor_entity_id: str | None = Query(default=None),
            fields: str | None = Query(default=None),
            limit: int = Query(default=50, ge=1, le=200),
            cursor: str | None = Query(default=None),
        ):
            """Return a bounded, permission-filtered entity summary page."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("EntitiesController.list_entity_record_summaries"):
                try:
                    selected_fields = {
                        value.strip() for value in (fields or "").split(",") if value.strip()
                    }
                    return self.manager.list_entity_record_summaries_for_actor(
                        actor,
                        entity_type_id=entity_type_id,
                        entity_type_name=entity_type_name,
                        include_archived=include_archived,
                        anchor_entity_id=anchor_entity_id,
                        fields=selected_fields,
                        limit=limit,
                        cursor=cursor,
                    )
                except Exception as exc:
                    raise_http_error(
                        exc, self._error_context(request_id, "list_entity_record_summaries")
                    )

        @app.get(
            "/entity-records/{entity_id}",
            status_code=status.HTTP_200_OK,
            tags=["entity-records"],
            response_model=EntityRecordResponse,
            dependencies=route_dependencies,
        )
        def get_entity_record_endpoint(
            request: Request,
            entity_id: str,
            actor: EntityReadActor,
        ):
            """GET /entity-records/{entity_id} — fetch one entity by id.
            Scoped to the actor's organization."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("EntitiesController.get_entity_record"):
                try:
                    logger.info("entity_records get", extra={"request_id": request_id})
                    return self.manager.get_entity_record_for_actor(actor, entity_id)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "get_entity_record"))

        @app.put(
            "/entity-records/{entity_id}",
            status_code=status.HTTP_200_OK,
            tags=["entity-records"],
            response_model=EntityRecordResponse,
            dependencies=route_dependencies,
        )
        def update_entity_record_endpoint(
            request: Request,
            entity_id: str,
            payload: EntityRecordUpdateRequest,
            actor: EntityWriteActor,
        ):
            """PUT /entity-records/{entity_id} — put entity data/owner.
            Scoped to the actor's organization."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("EntitiesController.update_entity_record"):
                try:
                    logger.info("entity_records update", extra={"request_id": request_id})
                    return self.manager.update_entity_record_for_actor(actor, entity_id, payload)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "update_entity_record"))

        @app.put(
            "/entity-records/{entity_id}/assignee",
            status_code=status.HTTP_200_OK,
            tags=["entity-records"],
            response_model=EntityRecordResponse,
            dependencies=route_dependencies,
        )
        def set_entity_assignee_endpoint(
            request: Request,
            entity_id: str,
            payload: EntityAssigneeUpdateRequest,
            actor: EntityWriteActor,
            background_tasks: BackgroundTasks,
        ):
            """PUT /entity-records/{entity_id}/assignee — assign the entity to a
            user, to its original creator (`assign_to_originator`), or clear it
            (assignee_id omitted/blank). Every assignment requires entity edit
            permission, self-assignment included."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("EntitiesController.set_entity_assignee"):
                try:
                    logger.info(
                        "entity_records set_assignee",
                        extra={
                            "request_id": request_id,
                            "assign_to_originator": payload.assign_to_originator,
                        },
                    )
                    return self.manager.set_entity_assignee_for_actor(
                        actor,
                        entity_id,
                        payload.assignee_id,
                        assign_to_originator=payload.assign_to_originator,
                        background_tasks=background_tasks,
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "set_entity_assignee"))

        @app.delete(
            "/entity-records/{entity_id}",
            status_code=status.HTTP_200_OK,
            tags=["entity-records"],
            response_model=EntityRecordResponse,
            dependencies=route_dependencies,
        )
        def archive_entity_record_endpoint(
            request: Request,
            entity_id: str,
            actor: EntityWriteActor,
        ):
            """DELETE /entity-records/{entity_id} — soft-archive an entity.
            Scoped to the actor's organization."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("EntitiesController.archive_entity_record"):
                try:
                    logger.info("entity_records archive", extra={"request_id": request_id})
                    return self.manager.archive_entity_record_for_actor(actor, entity_id)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "archive_entity_record"))

        @app.post(
            "/entity-records/{entity_id}/restore",
            status_code=status.HTTP_200_OK,
            tags=["entity-records"],
            response_model=EntityRecordResponse,
            dependencies=route_dependencies,
        )
        def restore_entity_record_endpoint(
            request: Request,
            entity_id: str,
            actor: EntityWriteActor,
        ):
            """POST /entity-records/{entity_id}/restore — clear archived_at on
            a previously archived entity. Scoped to the actor's organization.
            404 if no entity exists for the id."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("EntitiesController.restore_entity_record"):
                try:
                    logger.info("entity_records restore", extra={"request_id": request_id})
                    return self.manager.restore_entity_record_for_actor(actor, entity_id)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "restore_entity_record"))

        @app.get(
            "/entity-records/{entity_id}/thumbnail-url",
            status_code=status.HTTP_200_OK,
            tags=["entity-records"],
            response_model=EntityThumbnailUrlResponse,
            dependencies=route_dependencies,
        )
        def get_entity_thumbnail_url_endpoint(
            request: Request,
            entity_id: str,
            field: str,
            actor: EntityReadActor,
        ):
            """GET /entity-records/{entity_id}/thumbnail-url — return a fresh URL for the dot-path field in entity data."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("EntitiesController.get_entity_thumbnail_url"):
                try:
                    logger.info("entity_records thumbnail_url", extra={"request_id": request_id})
                    record = self.manager.get_entity_record_for_actor(actor, entity_id)
                    url = self.blob_storage.get_fresh_url(record.data, field)
                    return EntityThumbnailUrlResponse(url=url)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "get_entity_thumbnail_url"))

        @app.get(
            "/entity-records/{entity_id}/with-states",
            status_code=status.HTTP_200_OK,
            tags=["entity-records"],
            response_model=EntityWithStatesResponse,
            dependencies=route_dependencies,
        )
        def get_entity_with_states_endpoint(
            request: Request,
            entity_id: str,
            actor: EntityReadActor,
            include_archived: bool = False,
        ):
            """GET /entity-records/{entity_id}/with-states — fetch the entity
            together with every workflow it is enrolled in. Scoped to the
            actor's organization. Replaces the legacy combined `EntityState`
            shape from the workflow controller."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("EntitiesController.get_entity_with_states"):
                try:
                    logger.info("entity_records with_states", extra={"request_id": request_id})
                    return self.manager.get_entity_with_states_for_actor(
                        actor, entity_id, include_archived=include_archived
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "get_entity_with_states"))

        # ── /entities/{entity_id}/relations (graph edges) ───────────────────

        @app.post(
            "/entities/{entity_id}/relations",
            status_code=status.HTTP_201_CREATED,
            tags=["entity-relations"],
            response_model=EntityRelationResponse,
            dependencies=route_dependencies,
        )
        def create_entity_relation_endpoint(
            request: Request,
            entity_id: str,
            payload: EntityRelationCreateRequest,
            actor: EntityWriteActor,
        ):
            """POST /entities/{id}/relations — link two entities."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("EntitiesController.create_entity_relation"):
                try:
                    logger.info("entity_relations create", extra={"request_id": request_id})
                    return self.manager.create_entity_relation_for_actor(actor, entity_id, payload)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "create_entity_relation"))

        @app.get(
            "/entities/{entity_id}/relations",
            status_code=status.HTTP_200_OK,
            tags=["entity-relations"],
            response_model=EntityRelationListResponse,
            dependencies=route_dependencies,
        )
        def list_entity_relations_endpoint(
            request: Request,
            entity_id: str,
            actor: EntityReadActor,
            direction: str = "both",
            relation_type: str | None = None,
        ):
            """GET /entities/{id}/relations — list relations involving the entity."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("EntitiesController.list_entity_relations"):
                try:
                    logger.info("entity_relations list", extra={"request_id": request_id})
                    return self.manager.list_entity_relations_for_actor(
                        actor, entity_id, direction=direction, relation_type=relation_type
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "list_entity_relations"))

        @app.get(
            "/entity-records/{entity_id}/related-files",
            status_code=status.HTTP_200_OK,
            tags=["entity-records"],
            response_model=RelatedEntityFileListResponse,
            dependencies=route_dependencies,
        )
        def list_related_files_endpoint(
            request: Request,
            entity_id: str,
            actor: EntityReadActor,
        ):
            """GET /entity-records/{id}/related-files — list read-only files
            from configured related entities."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("EntitiesController.list_related_files"):
                try:
                    logger.info("entity_records related_files", extra={"request_id": request_id})
                    return self.manager.list_related_files_for_actor(actor, entity_id)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "list_related_files"))

        @app.delete(
            "/entity-relations/{relation_id}",
            status_code=status.HTTP_200_OK,
            tags=["entity-relations"],
            response_model=EntityRelationResponse,
            dependencies=route_dependencies,
        )
        def delete_entity_relation_endpoint(
            request: Request,
            relation_id: str,
            actor: EntityWriteActor,
        ):
            """DELETE /entity-relations/{id} — remove a relation by id."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("EntitiesController.delete_entity_relation"):
                try:
                    logger.info("entity_relations delete", extra={"request_id": request_id})
                    return self.manager.delete_entity_relation_for_actor(actor, relation_id)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "delete_entity_relation"))
