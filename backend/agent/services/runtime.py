"""Agent run lifecycle service for the phase-1 runtime path."""

from __future__ import annotations

import base64
import hashlib
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from agent.models.interface import (
    SESSION_TITLE_MAX_LENGTH,
    AgentRunContract,
    RequestContext,
    RuntimeBackendResult,
    RuntimeBackendResumeRequest,
    RuntimeBackendRunRequest,
)
from common.logger import logger
from exceptions import NotFoundError, ValidationError

if TYPE_CHECKING:
    from agent.models.request import AgentResumeRequest, AgentRunRequest
    from agent.services.context import AgentContextService
    from agent.services.definitions import AgentDefinitionService
    from agent.services.sdk_adapter import AgentExecutionBackend

# Max raw image bytes attached to a vision model (oversized images are skipped,
# not truncated). base64 inflates this ~1.33x on the wire.
_MAX_IMAGE_BYTES = 5_000_000

# Shown in the chat when a run fails, instead of the raw error. Kept plain,
# because whatever goes here is replayed to the model on the next turn.
_RUN_FAILED_MESSAGE = "I wasn't able to complete that request."


class AgentRuntimeService:
    """Persist run status and delegate execution through one backend adapter."""

    def __init__(
        self,
        agent_model_service,
        definition_service: AgentDefinitionService,
        context_service: AgentContextService,
        execution_backend: AgentExecutionBackend,
        capability_resolver=None,
        llm_service_manager=None,
        document_source_fn=None,
    ) -> None:
        self.agent_model_service = agent_model_service
        self.definition_service = definition_service
        self.context_service = context_service
        self.execution_backend = execution_backend
        self.capability_resolver = capability_resolver
        # For the vision guard: resolve whether the run's model accepts images.
        self.llm_service_manager = llm_service_manager
        # Late-bound in main.py to FilehandlerServiceManager.read_document_source;
        # returns the stored file's bytes + content_type for a document_id. The
        # runtime builds the base64 model input from it (never persisted).
        self.document_source_fn = document_source_fn

    def _resolve_input_images(
        self,
        context: RequestContext,
        *,
        model: str,
        document_id: str | None = None,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        """Prepare the stored image for a vision run (one path for sync + async).

        Reads the stored file (by ``document_id``) via the filehandler's
        ``read_document_source``, verifies it is an image within the size cap,
        checks the model supports vision, and builds the base64 ``data:`` URL.

        Returns ``(data_urls, audit)`` where ``audit`` records the image's
        ``document_id`` / ``content_type`` / ``size_bytes`` / ``sha256`` (never the
        base64) for the run record. When the document is not an image (or there is
        none) returns ``([], [])`` so the run proceeds as a normal text run.

        Since image OCR no longer exists, an image that cannot be delivered to the
        model is a hard failure rather than silent incomplete input: this raises
        ``ValidationError`` when the file is an image but the model is not
        vision-capable, or when the image exceeds the size cap.
        """
        if not document_id or self.document_source_fn is None:
            return [], []
        try:
            src = self.document_source_fn(context.organization_id, document_id)
        except Exception:
            logger.warning(
                "agent images: failed to read document",
                extra={"document_id": document_id},
                exc_info=True,
            )
            return [], []
        if not src:
            return [], []
        content_type = str(src.get("content_type") or "").split(";")[0].strip().lower()
        if not content_type.startswith("image/"):
            return [], []
        data = src.get("file_bytes") or b""
        if not data:
            return [], []
        # Compute the audit up front so it is available on every path — including
        # the fail-fast raises below and a later model-call failure — never only
        # on success.
        audit = [
            {
                "document_id": document_id,
                "content_type": content_type,
                "size_bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        ]
        if len(data) > _MAX_IMAGE_BYTES:
            raise self._image_input_error(
                f"Image document '{document_id}' is {len(data)} bytes, exceeding the "
                f"{_MAX_IMAGE_BYTES}-byte limit for vision input.",
                audit,
            )
        if self.llm_service_manager is None or not self.llm_service_manager.supports_vision(model):
            raise self._image_input_error(
                f"Model '{model}' does not support image input, so image document "
                f"'{document_id}' cannot be processed.",
                audit,
            )
        data_url = f"data:{content_type};base64,{base64.b64encode(data).decode('ascii')}"
        return [data_url], audit

    @staticmethod
    def _image_input_error(message: str, audit: list[dict[str, Any]]) -> ValidationError:
        """Build a ValidationError that also carries the image audit.

        The run's ``except`` reads ``exc.backend_metadata`` when finalizing a
        failed run, so attaching the audit here means a run that fails because the
        image can't be delivered still records the image details (document_id,
        content_type, size, sha256) — never the base64.
        """
        error = ValidationError(message)
        error.backend_metadata = {"input_images": audit}
        return error

    def run(self, context: RequestContext, request: AgentRunRequest) -> AgentRunContract:
        """Create and execute an agent run, persisting status before and after.

        Builds the runtime spec and execution context, persists a ``running``
        run record, delegates execution to the backend adapter, and finalizes
        the record. On backend failure the run is marked ``failed`` with a
        secret-safe error message rather than raising.

        Args:
            context: Authenticated request context (provides the tenant/user).
            request: Run payload with definition id, input, and optional session.

        Returns:
            The completed or failed AgentRunContract.
        """
        runtime_spec = self.definition_service.build_runtime_spec(context, request.definition_id)
        session_id = request.session_id
        session_title: str | None = None
        if session_id is None:
            session = self.agent_model_service.create_session(
                request.definition_id,
                context.user_id or "system",
                context.organization_id,
                request.context,
            )
            session_id = session.session_id
            session_title = request.input[:80]
        execution_context = self.context_service.build_context(
            context,
            session_id=session_id,
            request_context=request.context,
        )
        now = datetime.now(UTC)
        run = self.agent_model_service.create_run(
            {
                "organization_id": context.organization_id,
                "definition_id": request.definition_id,
                "session_id": session_id,
                "user_id": context.user_id,
                "status": "running",
                "input_text": request.input,
                "execution_context": execution_context.model_dump(mode="json"),
                "backend_metadata": {
                    "runtime_spec": runtime_spec.model_dump(mode="json"),
                    # Needed so resume() can still resolve read_job_document's slugs.
                    "file_slug_map": request.file_slug_map,
                },
                "started_at": now,
                "created_at": now,
                "updated_at": now,
            }
        )
        # Initialized before the try so the failure path can still record which
        # image was involved (the base64 is never stored — only these details).
        image_audit: list[dict[str, Any]] = []
        try:
            # Resolve inside the try: an image the model can't accept raises, and
            # that must mark the run failed (image OCR fallback no longer exists).
            input_images, image_audit = self._resolve_input_images(
                context,
                model=runtime_spec.model,
                document_id=request.document_id,
            )
            backend_request = RuntimeBackendRunRequest(
                run_id=run.run_id,
                runtime_spec=runtime_spec,
                input_text=request.input,
                execution_context=execution_context,
                input_images=input_images,
                tools=self._build_sdk_tools(
                    context,
                    runtime_spec.tool_ids,
                    execution_context,
                    run_id=run.run_id,
                    session_id=session_id,
                    document_id=request.document_id,
                    file_slug_map=request.file_slug_map,
                    all_tools=runtime_spec.all_tools,
                ),
            )
            backend_result = self.execution_backend.run(backend_request)
            updated = self._finish_run(
                context,
                run,
                backend_result,
                extra_metadata={"input_images": image_audit} if image_audit else None,
            )
            self._persist_run_messages(
                run=updated,
                user_input=request.input,
                session_title=session_title,
                tokens_used=backend_result.tokens_used,
            )
            self._persist_trace(
                context=context,
                run=updated,
                user_input=request.input,
            )
            return updated
        except Exception as exc:
            exc_metadata = getattr(exc, "backend_metadata", None)
            metadata_updates = dict(run.backend_metadata)
            if isinstance(exc_metadata, dict):
                metadata_updates.update(exc_metadata)
            # Record the image audit on failure too: a model-call error carries it
            # via image_audit; a fail-fast image error carries it via
            # exc.backend_metadata (merged above). Never the base64.
            if image_audit:
                metadata_updates["input_images"] = image_audit
            failed = self.agent_model_service.update_run(
                run.run_id,
                context.organization_id,
                {
                    "status": "failed",
                    "error": self._safe_error(exc),
                    "backend_metadata": metadata_updates,
                    "completed_at": datetime.now(UTC),
                },
            )
            if failed is None:
                raise NotFoundError("agent run not found") from exc
            self._persist_run_messages(
                run=failed,
                user_input=request.input,
                session_title=session_title,
                tokens_used=0,
            )
            self._persist_trace(
                context=context,
                run=failed,
                user_input=request.input,
            )
            return failed

    def async_run(self, context: RequestContext, request: AgentRunRequest) -> AgentRunContract:
        """Create a ``queued`` agent run for later background execution.

        Mirrors the setup portion of :meth:`run` (build runtime spec, resolve the
        session, assemble the execution context) but persists the run as
        ``queued`` and returns immediately **without executing**. The worker later
        picks it up via :meth:`execute_async_run`. The inputs needed to replay
        execution off-request are stashed under ``backend_metadata["async_request"]``.

        Args:
            context: Authenticated request context (tenant/user/roles).
            request: Run payload with definition id, input, and optional session.

        Returns:
            The persisted ``queued`` AgentRunContract (not yet executed).
        """
        runtime_spec = self.definition_service.build_runtime_spec(context, request.definition_id)
        session_id = request.session_id
        session_title: str | None = None
        if session_id is None:
            session = self.agent_model_service.create_session(
                request.definition_id,
                context.user_id or "system",
                context.organization_id,
                request.context,
            )
            session_id = session.session_id
            session_title = request.input[:SESSION_TITLE_MAX_LENGTH]
        execution_context = self.context_service.build_context(
            context,
            session_id=session_id,
            request_context=request.context,
        )
        now = datetime.now(UTC)
        run = self.agent_model_service.create_run(
            {
                "organization_id": context.organization_id,
                "definition_id": request.definition_id,
                "session_id": session_id,
                "user_id": context.user_id,
                "status": "queued",
                "input_text": request.input,
                "execution_context": execution_context.model_dump(mode="json"),
                "backend_metadata": {
                    "runtime_spec": runtime_spec.model_dump(mode="json"),
                    # Inputs the worker needs to reproduce the request context and
                    # execution off-request (there is no HTTP actor in the worker).
                    "async_request": {
                        "document_id": request.document_id,
                        "session_title": session_title,
                        "request_context": request.context,
                        "roles": list(context.roles),
                        "request_id": context.request_id,
                    },
                },
                "created_at": now,
                "updated_at": now,
                # No started_at — set by the worker when execution begins.
            }
        )
        return run

    def execute_async_run(self, run_id: str) -> None:
        """Execute a previously ``queued`` agent run from the background worker.

        Mirrors the execution portion of :meth:`run`: rebuilds the request context
        from the persisted ``async_request`` payload, flips the run
        ``queued -> running``, delegates to the backend adapter, and finalizes the
        record (persisting messages and trace). On backend failure the run is
        marked ``failed`` with a secret-safe message rather than raising.

        This is a no-op when the run is missing or is no longer ``queued`` (claim
        guard against double execution from startup reconcile + normal enqueue).

        Args:
            run_id: Identifier of the queued run to execute.
        """
        run = self.agent_model_service.get_run_by_id(run_id)
        if run is None:
            logger.warning("async agent run not found", extra={"run_id": run_id})
            return
        if run.status != "queued":
            logger.info(
                "async agent run not queued; skipping",
                extra={"run_id": run_id, "status": run.status},
            )
            return

        async_meta = dict((run.backend_metadata or {}).get("async_request") or {})
        context = RequestContext(
            organization_id=run.organization_id,
            user_id=run.user_id,
            roles=[str(role) for role in (async_meta.get("roles") or [])],
            request_id=async_meta.get("request_id"),
            source="background_job",
        )
        now = datetime.now(UTC)
        run = self.agent_model_service.update_run(
            run_id,
            context.organization_id,
            {"status": "running", "started_at": now},
        )
        if run is None:
            raise NotFoundError("agent run not found")

        runtime_spec = self.definition_service.build_runtime_spec(context, run.definition_id)
        execution_context = self.context_service.build_context(
            context,
            session_id=run.session_id,
            request_context=async_meta.get("request_context"),
        )
        document_id = async_meta.get("document_id")
        session_title = async_meta.get("session_title")
        # Initialized before the try so the failure path can still record which
        # image was involved (the base64 is never stored — only these details).
        image_audit: list[dict[str, Any]] = []
        try:
            # Re-source the image from the persisted document_id (no base64 was
            # persisted); identical mechanism to the sync path. A model that can't
            # accept the image raises here and marks the run failed.
            input_images, image_audit = self._resolve_input_images(
                context,
                model=runtime_spec.model,
                document_id=document_id,
            )
            backend_request = RuntimeBackendRunRequest(
                run_id=run.run_id,
                runtime_spec=runtime_spec,
                input_text=run.input_text,
                execution_context=execution_context,
                input_images=input_images,
                tools=self._build_sdk_tools(
                    context,
                    runtime_spec.tool_ids,
                    execution_context,
                    run_id=run.run_id,
                    session_id=run.session_id,
                    document_id=document_id,
                    all_tools=runtime_spec.all_tools,
                ),
            )
            backend_result = self.execution_backend.run(backend_request)
            updated = self._finish_run(
                context,
                run,
                backend_result,
                extra_metadata={"input_images": image_audit} if image_audit else None,
            )
            self._persist_run_messages(
                run=updated,
                user_input=run.input_text,
                session_title=session_title,
                tokens_used=backend_result.tokens_used,
            )
            self._persist_trace(
                context=context,
                run=updated,
                user_input=run.input_text,
            )
        except Exception as exc:
            logger.exception(
                "async agent run execution failed",
                extra={
                    "run_id": run.run_id,
                    "definition_id": run.definition_id,
                    "organization_id": context.organization_id,
                },
            )
            backend_metadata = getattr(exc, "backend_metadata", None)
            metadata_updates = (
                {**run.backend_metadata, **backend_metadata}
                if isinstance(backend_metadata, dict)
                else run.backend_metadata
            )
            failed = self.agent_model_service.update_run(
                run.run_id,
                context.organization_id,
                {
                    "status": "failed",
                    "error": self._safe_error(exc),
                    "backend_metadata": metadata_updates,
                    "completed_at": datetime.now(UTC),
                },
            )
            if failed is None:
                raise NotFoundError("agent run not found") from None
            self._persist_run_messages(
                run=failed,
                user_input=run.input_text,
                session_title=session_title,
                tokens_used=0,
            )
            self._persist_trace(
                context=context,
                run=failed,
                user_input=run.input_text,
            )

    def resume(
        self, context: RequestContext, run_id: str, request: AgentResumeRequest
    ) -> AgentRunContract:
        """Resume a paused or failed run through the backend adapter.

        Args:
            context: Authenticated request context (provides the tenant).
            run_id: Identifier of the run to resume.
            request: Resume payload with optional new input and context.

        Returns:
            The updated AgentRunContract after the resumed execution.

        Raises:
            NotFoundError: If the run does not exist for this tenant.
            ValidationError: If the run is not in a resumable state.
        """
        run = self.get_run(context, run_id)
        if run.status not in {"waiting_for_approval", "failed"}:
            raise ValidationError("agent run is not resumable")
        execution_context = self.context_service.build_context(
            context,
            session_id=run.session_id,
            request_context=request.context,
        )
        backend_result = self.execution_backend.resume(
            RuntimeBackendResumeRequest(
                run=run,
                input_text=request.input,
                execution_context=execution_context,
                tools=self._build_sdk_tools(
                    context,
                    list((run.backend_metadata.get("runtime_spec") or {}).get("tool_ids") or []),
                    execution_context,
                    run_id=run.run_id,
                    session_id=run.session_id,
                    file_slug_map=run.backend_metadata.get("file_slug_map"),
                    all_tools=bool(
                        (run.backend_metadata.get("runtime_spec") or {}).get("all_tools")
                    ),
                ),
            )
        )
        updated = self._finish_run(context, run, backend_result)
        if request.input:
            self._persist_run_messages(
                run=updated,
                user_input=request.input,
                session_title=None,
                tokens_used=backend_result.tokens_used,
            )
        self._persist_trace(
            context=context,
            run=updated,
            user_input=request.input or "",
        )
        return updated

    def get_run(self, context: RequestContext, run_id: str) -> AgentRunContract:
        run = self.agent_model_service.get_run(run_id, context.organization_id)
        if run is None:
            raise NotFoundError("agent run not found")
        return run

    def list_runs(
        self,
        context: RequestContext,
        *,
        limit: int,
        offset: int,
        status: str | None = None,
        definition_id: str | None = None,
    ) -> tuple[list[AgentRunContract], int]:
        return self.agent_model_service.list_runs(
            context.organization_id,
            limit=limit,
            offset=offset,
            status=status,
            definition_id=definition_id,
        )

    def cancel_run(self, context: RequestContext, run_id: str) -> AgentRunContract:
        run = self.get_run(context, run_id)
        if run.status in {"completed", "cancelled"}:
            return run
        cancelled = self.agent_model_service.update_run(
            run_id,
            context.organization_id,
            {"status": "cancelled", "completed_at": datetime.now(UTC)},
        )
        if cancelled is None:
            raise NotFoundError("agent run not found")
        return cancelled

    def _finish_run(
        self,
        context: RequestContext,
        run: AgentRunContract,
        backend_result: RuntimeBackendResult,
        extra_metadata: dict[str, Any] | None = None,
    ) -> AgentRunContract:
        status = backend_result.status
        updates: dict[str, Any] = {
            "status": status,
            "output_text": backend_result.output_text,
            "error": backend_result.error,
            "backend_metadata": {
                **run.backend_metadata,
                **backend_result.backend_metadata,
                **(extra_metadata or {}),
                "tokens_used": backend_result.tokens_used,
            },
        }
        if status in {"completed", "failed"}:
            updates["completed_at"] = datetime.now(UTC)
        updated = self.agent_model_service.update_run(run.run_id, context.organization_id, updates)
        if updated is None:
            raise NotFoundError("agent run not found")
        return updated

    def _persist_run_messages(
        self,
        *,
        run: AgentRunContract,
        user_input: str,
        session_title: str | None,
        tokens_used: int,
    ) -> None:
        if not run.session_id:
            return
        self.agent_model_service.create_message(
            session_id=run.session_id,
            role="user",
            content=user_input,
        )
        # Never store `run.error` as the assistant's reply. Stored messages are
        # replayed to the model, so it read "Max turns (12) exceeded" as its own
        # words and made up an explanation. The UI shows the error separately.
        if run.output_text:
            agent_content = run.output_text
        elif run.error:
            agent_content = _RUN_FAILED_MESSAGE
        else:
            agent_content = "Agent run completed without a response."
        self.agent_model_service.create_message(
            session_id=run.session_id,
            role="agent",
            content=agent_content,
            tool_calls=self._metadata_list(run.backend_metadata, "tool_calls"),
            pending_actions=self._metadata_list(run.backend_metadata, "pending_actions"),
            tokens_used=tokens_used,
        )
        self.agent_model_service.update_session(
            run.session_id,
            title=session_title,
            token_delta=tokens_used,
            message_delta=2,
        )

    def _persist_trace(
        self,
        *,
        context: RequestContext,
        run: AgentRunContract,
        user_input: str,
    ) -> None:
        try:
            events = self._build_trace_events(context, run, user_input)
            self.agent_model_service.persist_trace(
                {
                    "organization_id": context.organization_id,
                    "user_id": context.user_id,
                    "agent_name": self._agent_name(run),
                    "run_type": "agent_run",
                    "status": self._trace_status(run),
                    "model": self._runtime_spec(run).get("model"),
                    "input_message": user_input or run.input_text,
                    "session_id": run.session_id,
                    "context": run.execution_context,
                    "error": run.error,
                    "tokens_used": int(run.backend_metadata.get("tokens_used") or 0),
                    "duration_ms": self._duration_ms(run),
                    "started_at": run.started_at or run.created_at,
                    "completed_at": run.completed_at,
                    "expires_at": datetime.now(UTC) + timedelta(days=30),
                    "created_at": run.created_at,
                    "updated_at": run.updated_at or datetime.now(UTC),
                },
                events,
            )
        except Exception as exc:
            logger.warning(
                "agent trace persistence failed",
                extra={"run_id": run.run_id, "error": str(exc)},
            )

    def _build_trace_events(
        self,
        context: RequestContext,
        run: AgentRunContract,
        user_input: str,
    ) -> list[dict[str, Any]]:
        runtime_spec = self._runtime_spec(run)
        events: list[dict[str, Any]] = [
            {
                "seq": 1,
                "kind": "context",
                "payload": {
                    "run_id": run.run_id,
                    "definition_id": run.definition_id,
                    "session_id": run.session_id,
                    "agent": {
                        "key": runtime_spec.get("key"),
                        "name": runtime_spec.get("name"),
                        "model": runtime_spec.get("model"),
                    },
                    "tool_summary": self._tool_summary(context, runtime_spec),
                    "runtime_spec": runtime_spec,
                    "execution_context": run.execution_context,
                },
            },
        ]

        seq = 2
        for llm_request in self._metadata_list(run.backend_metadata, "llm_requests") or []:
            events.append({"seq": seq, "kind": "llm_request", "payload": llm_request})
            seq += 1

        events.append(
            {
                "seq": seq,
                "kind": "user_message",
                "payload": {"content": user_input or run.input_text},
            }
        )
        seq += 1

        for tool_call in self._metadata_list(run.backend_metadata, "tool_calls") or []:
            events.append({"seq": seq, "kind": "tool_call", "payload": tool_call})
            seq += 1
        for pending_action in self._metadata_list(run.backend_metadata, "pending_actions") or []:
            events.append({"seq": seq, "kind": "pending_action", "payload": pending_action})
            seq += 1

        if run.error:
            events.append({"seq": seq, "kind": "error", "payload": {"message": run.error}})
            seq += 1
        else:
            events.append(
                {
                    "seq": seq,
                    "kind": "assistant_message",
                    "payload": {"content": run.output_text or ""},
                }
            )
            seq += 1

        events.append(
            {
                "seq": seq,
                "kind": "run_summary",
                "payload": {
                    "status": run.status,
                    "trace_status": self._trace_status(run),
                    "tokens_used": int(run.backend_metadata.get("tokens_used") or 0),
                    "duration_ms": self._duration_ms(run),
                },
            }
        )
        return events

    @staticmethod
    def _runtime_spec(run: AgentRunContract) -> dict[str, Any]:
        value = run.backend_metadata.get("runtime_spec")
        return dict(value) if isinstance(value, dict) else {}

    def _agent_name(self, run: AgentRunContract) -> str:
        runtime_spec = self._runtime_spec(run)
        return str(runtime_spec.get("name") or runtime_spec.get("key") or run.definition_id)

    def _trace_status(self, run: AgentRunContract) -> str:
        if run.status == "failed":
            return "error"
        if run.status == "completed":
            return "partial" if self._has_failed_tool_call(run) else "success"
        return run.status

    @staticmethod
    def _has_failed_tool_call(run: AgentRunContract) -> bool:
        tool_calls = run.backend_metadata.get("tool_calls") or []
        return any(
            isinstance(tool_call, dict) and tool_call.get("success") is False
            for tool_call in tool_calls
        )

    @staticmethod
    def _duration_ms(run: AgentRunContract) -> int | None:
        if run.started_at is None or run.completed_at is None:
            return None
        return max(0, int((run.completed_at - run.started_at).total_seconds() * 1000))

    def _tool_summary(
        self, context: RequestContext, runtime_spec: dict[str, Any]
    ) -> dict[str, Any]:
        tool_ids = [str(tool_id) for tool_id in runtime_spec.get("tool_ids") or [] if tool_id]
        if self.capability_resolver is None or not tool_ids:
            return {"count": len(tool_ids), "tools": [], "tool_ids": tool_ids}
        try:
            capabilities = self.capability_resolver.mcp_registry_service.list_enabled_capabilities(
                context, tool_ids
            )
            tools = [
                {
                    "id": capability.id,
                    "tool_id": capability.tool_id,
                    "capability_key": capability.capability_key,
                }
                for capability in capabilities
            ]
            return {"count": len(tool_ids), "tools": tools, "tool_ids": tool_ids}
        except Exception as exc:
            logger.warning(
                "agent trace tool summary failed",
                extra={"tool_count": len(tool_ids), "error": str(exc)},
            )
            return {"count": len(tool_ids), "tools": [], "tool_ids": tool_ids}

    @staticmethod
    def _metadata_list(metadata: dict[str, Any], key: str) -> list[dict[str, Any]] | None:
        value = metadata.get(key)
        if not isinstance(value, list):
            return None
        rows = [dict(item) for item in value if isinstance(item, dict)]
        return rows or None

    def _build_sdk_tools(
        self,
        context: RequestContext,
        tool_ids: list[str],
        execution_context,
        *,
        run_id: str,
        session_id: str | None,
        document_id: str | None = None,
        file_slug_map: dict[str, str] | None = None,
        all_tools: bool = False,
    ) -> list[object]:
        if self.capability_resolver is None:
            return []
        # The Agent Mode assistant gets every active capability, bypassing the
        # stored tool_ids and the per-org enablement gate.
        if all_tools:
            return self.capability_resolver.build_all_sdk_tools(
                context,
                execution_context,
                run_id=run_id,
                session_id=session_id,
                document_id=document_id,
                file_slug_map=file_slug_map,
            )
        if not tool_ids:
            return []
        return self.capability_resolver.build_sdk_tools(
            context,
            tool_ids,
            execution_context,
            run_id=run_id,
            session_id=session_id,
            document_id=document_id,
            file_slug_map=file_slug_map,
        )

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        message = str(exc).strip() or exc.__class__.__name__
        blocked_terms = ("api_key", "authorization", "bearer ", "token=")
        lowered = message.lower()
        if any(term in lowered for term in blocked_terms):
            return "Agent execution failed due to provider configuration."
        return message[:1000]
