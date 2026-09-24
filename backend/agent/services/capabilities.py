"""Resolve enabled MCP capabilities into SDK tools for agent runs."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from tools.models.interface import ToolExecutionContext

if TYPE_CHECKING:
    from agent.models.interface import AgentExecutionContext, RequestContext


class AgentCapabilityResolver:
    """Bridge agent tool IDs to the platform-managed MCP registry and tools module."""

    def __init__(self, mcp_registry_service, tools_service_manager) -> None:
        """Store the MCP registry and tools service dependencies."""
        self.mcp_registry_service = mcp_registry_service
        self.tools_service_manager = tools_service_manager

    def validate_enabled_capability_ids(
        self, context: RequestContext, capability_ids: list[str]
    ) -> None:
        """Validate that every requested capability is enabled for the tenant."""
        self.mcp_registry_service.validate_enabled_capability_ids(context, capability_ids)

    def normalize_tool_refs(
        self, context: RequestContext, tool_refs: list[str] | None
    ) -> list[str] | None:
        """Convert legacy tool names to capability IDs while preserving UUID refs."""
        if tool_refs is None:
            return None
        normalized: list[str] = []
        for ref in tool_refs:
            text = str(ref)
            if self._looks_like_uuid(text):
                normalized.append(text)
            else:
                normalized.append(self.capability_id_for_tool_name(context, text))
        return normalized

    def capability_id_for_tool_name(self, context: RequestContext, tool_name: str) -> str:
        """Resolve a platform tool name to its current MCP capability ID."""
        for capability in self.mcp_registry_service.list_capabilities(context):
            if capability.tool_id == tool_name:
                return capability.id
        # Unknown legacy template tools stay invalid rather than silently being dropped.
        from exceptions import ValidationError

        raise ValidationError(f"Unknown MCP capability tool: {tool_name}")

    def build_sdk_tools(
        self,
        context: RequestContext,
        capability_ids: list[str],
        execution_context: AgentExecutionContext,
        *,
        run_id: str,
        session_id: str | None,
        document_id: str | None = None,
        file_slug_map: dict[str, str] | None = None,
    ) -> list[Any]:
        """Build OpenAI Agents SDK tools for enabled capability IDs."""
        capabilities = self.mcp_registry_service.list_enabled_capabilities(context, capability_ids)
        if set(capability_ids) - {capability.id for capability in capabilities}:
            self.validate_enabled_capability_ids(context, capability_ids)
        return [
            self._build_function_tool(
                capability, execution_context, run_id, session_id, document_id, file_slug_map
            )
            for capability in capabilities
        ]

    def build_all_sdk_tools(
        self,
        context: RequestContext,
        execution_context: AgentExecutionContext,
        *,
        run_id: str,
        session_id: str | None,
        document_id: str | None = None,
        file_slug_map: dict[str, str] | None = None,
    ) -> list[Any]:
        """Build SDK tools for EVERY active capability, bypassing the per-org
        enablement gate. Used only by the built-in Agent Mode assistant so it has
        direct access to all tool calls."""
        capabilities = [
            capability
            for capability in self.mcp_registry_service.list_capabilities(context)
            if getattr(capability, "is_active", True)
        ]
        return [
            self._build_function_tool(
                capability, execution_context, run_id, session_id, document_id, file_slug_map
            )
            for capability in capabilities
        ]

    def _build_function_tool(
        self,
        capability,
        execution_context: AgentExecutionContext,
        run_id: str,
        session_id: str | None,
        document_id: str | None = None,
        file_slug_map: dict[str, str] | None = None,
    ) -> Any:
        """Create one SDK FunctionTool that routes through platform tool execution."""
        from agents import FunctionTool

        async def invoke_tool(_tool_context, raw_input: str) -> str:
            """Execute a tool call and always return model-visible JSON output."""
            try:
                arguments = json.loads(raw_input or "{}")
                result = self.tools_service_manager.execute_tool(
                    capability.tool_id,
                    arguments,
                    ToolExecutionContext(
                        run_id=run_id,
                        session_id=session_id,
                        organization_id=execution_context.runtime.organization_id,
                        user_id=execution_context.runtime.user_id,
                        actor_id=execution_context.runtime.user_id,
                        actor_type="AGENT",
                        roles=list(execution_context.runtime.roles or []),
                        source="agent",
                        request_id=execution_context.runtime.request_id,
                        metadata={
                            "capability_id": capability.id,
                            "capability_key": capability.capability_key,
                            # Uploaded-file id (if this run was triggered by a document
                            # upload) so read_document can resolve it without a prompt arg.
                            **({"file_id": document_id} if document_id else {}),
                            # Slug -> real file id map (if this run owns many files) so
                            # read_job_document can resolve a model-supplied slug without
                            # the real id ever appearing in the prompt/tool-call history.
                            **({"file_slug_map": file_slug_map} if file_slug_map else {}),
                        },
                    ),
                )
                payload = result.model_dump(mode="json")
            except Exception as exc:
                payload = self._tool_error_payload(capability.tool_id, exc)
            return json.dumps(payload)

        return FunctionTool(
            name=capability.tool_id,
            description=capability.description,
            params_json_schema=capability.input_schema,
            on_invoke_tool=invoke_tool,
            strict_json_schema=False,
        )

    @staticmethod
    def _tool_error_payload(tool_name: str, exc: Exception) -> dict[str, Any]:
        """Build a structured failed tool result that the model can recover from."""
        message = str(exc).strip() or exc.__class__.__name__
        return {
            "success": False,
            "tool_name": tool_name,
            "output": {},
            "error": message[:1000],
            "recoverable": True,
        }

    @staticmethod
    def _looks_like_uuid(value: str) -> bool:
        """Return whether a string has the shape of a UUID."""
        return len(value) == 36 and value.count("-") == 4
