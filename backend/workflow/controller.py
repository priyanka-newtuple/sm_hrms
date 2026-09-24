from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from common.auth import require_permission
from common.logger import logger, tracer
from exceptions import (
    AuthorizationError,
    ConflictError,
    NotFoundError,
    PersistenceError,
    ServiceError,
    ValidationError,
)
from workflow.db_models import SERVICE_PAGE_LIMIT
from workflow.manager import WorkflowServiceManager
from workflow.models.interface import (
    DefinitionReport,
    EntityState,
    StateMachineDefinition,
    StateMachineRecord,
    WorkflowBoardDisplayFieldsRecord,
    WorkflowDraftRecord,
    WorkflowService,
)
from workflow.models.request import (
    EntityDryRunRequest,
    RunFactsRequest,
    StateActionRerunRequest,
    StateMachineValidateRequest,
    TransitionExecuteRequest,
    WorkflowBoardDisplayFieldsUpdateRequest,
    WorkflowDraftCreateRequest,
    WorkflowDraftSeedRequest,
    WorkflowDraftUpdateRequest,
    WorkflowEnrollmentRequest,
    WorkflowListScopeRequest,
    WorkflowPublishRequest,
    WorkflowRowLookupRequest,
    WorkflowScope,
    WorkflowServiceCreateRequest,
    WorkflowServiceRenameRequest,
)
from workflow.models.response import (
    AvailableTransitionsResponse,
    EntityDryRunResponse,
    RunFactsResponse,
    StateActionRerunResponse,
    StateMachinePublishResponse,
    StateMachineValidationResponse,
    StateMachineVersionCompareResponse,
    TransitionExecutionResponse,
    TransitionPreflightResponse,
    WorkflowDraftSaveResponse,
    WorkflowListResponse,
    WorkflowPathsResponse,
    WorkflowEnrollmentSummaryPage,
    WorkflowServiceListResponse,
    WorkflowServiceWithWorkflowsListResponse,
    WorkflowStatusResponse,
)

# Ceiling for the paginated services listing, mirroring method_library's
# MAX_PAGE_LIMIT rather than inventing a different bound.
SERVICE_MAX_PAGE_LIMIT = 200

WorkflowReadActor = Annotated[dict[str, object], Depends(require_permission("workflow", "read"))]
WorkflowWriteActor = Annotated[dict[str, object], Depends(require_permission("workflow", "write"))]

# Max values in a single multi-select field_filters list (e.g. several picked
# labels OR'd together) — bounds the OR clause size in the resulting query.


class WorkflowRestController:
    """Implements workflow REST endpoints."""

    def __init__(
        self,
        workflow_service_manager: WorkflowServiceManager,
        database_service_manager=None,
        auth_service_manager=None,
    ) -> None:
        """Hold the manager + auxiliary deps the route handlers will close over.

        `database_service_manager` and `auth_service_manager` are kept on
        the controller for parity with other modules even though most
        routes just delegate to `workflow_service_manager`."""
        super().__init__()
        self.workflow_service_manager = workflow_service_manager
        self.database_service_manager = database_service_manager
        self.auth_service_manager = auth_service_manager

    @staticmethod
    def _route_dependencies(security: Depends | None) -> list[Depends] | None:
        """Wrap an optional FastAPI Depends in the list shape the decorators expect."""
        if security is None:
            return None
        return [security]

    @staticmethod
    def _raise_http_exception(operation: str, exc: Exception) -> None:
        """Translate manager-layer exceptions into HTTP responses.

        Maps NotFoundError -> 404, ValidationError -> 400, ConflictError -> 409,
        AuthorizationError -> 403, anything else -> 500. Pre-existing
        HTTPException instances are re-raised verbatim. `operation` is
        included in the response detail to make logs easier to grep."""
        if isinstance(exc, HTTPException):
            logger.exception(f"workflow {operation} failed: {exc}")
            raise exc
        if isinstance(exc, NotFoundError):
            logger.warning(f"workflow {operation} 404 not found: {exc}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
        if isinstance(exc, (ValidationError, ValueError)):
            logger.warning(f"workflow {operation} 400 bad request: {exc}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
        if isinstance(exc, (AuthorizationError, PermissionError)):
            logger.warning(f"workflow {operation} 403 forbidden: {exc}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
        if isinstance(exc, ConflictError):
            logger.warning(f"workflow {operation} 409 conflict: {exc}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
        if isinstance(exc, (PersistenceError, ServiceError)):
            logger.error(f"workflow {operation} 500 internal service error: {exc}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
        logger.error(f"workflow {operation} 500 unhandled error: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error"
        )

    @staticmethod
    def _parse_inputs_json(raw: str | None) -> dict[str, object]:
        """Parse optional transition inputs passed through a query string."""
        if raw is None or not raw.strip():
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"inputs_json must be valid JSON: {exc.msg}",
            ) from exc
        if not isinstance(parsed, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="inputs_json must decode to a JSON object",
            )
        return parsed

    def prepare(self, app: APIRouter, security: Depends | None = None) -> None:
        """Prepare the workflow REST controller."""
        route_dependencies = self._route_dependencies(security)

        @app.get(
            "/workflow-state-machines/status",
            status_code=status.HTTP_200_OK,
            tags=["state-machines"],
            response_model=WorkflowStatusResponse,
            dependencies=route_dependencies,
        )
        def status_endpoint(request: Request):
            """Return workflow module status.

            Use:
            Frontend can call this endpoint to confirm that the compact workflow
            module is wired and healthy before issuing definition or runtime calls.

            Args:
            request: FastAPI request carrying request-scoped tracing metadata.

            Raises:
            HTTPException: Raised when the controller cannot obtain module status.

            Returns:
            WorkflowStatusResponse: Current module name, readiness status, and
            started flag.
            """
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("WorkflowController.status"):
                try:
                    logger.info("workflow status requested", extra={"request_id": request_id})
                    return self.workflow_service_manager.get_status()
                except Exception as exc:
                    self._raise_http_exception("status", exc)

        @app.post(
            "/workflow-state-machines/validate",
            status_code=status.HTTP_200_OK,
            tags=["state-machines"],
            response_model=StateMachineValidationResponse,
            dependencies=route_dependencies,
        )
        def validate_candidate_state_machine_endpoint(
            request: Request,
            actor: WorkflowWriteActor,
            payload: StateMachineValidateRequest,
        ):
            """Validate one candidate state machine definition without persisting it.

            Use:
            Frontend sends the currently built full definition from the UI. Backend
            validates the candidate, persists the validation report, and only runs
            the dry-run simulation when structural validation succeeds.

            Args:
            request: FastAPI request carrying request-scoped tracing metadata.
            payload: Candidate definition validation request.
            actor: Current actor resolved from request headers and role checks.

            Raises:
            HTTPException: Raised when validation cannot be completed.

            Returns:
            StateMachineValidationResponse: Candidate validation outcome plus the
            validation and dry-run reports.
            """
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span(
                "WorkflowController.validate_candidate_state_machine"
            ):
                try:
                    logger.info(
                        "workflow validate_candidate_state_machine",
                        extra={"request_id": request_id},
                    )
                    response = self.workflow_service_manager.validate_candidate_workflow_for_actor(
                        actor, payload
                    )
                    return response
                except Exception as exc:
                    self._raise_http_exception("validate_candidate_state_machine", exc)

        @app.post(
            "/workflow-state-machines/workflow-paths",
            status_code=status.HTTP_200_OK,
            tags=["state-machines"],
            response_model=WorkflowPathsResponse,
            dependencies=route_dependencies,
        )
        def workflow_paths_endpoint(
            request: Request,
            actor: WorkflowWriteActor,
            payload: StateMachineValidateRequest,
        ):
            """Render all currently discoverable workflow paths for a candidate definition."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("WorkflowController.workflow_paths"):
                try:
                    logger.info("workflow workflow_paths", extra={"request_id": request_id})
                    response = self.workflow_service_manager.list_workflow_paths_for_actor(
                        actor, payload
                    )
                    return response
                except Exception as exc:
                    self._raise_http_exception("workflow_paths", exc)

        @app.post(
            "/workflow-state-machines/draft",
            status_code=status.HTTP_201_CREATED,
            tags=["state-machines"],
            response_model=WorkflowDraftRecord,
            dependencies=route_dependencies,
        )
        def create_workflow_draft_endpoint(
            request: Request,
            actor: WorkflowWriteActor,
            payload: WorkflowDraftCreateRequest | None = None,
        ):
            """Create one empty workflow draft.

            Use:
            Frontend calls this endpoint when the user clicks "+" to start a new
            workflow. Backend generates a stable workflow-family `machine_name`, persists a draft
            at version 0 with `is_active=false` and one initial "draft" state.
            No validation runs; the draft is meant to be edited and later
            published as a real version via the publish endpoint.

            Args:
            request: FastAPI request carrying request-scoped tracing metadata.
            payload: Optional draft metadata (name, description).
            actor: Current actor resolved from request headers and role checks.

            Raises:
            HTTPException: Raised when the draft cannot be persisted.

            Returns:
            WorkflowDraftRecord: Persisted draft workflow record.
            """
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("WorkflowController.create_workflow_draft"):
                try:
                    logger.info("workflow create_workflow_draft", extra={"request_id": request_id})
                    return self.workflow_service_manager.create_workflow_draft_for_actor(
                        actor,
                        payload or WorkflowDraftCreateRequest(),
                    )
                except Exception as exc:
                    self._raise_http_exception("create_workflow_draft", exc)

        # ── Static GET routes must appear before /{row_id} so FastAPI does not
        # shadow them. A bare {row_id} segment matches any single path token,
        # including literal strings like "default-template".

        @app.get(
            "/workflow-state-machines",
            status_code=status.HTTP_200_OK,
            tags=["state-machines"],
            response_model=WorkflowListResponse,
            dependencies=route_dependencies,
        )
        def list_state_machines_endpoint(
            request: Request,
            actor: WorkflowReadActor,
            scope: str = Query(default=WorkflowScope.ALL.value),
            machine_name: str | None = Query(default=None),
            include_archived: bool = Query(default=False),
        ):
            """List workflows with scope-aware filtering.

            Use:
            Frontend can fetch published, draft, or all workflow rows in one API.

            Args:
            request: FastAPI request carrying request-scoped tracing metadata.
            actor: Current actor resolved from request headers and role checks.
            scope: One of `published`, `draft`, `all`.
            machine_name: Optional workflow identity filter.

            Raises:
            HTTPException: Raised when the query cannot be completed.

            Returns:
            WorkflowListResponse: Scoped workflow records.
            """
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("WorkflowController.list_state_machines"):
                try:
                    logger.info(
                        f"workflow list_state_machines: scope={scope}",
                        extra={"request_id": request_id},
                    )
                    return self.workflow_service_manager.list_state_machines_scoped_for_actor(
                        actor,
                        WorkflowListScopeRequest(scope=scope, machine_name=machine_name),
                        include_archived=include_archived,
                    )
                except Exception as exc:
                    self._raise_http_exception("list_state_machines", exc)

        @app.get(
            "/workflow-state-machines/default-template",
            status_code=status.HTTP_200_OK,
            tags=["state-machines"],
            response_model=StateMachineDefinition,
            dependencies=route_dependencies,
        )
        def get_default_template_endpoint(
            request: Request,
            actor: WorkflowReadActor,
        ):
            """Return the canonical default state machine definition template.

            Use:
            Frontend calls this endpoint to retrieve the current backend-defined
            job application workflow schema. The returned definition is used as
            the body for validate and publish requests, so the frontend never
            needs to hardcode field names, states, or transitions. When
            the backend definition changes, the frontend picks up the new schema
            on the next call to this endpoint.

            Args:
            request: FastAPI request carrying request-scoped tracing metadata.
            actor: Current actor resolved from request headers and role checks.

            Raises:
            HTTPException: Raised when the template cannot be retrieved.

            Returns:
            StateMachineDefinition: The current canonical workflow definition.
            """
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("WorkflowController.get_default_template"):
                try:
                    logger.info("workflow get_default_template", extra={"request_id": request_id})
                    return self.workflow_service_manager.get_default_template_for_actor(actor)
                except Exception as exc:
                    self._raise_http_exception("get_default_template", exc)

        @app.post(
            "/workflow-state-machines/services",
            status_code=status.HTTP_201_CREATED,
            tags=["state-machines"],
            response_model=WorkflowService,
            dependencies=route_dependencies,
        )
        def create_workflow_service_endpoint(
            request: Request, payload: WorkflowServiceCreateRequest, actor: WorkflowWriteActor
        ):
            """Create a service. Names are unique per organization, ignoring case."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("WorkflowController.create_service"):
                try:
                    logger.info("workflow create_service", extra={"request_id": request_id})
                    return self.workflow_service_manager.create_service_for_actor(actor, payload)
                except Exception as exc:
                    self._raise_http_exception("create_service", exc)

        @app.get(
            "/workflow-state-machines/services",
            status_code=status.HTTP_200_OK,
            tags=["state-machines"],
            response_model=WorkflowServiceListResponse,
            dependencies=route_dependencies,
        )
        def list_workflow_services_endpoint(request: Request, actor: WorkflowReadActor):
            """Every service in the actor's organization, ordered by name."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("WorkflowController.list_services"):
                try:
                    logger.info("workflow list_services", extra={"request_id": request_id})
                    items = self.workflow_service_manager.list_services_for_actor(actor)
                    return WorkflowServiceListResponse(
                        organization_id=str(actor.get("organization_id") or ""), items=items
                    )
                except Exception as exc:
                    self._raise_http_exception("list_services", exc)

        # Registered before the /services/{service_id} routes so the literal
        # path segment is matched first and never read as a service id.
        @app.get(
            "/workflow-state-machines/services/with-workflows",
            status_code=status.HTTP_200_OK,
            tags=["state-machines"],
            response_model=WorkflowServiceWithWorkflowsListResponse,
            dependencies=route_dependencies,
        )
        def list_workflow_services_with_workflows_endpoint(
            request: Request,
            actor: WorkflowReadActor,
            limit: int = Query(default=SERVICE_PAGE_LIMIT, ge=1, le=SERVICE_MAX_PAGE_LIMIT),
            offset: int = Query(default=0, ge=0),
        ):
            """A page of services, each with the workflows filed under it.

            Paginated over services: `total` counts every service in the
            organization, while each item carries its own full workflow list,
            one entry per machine name at its highest non-archived version.
            """
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("WorkflowController.list_services_with_workflows"):
                try:
                    logger.info(
                        "workflow list_services_with_workflows", extra={"request_id": request_id}
                    )
                    items, total = (
                        self.workflow_service_manager.list_services_with_workflows_for_actor(
                            actor, limit=limit, offset=offset
                        )
                    )
                    return WorkflowServiceWithWorkflowsListResponse(
                        organization_id=str(actor.get("organization_id") or ""),
                        items=items,
                        total=total,
                        limit=limit,
                        offset=offset,
                    )
                except Exception as exc:
                    self._raise_http_exception("list_services_with_workflows", exc)

        @app.patch(
            "/workflow-state-machines/services/{service_id}",
            status_code=status.HTTP_200_OK,
            tags=["state-machines"],
            response_model=WorkflowService,
            dependencies=route_dependencies,
        )
        def rename_workflow_service_endpoint(
            request: Request,
            service_id: str,
            payload: WorkflowServiceRenameRequest,
            actor: WorkflowWriteActor,
        ):
            """Rename a service. Its workflows stay filed under it."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("WorkflowController.rename_service"):
                try:
                    logger.info(
                        f"workflow rename_service: service_id={service_id}",
                        extra={"request_id": request_id},
                    )
                    return self.workflow_service_manager.rename_service_for_actor(
                        actor, service_id, payload
                    )
                except Exception as exc:
                    self._raise_http_exception("rename_service", exc)

        @app.delete(
            "/workflow-state-machines/services/{service_id}",
            status_code=status.HTTP_204_NO_CONTENT,
            tags=["state-machines"],
            dependencies=route_dependencies,
        )
        def delete_workflow_service_endpoint(
            request: Request, service_id: str, actor: WorkflowWriteActor
        ):
            """Delete a service. Refused while a workflow is still filed under it."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("WorkflowController.delete_service"):
                try:
                    logger.info(
                        f"workflow delete_service: service_id={service_id}",
                        extra={"request_id": request_id},
                    )
                    self.workflow_service_manager.delete_service_for_actor(actor, service_id)
                except Exception as exc:
                    self._raise_http_exception("delete_service", exc)
        @app.get(
            "/workflow-board-display-fields",
            status_code=status.HTTP_200_OK,
            tags=["state-machines"],
            response_model=WorkflowBoardDisplayFieldsRecord,
            dependencies=route_dependencies,
        )
        def get_workflow_board_display_fields_endpoint(
            request: Request,
            actor: WorkflowReadActor,
            machine_name: str = Query(...),
        ):
            """Fetch the extra entity fields configured for one workflow's Kanban cards.

            Use:
            The Kanban board's "Card fields" picker calls this on load so the
            picker's checked state and the cards' extra field rows both start
            from the currently saved configuration. Returns an empty-fields
            record (not a 404) when nothing has been configured yet.

            Args:
            request: FastAPI request carrying request-scoped tracing metadata.
            machine_name: The workflow to fetch the configuration for.
            actor: Current actor resolved from request headers and role checks.

            Raises:
            HTTPException: Raised when the workflow cannot be resolved.

            Returns:
            WorkflowBoardDisplayFieldsRecord: The configured extra card fields.
            """
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("WorkflowController.get_workflow_board_display_fields"):
                try:
                    logger.info(
                        f"workflow get_board_display_fields: machine_name={machine_name}",
                        extra={"request_id": request_id},
                    )
                    return self.workflow_service_manager.get_board_display_fields_for_actor(
                        actor, machine_name
                    )
                except Exception as exc:
                    self._raise_http_exception("get_board_display_fields", exc)

        @app.put(
            "/workflow-board-display-fields",
            status_code=status.HTTP_200_OK,
            tags=["state-machines"],
            response_model=WorkflowBoardDisplayFieldsRecord,
            dependencies=route_dependencies,
        )
        def update_workflow_board_display_fields_endpoint(
            request: Request,
            payload: WorkflowBoardDisplayFieldsUpdateRequest,
            actor: WorkflowWriteActor,
        ):
            """Replace the extra entity fields configured for one workflow's Kanban cards.

            Use:
            The Kanban board's "Card fields" picker calls this on save. The
            change applies immediately to everyone viewing this workflow's
            board — it does not go through the workflow draft/publish flow.

            Args:
            request: FastAPI request carrying request-scoped tracing metadata.
            payload: The workflow and the up-to-3 field ids to show on its cards.
            actor: Current actor resolved from request headers and role checks.

            Raises:
            HTTPException: Raised when the workflow cannot be resolved, or when
            more than 3 fields are supplied.

            Returns:
            WorkflowBoardDisplayFieldsRecord: The saved card field configuration.
            """
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("WorkflowController.update_workflow_board_display_fields"):
                try:
                    logger.info(
                        "workflow update_board_display_fields",
                        extra={"request_id": request_id},
                    )
                    return self.workflow_service_manager.update_board_display_fields_for_actor(
                        actor, payload
                    )
                except Exception as exc:
                    self._raise_http_exception("update_board_display_fields", exc)

        # ── Dynamic /{row_id} routes below this line ─────────────────────────

        @app.get(
            "/workflow-state-machines/{row_id}",
            status_code=status.HTTP_200_OK,
            tags=["state-machines"],
            response_model=WorkflowDraftRecord | StateMachineRecord,
            dependencies=route_dependencies,
        )
        def get_workflow_by_row_id_endpoint(
            request: Request,
            row_id: str,
            actor: WorkflowReadActor,
        ):
            """Fetch one exact workflow row by row ID.

            Use:
            Frontend can reload one exact persisted workflow row when it already
            knows the row identifier returned from draft create, publish, or list
            operations.

            Args:
            request: FastAPI request carrying request-scoped tracing metadata.
            row_id: Workflow row primary-key ID.
            actor: Current actor resolved from request headers and role checks.

            Raises:
            HTTPException: Raised when the workflow cannot be resolved.

            Returns:
            WorkflowDraftRecord | StateMachineRecord: The exact persisted workflow row.
            """
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("WorkflowController.get_workflow_by_row_id"):
                try:
                    logger.info(
                        f"workflow get_workflow_by_row_id: row_id={row_id}",
                        extra={"request_id": request_id},
                    )
                    return self.workflow_service_manager.get_workflow_by_row_id_for_actor(
                        actor,
                        WorkflowRowLookupRequest(row_id=row_id),
                    )
                except Exception as exc:
                    self._raise_http_exception("get_workflow_by_row_id", exc)

        @app.put(
            "/workflow-state-machines/{row_id}/draft",
            status_code=status.HTTP_200_OK,
            tags=["state-machines"],
            response_model=WorkflowDraftSaveResponse,
            dependencies=route_dependencies,
        )
        def update_workflow_draft_endpoint(
            request: Request,
            row_id: str,
            payload: WorkflowDraftUpdateRequest,
            actor: WorkflowWriteActor,
        ):
            """Update one in-progress workflow draft definition with structural validation.

            Use:
            Frontend calls this when the user clicks "Save as draft" in the
            builder. Backend overwrites the persisted definition for the row
            identified by `row_id` and runs structural validation.
            Draft definitions are persisted even when invalid; validation
            issues are returned in the response for client-side guidance.

            Args:
            request: FastAPI request carrying request-scoped tracing metadata.
            row_id: Primary-key ID of the workflow draft row to update.
            payload: Replacement definition.
            actor: Current actor resolved from request headers and role checks.

            Raises:
            HTTPException: 404 if the target row is missing.

            Returns:
            WorkflowDraftSaveResponse: Updated record, validation issues, validity
            flag.
            """
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("WorkflowController.save_workflow_draft"):
                try:
                    logger.info("workflow update_workflow_draft", extra={"request_id": request_id})
                    return self.workflow_service_manager.update_workflow_draft_for_actor(
                        actor,
                        row_id,
                        payload,
                    )
                except Exception as exc:
                    self._raise_http_exception("update_workflow_draft", exc)

        @app.delete(
            "/workflow-state-machines/{row_id}",
            status_code=status.HTTP_200_OK,
            tags=["state-machines"],
            response_model=WorkflowDraftRecord | StateMachineRecord,
            dependencies=route_dependencies,
        )
        def delete_workflow_endpoint(
            request: Request,
            row_id: str,
            actor: WorkflowWriteActor,
        ):
            """Archive one workflow row by its row ID (soft-delete).

            The row is not removed from the database. Instead, archived_at is
            stamped with the current timestamp so the workflow no longer appears
            in active listings. Archiving is blocked if any entities are still
            in a non-terminal state under this workflow.

            Args:
            request: FastAPI request carrying request-scoped tracing metadata.
            row_id: Primary-key ID of the workflow row to archive.
            actor: Current actor resolved from request headers and role checks.

            Raises:
            HTTPException: 404 if no row matches the given row_id.
            HTTPException: 400 if one or more entities are still active in this workflow.

            Returns:
            StateMachineRecord: The archived workflow row with archived_at set.
            """
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("WorkflowController.delete_workflow"):
                try:
                    logger.info(
                        f"workflow delete_workflow: row_id={row_id}",
                        extra={"request_id": request_id},
                    )
                    return self.workflow_service_manager.delete_workflow_for_actor(
                        actor,
                        row_id,
                    )
                except Exception as exc:
                    self._raise_http_exception("delete_workflow", exc)

        @app.post(
            "/workflow-state-machines/{row_id}/publish",
            status_code=status.HTTP_200_OK,
            tags=["state-machines"],
            response_model=StateMachinePublishResponse,
            dependencies=route_dependencies,
        )
        def publish_state_machine_endpoint(
            request: Request,
            row_id: str,
            payload: WorkflowPublishRequest,
            actor: WorkflowWriteActor,
        ):
            """Publish the specified workflow draft row as a new persisted workflow version."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("WorkflowController.publish_state_machine"):
                try:
                    logger.info("workflow publish_state_machine", extra={"request_id": request_id})
                    return self.workflow_service_manager.publish_workflow_for_actor(
                        actor, row_id, payload
                    )
                except Exception as exc:
                    self._raise_http_exception("publish_state_machine", exc)

        @app.post(
            "/workflow-state-machines/{machine_name}/draft",
            status_code=status.HTTP_201_CREATED,
            tags=["state-machines"],
            response_model=WorkflowDraftRecord,
            dependencies=route_dependencies,
        )
        def seed_workflow_draft_endpoint(
            request: Request,
            machine_name: str,
            actor: WorkflowWriteActor,
            payload: WorkflowDraftSeedRequest | None = None,
        ):
            """Seed a version-0 draft for an existing published workflow family.

            Use:
            Frontend calls this when the user opens a published workflow that has
            no associated draft row, and then clicks "Save as draft" for the first
            time. The created draft is anchored to the correct workflow family so
            subsequent PUT /{row_id}/draft and POST /{row_id}/publish calls operate
            on the right family.

            Rejected when no published versions exist for `machine_name` in this org,
            or when a version-0 draft already exists (returns 409 with the existing
            row_id so the frontend can switch to the update path immediately).

            Args:
            request: FastAPI request carrying request-scoped tracing metadata.
            machine_name: Workflow family identity. Must have at least one published
            version in the caller's organization.
            payload: Optional starting definition and canvas metadata. When omitted
            the draft is seeded with the standard blank template.
            actor: Current actor resolved from request headers and role checks.

            Raises:
            HTTPException: 404 if the workflow family does not exist in this org.
            HTTPException: 409 if a draft already exists for the family.
            HTTPException: 400 if the family has no published versions.

            Returns:
            WorkflowDraftRecord: The newly created version-0 draft row.
            """
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("WorkflowController.seed_workflow_draft"):
                try:
                    logger.info(
                        f"workflow seed_workflow_draft machine={machine_name}",
                        extra={"request_id": request_id},
                    )
                    return self.workflow_service_manager.seed_workflow_draft_for_actor(
                        actor,
                        machine_name,
                        payload or WorkflowDraftSeedRequest(),
                    )
                except Exception as exc:
                    self._raise_http_exception("seed_workflow_draft", exc)

        @app.get(
            "/workflow-state-machines/{machine_name}/active",
            status_code=status.HTTP_200_OK,
            tags=["state-machines"],
            response_model=StateMachineRecord,
            dependencies=route_dependencies,
        )
        def get_active_state_machine_endpoint(
            request: Request,
            machine_name: str,
            actor: WorkflowReadActor,
        ):
            """Fetch the active version of one named state machine.

            Use:
            Frontend calls this endpoint to resolve the current active definition for
            a workflow identity before rendering or applying runtime actions.

            Args:
            request: FastAPI request carrying request-scoped tracing metadata.
            machine_name: Workflow identity to resolve.
            actor: Current actor resolved from request headers and role checks.

            Raises:
            HTTPException: Raised when the state machine cannot be found or read.

            Returns:
            StateMachineRecord: The active workflow version.
            """
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("WorkflowController.get_active_state_machine"):
                try:
                    logger.info(
                        "workflow get_active_state_machine", extra={"request_id": request_id}
                    )
                    return self.workflow_service_manager.get_active_state_machine_for_actor(
                        actor, machine_name
                    )
                except Exception as exc:
                    self._raise_http_exception("get_active_state_machine", exc)

        @app.get(
            "/workflow-state-machines/{machine_name}/{version:int}",
            status_code=status.HTTP_200_OK,
            tags=["state-machines"],
            response_model=StateMachineRecord,
            dependencies=route_dependencies,
        )
        def get_state_machine_endpoint(
            request: Request,
            machine_name: str,
            version: int,
            actor: WorkflowReadActor,
        ):
            """Fetch one specific state machine version.

            Use:
            Frontend can load a historical or draft workflow version by exact version
            number for inspection, compare, or activation workflows.

            Args:
            request: FastAPI request carrying request-scoped tracing metadata.
            machine_name: Workflow identity to resolve.
            version: Exact workflow version to load.
            actor: Current actor resolved from request headers and role checks.

            Raises:
            HTTPException: Raised when the version cannot be found or read.

            Returns:
            StateMachineRecord: The requested workflow version.
            """
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("WorkflowController.get_state_machine"):
                try:
                    logger.info("workflow get_state_machine", extra={"request_id": request_id})
                    return self.workflow_service_manager.get_state_machine_for_actor(
                        actor, machine_name, version
                    )
                except Exception as exc:
                    self._raise_http_exception("get_state_machine", exc)

        @app.get(
            "/workflow-state-machines/{machine_name}/compare/{from_version:int}/{to_version:int}",
            status_code=status.HTTP_200_OK,
            tags=["state-machines"],
            response_model=StateMachineVersionCompareResponse,
            dependencies=route_dependencies,
        )
        def compare_state_machine_versions_endpoint(
            request: Request,
            machine_name: str,
            from_version: int,
            to_version: int,
            actor: WorkflowReadActor,
        ):
            """Compare two versions of the same state machine definition.

            Use:
            Frontend can diff one workflow version against another and inspect added
            states, removed transitions, guard changes, role changes, and required
            field changes without mutating anything.

            Args:
            request: FastAPI request carrying request-scoped tracing metadata.
            machine_name: Workflow identity shared by both compared versions.
            from_version: Base version for the comparison.
            to_version: Candidate version for the comparison.
            actor: Current actor resolved from request headers and role checks.

            Raises:
            HTTPException: Raised when either version is missing or access fails.

            Returns:
            StateMachineVersionCompareResponse: Structured diff between the two
            versions.
            """
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("WorkflowController.compare_state_machine_versions"):
                try:
                    logger.info(
                        "workflow compare_state_machine_versions", extra={"request_id": request_id}
                    )
                    return self.workflow_service_manager.compare_state_machine_versions_for_actor(
                        actor,
                        machine_name,
                        from_version,
                        to_version,
                    )
                except Exception as exc:
                    self._raise_http_exception("compare_state_machine_versions", exc)

        @app.post(
            "/workflow-state-machines/{machine_name}/{version:int}/validate",
            status_code=status.HTTP_200_OK,
            tags=["state-machines"],
            response_model=DefinitionReport,
            dependencies=route_dependencies,
        )
        def validate_state_machine_endpoint(
            request: Request,
            machine_name: str,
            version: int,
            actor: WorkflowWriteActor,
        ):
            """Validate one persisted workflow version and store the report.

            Use:
            Frontend can explicitly validate a workflow version before attempting
            activation. This is definition-level validation, not runtime transition
            preflight.

            Args:
            request: FastAPI request carrying request-scoped tracing metadata.
            machine_name: Workflow identity to validate.
            version: Workflow version to validate.
            actor: Current actor resolved from request headers and role checks.

            Raises:
            HTTPException: Raised when validation cannot be completed.

            Returns:
            DefinitionReport: Persisted validation report for the version.
            """
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("WorkflowController.validate_state_machine"):
                try:
                    logger.info("workflow validate_state_machine", extra={"request_id": request_id})
                    return self.workflow_service_manager.validate_workflow_version_for_actor(
                        actor,
                        machine_name,
                        version,
                    )
                except Exception as exc:
                    self._raise_http_exception("validate_state_machine", exc)

        @app.post(
            "/workflow-state-machines/{machine_name}/{version:int}/activate",
            status_code=status.HTTP_200_OK,
            tags=["state-machines"],
            response_model=StateMachineRecord,
            dependencies=route_dependencies,
        )
        def activate_state_machine_endpoint(
            request: Request,
            machine_name: str,
            version: int,
            actor: WorkflowWriteActor,
        ):
            """Activate one safe workflow version for a machine name.

            Use:
            Frontend calls this endpoint after validation and compatibility checks
            succeed. Activation promotes the specified version and deactivates the
            rest for the same `machine_name`.

            Args:
            request: FastAPI request carrying request-scoped tracing metadata.
            machine_name: Workflow identity to activate.
            version: Version to promote to active.
            actor: Current actor resolved from request headers and role checks.

            Raises:
            HTTPException: Raised when compatibility or activation fails.

            Returns:
            StateMachineRecord: The newly active workflow version.
            """
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("WorkflowController.activate_state_machine"):
                try:
                    logger.info("workflow activate_state_machine", extra={"request_id": request_id})
                    return self.workflow_service_manager.activate_workflow_for_actor(
                        actor, machine_name, version
                    )
                except Exception as exc:
                    self._raise_http_exception("activate_state_machine", exc)

        @app.post(
            "/workflow-state-machines/{machine_name}/{version:int}/revert",
            status_code=status.HTTP_200_OK,
            tags=["state-machines"],
            response_model=StateMachineRecord,
            dependencies=route_dependencies,
        )
        def revert_state_machine_endpoint(
            request: Request,
            machine_name: str,
            version: int,
            actor: WorkflowWriteActor,
        ):
            """Re-activate one earlier safe workflow version.

            Use:
            Frontend can revert to any earlier persisted version. Revert does not
            delete newer versions; it re-runs the safety checks and activates the
            requested version only if it is still compatible.

            Args:
            request: FastAPI request carrying request-scoped tracing metadata.
            machine_name: Workflow identity to revert.
            version: Historical version to reactivate.
            actor: Current actor resolved from request headers and role checks.

            Raises:
            HTTPException: Raised when the historical version is unsafe or missing.

            Returns:
            StateMachineRecord: The reactivated workflow version.
            """
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("WorkflowController.revert_state_machine"):
                try:
                    logger.info("workflow revert_state_machine", extra={"request_id": request_id})
                    return self.workflow_service_manager.revert_workflow_version_for_actor(
                        actor,
                        machine_name,
                        version,
                    )
                except Exception as exc:
                    self._raise_http_exception("revert_state_machine", exc)

        @app.post(
            "/workflow-state-machines/{machine_name}/enrollments",
            status_code=status.HTTP_201_CREATED,
            tags=["state-machines"],
            response_model=EntityState,
            dependencies=route_dependencies,
        )
        def enroll_entity_endpoint(
            request: Request,
            machine_name: str,
            payload: WorkflowEnrollmentRequest,
            actor: WorkflowWriteActor,
        ):
            """Enroll an existing entity in the active version of a workflow.

            The entity record must already exist; the entities controller
            owns entity creation. This endpoint just writes the enrollment
            row at the workflow's `initial_state` and emits one
            ENTITY_ENROLLED event."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("WorkflowController.enroll_entity"):
                try:
                    logger.info("workflow enroll_entity", extra={"request_id": request_id})
                    return self.workflow_service_manager.enroll_entity_for_actor(
                        actor, machine_name, payload.entity_id
                    )
                except Exception as exc:
                    self._raise_http_exception("enroll_entity", exc)

        @app.get(
            "/workflow-enrollments",
            status_code=status.HTTP_200_OK,
            tags=["state-machines"],
            response_model=WorkflowEnrollmentSummaryPage,
            dependencies=route_dependencies,
        )
        def list_all_enrollments_endpoint(
            request: Request,
            actor: WorkflowReadActor,
            machine_name: str | None = Query(default=None),
            current_state: str | None = Query(default=None),
            exclude_states: str | None = Query(default=None),
            entity_type_name: str | None = Query(default=None),
            entity_type_id: str | None = Query(default=None),
            include_archived: bool = Query(default=False),
            anchor_entity_id: str | None = Query(default=None),
            assignee_ids: str | None = Query(default=None),
            search: str | None = Query(default=None),
            field_filters: str | None = Query(default=None),
            identifier: str | None = Query(default=None),
            sort_by: str | None = Query(default=None),
            sort_dir: str = Query(default="asc"),
            fields: str | None = Query(default=None),
            sum_fields: str | None = Query(default=None),
            thumbnail_field: str | None = Query(default=None),
            include: str | None = Query(default=None),
            limit: int = Query(default=50, ge=1, le=200),
            offset: int | None = Query(default=None, ge=0),
        ):
            """Canonical offset-paginated workflow-enrollment summary API."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("WorkflowController.list_all_enrollments"):
                try:
                    logger.info("workflow list_all_enrollments", extra={"request_id": request_id})
                    return self.workflow_service_manager.list_enrollment_summaries_for_actor(
                        actor,
                        machine_name=machine_name,
                        current_state=current_state,
                        exclude_states=exclude_states,
                        entity_type_name=entity_type_name,
                        entity_type_id=entity_type_id,
                        include_archived=include_archived,
                        anchor_entity_id=anchor_entity_id,
                        fields=fields,
                        sum_fields=sum_fields,
                        thumbnail_field=thumbnail_field,
                        include=include,
                        assignee_ids=assignee_ids,
                        search=search,
                        field_filters=field_filters,
                        identifier=identifier,
                        sort_by=sort_by,
                        sort_dir=sort_dir,
                        limit=limit,
                        offset=offset,
                    )
                except Exception as exc:
                    self._raise_http_exception("list_all_enrollments", exc)

        @app.post(
            "/workflow-enrollments/run-facts",
            status_code=status.HTTP_200_OK,
            tags=["state-machines"],
            response_model=RunFactsResponse,
            dependencies=route_dependencies,
        )
        def run_facts_endpoint(
            request: Request,
            payload: RunFactsRequest,
            actor: WorkflowReadActor,
        ):
            """Batched run facts (state, timestamps, assignee) for a set of entity ids."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("WorkflowController.run_facts"):
                try:
                    logger.info("workflow run_facts", extra={"request_id": request_id})
                    return self.workflow_service_manager.run_facts_for_actor(actor, payload)
                except Exception as exc:
                    self._raise_http_exception("run_facts", exc)

        @app.post(
            "/workflow-state-machines/{machine_name}/{version:int}/dry-run-entity",
            status_code=status.HTTP_200_OK,
            tags=["state-machines"],
            response_model=EntityDryRunResponse,
            dependencies=route_dependencies,
        )
        def dry_run_entity_endpoint(
            request: Request,
            machine_name: str,
            version: int,
            payload: EntityDryRunRequest,
            actor: WorkflowWriteActor,
        ):
            """Dry-run one entity snapshot against a full workflow version.

            Use:
            Frontend sends the entity type, current state, entity data, and any
            transition-relevant inputs already merged in the payload data. Backend
            returns the full definition, a validation report, and a bounded
            simulation summary for that one entity snapshot. Nothing is persisted
            because this is a pure dry run.

            Args:
            request: FastAPI request carrying request-scoped tracing metadata.
            machine_name: Workflow identity to test.
            version: Exact workflow version to dry-run.
            payload: Entity snapshot and actor-role context.
            actor: Current actor resolved from request headers and role checks.

            Raises:
            HTTPException: Raised when the dry run cannot be completed.

            Returns:
            EntityDryRunResponse: Definition, reports, and full dry-run summary.
            """
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("WorkflowController.dry_run_entity"):
                try:
                    logger.info("workflow dry_run_entity", extra={"request_id": request_id})
                    return self.workflow_service_manager.dry_run_entity_for_actor(
                        actor,
                        machine_name,
                        version,
                        payload,
                    )
                except Exception as exc:
                    self._raise_http_exception("dry_run_entity", exc)

        @app.get(
            "/entities/{entity_id}/transitions/available",
            status_code=status.HTTP_200_OK,
            tags=["transitions"],
            response_model=AvailableTransitionsResponse,
            dependencies=route_dependencies,
        )
        def list_available_transitions_endpoint(
            request: Request,
            entity_id: str,
            actor: WorkflowReadActor,
            machine_name: str | None = Query(default=None),
            workflow_id: str | None = Query(default=None),
            current_state: str | None = Query(default=None),
            inputs_json: str | None = Query(default=None),
        ):
            """List transitions available from the current entity state.

            Use:
            Frontend uses this endpoint to render action buttons for an entity
            before asking the backend to execute a transition.

            Args:
            request: FastAPI request carrying request-scoped tracing metadata.
            machine_name: Workflow identity currently governing the entity.
            current_state: Entity state to evaluate from.
            entity_id: Runtime entity identifier.
            inputs_json: Optional JSON object string containing proposed
            transition inputs so required field checks can evaluate the user's
            form values before execution.
            actor: Current actor resolved from request headers and role checks.

            Raises:
            HTTPException: Raised when the transition lookup fails.

            Returns:
            AvailableTransitionsResponse: Transition summaries and blocked reasons.
            """
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("WorkflowController.list_available_transitions"):
                try:
                    logger.info(
                        "workflow list_available_transitions", extra={"request_id": request_id}
                    )
                    return self.workflow_service_manager.list_available_transitions_for_actor(
                        actor=actor,
                        machine_name=machine_name,
                        workflow_id=workflow_id,
                        current_state=current_state,
                        entity_id=entity_id,
                        inputs=self._parse_inputs_json(inputs_json),
                    )
                except Exception as exc:
                    self._raise_http_exception("list_available_transitions", exc)

        @app.get(
            "/entities/{entity_id}/transitions/{trigger}/preflight",
            status_code=status.HTTP_200_OK,
            tags=["transitions"],
            response_model=TransitionPreflightResponse,
            dependencies=route_dependencies,
        )
        def preflight_transition_endpoint(
            request: Request,
            machine_name: str,
            current_state: str,
            entity_id: str,
            trigger: str,
            actor: WorkflowReadActor,
            workflow_id: str | None = Query(default=None),
            inputs_json: str | None = Query(default=None),
        ):
            """Return transition readiness without mutating state.

            Use:
            Frontend calls this endpoint before submit when it wants to know whether
            one trigger is currently allowed, which required fields are still
            missing, and which guards block the move.

            Args:
            request: FastAPI request carrying request-scoped tracing metadata.
            machine_name: Workflow identity currently governing the entity.
            current_state: Entity state to evaluate from.
            entity_id: Runtime entity identifier.
            trigger: Transition trigger to preflight.
            inputs_json: Optional JSON object string containing proposed
            transition inputs so required field checks can evaluate the user's
            form values before execution.
            actor: Current actor resolved from request headers and role checks.

            Raises:
            HTTPException: Raised when preflight cannot be completed.

            Returns:
            TransitionPreflightResponse: Non-mutating readiness result.
            """
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("WorkflowController.preflight_transition"):
                try:
                    logger.info("workflow preflight_transition", extra={"request_id": request_id})
                    return self.workflow_service_manager.preflight_transition_for_actor(
                        actor=actor,
                        machine_name=machine_name,
                        current_state=current_state,
                        entity_id=entity_id,
                        workflow_id=workflow_id,
                        trigger=trigger,
                        inputs=self._parse_inputs_json(inputs_json),
                    )
                except Exception as exc:
                    self._raise_http_exception("preflight_transition", exc)

        @app.post(
            "/entities/{entity_id}/transitions",
            status_code=status.HTTP_200_OK,
            tags=["transitions"],
            response_model=TransitionExecutionResponse,
            dependencies=route_dependencies,
        )
        def execute_transition_endpoint(
            request: Request,
            entity_id: str,
            payload: TransitionExecuteRequest,
            actor: WorkflowWriteActor,
        ):
            """Execute one workflow transition for one entity.

            Use:
            Frontend sends the trigger, optional idempotency key, and
            any transition inputs. Backend resolves the active version for the
            entity's machine, executes the transition, records history, emits task
            events, and returns the committed transition result.

            Args:
            request: FastAPI request carrying request-scoped tracing metadata.
            entity_id: Runtime entity identifier.
            payload: Transition execute request.
            actor: Current actor resolved from request headers.

            Raises:
            HTTPException: Raised when the transition is blocked, conflicts, or
            fails execution.

            Returns:
            TransitionExecutionResponse: Committed transition result or idempotent
            replay of a previous success.
            """
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("WorkflowController.execute_transition"):
                try:
                    logger.info(
                        "workflow execute_transition",
                        extra={"request_id": request_id, "entity_id": entity_id},
                    )
                    return self.workflow_service_manager.execute_transition_for_actor(
                        actor, entity_id, payload
                    )
                except Exception as exc:
                    self._raise_http_exception("execute_transition", exc)

        @app.post(
            "/entities/{entity_id}/actions/rerun",
            status_code=status.HTTP_200_OK,
            tags=["transitions"],
            response_model=StateActionRerunResponse,
            dependencies=route_dependencies,
        )
        def rerun_state_action_endpoint(
            request: Request,
            entity_id: str,
            actor: WorkflowWriteActor,
            payload: StateActionRerunRequest | None = None,
            workflow_id: str | None = Query(default=None),
        ):
            """Re-run the on-state action(s) of the entity's current state.

            Use:
            Frontend offers a "re-run action" button on the entity detail view.
            With no body (or `action_index` omitted), re-runs the whole action
            chain starting at action 0. With `action_index` set, re-runs just
            that one action in isolation — it will not cascade to the next
            action regardless of outcome.

            Args:
            request: FastAPI request carrying request-scoped tracing metadata.
            entity_id: Runtime entity identifier.
            actor: Current actor resolved from request headers and role checks.
            payload: Optional body selecting a specific action to re-run.

            Raises:
            HTTPException: 404 when the entity has no workflow state, 400 when
            the current state defines no action (or the index is out of
            range), 409 while a run for the current state is still pending
            or running.

            Returns:
            StateActionRerunResponse: The freshly created pending action run.
            """
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("WorkflowController.rerun_state_action"):
                try:
                    logger.info(
                        "workflow rerun_state_action",
                        extra={"request_id": request_id, "entity_id": entity_id},
                    )
                    return self.workflow_service_manager.rerun_state_action_for_actor(
                        actor, entity_id,
                        action_index=payload.action_index if payload else None,
                        workflow_id=workflow_id,
                    )
                except Exception as exc:
                    self._raise_http_exception("rerun_state_action", exc)
