"""Business orchestration for the shared tools module."""

from __future__ import annotations

import contextlib
import json
import re
import time
from typing import TYPE_CHECKING, Any, Callable

from comments.models.interface import render_mentions_as_text
from comments.models.request import CommentCreateRequest
from exceptions import NotFoundError, PersistenceError, ServiceError, ValidationError
from common.auth import actor_str
from common.logger import logger
from schedules.models.request import ScheduleRunNowRequest

from tools.models.interface import (
    READ_JOB_DOCUMENT_MAX_FILES_PER_CALL,
    READ_JOB_DOCUMENT_PER_FILE_CHAR_CAP,
    READ_JOB_DOCUMENT_RUN_BUDGET_CHARS,
    READ_JOB_DOCUMENT_TRACKED_RUNS_LIMIT,
    ToolDescriptorContract,
    ToolExecutionContext,
    ToolExecutionLogContract,
    ToolExecutionResult,
    ToolPresetContract,
)
from tools.models.request import ToolExecutionLogListRequest, ToolExecutionRequest
from tools.models.response import ToolCatalogResponse, ToolExecutionLogListResponse, ToolPresetListResponse

if TYPE_CHECKING:
    # Type-only: referenced in annotations, never at runtime.
    from connectors.manager import ConnectorCallResult
    from connectors.models.interface import ConnectorContract

ToolHandlerCallable = Callable[[dict[str, object], ToolExecutionContext], ToolExecutionResult]
ActorContext = dict[str, object]
PLATFORM_RUNTIME_EXECUTION_BACKEND = "platform_runtime"
_RECORD_REF_PROPERTIES: dict[str, Any] = {
    "entity_id": {
        "type": "string",
        "description": "The record's id. Use identifier instead for a name.",
    },
    "identifier": {
        "type": "string",
        "description": (
            "The record's name as shown in the app. Prefer this whenever "
            "you were given a name rather than an id."
        ),
    },
}
# Candidate names listed back when an ambiguous record name matches several.
MAX_MATCHING_NAMES_SHOWN = 5

# How many rows the model gets with a pipeline component. Enough to answer
# "who is on the board" without bloating the result. The widget ignores these.
_PIPELINE_SUMMARY_ROW_CAP = 50


class ToolsServiceManager:
    """Own the shared tool catalog, presets, execution, and execution-history APIs."""

    def __init__(
        self,
        tools_db_model_service,
        database_service_manager,
        config,
        llm_service_manager=None,
        entities_service_manager=None,
        forms_service_manager=None,
        documents_service_manager=None,
        communications_service_manager=None,
        integrations_service_manager=None,
        connectors_service_manager=None,
        workflow_service_manager=None,
        auth_service_manager=None,
        fileprocessor_service_manager=None,
        dashboard_service_manager=None,
        comments_service_manager=None,
        *dependencies,
    ) -> None:  # noqa: ANN001
        """Store dependencies required by the shared tools module.

        Args:
            tools_db_model_service: Persistence service for tool execution history.
            database_service_manager: Shared database manager reserved for module wiring.
            config: Runtime configuration object.
            llm_service_manager: Optional LLM manager reserved for future tool flows.
            entities_service_manager: Optional entities manager dependency.
            forms_service_manager: Optional forms manager reserved for future tool flows.
            documents_service_manager: Optional documents manager dependency.
            communications_service_manager: Optional communications manager dependency.
            integrations_service_manager: Optional integrations manager dependency.
            workflow_service_manager: Optional workflow manager dependency.
            auth_service_manager: Optional auth manager reserved for future policy use.
            dashboard_service_manager: Optional dashboard manager dependency, used by
                render_ui_component to fetch real metric values.
            *dependencies: Additional unused dependencies reserved for future platform wiring.

        Returns:
            `None`.
        """
        _ = database_service_manager, config, llm_service_manager, forms_service_manager, auth_service_manager, dependencies
        if tools_db_model_service is None:
            raise ServiceError("tools persistence dependency is not configured")

        self.db_model_service = tools_db_model_service
        self.entities_service_manager = entities_service_manager
        self.documents_service_manager = documents_service_manager
        self.communications_service_manager = communications_service_manager
        self.integrations_service_manager = integrations_service_manager
        self.connectors_service_manager = connectors_service_manager
        self.workflow_service_manager = workflow_service_manager
        self.schedules_service_manager = None
        self.fileprocessor_service_manager = fileprocessor_service_manager
        self.dashboard_service_manager = dashboard_service_manager
        self.comments_service_manager = comments_service_manager
        # Per-run cumulative chars read via read_job_document, keyed by run_id — the
        # budget guard that stops a single job's agent run from reading past a safe
        # share of the model's context window. Bounded/evicted in
        # `_charge_read_job_document_budget`.
        self._read_job_document_run_budget: dict[str, int] = {}
        self._catalog = self._build_catalog()
        self._catalog_map = {tool.name: tool for tool in self._catalog}
        self._native_tool_handlers: dict[str, ToolHandlerCallable] = {
            "add_stage_comment": self._execute_add_stage_comment,
            "list_stage_comments": self._execute_list_stage_comments,
            "list_entity_types": self._execute_list_entity_types,
            "create_entity": self._execute_create_entity,
            "update_entity": self._execute_update_entity,
            "delete_entity": self._execute_delete_entity,
            "enroll_entity_in_workflow": self._execute_enroll_entity_in_workflow,
            "move_entity_to_state": self._execute_move_entity_to_state,
            "list_workflows": self._execute_list_workflows,
            "render_ui_component": self._execute_render_ui_component,
            "list_schedules": self._execute_list_schedules,
            "get_schedule": self._execute_get_schedule,
            "list_upcoming_scheduled_entities": self._execute_list_upcoming_scheduled_entities,
            "preview_schedule_run": self._execute_preview_schedule_run,
            "run_schedule_now": self._execute_run_schedule_now,
            "send_calendar_invite": self._execute_calendar_invite,
        }
        self._platform_tool_handlers: dict[str, ToolHandlerCallable] = {
            "read_document": self._execute_read_document,
            "read_job_document": self._execute_read_job_document,
            "get_form_schema": self._execute_get_form_schema,
            "get_picklist_values": self._execute_get_picklist_values,
            "list_events": self._execute_list_events,
        }
        self._supported_tool_names = set(self._native_tool_handlers) | set(self._platform_tool_handlers)
        self._exposed_catalog = [tool for tool in self._catalog if tool.name in self._supported_tool_names]
        self._exposed_catalog_map = {tool.name: tool for tool in self._exposed_catalog}
        self._presets = self._build_presets()

    # region Catalog and Preset Reads
    def get_catalog(self) -> ToolCatalogResponse:
        """Return the canonical shared tool catalog.

        Args:
            None.

        Returns:
            The tool catalog response with default-enabled tool names.
        """
        return ToolCatalogResponse(tools=list(self._exposed_catalog), default_tools=self.get_default_tools())

    def get_tool_descriptor(
        self, tool_name: str, organization_id: str | None = None
    ) -> ToolDescriptorContract:
        """Return one tool descriptor by name.

        Args:
            tool_name: Tool name to resolve.

        Returns:
            The matching tool descriptor contract.
        """
        descriptor = self._exposed_catalog_map.get(tool_name)
        if descriptor is None and organization_id:
            descriptor = self._connector_tool_descriptor(organization_id, tool_name)
        if descriptor is None:
            raise ValidationError(f"Tool is not available in modular backend: {tool_name}")
        return descriptor

    def list_connector_tool_descriptors(self, organization_id: str) -> list[ToolDescriptorContract]:
        """Return descriptors for connectors exposed as agent tools in one organization."""
        return [
            self._build_connector_tool_descriptor(connector)
            for connector in self._connector_contracts_for_org(organization_id)
            if connector.expose_as_tool
        ]

    def get_presets(self) -> ToolPresetListResponse:
        """Return the shared tool preset definitions.

        Args:
            None.

        Returns:
            The current tool preset list response.
        """
        return ToolPresetListResponse(presets=dict(self._presets))

    def get_preset(self, preset_name: str) -> ToolPresetContract:
        """Return one named tool preset.

        Args:
            preset_name: Preset name to resolve.

        Returns:
            The matching tool preset contract.
        """
        preset = self._presets.get(preset_name)
        if preset is None:
            raise ValidationError(f"Unknown tool preset: {preset_name}")
        return preset

    def get_default_tools(self) -> list[str]:
        """List tool names enabled by default.

        Args:
            None.

        Returns:
            Tool names flagged as default-enabled.
        """
        return [tool.name for tool in self._exposed_catalog if tool.default_enabled]

    def list_tool_names(self) -> list[str]:
        """List all registered tool names in catalog order.

        Args:
            None.

        Returns:
            All tool names in the shared catalog.
        """
        return [tool.name for tool in self._exposed_catalog]

    # endregion Catalog and Preset Reads

    # region Validation and Runtime Projection
    def validate_tool_names(self, tool_names: list[str] | None) -> list[str]:
        """Validate and deduplicate explicit tool names.

        Args:
            tool_names: Explicit tool names requested by a caller.

        Returns:
            Valid tool names in first-seen order.
        """
        if tool_names is None:
            return []

        normalized_names: list[str] = []
        seen_names: set[str] = set()
        unknown_names: list[str] = []

        for raw_name in tool_names:
            tool_name = str(raw_name).strip()
            if not tool_name:
                raise ValidationError("Tool names must be non-empty strings")
            if tool_name in seen_names:
                continue
            if tool_name not in self._exposed_catalog_map:
                unknown_names.append(tool_name)
                continue
            seen_names.add(tool_name)
            normalized_names.append(tool_name)

        if unknown_names:
            raise ValidationError(f"Unknown tools requested: {', '.join(unknown_names)}")
        return normalized_names

    def validate_runtime_tools(self, tool_names: list[str] | None) -> list[str]:
        """Resolve the effective runtime tool set.

        Args:
            tool_names: Explicit tool names requested for runtime execution.

        Returns:
            The effective ordered tool-name list for runtime use.
        """
        if tool_names is None:
            return self.list_tool_names()
        return self.validate_tool_names(tool_names)

    def build_runtime_tools(self, tool_names: list[str] | None = None) -> list[dict[str, object]]:
        """Build OpenAI-compatible tool descriptors for runtime execution.

        Args:
            tool_names: Optional explicit tool-name allowlist.

        Returns:
            Runtime tool descriptors in OpenAI function-tool format.
        """
        selected_names = self.validate_runtime_tools(tool_names)
        return [
            {
                "type": "function",
                "function": {
                    "name": self._exposed_catalog_map[name].name,
                    "description": self._exposed_catalog_map[name].description,
                    "parameters": self._exposed_catalog_map[name].parameters,
                },
            }
            for name in selected_names
        ]

    # endregion Validation and Runtime Projection

    # region Execution Flows
    def execute_tool_for_actor(self, actor: ActorContext, request: ToolExecutionRequest) -> ToolExecutionResult:
        """Execute one tool call on behalf of an authenticated actor.

        Args:
            actor: Authenticated actor context resolved by the controller.
            request: Typed direct tool-execution request.

        Returns:
            The normalized tool execution result.
        """
        organization_id = self._require_actor_field(actor, "organization_id")
        user_id = self._require_actor_field(actor, "user_id")
        request_id = actor_str(actor, "request_id") or None
        roles_value = actor.get("roles")
        roles = [str(role) for role in roles_value] if isinstance(roles_value, list) else []

        context = ToolExecutionContext(
            run_id=request.run_id,
            session_id=request.session_id,
            organization_id=organization_id,
            user_id=user_id,
            actor_id=user_id,
            actor_type="USER",
            roles=roles,
            entity_id=request.entity_id,
            entity_type=request.entity_type,
            source=request.source,
            request_id=request_id,
            metadata=dict(request.metadata or {}),
        )
        return self.execute_tool(request.tool_name, request.arguments, context)

    def execute_tool(self, tool_name: str, arguments: dict[str, object], context: ToolExecutionContext) -> ToolExecutionResult:
        """Execute one tool call through a modular handler or platform runtime path.

        Args:
            tool_name: Tool name to execute.
            arguments: Tool input arguments.
            context: Shared execution context for the tool call.

        Returns:
            The normalized tool execution result.
        """
        if not context.organization_id:
            raise ValidationError("organization_id is required for tool execution")

        descriptor = self.get_tool_descriptor(tool_name, context.organization_id)

        normalized_arguments = dict(arguments or {})
        execution_backend = self._select_execution_path(descriptor.name)
        started_at = time.perf_counter()
        result: ToolExecutionResult | None = None
        execution_error: Exception | None = None
        try:
            if execution_backend == "modular":
                result = self._execute_modular_tool(descriptor.name, normalized_arguments, context)
            else:
                result = self._execute_platform_tool(descriptor.name, normalized_arguments, context)
        except Exception as exc:  # noqa: BLE001
            execution_error = exc

        duration_ms = int((time.perf_counter() - started_at) * 1000)
        if result is not None:
            duration_ms = max(duration_ms, int(result.duration_ms or 0))

        execution_log = self._persist_execution_result(
            self._build_execution_log_payload(
                context=context,
                tool_name=descriptor.name,
                arguments=normalized_arguments,
                execution_backend=execution_backend,
                duration_ms=duration_ms,
                result=result,
                error=execution_error,
            )
        )
        if execution_error is not None:
            raise execution_error
        if result is None:
            raise ServiceError(f"Tool {descriptor.name} did not return a result")

        return result.model_copy(
            update={
                "execution_id": execution_log.id if execution_log is not None else None,
                "execution_backend": execution_backend,
                "duration_ms": duration_ms,
                "tool_name": descriptor.name,
            }
        )

    # endregion Execution Flows

    # region Execution History Flows
    def list_executions_for_actor(
        self,
        actor: ActorContext,
        request: ToolExecutionLogListRequest,
    ) -> ToolExecutionLogListResponse:
        """List execution-history rows for the actor's organization.

        Args:
            actor: Current request actor context.
            request: Typed execution-history query payload.

        Returns:
            Paginated execution-history rows for the organization.
        """
        organization_id = self._require_actor_field(actor, "organization_id")
        items, total = self.db_model_service.list_execution_logs(
            organization_id,
            limit=request.limit,
            offset=request.offset,
            tool_name=request.tool_name,
            source=request.source,
            success=request.success,
            execution_backend=request.execution_backend,
        )
        return ToolExecutionLogListResponse(items=items, total=total)

    def get_execution_for_actor(self, actor: ActorContext, execution_id: str) -> ToolExecutionLogContract:
        """Return one execution-history row scoped to the actor's organization.

        Args:
            actor: Current request actor context.
            execution_id: Execution-log identifier to load.

        Returns:
            The requested execution-history contract.
        """
        organization_id = self._require_actor_field(actor, "organization_id")
        row = self.db_model_service.get_execution_log(execution_id, organization_id)
        if row is None:
            raise NotFoundError("tool execution log not found")
        return row

    # endregion Execution History Flows

    # region Modular Tool Handlers
    def _execute_modular_tool(
        self,
        tool_name: str,
        arguments: dict[str, object],
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        """Execute one tool through a modular-native handler.

        Args:
            tool_name: Tool name to execute.
            arguments: Tool arguments supplied by the caller.
            context: Shared execution context for the tool call.

        Returns:
            The normalized modular tool result.
        """
        handler = self._native_tool_handlers.get(tool_name)
        if handler is None and self._is_connector_tool_name(tool_name):
            return self._execute_connector_tool(tool_name, arguments, context)
        if handler is None:
            raise ServiceError(f"Modular tool handler is not configured for {tool_name}")
        return handler(arguments, context)

    def _execute_platform_tool(
        self,
        tool_name: str,
        arguments: dict[str, object],
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        """Execute one tool through the current platform runtime path.

        Args:
            tool_name: Tool name to execute.
            arguments: Tool input arguments.
            context: Shared execution context for the tool call.

        Returns:
            The normalized tool execution result.
        """
        handler = self._platform_tool_handlers.get(tool_name)
        if handler is None:
            raise ServiceError(f"Tool {tool_name} is not implemented in modular backend yet")
        return handler(arguments, context)

    def _execute_read_document(
        self,
        arguments: dict[str, object],
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        """Read a document and extract its content via the fileprocessor adapters.

        Fetches the raw bytes (storage-aware: local or blob) through the filehandler,
        then parses them per-format (PDF/OCR/docx/sheet/text) via fileprocessor. This
        replaces the previous naive utf-8 decode, which returned garbage for binary files.
        """
        if self.documents_service_manager is None:
            raise ServiceError("documents manager dependency is not configured")
        if self.fileprocessor_service_manager is None:
            raise ServiceError("fileprocessor manager dependency is not configured")
        if not context.organization_id:
            raise ValidationError("organization_id is required for read_document")

        # When the run was triggered by a document upload, the run context carries the
        # authoritative file id. The run is scoped to that one document, so it WINS over
        # any id the model may have guessed (e.g. a filename) in the tool arguments.
        context_file_id = _normalize_optional_string(context.metadata.get("file_id"))
        if context_file_id:
            document_id = context_file_id
            storage_key = None
        else:
            document_id = _normalize_optional_string(arguments.get("document_id"))
            storage_key = _normalize_optional_string(arguments.get("storage_key"))
        if document_id is None and storage_key is None:
            raise ValidationError("document_id or storage_key is required")

        reference = document_id or storage_key or "unknown"
        # Storage/parse failures propagate to execute_tool, which persists a failed
        # execution log (with these arguments) and re-raises — so no local try/except
        # is needed just to log context here.
        source = self.documents_service_manager.read_document_source(
            context.organization_id,
            document_id=document_id,
            storage_key=storage_key,
        )
        if source is None:
            logger.warning("read_document: document not found: %s", reference)
            raise NotFoundError(f"document not found: {reference}")

        extracted = self.fileprocessor_service_manager.extract_content(
            filename=str(source.get("filename") or "unknown"),
            content_type=str(source.get("content_type") or "application/octet-stream"),
            file_bytes=source.get("file_bytes") or b"",
        )
        if not extracted.get("parse_ok"):
            logger.warning(
                "read_document: could not extract %s: %s", reference, extracted.get("parse_error")
            )
            raise ServiceError(
                f"failed to read document {reference}: {extracted.get('parse_error')}"
            )
        logger.info(
            "read_document: extracted %s (format=%s, truncated=%s)",
            reference,
            extracted.get("detected_format"),
            extracted.get("truncated"),
        )

        output = {
            "document_id": source.get("document_id"),
            "storage_key": source.get("storage_key"),
            "filename": source.get("filename"),
            "content_type": source.get("content_type"),
            "status": source.get("status"),
            "metadata": source.get("metadata") or {},
            "detected_format": extracted.get("detected_format"),
            "text": extracted.get("text"),
            "tables": extracted.get("tables") or [],
            "truncated": extracted.get("truncated", False),
        }
        return ToolExecutionResult(success=True, tool_name="read_document", output=output)

    def _execute_read_job_document(
        self,
        arguments: dict[str, object],
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        """Read up to 3 job files at once for the bulk-import single-agent pipeline.

        Unlike read_document (one fixed document baked into the run), this tool takes
        file *slugs* from the model (e.g. "file_1"), never a real file id — the real
        id never appears anywhere in the prompt or tool-call history. Slugs are
        resolved against `context.metadata["file_slug_map"]`, built once per run by
        `bulk_import/manager.py`. A per-file failure never fails the whole call: each
        entry in the response carries its own status, so one bad slug or oversized
        file can't take the other files in the same call down with it.
        """
        if self.documents_service_manager is None:
            raise ServiceError("documents manager dependency is not configured")
        if self.fileprocessor_service_manager is None:
            raise ServiceError("fileprocessor manager dependency is not configured")
        if not context.organization_id:
            raise ValidationError("organization_id is required for read_job_document")

        slugs = [
            normalized
            for normalized in (
                _normalize_optional_string(raw_slug)
                for raw_slug in (arguments.get("file_ids") or [])
            )
            if normalized
        ]
        if not slugs:
            raise ValidationError("file_ids is required and must be non-empty")
        if len(slugs) > READ_JOB_DOCUMENT_MAX_FILES_PER_CALL:
            raise ValidationError(
                "read_job_document accepts at most "
                f"{READ_JOB_DOCUMENT_MAX_FILES_PER_CALL} file_ids per call"
            )

        file_slug_map = context.metadata.get("file_slug_map")
        if not isinstance(file_slug_map, dict):
            file_slug_map = {}

        run_id = context.run_id or "unscoped"
        results = [
            self._read_one_job_file(context.organization_id, run_id, slug, file_slug_map)
            for slug in slugs
        ]
        return ToolExecutionResult(
            success=True, tool_name="read_job_document", output={"results": results}
        )

    def _read_one_job_file(
        self,
        organization_id: str,
        run_id: str,
        slug: str,
        file_slug_map: dict[str, object],
    ) -> dict[str, object]:
        """Read and extract one job file by slug — never raises, always returns a
        per-file result. Every result echoes the slug (never the real file id)."""
        if self._read_job_document_budget_exhausted(run_id):
            return {
                "file_id": slug,
                "status": "error",
                "message": (
                    "context budget exhausted for this job — stop reading further "
                    "files and return your consolidated results now for the files "
                    "already processed."
                ),
            }
        real_file_id = _normalize_optional_string(file_slug_map.get(slug))
        if real_file_id is None:
            return {"file_id": slug, "status": "error", "message": f"unknown file slug: {slug}"}
        try:
            source = self.documents_service_manager.read_document_source(
                organization_id, document_id=real_file_id, storage_key=None
            )
            if source is None:
                return {"file_id": slug, "status": "error", "message": f"document not found: {slug}"}

            extracted = self.fileprocessor_service_manager.extract_content(
                filename=str(source.get("filename") or "unknown"),
                content_type=str(source.get("content_type") or "application/octet-stream"),
                file_bytes=source.get("file_bytes") or b"",
            )
            if not extracted.get("parse_ok"):
                return {
                    "file_id": slug,
                    "status": "error",
                    "message": f"failed to read document {slug}: {extracted.get('parse_error')}",
                }

            text = str(extracted.get("text") or "")
            truncated = bool(extracted.get("truncated", False))
            remaining_budget = READ_JOB_DOCUMENT_RUN_BUDGET_CHARS - self._read_job_document_run_budget.get(
                run_id, 0
            )
            effective_cap = max(min(READ_JOB_DOCUMENT_PER_FILE_CHAR_CAP, remaining_budget), 0)
            if len(text) > effective_cap:
                text = text[:effective_cap]
                truncated = True

            self._charge_read_job_document_budget(run_id, len(text))
            return {
                "file_id": slug,
                "status": "ok",
                "filename": source.get("filename"),
                "detected_format": extracted.get("detected_format"),
                "text": text,
                "truncated": truncated,
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "read_job_document: failed to read %s: %s",
                slug,
                exc,
                extra={"file_id": slug, "run_id": run_id},
            )
            return {"file_id": slug, "status": "error", "message": str(exc)[:1000]}

    def _read_job_document_budget_exhausted(self, run_id: str) -> bool:
        """Return whether this run has already read past its context share."""
        return self._read_job_document_run_budget.get(run_id, 0) >= READ_JOB_DOCUMENT_RUN_BUDGET_CHARS

    def _charge_read_job_document_budget(self, run_id: str, chars_read: int) -> None:
        """Add to a run's cumulative read total, evicting the oldest entry if unbounded growth risks memory."""
        if run_id not in self._read_job_document_run_budget and (
            len(self._read_job_document_run_budget) >= READ_JOB_DOCUMENT_TRACKED_RUNS_LIMIT
        ):
            oldest_run_id = next(iter(self._read_job_document_run_budget))
            del self._read_job_document_run_budget[oldest_run_id]
        self._read_job_document_run_budget[run_id] = (
            self._read_job_document_run_budget.get(run_id, 0) + chars_read
        )

    def _execute_get_form_schema(
        self,
        arguments: dict[str, object],
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        """Return configured field definitions for one entity type.

        Scalar fields are emitted as ``{id,label,type,required,options}``. A
        Table/Grid field (stored as ``type:"json"`` with a ``table_config``) is
        emitted as ``type:"table"`` with a nested ``table`` block describing its
        columns / row-mode, so an agent can build the correct row-array for
        update_entity (a list of row objects keyed by column key).
        """
        if self.entities_service_manager is None:
            raise ServiceError("entities manager dependency is not configured")
        if not context.organization_id:
            raise ValidationError("organization_id is required for get_form_schema")

        entity_type = str(arguments.get("entity_type") or "").strip()
        if not entity_type:
            raise ValidationError("entity_type is required")

        # Raw merged field dicts (carry table_config etc.) rather than the flattened
        # FieldDefinition, so table structure survives.
        raw_fields = self.entities_service_manager.get_form_fields(
            organization_id=context.organization_id,
            form_key=entity_type,
        )

        entity_type_record = self.entities_service_manager.get_entity_type_record(
            organization_id=context.organization_id,
            name=entity_type,
        )
        if not raw_fields and entity_type_record is None:
            raise NotFoundError(f"form schema not found for entity type: {entity_type}")
        identifier_config = (
            dict(entity_type_record.schema_definition or {})
            if entity_type_record is not None
            else {}
        )
        identifier_template = str(identifier_config.get("identifier_template") or "").strip()
        identifier_label = str(identifier_config.get("identifier_label") or "").strip()

        # `identifier` is a platform field stored on every entity, not a configured
        # form field. Agents still need it in the schema so extraction and column
        # mapping can provide the human-readable record name used throughout the UI.
        fields: list[dict[str, object]] = [
            {
                "id": "identifier",
                "label": identifier_label or "Entity Unique Name",
                "type": "string",
                "required": not bool(identifier_template),
                "options": [],
                "system": True,
                "generated": bool(identifier_template),
                "description": (
                    "Unique, human-readable name for this record. The same source value may "
                    "also populate a domain field such as product_name or full_name."
                ),
            }
        ]
        seen: set[str] = {"identifier"}
        for field in raw_fields:
            key = field.get("field") or field.get("name") or field.get("id")
            if not key or str(key) in seen:
                continue
            seen.add(str(key))
            raw_type = str(field.get("type") or "string")
            entry: dict[str, object] = {
                "id": str(key),
                "label": str(key).replace("_", " ").title(),
                "type": raw_type,
                "required": bool(field.get("required", False)),
                "options": [str(o) for o in (field.get("enum_values") or [])],
            }
            table_config = field.get("table_config")
            if raw_type == "json" and isinstance(table_config, dict) and table_config.get("columns"):
                entry["type"] = "table"
                entry["table"] = self._build_table_schema(table_config)
            fields.append(entry)

        return ToolExecutionResult(
            success=True,
            tool_name="get_form_schema",
            output={
                "entity_type": entity_type,
                "version": 1,
                "is_default": False,
                "fields": fields,
                "attachment_support": {
                    "supported": True,
                    "mapping_key": "remote_file_columns",
                    "default_mode": "managed_copy_with_source_url",
                    "accepted_references": ["https_url", "uploaded_filename"],
                    "description": (
                        "In spreadsheet mapping mode, classify image/document URL or uploaded "
                        "filename columns as remote_file_columns. The platform previews URLs "
                        "directly, then fetches and attaches managed copies only after final "
                        "confirmation; do not place file bytes in entity fields."
                    ),
                },
            },
        )

    @staticmethod
    def _build_table_schema(table_config: dict[str, object]) -> dict[str, object]:
        """Shape a Table/Grid field's ``table_config`` into the agent-facing block.

        Surfaces the column KEYS (``id``), types/options, row-mode and limits so the
        agent can construct rows for update_entity. ``readonly``/``calc`` columns are
        flagged so the agent skips computed cells.
        """
        columns: list[dict[str, object]] = []
        for col in table_config.get("columns") or []:
            if not isinstance(col, dict):
                continue
            col_key = col.get("id") or col.get("key")
            if not col_key:
                continue
            columns.append(
                {
                    "key": str(col_key),
                    "label": str(col.get("label") or col_key),
                    "type": str(col.get("type") or "text"),
                    "required": bool(col.get("required", False)),
                    "readonly": bool(col.get("readonly") or col.get("calc")),
                    "options": [str(o) for o in (col.get("enum_values") or [])],
                }
            )
        row_mode = str(table_config.get("row_mode") or "dynamic")
        table: dict[str, object] = {
            "row_mode": row_mode,
            "min_rows": table_config.get("min_rows"),
            "max_rows": table_config.get("max_rows"),
            "columns": columns,
        }
        if row_mode == "fixed":
            table["rows"] = [
                {"id": str(r.get("id")), "label": str(r.get("label") or r.get("line") or r.get("id"))}
                for r in (table_config.get("rows") or [])
                if isinstance(r, dict) and r.get("id")
            ]
        return table

    def _execute_get_picklist_values(
        self,
        arguments: dict[str, object],
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        """Return picklist-like values derived from configured form fields."""
        if self.entities_service_manager is None:
            raise ServiceError("entities manager dependency is not configured")
        if not context.organization_id:
            raise ValidationError("organization_id is required for get_picklist_values")

        requested_picklist_id = _normalize_optional_string(arguments.get("picklist_id"))
        form_configs = self.entities_service_manager.list_form_config_definitions(context.organization_id)
        discovered_picklists: list[dict[str, object]] = []

        for form_config in form_configs:
            for field in form_config.fields:
                if not field.options:
                    continue
                picklist_id = field.name
                if requested_picklist_id and picklist_id != requested_picklist_id:
                    continue
                discovered_picklists.append(
                    {
                        "picklist_id": picklist_id,
                        "name": picklist_id.replace("_", " ").title(),
                        "options": list(field.options),
                        "form_key": form_config.form_key,
                    }
                )

        if requested_picklist_id:
            if not discovered_picklists:
                raise NotFoundError(f"picklist not found: {requested_picklist_id}")
            selected_picklist = discovered_picklists[0]
            return ToolExecutionResult(success=True, tool_name="get_picklist_values", output=selected_picklist)

        return ToolExecutionResult(
            success=True,
            tool_name="get_picklist_values",
            output={"count": len(discovered_picklists), "picklists": discovered_picklists},
        )

    def _execute_list_events(
        self,
        arguments: dict[str, object],
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        """List modular calendar events, optionally filtered by entity."""
        if self.integrations_service_manager is None:
            raise ServiceError("integrations manager dependency is not configured")
        if not context.organization_id:
            raise ValidationError("organization_id is required for list_events")

        entity_id = _normalize_optional_string(arguments.get("entity_id"))
        provider = _normalize_optional_string(arguments.get("provider"))
        user_id = _normalize_optional_string(arguments.get("user_id")) or context.user_id

        events_response = self.integrations_service_manager.list_events(
            {
                "organization_id": context.organization_id,
                "provider": provider,
                "user_id": user_id,
            }
        )
        events = [event.model_dump() for event in events_response.items]
        if entity_id is not None:
            events = [event for event in events if str(event.get("entity_id") or "").strip() == entity_id]

        return ToolExecutionResult(
            success=True,
            tool_name="list_events",
            output={"count": len(events), "events": events},
        )

    def _execute_add_stage_comment(
        self,
        arguments: dict[str, object],
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        """Execute the modular stage-comment tool.

        Args:
            arguments: Tool arguments supplied by the caller.
            context: Shared execution context for the tool call.

        Returns:
            The normalized comment-creation result.
        """
        text = str(arguments.get("text") or "").strip()
        if not text:
            logger.warning("add_stage_comment: called without comment text")
            raise ValidationError("text is required")

        actor, entity_id = self._require_resolved_record(arguments, context, "add_stage_comment")

        comment = self.comments_service_manager.create_comment_for_agent(
            actor, entity_id, CommentCreateRequest(text=text)
        )
        return ToolExecutionResult(success=True, tool_name="add_stage_comment", output=comment.model_dump())

    def _resolve_entity_id(
        self, actor: dict[str, object], organization_id: str, value: str
    ) -> str | None:
        """Map a record's id or its human identifier to the stored entity_id.

        Agents name records the way a user sees them, so a tool accepting only
        an id would silently return nothing. Reads go through the actor-scoped
        methods, so a record the caller cannot see stays hidden.
        """
        if self.entities_service_manager is None:
            return value

        with contextlib.suppress(NotFoundError):
            if self.entities_service_manager.get_entity_record_for_actor(
                actor, value, organization_id
            ):
                return value

        def _norm(text: str) -> str:
            return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()

        needle = _norm(value)
        if not needle:
            return None

        partial: list[tuple[str, str]] = []
        for entity_type in self.entities_service_manager.list_entity_type_records(
            organization_id=organization_id
        ):
            listed = self.entities_service_manager.list_entity_records_for_actor(
                actor, organization_id, entity_type.entity_type_id
            )
            for candidate in listed.items:
                raw = str((candidate.data or {}).get("identifier") or "")
                identifier = _norm(raw)
                if identifier == needle:
                    return candidate.entity_id
                if needle in identifier:
                    partial.append((candidate.entity_id, raw))

        if len(partial) == 1:
            return partial[0][0]
        if partial:
            names = ", ".join(
                sorted(f'"{name}"' for _, name in partial)[:MAX_MATCHING_NAMES_SHOWN]
            )
            logger.warning(f"entity lookup: {value} matches {len(partial)} records")
            raise ValidationError(
                f"'{value}' matches {len(partial)} records ({names}). Use the full name or the record id."
            )
        return None

    def _require_resolved_record(
        self,
        arguments: dict[str, object],
        context: ToolExecutionContext,
        tool_name: str,
    ) -> tuple[dict[str, object], str]:
        """Validate a comment tool's shared arguments and resolve its record."""
        if self.comments_service_manager is None:
            logger.error(f"{tool_name}: comments manager dependency is not configured")
            raise ServiceError("comments manager dependency is not configured")
        if not context.organization_id:
            logger.warning(f"{tool_name}: called without an organization_id")
            raise ValidationError(f"organization_id is required for {tool_name}")

        requested = str(
            arguments.get("identifier") or arguments.get("entity_id") or ""
        ).strip()
        if not requested:
            logger.warning(f"{tool_name}: called without an identifier or entity_id")
            raise ValidationError("identifier or entity_id is required")

        actor = self._actor_from_context(context)
        entity_id = self._resolve_entity_id(actor, context.organization_id, requested)
        if entity_id is None:
            logger.warning(f"{tool_name}: no record matching {requested}")
            raise NotFoundError(f"No record found matching '{requested}'")
        return actor, entity_id

    def _execute_list_stage_comments(
        self,
        arguments: dict[str, object],
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        """Return a record's comment history, newest first."""
        actor, entity_id = self._require_resolved_record(arguments, context, "list_stage_comments")

        listed = self.comments_service_manager.list_comments_for_agent(
            actor, entity_id, state_name=str(arguments.get("state_name") or "") or None
        )
        comments = [
            {
                "comment_id": comment.id,
                "author": comment.author_name or comment.author_id,
                "text": render_mentions_as_text(comment.text),
                "state": comment.state_name,
                "created_at": comment.created_at,
                "reply_count": comment.reply_count,
            }
            for comment in reversed(listed.comments)
        ]

        limit = arguments.get("limit")
        if isinstance(limit, int) and limit > 0:
            comments = comments[:limit]

        return ToolExecutionResult(
            success=True,
            tool_name="list_stage_comments",
            output={"entity_id": entity_id, "count": len(comments), "comments": comments},
        )

    def _execute_list_entity_types(
        self,
        arguments: dict[str, object],
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        """Execute the modular entity-type discovery tool.

        Args:
            arguments: Tool arguments supplied by the caller.
            context: Shared execution context for the tool call.

        Returns:
            The entity-type listing result.
        """
        _ = arguments
        if self.entities_service_manager is None:
            raise ServiceError("entities manager dependency is not configured")
        if not context.organization_id:
            raise ValidationError("organization_id is required for list_entity_types")

        entity_types = self.entities_service_manager.list_entity_type_records(
            organization_id=context.organization_id
        )
        # Expose the entity type's ``name`` under the stable ``entity_type`` key
        # that downstream callers key off, while keeping the full record fields.
        return ToolExecutionResult(
            success=True,
            tool_name="list_entity_types",
            output={
                "count": len(entity_types),
                "entity_types": [
                    {**item.model_dump(), "entity_type": item.name} for item in entity_types
                ],
            },
        )

    def _execute_create_entity(
        self,
        arguments: dict[str, object],
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        """Create one entity record through the modular entities manager."""
        if self.entities_service_manager is None:
            raise ServiceError("entities manager dependency is not configured")
        if not context.organization_id:
            raise ValidationError("organization_id is required for create_entity")

        raw_entity_type = str(arguments.get("entity_type_id") or arguments.get("entity_type") or "").strip()
        if not raw_entity_type:
            raise ValidationError("entity_type_id is required")
        # The model often passes a human name ("candidate") or a workflow's
        # entity type rather than the stored id; resolve it, and on failure give
        # an actionable message listing what's available.
        entity_type_id = self._resolve_entity_type_id(context.organization_id, raw_entity_type)
        if not entity_type_id:
            available = ", ".join(
                sorted(str(getattr(r, "name", "")) for r in self._entity_type_records(context.organization_id))
            ) or "none"
            raise ValidationError(
                f"entity type '{raw_entity_type}' was not found. Call list_entity_types to discover valid types. "
                f"Available entity types: {available}"
            )
        data = arguments.get("data") or {}
        if not isinstance(data, dict):
            raise ValidationError("data must be an object")
        data = dict(data)

        # Every entity requires a unique "identifier" (the "Unique Name" field on the
        # manual create form) — an agent extracting structured data from a document has
        # no reason to know that implicit, form-only field exists, so it's routinely
        # omitted no matter how the agent's prompt is worded. Fall back to the first
        # human-readable field the agent did extract rather than hard-failing the call.
        if not str(data.get("identifier") or "").strip():
            # Same candidate keys used elsewhere to derive a display value for an entity
            # (entities/services/relationships.py) — kept consistent with that convention.
            fallback_keys = ("full_name", "name", "title", "display_name", "email")
            fallback = next(
                (str(data[key]).strip() for key in fallback_keys if str(data.get(key) or "").strip()),
                None,
            )
            if fallback:
                data["identifier"] = fallback

        # Link provider records when the agent can supply them (e.g. the file's
        # owner entity), but never hard-fail on a missing required REFERENCE: a
        # document-created entity often has no source yet, and the link can be
        # added later. The manual create path keeps the default (required).
        raw_sources = arguments.get("source_entity_ids")
        source_entity_ids = (
            [str(sid).strip() for sid in raw_sources if str(sid).strip()]
            if isinstance(raw_sources, list)
            else []
        )

        from entities.models.request import EntityRecordCreateRequest

        # Route through the actor-facing path so the tool inherits the same
        # RBAC, unique-identifier validation, and guard checks as the entity API
        # rather than writing straight to the system-level create.
        record = self.entities_service_manager.create_entity_record_for_actor(
            self._actor_from_context(context),
            EntityRecordCreateRequest(
                organization_id=context.organization_id,
                entity_type_id=entity_type_id,
                data=dict(data),
                owner_id=_normalize_optional_string(arguments.get("owner_id")) or context.user_id,
                source_entity_ids=source_entity_ids,
            ),
            require_reference_sources=False,
        )
        return ToolExecutionResult(
            success=True, tool_name="create_entity", output=record.model_dump(mode="json")
        )

    def _execute_update_entity(
        self,
        arguments: dict[str, object],
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        """Update one entity record through the modular entities manager."""
        if self.entities_service_manager is None:
            raise ServiceError("entities manager dependency is not configured")
        if not context.organization_id:
            raise ValidationError("organization_id is required for update_entity")

        entity_id = str(arguments.get("entity_id") or "").strip()
        if not entity_id:
            raise ValidationError("entity_id is required")
        data = arguments.get("data")
        if data is not None and not isinstance(data, dict):
            raise ValidationError("data must be an object")

        from entities.models.request import EntityRecordUpdateRequest

        # Route through the actor-facing path so a partial update merges with the
        # existing record (the system-level update overwrites all fields) and the
        # same RBAC/guard checks apply.
        record = self.entities_service_manager.update_entity_record_for_actor(
            self._actor_from_context(context),
            entity_id,
            EntityRecordUpdateRequest(
                data=dict(data) if data is not None else None,
                owner_id=_normalize_optional_string(arguments.get("owner_id")),
            ),
            organization_id=context.organization_id,
        )
        if record is None:
            raise NotFoundError(f"entity not found: {entity_id}")
        return ToolExecutionResult(
            success=True, tool_name="update_entity", output=record.model_dump(mode="json")
        )

    def _execute_delete_entity(
        self,
        arguments: dict[str, object],
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        """Archive (soft-delete) one entity record through the entities manager."""
        if self.entities_service_manager is None:
            raise ServiceError("entities manager dependency is not configured")
        if not context.organization_id:
            raise ValidationError("organization_id is required for delete_entity")

        entity_id = str(arguments.get("entity_id") or "").strip()
        if not entity_id:
            raise ValidationError("entity_id is required")

        record = self.entities_service_manager.archive_entity_record_for_actor(
            self._actor_from_context(context),
            entity_id,
            organization_id=context.organization_id,
        )
        if record is None:
            raise NotFoundError(f"entity not found: {entity_id}")
        return ToolExecutionResult(
            success=True, tool_name="delete_entity", output=record.model_dump(mode="json")
        )

    def _execute_enroll_entity_in_workflow(
        self,
        arguments: dict[str, object],
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        """Enroll an existing entity into an active workflow."""
        if self.workflow_service_manager is None:
            raise ServiceError("workflow manager dependency is not configured")
        if not context.organization_id:
            raise ValidationError("organization_id is required for enroll_entity_in_workflow")

        entity_id = str(arguments.get("entity_id") or "").strip()
        if not entity_id:
            raise ValidationError("entity_id is required")
        machine_name = str(
            arguments.get("machine_name")
            or arguments.get("workflow_machine_name")
            or arguments.get("workflow")
            or ""
        ).strip()
        if not machine_name:
            raise ValidationError("machine_name is required")

        # The model routinely passes the workflow's display name ("Candidate
        # Application") instead of its machine_name slug; resolve name/id/slug so
        # enrollment (which is what makes the entity show on the board) succeeds.
        actor = self._actor_from_context(context)
        workflow = self._resolve_active_workflow(actor, machine_name)
        enrollment = self.workflow_service_manager.enroll_entity_for_actor(
            actor,
            workflow.machine_name,
            entity_id,
        )
        return ToolExecutionResult(
            success=True,
            tool_name="enroll_entity_in_workflow",
            output=enrollment.model_dump(mode="json"),
        )

    def _execute_move_entity_to_state(
        self,
        arguments: dict[str, object],
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        """Move an entity to a target state by NAME, finding the right transition itself.

        The model thinks in terms of "move X to the SCREENING stage", not the
        internal trigger name, so this resolves the current state's available
        transitions to the one that lands on the requested state and executes it.
        """
        if self.workflow_service_manager is None:
            raise ServiceError("workflow manager dependency is not configured")
        if not context.organization_id:
            raise ValidationError("organization_id is required for move_entity_to_state")

        entity_id = str(arguments.get("entity_id") or "").strip()
        if not entity_id:
            raise ValidationError("entity_id is required")
        target = _normalize_optional_string(arguments.get("target_state") or arguments.get("state"))
        if not target:
            raise ValidationError("target_state is required")

        actor = self._actor_from_context(context)
        available = self.workflow_service_manager.list_available_transitions_for_actor(
            actor, None, None, entity_id
        )
        current = available.current_state or ""
        wanted = target.strip().lower()

        # Already there - report a no-op rather than erroring.
        if current.strip().lower() == wanted:
            return ToolExecutionResult(
                success=True,
                tool_name="move_entity_to_state",
                output={"entity_id": entity_id, "state": current, "changed": False,
                        "message": f"Entity is already in the {current} state."},
            )

        transitions = available.available_transitions
        allowed = next((t for t in transitions if t.to_state.strip().lower() == wanted and t.allowed), None)
        if allowed is None:
            blocked = next((t for t in transitions if t.to_state.strip().lower() == wanted), None)
            if blocked is not None:
                reasons = "; ".join(blocked.blocked_reasons) or "a guard on that transition is not satisfied"
                raise ValidationError(f"Cannot move to '{target}': {reasons}.")
            reachable = ", ".join(sorted({t.to_state for t in transitions})) or "none"
            raise ValidationError(
                f"No transition from '{current or 'the current state'}' to '{target}'. "
                f"Reachable states from here: {reachable}."
            )

        from workflow.models.request import TransitionExecuteRequest

        result = self.workflow_service_manager.execute_transition_for_actor(
            actor,
            entity_id,
            TransitionExecuteRequest(entity_id=entity_id, trigger=allowed.trigger),
        )
        return ToolExecutionResult(
            success=True,
            tool_name="move_entity_to_state",
            output={**result.model_dump(mode="json"), "changed": True},
        )

    def _execute_list_workflows(
        self,
        arguments: dict[str, object],
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        """Execute the modular workflow discovery tool.

        Args:
            arguments: Tool arguments supplied by the caller.
            context: Shared execution context for the tool call.

        Returns:
            The published-workflow listing result.
        """
        _ = arguments
        if self.workflow_service_manager is None:
            raise ServiceError("workflow manager dependency is not configured")
        if not context.organization_id:
            raise ValidationError("organization_id is required for list_workflows")

        from workflow.models.request import WorkflowListScopeRequest, WorkflowScope

        listing = self.workflow_service_manager.list_state_machines_scoped_for_actor(
            self._actor_from_context(context),
            WorkflowListScopeRequest(scope=WorkflowScope.PUBLISHED),
        )
        # One row per workflow, not per published version. Every version shares a
        # machine_name, so returning all of them showed one workflow as many and
        # the model counted a metric once per version and added the results up,
        # reporting 8 where the answer was 4. Newest version wins.
        newest: dict[str, Any] = {}
        for item in listing.published_items:
            key = str(item.machine_name or item.id or "")
            current = newest.get(key)
            if current is None or (item.version or 0) > (current.version or 0):
                newest[key] = item
        workflows = [
            {
                "id": item.id,
                "machine_name": item.machine_name,
                "name": item.name,
                "entity_type": item.entity_type,
                "version": item.version,
                # State names are matched exactly and are mixed case in practice.
                # Without them the model guessed ("Done" for "DONE") and every
                # state-filtered metric quietly counted zero.
                "states": [state.name for state in item.definition.states],
            }
            for item in sorted(newest.values(), key=lambda i: str(i.name or ""))
        ]
        return ToolExecutionResult(
            success=True,
            tool_name="list_workflows",
            output={"count": len(workflows), "workflows": workflows},
        )

    _RENDERABLE_COMPONENT_IDS = (
        "dashboard",
        "dashboard_widget",
        "pipeline_board",
        "pipeline_list",
        "pipeline_calendar",
        "entity_table",
        "stat_tile",
    )
    _RENDERABLE_METRICS = ("entities.count", "entities.in_state", "entities.reached_state", "sla.breaches")
    _PIPELINE_VIEW_BY_COMPONENT = {
        "pipeline_board": "kanban",
        "pipeline_list": "list",
        "pipeline_calendar": "calendar",
    }
    # Visuals that plot a series. Asking for one implies a trend over time.
    _SERIES_VISUALS = frozenset({"bar", "barh", "line", "area", "funnel"})
    _VALID_WIDGET_VIZ = frozenset(
        {"number", "bar", "barh", "line", "area", "pie", "funnel", "table", "gauge"}
    )

    def _execute_render_ui_component(
        self,
        arguments: dict[str, object],
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        """Execute the Agent Mode canvas-rendering tool.

        Fetches real data server-side for the requested component - the model
        only ever selects which view and filters, never authors data values,
        so the canvas can never show fabricated numbers or rows.

        Args:
            arguments: Tool arguments supplied by the caller.
            context: Shared execution context for the tool call.

        Returns:
            A `{"__render__": {"component", "props"}}` payload the canvas renders.
        """
        if not context.organization_id:
            raise ValidationError("organization_id is required for render_ui_component")

        component_id = _normalize_optional_string(arguments.get("component_id")) or ""
        if not component_id:
            # Dropped on a retry often enough to matter: the model re-sent a call
            # without it, got a bare "unsupported" back, and abandoned the
            # question instead of resending it complete.
            raise ValidationError(
                "component_id is required. Use 'dashboard_widget' for a metric as a chart "
                "or table, 'stat_tile' for a single number, 'pipeline_board'/'pipeline_list'/"
                "'pipeline_calendar' for a workflow's current board, 'entity_table' for a "
                "workflow's entities, or 'dashboard' for the saved dashboard. Resend the same "
                "arguments with component_id added."
            )
        if component_id not in self._RENDERABLE_COMPONENT_IDS:
            raise ValidationError(
                f"Unsupported component_id: {component_id!r}. Valid values: "
                f"{', '.join(self._RENDERABLE_COMPONENT_IDS)}."
            )

        actor = self._actor_from_context(context)

        if component_id in self._PIPELINE_VIEW_BY_COMPONENT:
            props = self._render_pipeline_component_props(component_id, actor, arguments)
        elif component_id == "entity_table":
            props = self._render_entity_table_props(actor, arguments)
        elif component_id == "dashboard_widget":
            props = self._render_dashboard_widget_props(actor, arguments)
        elif component_id == "dashboard":
            props = self._render_full_dashboard_props(actor)
        else:  # stat_tile
            props = self._render_stat_tile_props(actor, context.organization_id, arguments)

        return ToolExecutionResult(
            success=True,
            tool_name="render_ui_component",
            output={"__render__": {"component": component_id, "props": props}},
        )

    def _resolve_active_workflow(self, actor: ActorContext, identifier: str):  # noqa: ANN201
        """Resolve an active workflow from a machine_name, workflow id, or display name.

        The model often passes a human name ("Candidate Application") or a
        workflow id rather than the exact machine_name slug. Try the direct
        machine_name lookup first, then fall back to matching published
        workflows by id, machine_name, or case-insensitive name.
        """
        try:
            return self.workflow_service_manager.get_active_state_machine_for_actor(actor, identifier)
        except NotFoundError:
            pass

        from workflow.models.request import WorkflowListScopeRequest, WorkflowScope

        listing = self.workflow_service_manager.list_state_machines_scoped_for_actor(
            actor, WorkflowListScopeRequest(scope=WorkflowScope.PUBLISHED)
        )
        wanted = identifier.strip().lower()
        for item in listing.published_items:
            candidates = {
                str(item.id or "").lower(),
                str(item.machine_name or "").lower(),
                str(item.name or "").lower(),
            }
            if wanted in candidates:
                return self.workflow_service_manager.get_active_state_machine_for_actor(actor, item.machine_name)

        # Deduped, otherwise one workflow's version history filled the message
        # and truncated it mid-name, leaving nothing the model could act on.
        available = ", ".join(sorted({i.name for i in listing.published_items})) or "none"
        raise NotFoundError(
            f"workflow '{identifier}' was not found. Call list_workflows first. Available workflows: {available}"
        )

    def _render_pipeline_component_props(
        self,
        component_id: str,
        actor: ActorContext,
        arguments: dict[str, object],
    ) -> dict[str, object]:
        """Resolve one workflow + a citable summary for pipeline board/list/calendar.

        The widget loads its own entities from ``workflowId``, so the render
        props stay just the id + view.

        ``summary.rows`` is for the model to read, not the widget. Without it
        the model only saw counts and had to go looking for the rows this call
        had already loaded. Capped, so it stays a short reference.
        """
        if self.workflow_service_manager is None:
            raise ServiceError("workflow manager dependency is not configured")

        machine_name = _normalize_optional_string(arguments.get("machine_name"))
        if not machine_name:
            raise ValidationError("machine_name is required for this component")
        state = _normalize_optional_string(arguments.get("state"))

        workflow = self._resolve_active_workflow(actor, machine_name)
        entities = self.workflow_service_manager.list_enrollment_summaries_for_actor(
            actor, machine_name=workflow.machine_name, current_state=state
        )
        by_state: dict[str, int] = {}
        for item in entities.items:
            key = str(getattr(item, "current_state", "") or "")
            by_state[key] = by_state.get(key, 0) + 1

        rows = [
            {
                "entity_id": item.entity_id,
                "display_name": item.display_name,
                "current_state": item.current_state,
                "owner_name": item.owner_name,
                "assignee_name": item.assignee_name,
            }
            for item in entities.items[:_PIPELINE_SUMMARY_ROW_CAP]
        ]

        return {
            "workflowId": workflow.id,
            "view": self._PIPELINE_VIEW_BY_COMPONENT[component_id],
            "summary": {
                "total": len(entities.items),
                "by_state": by_state,
                "machine_name": machine_name,
                "workflow_name": workflow.name,
                "rows": rows,
                # So the model says "the first N" instead of treating a
                # short list as the whole board.
                "rows_truncated": len(entities.items) > len(rows),
            },
        }

    def _render_entity_table_props(
        self,
        actor: ActorContext,
        arguments: dict[str, object],
    ) -> dict[str, object]:
        """Fetch real entities for a read-only entity table.

        Includes ``entityType`` so the frontend resolves the same form schemas
        the records page uses, rendering real preview fields (not a field count).
        """
        if self.workflow_service_manager is None:
            raise ServiceError("workflow manager dependency is not configured")

        machine_name = _normalize_optional_string(arguments.get("machine_name"))
        if not machine_name:
            raise ValidationError("machine_name is required for this component")
        state = _normalize_optional_string(arguments.get("state"))

        workflow = self._resolve_active_workflow(actor, machine_name)
        entities = self.workflow_service_manager.list_enrollment_summaries_for_actor(
            actor, machine_name=workflow.machine_name, current_state=state
        )
        return {
            "entities": [item.model_dump(mode="json") for item in entities.items],
            "workflowId": workflow.id,
            "entityType": workflow.entity_type,
        }

    @classmethod
    def _widget_def_for_metric(
        cls,
        metric: str,
        viz: str | None,
        title: str | None,
        subtitle: str | None,
    ) -> dict[str, object]:
        """Build a synthetic DashboardWidgetDef for one metric, derived strictly
        from the metric registry (single source of truth for the real dashboard)."""
        from dashboard.metrics import METRIC_REGISTRY

        spec = next((s for s in METRIC_REGISTRY if s.key == metric), None)
        if spec is None:
            raise ValidationError(f"Unknown metric: {metric!r}")

        output = spec.output
        # A scalar metric drawn as a line or bar is one number in a chart frame,
        # which reads as a trend and is not one. The model reached for
        # entities.reached_state with viz=line for "chart tickets moved to Done
        # over time", so name the metric that actually plots that.
        if output == "scalar" and viz in cls._SERIES_VISUALS:
            raise ValidationError(
                f"{metric} returns a single number, so it cannot be charted as "
                f"{viz!r}. For movement into a state over time use metric "
                "transitions.over_time with a state filter; for one number drop "
                "the viz or use component_id stat_tile."
            )
        if output == "scalar":
            widget_type = "stat"
        elif output == "gauge":
            widget_type = "gauge"
        elif output == "rows":
            widget_type = "activity" if metric == "events.activity" else "table"
        else:  # series | multiseries
            widget_type = "chart"

        chosen_viz = viz if viz in cls._VALID_WIDGET_VIZ else None
        if chosen_viz is None:
            chosen_viz = spec.default_visuals[0] if spec.default_visuals else "bar"

        widget_def: dict[str, object] = {
            "id": f"agent-{metric}",
            "type": widget_type,
            "title": title or spec.label,
            "metric": metric,
            "viz": chosen_viz,
            "layout": {"x": 0, "y": 0, "w": 12, "h": 4},
        }
        if subtitle:
            widget_def["subtitle"] = subtitle
        return widget_def

    def _render_dashboard_widget_props(
        self,
        actor: ActorContext,
        arguments: dict[str, object],
    ) -> dict[str, object]:
        """Render one real dashboard widget: build its def from the metric
        registry and compute its data via the exact same path the dashboard uses."""
        if self.dashboard_service_manager is None:
            raise ServiceError("dashboard manager dependency is not configured")

        from dashboard.models.interface import WIDGET_RESULT_KIND_ERROR
        from dashboard.models.request import DashboardDataItem

        metric = _normalize_optional_string(arguments.get("metric"))
        if not metric:
            raise ValidationError("metric is required for dashboard_widget")
        viz = _normalize_optional_string(arguments.get("viz"))
        title = _normalize_optional_string(arguments.get("title"))
        subtitle = _normalize_optional_string(arguments.get("subtitle"))
        organization_id = str(actor.get("organization_id", ""))
        filters = self._build_metric_filters(actor, organization_id, metric, arguments)

        widget_def = self._widget_def_for_metric(metric, viz, title, subtitle)
        item = DashboardDataItem(widget_id=str(widget_def["id"]), metric=metric, filters=filters)
        response = self.dashboard_service_manager.get_data_for_actor(actor, [item])
        data = response.results.get(str(widget_def["id"]))
        # The dashboard turns a failed widget into an error payload so one bad
        # widget can't blank a page. A tool has no such page: hand the model an
        # error instead of props it would read as data.
        if isinstance(data, dict) and data.get("kind") == WIDGET_RESULT_KIND_ERROR:
            raise ValidationError(str(data.get("error") or f"metric {metric} failed"))
        return {"def": widget_def, "data": data}

    def _render_full_dashboard_props(self, actor: ActorContext) -> dict[str, object]:
        """Render the whole saved 'primary' dashboard: every widget def plus its
        computed data, exactly as the real dashboard page hydrates it."""
        if self.dashboard_service_manager is None:
            raise ServiceError("dashboard manager dependency is not configured")

        from dashboard.models.request import DashboardDataItem

        dashboard = self.dashboard_service_manager.get_dashboard_for_actor(actor, "primary")
        config = dashboard.config if isinstance(dashboard.config, dict) else {}
        widgets = config.get("widgets") or []

        items: list[Any] = []
        for widget in widgets:
            if not isinstance(widget, dict):
                continue
            widget_id = widget.get("id")
            if not widget_id:
                continue
            widget_filters = widget.get("filters") if isinstance(widget.get("filters"), dict) else {}
            if widget.get("query"):
                items.append(
                    DashboardDataItem(widget_id=str(widget_id), query=widget["query"], filters=widget_filters)
                )
            elif widget.get("metric"):
                items.append(
                    DashboardDataItem(widget_id=str(widget_id), metric=str(widget["metric"]), filters=widget_filters)
                )

        results: dict[str, object] = {}
        if items:
            response = self.dashboard_service_manager.get_data_for_actor(actor, items)
            results = dict(response.results)

        return {
            "widgets": [
                {"def": widget, "data": results.get(str(widget.get("id")))}
                for widget in widgets
                if isinstance(widget, dict) and widget.get("id")
            ]
        }

    # Metrics that count a named state. Without one they return 0, which reads
    # as a real answer, so require it here instead.
    _STATE_REQUIRED_METRICS = ("entities.in_state", "entities.reached_state")

    def _build_metric_filters(
        self,
        actor: ActorContext,
        organization_id: str,
        metric: str,
        arguments: dict[str, object],
    ) -> dict[str, object]:
        """Build the filter dict for any metric-backed component.

        stat_tile used to assemble its own filters and ignore ``filters``
        entirely, so date ranges passed with it were dropped and the answer came
        back all-time. Both renderers share this now so they cannot drift again.
        """
        raw_filters = arguments.get("filters")
        filters: dict[str, object] = dict(raw_filters) if isinstance(raw_filters, dict) else {}

        # Top-level convenience arguments win over the same key inside `filters`.
        # The time keys are lifted too: the model generalizes from `state` being
        # top level and passes time_range there, which used to be dropped -
        # silently answering an all-time number for a windowed question.
        for key in (
            "state",
            "entity_type_id",
            "workflow_id",
            "time_range",
            "date_from",
            "date_to",
        ):
            value = _normalize_optional_string(arguments.get(key))
            if value:
                filters[key] = value

        workflow_id = _normalize_optional_string(filters.get("workflow_id"))
        machine_name = _normalize_optional_string(arguments.get("machine_name"))
        if machine_name and not workflow_id:
            workflow_id = self._resolve_active_workflow(actor, machine_name).id
            if not workflow_id:
                # Scoping was asked for explicitly. Running unscoped would answer
                # about every workflow while looking like an answer about this one.
                raise ServiceError(
                    f"workflow '{machine_name}' has no id, so the metric cannot be "
                    "scoped to it."
                )
            filters["workflow_id"] = workflow_id

        self._normalize_entity_type_filter(organization_id, filters)
        self._resolve_state_filter(actor, filters, workflow_id=workflow_id)

        if metric in self._STATE_REQUIRED_METRICS and not _normalize_optional_string(
            filters.get("state")
        ):
            raise ValidationError(
                f"{metric} needs a state. Pass the state name, e.g. state='DONE'. "
                "Call list_workflows to see each workflow's states."
            )
        return filters

    def _resolve_state_filter(
        self,
        actor: ActorContext,
        filters: dict[str, object],
        workflow_id: str | None = None,
    ) -> None:
        """Correct the casing of a requested state, or fail naming the real ones.

        State names are matched exactly in SQL and are mixed case in practice
        (INITIAL, inprogress, Terminal). The model has no way to guess that, so
        "Done" silently counted zero rows. Resolve it here, where the answer can
        still be an error instead of a wrong number.
        """
        requested = _normalize_optional_string(filters.get("state"))
        if not requested or self.dashboard_service_manager is None:
            return

        options = self.dashboard_service_manager.get_filter_options_for_actor(
            actor, workflow_id=workflow_id
        )
        known = [option.value for option in options.states if option.value]
        if requested in known:
            return

        matches = sorted({name for name in known if name.lower() == requested.lower()})
        if len(matches) == 1:
            filters["state"] = matches[0]
            return

        available = ", ".join(sorted(known)) or "none"
        if not matches:
            # When the state exists but not in the workflow that was picked, say
            # so. Listing only that workflow's states invited the model to swap
            # the state for whichever listed name looked closest, so a question
            # about QA came back answered about REVIEW.
            if workflow_id:
                # The state may live in a workflow this scope cannot see, including
                # an unpublished one. Saying only "not in this workflow" sent the
                # model round every workflow in turn and then to the wrong state.
                org_wide = self.dashboard_service_manager.get_filter_options_for_actor(actor)
                org_states = [option.value for option in org_wide.states if option.value]
                elsewhere = sorted(
                    {name for name in org_states if name.lower() == requested.lower()}
                )
                if elsewhere:
                    exact = elsewhere[0]
                    raise ValidationError(
                        f"This workflow has no state {requested!r} (it has: {available}), but "
                        f"{exact!r} does exist in this organization. Re-run the same call "
                        "without machine_name to cover every workflow. Do not substitute a "
                        "different state and do not try the workflows one by one."
                    )
            raise ValidationError(
                f"Unknown state {requested!r}. Available states: {available}. "
                "Do not substitute a different state."
            )
        raise ValidationError(
            f"State {requested!r} matches more than one state ({', '.join(matches)}). "
            "Pass the exact name."
        )

    def _normalize_entity_type_filter(self, organization_id: str, filters: dict[str, object]) -> None:
        """Resolve a filters["entity_type_id"] that the model passed as a name to
        the real id in place. If it can't be resolved, drop it rather than
        silently filtering to zero (a wrong id matches no rows → misleading 0)."""
        raw = _normalize_optional_string(filters.get("entity_type_id"))
        if not raw:
            return
        resolved = self._resolve_entity_type_id(organization_id, raw)
        if resolved:
            filters["entity_type_id"] = resolved
        else:
            filters.pop("entity_type_id", None)

    def _render_stat_tile_props(
        self,
        actor: ActorContext,
        organization_id: str,
        arguments: dict[str, object],
    ) -> dict[str, object]:
        """Fetch one real KPI value for stat_tile, via the same query the Dashboard uses."""
        if self.dashboard_service_manager is None:
            raise ServiceError("dashboard manager dependency is not configured")

        metric = _normalize_optional_string(arguments.get("metric"))
        if metric not in self._RENDERABLE_METRICS:
            raise ValidationError(f"Unsupported metric: {metric!r}")

        filters = self._build_metric_filters(actor, organization_id, metric, arguments)
        result = self.dashboard_service_manager.db.run_metric(organization_id, metric, filters)
        label = _normalize_optional_string(arguments.get("label")) or metric.replace(".", " ").replace("_", " ").title()
        return {
            "value": result.get("value"),
            "prevValue": result.get("prevValue"),
            "trend": result.get("trend"),
            "subtitle": label,
        }

    def _execute_list_schedules(
        self, arguments: dict[str, object], context: ToolExecutionContext
    ) -> ToolExecutionResult:
        if self.schedules_service_manager is None:
            raise ServiceError("schedules manager dependency is not configured")
        response = self.schedules_service_manager.list_schedules_for_actor(
            self._actor_from_context(context),
            _normalize_optional_string(arguments.get("machine_name")),
        )
        return ToolExecutionResult(
            success=True,
            tool_name="list_schedules",
            output=response.model_dump(mode="json"),
        )

    def _execute_get_schedule(
        self, arguments: dict[str, object], context: ToolExecutionContext
    ) -> ToolExecutionResult:
        if self.schedules_service_manager is None:
            raise ServiceError("schedules manager dependency is not configured")
        schedule_id = str(arguments.get("schedule_id") or "").strip()
        if not schedule_id:
            raise ValidationError("schedule_id is required")
        schedule = self.schedules_service_manager.get_schedule_for_actor(
            self._actor_from_context(context), schedule_id
        )
        targets = self.schedules_service_manager.list_targets_for_actor(
            self._actor_from_context(context), schedule_id
        )
        return ToolExecutionResult(
            success=True,
            tool_name="get_schedule",
            output={
                "schedule": schedule.model_dump(mode="json"),
                "targets": targets.model_dump(mode="json"),
            },
        )

    def _execute_list_upcoming_scheduled_entities(
        self, arguments: dict[str, object], context: ToolExecutionContext
    ) -> ToolExecutionResult:
        if self.schedules_service_manager is None:
            raise ServiceError("schedules manager dependency is not configured")
        actor = self._actor_from_context(context)
        schedules = self.schedules_service_manager.list_schedules_for_actor(
            actor, _normalize_optional_string(arguments.get("machine_name"))
        ).items
        upcoming: list[dict[str, object]] = []
        for schedule in schedules:
            targets = self.schedules_service_manager.list_targets_for_actor(
                actor, schedule.schedule_id
            ).items
            upcoming.extend(
                {
                    "schedule_id": schedule.schedule_id,
                    "schedule_name": schedule.name,
                    "machine_name": schedule.machine_name,
                    "anchor_entity_id": target.anchor_entity_id,
                    "due_date": target.next_due_date.isoformat(),
                    "entity_creation_date": target.next_materialization_date.isoformat(),
                    "enabled": schedule.is_enabled and target.is_enabled,
                    "last_result": target.last_result,
                }
                for target in targets
            )
        upcoming.sort(key=lambda item: str(item["entity_creation_date"]))
        return ToolExecutionResult(
            success=True,
            tool_name="list_upcoming_scheduled_entities",
            output={"count": len(upcoming), "occurrences": upcoming},
        )

    def _execute_preview_schedule_run(
        self, arguments: dict[str, object], context: ToolExecutionContext
    ) -> ToolExecutionResult:
        if self.schedules_service_manager is None:
            raise ServiceError("schedules manager dependency is not configured")
        schedule_id = str(arguments.get("schedule_id") or "").strip()
        if not schedule_id:
            raise ValidationError("schedule_id is required")
        preview = self.schedules_service_manager.preview_run_now_for_actor(
            self._actor_from_context(context), schedule_id
        )
        return ToolExecutionResult(
            success=True,
            tool_name="preview_schedule_run",
            output=preview.model_dump(mode="json"),
        )

    def _execute_run_schedule_now(
        self, arguments: dict[str, object], context: ToolExecutionContext
    ) -> ToolExecutionResult:
        if self.schedules_service_manager is None:
            raise ServiceError("schedules manager dependency is not configured")
        schedule_id = str(arguments.get("schedule_id") or "").strip()
        if not schedule_id:
            raise ValidationError("schedule_id is required")
        invocation_id = str(arguments.get("invocation_id") or "").strip()
        if not invocation_id:
            raise ValidationError("invocation_id from preview_schedule_run is required")
        actor = self._actor_from_context(context)
        actor["source"] = "agent"
        result = self.schedules_service_manager.run_now_for_actor(
            actor,
            schedule_id,
            ScheduleRunNowRequest(invocation_id=invocation_id),
        )
        return ToolExecutionResult(
            success=True,
            tool_name="run_schedule_now",
            output=result.model_dump(mode="json"),
        )

    def _execute_calendar_invite(
        self,
        arguments: dict[str, object],
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        """Execute the modular calendar-invite scheduling tool.

        Args:
            arguments: Tool arguments supplied by the caller.
            context: Shared execution context for the tool call.

        Returns:
            The normalized scheduling result.
        """
        if self.integrations_service_manager is None:
            raise ServiceError("integrations manager dependency is not configured")
        if not context.organization_id:
            raise ValidationError("organization_id is required for calendar invite execution")
        if not context.user_id:
            raise ValidationError("user_id is required for calendar invite execution")

        starts_at = arguments.get("starts_at")
        ends_at = arguments.get("ends_at")
        if not starts_at or not ends_at:
            raise ValidationError("starts_at and ends_at are required")

        event = self.integrations_service_manager.schedule_event(
            {
                "organization_id": context.organization_id,
                "user_id": context.user_id,
                "provider": arguments.get("provider", "google"),
                "title": arguments.get("title", "Agent Scheduled Event"),
                "starts_at": starts_at,
                "ends_at": ends_at,
                "attendees": list(arguments.get("attendees") or []),
                "entity_id": arguments.get("entity_id") or context.entity_id,
            }
        )
        event_payload = event.model_dump() if hasattr(event, "model_dump") else event.to_dict()
        return ToolExecutionResult(success=True, tool_name="send_calendar_invite", output=event_payload)

    def _execute_connector_tool(
        self,
        tool_name: str,
        arguments: dict[str, object],
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        """Execute an org-scoped connector that has been exposed as a tool."""
        if self.connectors_service_manager is None:
            raise ServiceError("connectors manager dependency is not configured")
        if not context.organization_id:
            raise ValidationError("organization_id is required for connector tool execution")

        connector_id = self._connector_id_from_tool_name(tool_name)
        contract = self.connectors_service_manager.db_model_service.get_connector(
            connector_id,
            context.organization_id,
        )
        if contract is None or not contract.expose_as_tool:
            raise NotFoundError(f"connector tool not found: {tool_name}")

        secrets = self.connectors_service_manager.db_model_service.get_decrypted_secrets(
            connector_id,
            context.organization_id,
        )
        # {{input}} placeholders are filled from the agent's arguments;
        # $entity.field placeholders are auto-filled from the bound entity.
        field_values = {
            key: self._stringify_connector_input(value)
            for key, value in (arguments or {}).items()
        }
        entity_values = self._resolve_connector_entity_values(contract, arguments, context)
        result = self.connectors_service_manager.run_connector_call(
            contract=contract,
            secrets=secrets,
            field_values=field_values,
            entity_values=entity_values,
        )
        output = {
            "success": result.ok,
            "status_code": result.status_code,
            "mapped_fields": dict(result.mapped_fields or {}),
            "response_summary": result.response_summary,
            "entity_write_back": self._write_back_connector_response(
                contract, result, arguments, context
            ),
        }
        return ToolExecutionResult(
            success=result.ok,
            tool_name=tool_name,
            output=output,
            error=result.error,
        )

    def _write_back_connector_response(
        self,
        contract: ConnectorContract,
        result: ConnectorCallResult,
        arguments: dict[str, object],
        context: ToolExecutionContext,
    ) -> dict[str, object]:
        """Persist a connector's mapped response fields onto its bound entity.

        Only runs for an entity-bound connector whose call succeeded and produced
        mapped fields, when an entity id is resolvable. The HTTP call already
        happened, so a write-back failure is logged and reported in the output but
        does not flip the tool's success flag (that reflects the API call itself).
        """
        mapped = dict(result.mapped_fields or {})
        if not (result.ok and mapped and contract.entity_types):
            return {"written": False}
        entity_id, _ = self._resolve_execution_entity_metadata(context, arguments)
        if not entity_id:
            return {"written": False, "reason": "no entity id in context"}
        if self.entities_service_manager is None:
            logger.error("connector write-back skipped: entities manager not configured")
            return {"written": False, "error": "entities manager not configured"}
        return self._apply_entity_write_back(entity_id, mapped, context)

    def _apply_entity_write_back(
        self,
        entity_id: str,
        mapped: dict[str, Any],
        context: ToolExecutionContext,
    ) -> dict[str, object]:
        """Update one entity with the mapped fields, reporting the outcome."""
        from entities.models.request import EntityRecordUpdateRequest

        try:
            record = self.entities_service_manager.update_entity_record_for_actor(
                self._actor_from_context(context),
                entity_id,
                EntityRecordUpdateRequest(data=dict(mapped)),
                organization_id=context.organization_id,
            )
        except Exception as exc:  # noqa: BLE001 - surface, never abort the succeeded call
            logger.exception(f"connector write-back failed entity={entity_id}")
            return {"written": False, "entity_id": entity_id, "error": str(exc)}
        if record is None:
            logger.error(f"connector write-back: entity not found {entity_id}")
            return {"written": False, "entity_id": entity_id, "error": "entity not found"}
        return {"written": True, "entity_id": entity_id, "fields": sorted(mapped)}

    def _resolve_connector_entity_values(
        self,
        contract: ConnectorContract,
        arguments: dict[str, object],
        context: ToolExecutionContext,
    ) -> dict[str, str]:
        """Read the bound entity's record to fill the connector's $entity.field placeholders.

        Returns an empty mapping (placeholders resolve to "") when the connector
        uses no entity placeholders, no entity id is resolvable, or the record
        cannot be read — the call still proceeds with whatever inputs it has.
        """
        entity_names = self._connector_entity_placeholder_names(contract)
        if not entity_names:
            return {}
        entity_id, _ = self._resolve_execution_entity_metadata(context, arguments)
        if not entity_id:
            logger.warning("connector $entity.* placeholders present but no entity id in context")
            return {}
        if self.entities_service_manager is None:
            logger.error("connector entity placeholders skipped: entities manager not configured")
            return {}
        try:
            record = self.entities_service_manager.get_entity_record_for_actor(
                self._actor_from_context(context),
                entity_id,
                organization_id=context.organization_id,
            )
        except Exception:
            logger.exception(f"connector entity placeholder read failed entity={entity_id}")
            return {}
        data = dict(record.data or {})
        return {
            name: self._stringify_connector_input(data[name])
            for name in entity_names
            if name in data
        }

    # endregion Modular Tool Handlers

    # region Internal Helpers
    def _select_execution_path(self, tool_name: str) -> str:
        """Select the execution backend for one tool.

        Args:
            tool_name: Tool name to resolve.

        Returns:
            The execution backend identifier for the tool.
        """
        if tool_name in self._native_tool_handlers:
            return "modular"
        if self._is_connector_tool_name(tool_name):
            return "modular"
        return PLATFORM_RUNTIME_EXECUTION_BACKEND

    def _build_execution_log_payload(
        self,
        *,
        context: ToolExecutionContext,
        tool_name: str,
        arguments: dict[str, object],
        execution_backend: str,
        duration_ms: int,
        result: ToolExecutionResult | None,
        error: Exception | None,
    ) -> dict[str, object]:
        """Build the normalized execution-log payload for one tool attempt.

        Args:
            context: Shared execution context for the tool call.
            tool_name: Executed tool name.
            arguments: Normalized tool arguments.
            execution_backend: Backend used for execution.
            duration_ms: Total execution duration in milliseconds.
            result: Successful or failed normalized result, when available.
            error: Raised execution error, when execution failed with an exception.

        Returns:
            The normalized execution-log payload.
        """
        entity_id, entity_type = self._resolve_execution_entity_metadata(context, arguments)
        result_payload = dict(result.output or {}) if result is not None else {}
        resolved_entity_id = _normalize_optional_string(result_payload.get("entity_id"))
        if resolved_entity_id:
            entity_id = resolved_entity_id
        error_message = str(error) if error is not None else (result.error if result is not None else None)
        success = bool(result.success) if result is not None else False
        return {
            "organization_id": context.organization_id,
            "user_id": context.user_id,
            "actor_id": context.actor_id,
            "actor_type": context.actor_type,
            "source": context.source,
            "tool_name": tool_name,
            "arguments": arguments,
            "result": result_payload,
            "success": success,
            "error": error_message,
            "duration_ms": duration_ms,
            "execution_backend": execution_backend,
            "run_id": context.run_id,
            "session_id": context.session_id,
            "entity_id": entity_id,
            "entity_type": entity_type,
            "request_id": context.request_id,
            "metadata": dict(context.metadata or {}),
        }

    def _persist_execution_result(
        self, payload: dict[str, object]
    ) -> ToolExecutionLogContract | None:
        """Persist one tool execution log row, best-effort.

        Args:
            payload: Normalized execution-log payload.

        Returns:
            The persisted execution-log contract, or None when the write failed.

        The tool's work is finished by the time this runs, so a failure to
        record it must not turn a successful call into a failed one.
        """
        try:
            return self.db_model_service.create_execution_log(payload)
        except PersistenceError:
            logger.exception(f"tool execution log write failed for {payload.get('tool_name')}")
            return None

    @staticmethod
    def _resolve_execution_entity_metadata(
        context: ToolExecutionContext,
        arguments: dict[str, object],
    ) -> tuple[str | None, str | None]:
        """Resolve entity metadata for execution logging.

        Args:
            context: Shared execution context for the tool call.
            arguments: Normalized tool arguments.

        Returns:
            The resolved entity identifier and entity type.
        """
        entity_id = context.entity_id or _normalize_optional_string(arguments.get("entity_id"))
        if entity_id is None:
            entity_id = _normalize_optional_string(arguments.get("from_entity_id"))
        if entity_id is None:
            entity_id = _normalize_optional_string(arguments.get("to_entity_id"))

        entity_type = context.entity_type or _normalize_optional_string(arguments.get("entity_type"))
        if entity_type is None:
            entity_type = _normalize_optional_string(arguments.get("from_entity_type"))
        if entity_type is None:
            entity_type = _normalize_optional_string(arguments.get("to_entity_type"))
        return entity_id, entity_type

    def _entity_type_records(self, organization_id: str) -> list:
        """Fetch the org's entity type records, or [] when unavailable."""
        if self.entities_service_manager is None:
            return []
        try:
            return list(self.entities_service_manager.list_entity_type_records(organization_id=organization_id))
        except Exception:  # noqa: BLE001
            return []

    def _resolve_entity_type_id(self, organization_id: str, value: str | None) -> str | None:
        """Resolve an entity-type reference (real id, full name, or short name)
        to the canonical entity_type_id.

        The model routinely passes a human value like "candidate" instead of the
        stored id or the fully-qualified name ("ATS.Candidate"); match all three
        so those calls succeed instead of silently filtering to nothing.
        """
        if not value:
            return None
        wanted = value.strip().lower()
        for record in self._entity_type_records(organization_id):
            name = str(getattr(record, "name", "") or "")
            short = name.split(".")[-1]
            candidates = {
                str(getattr(record, "entity_type_id", "") or "").lower(),
                name.lower(),
                short.lower(),
            }
            if wanted in candidates:
                return record.entity_type_id
        return None

    @staticmethod
    def _actor_from_context(context: ToolExecutionContext) -> ActorContext:
        """Build an actor dict from a tool execution context.

        Lets tool handlers call the entities module's actor-facing methods so a
        tool runs with the invoking user's identity and roles (the agent acts on
        behalf of that user), inheriting the same RBAC and data invariants.
        """
        return {
            "user_id": context.user_id or "",
            "organization_id": context.organization_id or "",
            "roles": list(context.roles or []),
            "request_id": context.request_id or "",
        }

    @staticmethod
    def _require_actor_field(actor: ActorContext, field_name: str) -> str:
        """Require one non-empty actor field from request context.

        Args:
            actor: Current request actor context.
            field_name: Actor field that must be present.

        Returns:
            The normalized actor field value.
        """
        value = actor_str(actor, field_name)
        if not value:
            raise ValidationError(f"Missing actor field: {field_name}")
        return value

    def _connector_contracts_for_org(self, organization_id: str) -> list[ConnectorContract]:
        if self.connectors_service_manager is None:
            return []
        return self.connectors_service_manager.db_model_service.list_connectors(organization_id)

    def _connector_tool_descriptor(
        self,
        organization_id: str,
        tool_name: str,
    ) -> ToolDescriptorContract | None:
        for descriptor in self.list_connector_tool_descriptors(organization_id):
            if descriptor.name == tool_name:
                return descriptor
        return None

    def _build_connector_tool_descriptor(
        self,
        connector: ConnectorContract,
    ) -> ToolDescriptorContract:
        # Only {{input}} placeholders are asked of the agent; $entity.field
        # placeholders are auto-filled from the bound entity at call time.
        placeholders = sorted(self._connector_input_placeholder_names(connector))
        properties = {
            name: {
                "type": "string",
                "description": f"Value for connector input '{name}'",
            }
            for name in placeholders
        }
        return ToolDescriptorContract(
            name=self._connector_tool_name(connector.id),
            display_name=connector.name,
            description=f"Run connector '{connector.name}' against {connector.method} {connector.base_url}{connector.path or ''}",
            category="connector",
            risk_level="medium" if connector.method != "GET" else "low",
            default_enabled=connector.method == "GET",
            mcp_exposed=True,
            is_mutating=connector.method != "GET",
            parameters=self._schema(required=placeholders or None, properties=properties),
        )

    def _connector_input_placeholder_names(self, connector: ConnectorContract) -> set[str]:
        """Return the {{input}} placeholder names — the connector's caller-supplied inputs."""
        if self.connectors_service_manager is None:
            return set()
        return self._connector_placeholder_names(
            connector, self.connectors_service_manager.curly_placeholder
        )

    def _connector_entity_placeholder_names(self, connector: ConnectorContract) -> set[str]:
        """Return the $entity.field placeholder names — auto-filled from the bound entity."""
        if self.connectors_service_manager is None:
            return set()
        return self._connector_placeholder_names(
            connector, self.connectors_service_manager.entity_placeholder
        )

    def _connector_placeholder_names(
        self, connector: ConnectorContract, pattern: Any
    ) -> set[str]:
        """Collect placeholder names matching ``pattern`` across the connector's request fields."""
        names: set[str] = set()
        names.update(self._placeholder_names_in_value(connector.path, pattern))
        names.update(self._placeholder_names_in_value(connector.headers, pattern))
        names.update(self._placeholder_names_in_value(connector.query_params, pattern))
        names.update(self._placeholder_names_in_value(connector.body_template, pattern))
        return names

    def _placeholder_names_in_value(self, value: Any, pattern: Any) -> set[str]:
        """Recursively collect ``pattern`` placeholder names from a string/dict/list value."""
        names: set[str] = set()
        if isinstance(value, str):
            names.update(match.group(1) for match in pattern.finditer(value))
            return names
        if isinstance(value, dict):
            for item in value.values():
                names.update(self._placeholder_names_in_value(item, pattern))
            return names
        if isinstance(value, list):
            for item in value:
                names.update(self._placeholder_names_in_value(item, pattern))
        return names

    @staticmethod
    def _is_connector_tool_name(tool_name: str) -> bool:
        return bool(re.fullmatch(r"connector__[a-f0-9]{32}", str(tool_name or "")))

    @staticmethod
    def _connector_tool_name(connector_id: str) -> str:
        return f"connector__{str(connector_id).replace('-', '').lower()}"

    @staticmethod
    def _connector_id_from_tool_name(tool_name: str) -> str:
        normalized = str(tool_name).removeprefix("connector__")
        if len(normalized) != 32:
            raise ValidationError(f"Invalid connector tool name: {tool_name}")
        return (
            f"{normalized[0:8]}-{normalized[8:12]}-{normalized[12:16]}-"
            f"{normalized[16:20]}-{normalized[20:32]}"
        )

    @staticmethod
    def _stringify_connector_input(value: object) -> str:
        if isinstance(value, str):
            return value
        return json.dumps(value)

    @staticmethod
    def _schema(*, required: list[str] | None = None, properties: dict[str, Any] | None = None) -> dict[str, Any]:
        """Build a JSON-schema payload for a tool descriptor.

        Args:
            required: Required field names for the schema.
            properties: Schema property definitions.

        Returns:
            The normalized JSON-schema payload.
        """
        payload: dict[str, Any] = {"type": "object", "properties": properties or {}}
        if required:
            payload["required"] = required
        return payload

    def _build_catalog(self) -> list[ToolDescriptorContract]:
        """Build the canonical ordered shared tool catalog.

        Args:
            None.

        Returns:
            The ordered shared tool descriptor list.
        """
        return [
            *self._build_document_tool_descriptors(),
            *self._build_entity_tool_descriptors(),
            *self._build_workflow_tool_descriptors(),
            *self._build_canvas_tool_descriptors(),
            *self._build_communication_tool_descriptors(),
            *self._build_integration_tool_descriptors(),
        ]

    def _build_document_tool_descriptors(self) -> list[ToolDescriptorContract]:
        """Build document-oriented tool descriptors.

        Args:
            None.

        Returns:
            Document-oriented tool descriptors.
        """
        schema = self._schema
        return [
            ToolDescriptorContract(
                name="read_document",
                display_name="Read Document",
                description="Read and extract text from an uploaded document (PDF, Word, spreadsheet, image, or text)",
                category="document",
                risk_level="low",
                default_enabled=True,
                mcp_exposed=True,
                parameters=schema(
                    properties={
                        "document_id": {"type": "string"},
                        "storage_key": {"type": "string"},
                    }
                ),
            ),
            ToolDescriptorContract(
                name="read_job_document",
                display_name="Read Job Document(s)",
                description=(
                    "Read and extract text from up to "
                    f"{READ_JOB_DOCUMENT_MAX_FILES_PER_CALL} uploaded documents at once, "
                    "by file slug (e.g. \"file_1\", \"file_2\" — the slugs given to you in "
                    "the job's file list, never a raw id). Built for the bulk-import "
                    "extraction agent, which owns one job's whole file set in a single "
                    "run. Each file gets its own status in the response — one bad or "
                    "oversized file never fails the others in the same call. An "
                    "unrecognized slug comes back as a per-file error, not a failed call."
                ),
                category="document",
                risk_level="low",
                default_enabled=False,
                mcp_exposed=True,
                parameters=schema(
                    required=["file_ids"],
                    properties={
                        "file_ids": {
                            "type": "array",
                            "description": "File slugs (e.g. \"file_1\"), not raw ids.",
                            "items": {"type": "string"},
                            "maxItems": READ_JOB_DOCUMENT_MAX_FILES_PER_CALL,
                        },
                    },
                ),
            ),
            ToolDescriptorContract(
                name="list_document_types",
                display_name="List Document Types",
                description="Discover document type configurations",
                category="document",
                risk_level="low",
                default_enabled=True,
                parameters=schema(properties={"active_only": {"type": "boolean"}}),
            ),
        ]

    def _build_entity_tool_descriptors(self) -> list[ToolDescriptorContract]:
        """Build entity-oriented tool descriptors.

        Args:
            None.

        Returns:
            Entity-oriented tool descriptors.
        """
        schema = self._schema
        return [
            ToolDescriptorContract(
                name="get_entity",
                display_name="Get Entity",
                description="Read the current entity data to understand existing fields",
                category="entity",
                risk_level="low",
                default_enabled=True,
                mcp_exposed=True,
                parameters=schema(required=["entity_id"], properties={"entity_id": {"type": "string"}}),
            ),
            ToolDescriptorContract(
                name="get_form_schema",
                display_name="Get Form Schema",
                description=(
                    "Get field definitions (exact keys) for an entity type. A field of "
                    "type \"table\" includes a `table` block with its columns (each with a "
                    "`key`) and row_mode; to fill it via update_entity, set that field to a "
                    "list of row objects keyed by the column keys."
                ),
                category="entity",
                risk_level="low",
                default_enabled=True,
                mcp_exposed=True,
                parameters=schema(required=["entity_type"], properties={"entity_type": {"type": "string"}}),
            ),
            ToolDescriptorContract(
                name="create_entity",
                display_name="Create Entity",
                description=(
                    "Create a new entity record of a given type. entity_type_id may be the entity "
                    "type's id OR its name (e.g. \"candidate\" or \"ATS.Candidate\") - call "
                    "list_entity_types first if you're unsure which types exist, or list_workflows "
                    "to see each workflow's entity_type. data should include an \"identifier\" field "
                    "- a unique, human-readable name for this record (e.g. a person's full name) - "
                    "alongside the other extracted fields."
                ),
                category="entity",
                risk_level="medium",
                default_enabled=True,
                mcp_exposed=True,
                is_mutating=True,
                parameters=schema(
                    required=["entity_type_id", "data"],
                    properties={
                        "entity_type_id": {
                            "type": "string",
                            "description": "Entity type id or name (e.g. 'candidate'). Resolved server-side.",
                        },
                        "data": {
                            "type": "object",
                            "properties": {
                                "identifier": {
                                    "type": "string",
                                    "description": "Unique, human-readable name for this record (e.g. a person's full name).",
                                }
                            },
                        },
                        "owner_id": {"type": "string"},
                        "source_entity_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "Optional ids of existing provider records to link this new record to "
                                "(for entity types that reference another type). Include the owning "
                                "record's id when creating from within its context; omit if unknown."
                            ),
                        },
                    },
                ),
            ),
            ToolDescriptorContract(
                name="update_entity",
                display_name="Update Entity",
                description="Update entity fields with extracted or edited data",
                category="entity",
                risk_level="medium",
                default_enabled=True,
                mcp_exposed=True,
                is_mutating=True,
                parameters=schema(
                    required=["entity_id", "data"],
                    properties={
                        "entity_id": {"type": "string"},
                        "data": {"type": "object"},
                        "owner_id": {"type": "string"},
                    },
                ),
            ),
            ToolDescriptorContract(
                name="delete_entity",
                display_name="Delete Entity",
                description="Archive (soft-delete) an entity record",
                category="entity",
                risk_level="high",
                default_enabled=False,
                mcp_exposed=True,
                is_mutating=True,
                parameters=schema(
                    required=["entity_id"],
                    properties={"entity_id": {"type": "string"}},
                ),
            ),
            ToolDescriptorContract(
                name="list_entities",
                display_name="List Entities",
                description="List entities with optional filters",
                category="entity",
                risk_level="low",
                default_enabled=False,
                parameters=schema(properties={"entity_type": {"type": "string"}, "owner_id": {"type": "string"}}),
            ),
            ToolDescriptorContract(
                name="search_entities",
                display_name="Search Entities",
                description="Search entities by text in their data fields",
                category="entity",
                risk_level="low",
                default_enabled=True,
                parameters=schema(
                    required=["entity_type", "query"],
                    properties={
                        "entity_type": {"type": "string"},
                        "query": {"type": "string"},
                        "field": {"type": "string"},
                    },
                ),
            ),
            ToolDescriptorContract(
                name="list_entity_types",
                display_name="List Entity Types",
                description="Discover available entity types",
                category="entity",
                risk_level="low",
                default_enabled=True,
                mcp_exposed=True,
                parameters=schema(),
            ),
            ToolDescriptorContract(
                name="get_picklist_values",
                display_name="Get Picklist Values",
                description="Get valid dropdown values for picklists",
                category="entity",
                risk_level="low",
                default_enabled=True,
                mcp_exposed=True,
                parameters=schema(properties={"picklist_id": {"type": "string"}}),
            ),
            ToolDescriptorContract(
                name="create_relation",
                display_name="Create Relation",
                description="Link entities together",
                category="entity",
                risk_level="medium",
                default_enabled=False,
                parameters=schema(
                    required=["from_entity_id", "from_entity_type", "to_entity_id", "to_entity_type", "relation_type"],
                    properties={
                        "from_entity_id": {"type": "string"},
                        "from_entity_type": {"type": "string"},
                        "to_entity_id": {"type": "string"},
                        "to_entity_type": {"type": "string"},
                        "relation_type": {"type": "string"},
                        "metadata": {"type": "object"},
                    },
                ),
            ),
            ToolDescriptorContract(
                name="list_relations",
                display_name="List Relations",
                description="List relations for an entity",
                category="entity",
                risk_level="low",
                default_enabled=False,
                parameters=schema(required=["entity_id"], properties={"entity_id": {"type": "string"}}),
            ),
        ]

    def _build_workflow_tool_descriptors(self) -> list[ToolDescriptorContract]:
        """Build workflow-oriented tool descriptors.

        Args:
            None.

        Returns:
            Workflow-oriented tool descriptors.
        """
        schema = self._schema
        return [
            ToolDescriptorContract(
                name="get_entity_state",
                display_name="Get Entity State",
                description="Check the current workflow state",
                category="workflow",
                risk_level="low",
                default_enabled=False,
                parameters=schema(required=["entity_id"], properties={"entity_id": {"type": "string"}}),
            ),
            ToolDescriptorContract(
                name="get_available_transitions",
                display_name="Get Available Transitions",
                description="See what state transitions are available",
                category="workflow",
                risk_level="low",
                default_enabled=False,
                parameters=schema(required=["entity_id"], properties={"entity_id": {"type": "string"}}),
            ),
            ToolDescriptorContract(
                name="enroll_entity_in_workflow",
                display_name="Enroll Entity In Workflow",
                description=(
                    "Enroll an existing entity record into the active version of a workflow so it "
                    "appears on that workflow's board and lists. A newly created entity is NOT on "
                    "any board until it is enrolled - after create_entity, call this to make it "
                    "visible. machine_name may be the workflow's machine_name, id, or display name "
                    "(e.g. \"Candidate Application\")."
                ),
                category="workflow",
                risk_level="medium",
                default_enabled=True,
                mcp_exposed=True,
                is_mutating=True,
                parameters=schema(
                    required=["entity_id", "machine_name"],
                    properties={
                        "entity_id": {"type": "string"},
                        "machine_name": {
                            "type": "string",
                            "description": "Workflow machine_name, id, or display name (e.g. 'Candidate Application').",
                        },
                    },
                ),
            ),
            ToolDescriptorContract(
                name="move_entity_to_state",
                display_name="Move Entity To State",
                description=(
                    "Move an entity to a target workflow state by name (e.g. 'SCREENING', 'HIRED'). "
                    "Finds and runs the correct transition automatically - you do NOT need the trigger "
                    "name. Pass entity_id and target_state. Reports a no-op if it is already in that state, "
                    "or lists the reachable states if the move isn't allowed from the current state."
                ),
                category="workflow",
                risk_level="high",
                default_enabled=True,
                mcp_exposed=True,
                is_mutating=True,
                parameters=schema(
                    required=["entity_id", "target_state"],
                    properties={
                        "entity_id": {"type": "string"},
                        "target_state": {"type": "string", "description": "Target state name, e.g. 'SCREENING'."},
                    },
                ),
            ),
            ToolDescriptorContract(
                name="list_workflows",
                display_name="List Workflows",
                description="Discover available workflows (pipelines) and their machine_name identifiers, for use with render_ui_component",
                category="workflow",
                risk_level="low",
                default_enabled=True,
                mcp_exposed=True,
                parameters=schema(),
            ),
            ToolDescriptorContract(
                name="execute_transition",
                display_name="Execute Transition",
                description="Move an entity to a new workflow state",
                category="workflow",
                risk_level="high",
                default_enabled=False,
                parameters=schema(
                    required=["entity_id", "trigger"],
                    properties={
                        "entity_id": {"type": "string"},
                        "trigger": {"type": "string"},
                        "inputs": {"type": "object"},
                    },
                ),
            ),
            ToolDescriptorContract(
                name="create_signal",
                display_name="Create Signal",
                description="Schedule a future action or reminder",
                category="workflow",
                risk_level="medium",
                default_enabled=False,
                parameters=schema(
                    required=["entity_id", "entity_type", "signal_type"],
                    properties={
                        "entity_id": {"type": "string"},
                        "entity_type": {"type": "string"},
                        "signal_type": {"type": "string"},
                        "due_at": {"type": "string"},
                        "target_playbook": {"type": "string"},
                        "payload": {"type": "object"},
                    },
                ),
            ),
            ToolDescriptorContract(
                name="list_signals",
                display_name="List Signals",
                description="List signals optionally filtered by entity",
                category="workflow",
                risk_level="low",
                default_enabled=False,
                parameters=schema(properties={"entity_id": {"type": "string"}}),
            ),
            ToolDescriptorContract(
                name="list_schedules",
                display_name="List Schedules",
                description="List readable recurring entity schedules, optionally for one workflow",
                category="workflow",
                risk_level="low",
                default_enabled=True,
                mcp_exposed=True,
                parameters=schema(properties={"machine_name": {"type": "string"}}),
            ),
            ToolDescriptorContract(
                name="get_schedule",
                display_name="Get Schedule",
                description="Read one schedule, its conditions, recurrence, and target entities",
                category="workflow",
                risk_level="low",
                default_enabled=True,
                mcp_exposed=True,
                parameters=schema(required=["schedule_id"], properties={"schedule_id": {"type": "string"}}),
            ),
            ToolDescriptorContract(
                name="list_upcoming_scheduled_entities",
                display_name="List Upcoming Scheduled Entities",
                description="List entities that schedules will create, with creation and due dates",
                category="workflow",
                risk_level="low",
                default_enabled=True,
                mcp_exposed=True,
                parameters=schema(properties={"machine_name": {"type": "string"}}),
            ),
            ToolDescriptorContract(
                name="preview_schedule_run",
                display_name="Preview Schedule Run",
                description="Preview which related records are eligible or skipped before running a schedule now",
                category="workflow",
                risk_level="low",
                default_enabled=True,
                mcp_exposed=True,
                parameters=schema(required=["schedule_id"], properties={"schedule_id": {"type": "string"}}),
            ),
            ToolDescriptorContract(
                name="run_schedule_now",
                display_name="Run Schedule Now",
                description="Queue the next scheduled entity occurrence immediately for every eligible related record",
                category="workflow",
                risk_level="high",
                default_enabled=False,
                mcp_exposed=True,
                is_mutating=True,
                parameters=schema(
                    required=["schedule_id", "invocation_id"],
                    properties={
                        "schedule_id": {"type": "string"},
                        "invocation_id": {
                            "type": "string",
                            "description": "Invocation id returned by preview_schedule_run",
                        },
                    },
                ),
            ),
            ToolDescriptorContract(
                name="list_events",
                display_name="List Calendar Events",
                description=(
                    "List calendar events (Google/Outlook meetings) linked to an entity. "
                    "Returns meeting title, start/end time and attendees only. "
                    "This is NOT the record's comment or activity history - "
                    "use list_stage_comments for comments and recent updates."
                ),
                category="workflow",
                risk_level="low",
                default_enabled=False,
                mcp_exposed=True,
                parameters=schema(
                    required=["entity_id"],
                    properties={
                        "entity_id": {"type": "string"},
                        "provider": {"type": "string"},
                        "user_id": {"type": "string"},
                    },
                ),
            ),
        ]

    def _build_canvas_tool_descriptors(self) -> list[ToolDescriptorContract]:
        """Build Agent Mode canvas-rendering tool descriptors.

        Args:
            None.

        Returns:
            Canvas-oriented tool descriptors.
        """
        schema = self._schema
        return [
            ToolDescriptorContract(
                name="render_ui_component",
                display_name="Render UI Component",
                description=(
                    "Render one of the app's real UI components onto the user's Agent Mode canvas, "
                    "populated with live data fetched from the database - never author data values yourself. "
                    "component_id selects what to render: "
                    "'dashboard' (the whole saved dashboard with every widget), "
                    "'dashboard_widget' (one dashboard widget - pass metric, optional viz/title/subtitle/filters; "
                    "metric is any dashboard metric such as pipeline.by_state, entities.count, entities.in_state, "
                    "entities.reached_state, sla.breaches, sla.compliance, events.activity, incidents.trend), "
                    "'pipeline_board' / 'pipeline_list' / 'pipeline_calendar' (one workflow's board as kanban, list, "
                    "or calendar; machine_name required, call list_workflows first if you don't know it, state is an "
                    "optional filter), "
                    "'entity_table' (a real table of a workflow's entities; machine_name required, state optional), or "
                    "'stat_tile' (one simple KPI number; metric required: entities.count, entities.in_state, "
                    "entities.reached_state, or sla.breaches - the in_state/reached_state metrics also require state). "
                    "Pick the metric by what is being asked: 'how many MOVED TO / went into / were completed in a "
                    "period' is entities.reached_state, which counts state changes and is the one to use with a date "
                    "window; 'how many are CURRENTLY IN a state right now' is entities.in_state. For a chart of "
                    "movement over time use dashboard_widget with metric transitions.over_time and a state filter. "
                    "To LIST or SHOW which entities moved into a state during a period, use dashboard_widget with "
                    "metric entities.reached_state_list - never pipeline_board/pipeline_list/entity_table for that, "
                    "because those show whatever is sitting in the state now and ignore the date window, which lists "
                    "far more rows than the count you just reported. That metric returns at most 50 rows by default "
                    "alongside a `total`: state the total, and say the rows are the first N when total exceeds them."
                ),
                category="canvas",
                risk_level="low",
                default_enabled=False,
                mcp_exposed=True,
                is_mutating=False,
                parameters=schema(
                    required=["component_id"],
                    properties={
                        "component_id": {
                            "type": "string",
                            "enum": [
                                "dashboard",
                                "dashboard_widget",
                                "pipeline_board",
                                "pipeline_list",
                                "pipeline_calendar",
                                "entity_table",
                                "stat_tile",
                            ],
                        },
                        "machine_name": {
                            "type": "string",
                            "description": (
                                "Workflow machine_name (from list_workflows). Required for "
                                "pipeline_* and entity_table; optional on stat_tile and "
                                "dashboard_widget, where it scopes the metric to that workflow."
                            ),
                        },
                        "state": {
                            "type": "string",
                            "description": (
                                "State name, matched exactly. Use the state the user named, "
                                "verbatim. Never answer about a different state because it looks "
                                "similar - QA is not REVIEW, and swapping them returns different "
                                "tickets. list_workflows only shows published workflows, so a "
                                "state may exist without appearing there: leave machine_name out "
                                "to look across every workflow, and only say a state does not "
                                "exist once that has come back empty. On pipeline_* and "
                                "entity_table the state means where an entity is NOW and takes no "
                                "date window - to show what moved into a state during a period "
                                "use metric entities.reached_state_list instead."
                            ),
                        },
                        "metric": {
                            "type": "string",
                            "description": (
                                "Dashboard metric key. Required for dashboard_widget (any metric) and "
                                "stat_tile (entities.count, entities.in_state, entities.reached_state, sla.breaches). "
                                "entities.reached_state counts entities that moved into the state during the window; "
                                "entities.reached_state_list returns those same entities as a table, which is how to "
                                "show which ones moved; entities.in_state counts those sitting in it now. "
                                "transitions.over_time charts movement per day and takes the same state filter."
                            ),
                        },
                        "viz": {
                            "type": "string",
                            "description": "Optional chart style for dashboard_widget (bar, line, area, pie, funnel, barh, gauge, number, table).",
                        },
                        "title": {"type": "string", "description": "Optional title for a dashboard_widget."},
                        "subtitle": {"type": "string", "description": "Optional subtitle for a dashboard_widget."},
                        "filters": {
                            "type": "object",
                            "description": (
                                "Optional metric filters, for dashboard_widget and stat_tile alike. "
                                "Time window: time_range = all, today, this_week, this_month, "
                                "last_month, or last_<N>d for any N up to 365 (the last 5 days is "
                                "last_5d; last month is last_month, not last_30d). For any other "
                                "period use date_from/date_to as YYYY-MM-DD. An unusable "
                                "time_range is an error, not an all-time answer. Also accepts "
                                "workflow_id, state, entity_type_id."
                            ),
                        },
                        "entity_type_id": {
                            "type": "string",
                            "description": "Optional entity-type id (or name) filter for stat_tile entities.count.",
                        },
                        "label": {"type": "string", "description": "Optional human subtitle for a stat_tile."},
                        "time_range": {
                            "type": "string",
                            # Deliberately not an enum of the named presets. Pinning it to
                            # those made the model answer "the last 5 days" with last_7d,
                            # because the closest allowed value was all it could say.
                            "pattern": r"^(all|today|this_week|this_month|last_month|last_\d{1,3}d)$",
                            "description": (
                                "Time window for a metric component: all, today, this_week, "
                                "this_month, last_month (the whole previous calendar month), or "
                                "last_<N>d for any N up to 365 - so the last 5 days is last_5d "
                                "and last month is last_month, never last_30d, which starts "
                                "mid-month. Never substitute a window that does not match what "
                                "was asked. For any other period (a named month, a specific "
                                "range) use date_from/date_to instead."
                            ),
                        },
                        "date_from": {
                            "type": "string",
                            "description": "Start of a custom window, YYYY-MM-DD (inclusive).",
                        },
                        "date_to": {
                            "type": "string",
                            "description": "End of a custom window, YYYY-MM-DD (inclusive).",
                        },
                    },
                ),
            ),
        ]

    def _build_communication_tool_descriptors(self) -> list[ToolDescriptorContract]:
        """Build collaboration and communication tool descriptors.

        Args:
            None.

        Returns:
            Communication-oriented tool descriptors.
        """
        schema = self._schema
        return [
            ToolDescriptorContract(
                name="create_intervention",
                display_name="Request Human Review",
                description="Create a request for human review or approval",
                category="communication",
                risk_level="low",
                default_enabled=False,
                parameters=schema(
                    required=["entity_id", "entity_type", "kind", "requested_by"],
                    properties={
                        "entity_id": {"type": "string"},
                        "entity_type": {"type": "string"},
                        "kind": {"type": "string"},
                        "requested_by": {"type": "string"},
                        "assigned_to": {"type": "string"},
                        "reason": {"type": "string"},
                        "request_payload": {"type": "object"},
                    },
                ),
            ),
            ToolDescriptorContract(
                name="list_interventions",
                display_name="List Interventions",
                description="List interventions optionally filtered by entity",
                category="communication",
                risk_level="low",
                default_enabled=False,
                parameters=schema(properties={"entity_id": {"type": "string"}}),
            ),
            ToolDescriptorContract(
                name="list_stage_comments",
                display_name="List Comments",
                description=(
                    "Read the comments and notes people have left on a record - use this for "
                    "any question about comments, notes, discussion or recent updates on a "
                    "record. Pass identifier when you have the name shown in the app, or "
                    "entity_id when you have the record's id. Returns author, text, state and "
                    "timestamp, newest first."
                ),
                category="communication",
                risk_level="low",
                default_enabled=True,
                mcp_exposed=True,
                parameters=schema(
                    properties={
                        **_RECORD_REF_PROPERTIES,
                        "state_name": {"type": "string"},
                        "limit": {"type": "integer"},
                    },
                ),
            ),
            ToolDescriptorContract(
                name="add_stage_comment",
                display_name="Add Comment",
                description="Add a comment or note to the entity timeline",
                category="communication",
                risk_level="low",
                default_enabled=True,
                mcp_exposed=True,
                is_mutating=True,
                parameters=schema(
                    required=["text"],
                    properties={
                        **_RECORD_REF_PROPERTIES,
                        "text": {"type": "string"},
                        "comment_type": {"type": "string"},
                    },
                ),
            ),
        ]

    def _build_integration_tool_descriptors(self) -> list[ToolDescriptorContract]:
        """Build integration-oriented tool descriptors.

        Args:
            None.

        Returns:
            Integration-oriented tool descriptors.
        """
        schema = self._schema
        return [
            ToolDescriptorContract(
                name="send_calendar_invite",
                display_name="Send Calendar Invite",
                description="Schedule interviews or meetings through calendar integrations",
                category="integration",
                risk_level="medium",
                default_enabled=False,
                mcp_exposed=True,
                is_mutating=True,
                parameters=schema(
                    required=["title", "starts_at", "ends_at"],
                    properties={
                        "provider": {"type": "string"},
                        "title": {"type": "string"},
                        "starts_at": {"type": "string"},
                        "ends_at": {"type": "string"},
                        "attendees": {"type": "array", "items": {"type": "string"}},
                        "entity_id": {"type": "string"},
                    },
                ),
            ),
        ]

    def _build_presets(self) -> dict[str, ToolPresetContract]:
        """Build the shared named tool presets.

        Args:
            None.

        Returns:
            Preset definitions keyed by preset identifier.
        """
        return {
            "extraction_only": ToolPresetContract(
                name="Extraction Only",
                description="Read document and update entity fields based on schema",
                tools=self._select_available_tools(
                    [
                        "read_document",
                        "get_form_schema",
                        "add_stage_comment",
                        "list_entity_types",
                        "get_picklist_values",
                    ]
                ),
            ),
            "read_only": ToolPresetContract(
                name="Read Only",
                description="Read and summarize without making changes",
                tools=self._select_available_tools(
                    [
                        "read_document",
                        "get_form_schema",
                        "list_entity_types",
                        "get_picklist_values",
                    ]
                ),
            ),
            "full_workflow": ToolPresetContract(
                name="Full Workflow",
                description="All tools currently implemented inside modular backend",
                tools=self.list_tool_names(),
            ),
        }

    # endregion Internal Helpers

    def _select_available_tools(self, tool_names: list[str]) -> list[str]:
        return [tool_name for tool_name in tool_names if tool_name in self._supported_tool_names]


def _normalize_optional_string(value: object) -> str | None:
    """Normalize one optional string value for logging metadata.

    Args:
        value: Optional value to normalize.

    Returns:
        The stripped string value, or `None` when empty.
    """
    normalized = str(value or "").strip()
    return normalized or None
