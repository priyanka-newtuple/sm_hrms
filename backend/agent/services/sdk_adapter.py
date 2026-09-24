"""OpenAI Agents SDK adapter for the phase-1 runtime."""

from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Protocol

from agents import Agent, ModelSettings

from agent.models.interface import (
    AgentExecutionContext,
    AgentRuntimeSpec,
    RuntimeBackendResult,
    RuntimeBackendResumeRequest,
    RuntimeBackendRunRequest,
)
from exceptions import ServiceError

if TYPE_CHECKING:
    from llm.manager import LlmServiceManager

_DROP = object()


class AgentExecutionBackendError(ServiceError):
    def __init__(self, message: str, backend_metadata: dict[str, Any]) -> None:
        super().__init__(message)
        self.backend_metadata = backend_metadata


class AgentExecutionBackend(Protocol):
    def run(self, request: RuntimeBackendRunRequest) -> RuntimeBackendResult: ...

    def resume(self, request: RuntimeBackendResumeRequest) -> RuntimeBackendResult: ...


class AgentsSdkRuntimeAdapterBase(ABC):
    """Shared OpenAI Agents SDK runtime plumbing for provider adapters.

    Subclasses own only provider-specific SDK agent/model assembly. Shared
    session input mapping, run/resume orchestration, output normalization, tool
    call extraction, and trace metadata handling live here so future provider
    adapters can reuse the same runtime behavior.
    """

    def run(self, request: RuntimeBackendRunRequest) -> RuntimeBackendResult:
        """Execute one turn by translating the request into an SDK Runner call.

        Args:
            request: Platform runtime request (spec, input, execution context).

        Returns:
            A RuntimeBackendResult with the final output and backend metadata.
        """
        sdk_agent, sdk_model = self._build_agent(
            request.runtime_spec, request.execution_context, request.tools
        )
        from agents import Runner

        try:
            result = asyncio.run(
                Runner.run(
                    sdk_agent,
                    self._build_runner_input(request),
                    max_turns=request.runtime_spec.max_turns,
                )
            )
        except Exception as exc:
            llm_requests = list(getattr(sdk_model, "captured_llm_requests", []))
            if llm_requests:
                raise AgentExecutionBackendError(
                    str(exc),
                    {
                        "last_agent": None,
                        "llm_requests": llm_requests,
                    },
                ) from exc
            raise
        llm_requests = list(getattr(sdk_model, "captured_llm_requests", []))
        tool_calls = self._extract_tool_calls(result)
        return RuntimeBackendResult(
            status="completed",
            output_text=str(getattr(result, "final_output", "")),
            tokens_used=self._extract_tokens_used(result),
            backend_metadata={
                "last_agent": getattr(getattr(result, "last_agent", None), "name", None),
                "llm_requests": llm_requests,
                "tool_calls": tool_calls,
            },
        )

    @staticmethod
    def _build_runner_input(request: RuntimeBackendRunRequest) -> str | list[dict[str, Any]]:
        """Build SDK input, preserving recent session messages when available.

        When ``input_images`` is present, the current user turn becomes a
        multimodal message: an ``input_text`` block plus one ``input_image`` block
        per image (the Agents SDK converts these to chat ``image_url`` parts for
        the model). With no images, behaviour is unchanged (plain string / string
        message content).
        """
        recent_messages = (
            request.execution_context.session.recent_messages
            if request.execution_context.session
            else []
        )
        user_content = AgentsSdkRuntimeAdapterBase._build_user_content(request)
        if not recent_messages:
            # No history: a plain string when text-only, else a single multimodal
            # user message (SDK input must be a list to carry content blocks).
            if isinstance(user_content, str):
                return user_content
            return [{"role": "user", "content": user_content}]

        items: list[dict[str, Any]] = []
        for message in recent_messages:
            content = str(message.get("content") or "").strip()
            if not content:
                continue
            items.append(
                {
                    "role": AgentsSdkRuntimeAdapterBase._sdk_role(str(message.get("role") or "")),
                    "content": content,
                }
            )
        items.append({"role": "user", "content": user_content})
        return items

    @staticmethod
    def _build_user_content(
        request: RuntimeBackendRunRequest,
    ) -> str | list[dict[str, Any]]:
        """Current user turn: plain text, or text + image blocks when images present."""
        if not request.input_images:
            return request.input_text
        content: list[dict[str, Any]] = [{"type": "input_text", "text": request.input_text}]
        content.extend({"type": "input_image", "image_url": url} for url in request.input_images)
        return content

    @staticmethod
    def _sdk_role(role: str) -> str:
        """Map platform message roles to OpenAI Agents SDK input roles."""
        if role == "agent":
            return "assistant"
        if role in {"assistant", "system", "developer"}:
            return role
        return "user"

    def resume(self, request: RuntimeBackendResumeRequest) -> RuntimeBackendResult:
        """Resume a run by re-invoking the SDK with the persisted runtime spec.

        Args:
            request: Resume request carrying the prior run and new input.

        Returns:
            A RuntimeBackendResult from the resumed execution.

        Raises:
            ServiceError: If resume input or the persisted runtime spec is missing.
        """
        if request.input_text is None:
            raise ServiceError("resume input is required for the phase-1 SDK adapter")
        runtime_spec_payload = request.run.backend_metadata.get("runtime_spec")
        if not isinstance(runtime_spec_payload, dict):
            raise ServiceError("runtime spec is missing for resumed agent run")
        return self.run(
            RuntimeBackendRunRequest(
                run_id=request.run.run_id,
                runtime_spec=AgentRuntimeSpec.model_validate(runtime_spec_payload),
                input_text=request.input_text,
                execution_context=request.execution_context,
                tools=request.tools,
            )
        )

    @abstractmethod
    def _build_agent(
        self,
        runtime_spec: AgentRuntimeSpec,
        execution_context: AgentExecutionContext,
        tools: list[object] | None = None,
    ) -> tuple[Any, Any]:
        """Build a provider-specific SDK agent and model pair."""

    @classmethod
    def _extract_tokens_used(cls, result: Any) -> int:
        total = 0
        for response in getattr(result, "raw_responses", []) or []:
            usage = getattr(response, "usage", None)
            total += int(getattr(usage, "total_tokens", 0) or 0)
        return total

    @classmethod
    def _extract_tool_calls(cls, result: Any) -> list[dict[str, Any]]:
        calls_by_id: dict[str, dict[str, Any]] = {}
        ordered_calls: list[dict[str, Any]] = []
        for item in getattr(result, "new_items", []) or []:
            item_type = str(getattr(item, "type", "") or "")
            raw_item = getattr(item, "raw_item", None)
            if item_type == "tool_call_item":
                call = cls._tool_call_from_raw(raw_item)
                if call is None:
                    continue
                ordered_calls.append(call)
                if call["tool_call_id"]:
                    calls_by_id[call["tool_call_id"]] = call
            elif item_type == "tool_call_output_item":
                output = cls._tool_output_from_item(item)
                call_id = output.get("tool_call_id")
                if call_id and call_id in calls_by_id:
                    calls_by_id[call_id]["result"] = output["result"]
                    calls_by_id[call_id]["success"] = output["success"]
                elif call_id:
                    ordered_calls.append(
                        {
                            "tool": output.get("tool") or "unknown_tool",
                            "args": {},
                            "result": output["result"],
                            "success": output["success"],
                            "duration_ms": 0,
                            "tool_call_id": call_id,
                        }
                    )
        return ordered_calls

    @classmethod
    def _tool_call_from_raw(cls, raw_item: Any) -> dict[str, Any] | None:
        payload = cls._json_safe_payload(raw_item)
        if not isinstance(payload, dict):
            return None
        name = payload.get("name")
        call_id = payload.get("call_id") or payload.get("id")
        arguments = payload.get("arguments")
        return {
            "tool": str(name or "unknown_tool"),
            "args": cls._parse_jsonish(arguments),
            "result": None,
            "success": True,
            "duration_ms": 0,
            "tool_call_id": str(call_id) if call_id else None,
            "raw_call": payload,
        }

    @classmethod
    def _tool_output_from_item(cls, item: Any) -> dict[str, Any]:
        raw_payload = cls._json_safe_payload(getattr(item, "raw_item", None))
        raw = raw_payload if isinstance(raw_payload, dict) else {}
        output = getattr(item, "output", None)
        if output is None:
            output = raw.get("output")
        parsed_output = cls._parse_jsonish(output)
        success = not (isinstance(parsed_output, dict) and parsed_output.get("success") is False)
        return {
            "tool": raw.get("name"),
            "tool_call_id": raw.get("call_id") or raw.get("tool_call_id"),
            "result": parsed_output,
            "success": success,
        }

    @staticmethod
    def _parse_jsonish(value: Any) -> Any:
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return value if value is not None else {}

    @classmethod
    def _json_safe_payload(cls, value: Any) -> Any:
        try:
            from openai import NotGiven
        except ImportError:  # pragma: no cover - SDK import failures are handled earlier
            NotGiven = ()  # type: ignore[assignment]

        if isinstance(value, NotGiven):
            return _DROP
        if value is None or isinstance(value, str | int | float | bool):
            return value
        if isinstance(value, dict):
            payload: dict[str, Any] = {}
            for key, item in value.items():
                if key in {"extra_headers", "extra_query"}:
                    continue
                cleaned = cls._json_safe_payload(item)
                if cleaned is not _DROP:
                    payload[str(key)] = cleaned
            return payload
        if isinstance(value, list | tuple):
            return [
                cleaned for item in value if (cleaned := cls._json_safe_payload(item)) is not _DROP
            ]
        if hasattr(value, "model_dump"):
            return cls._json_safe_payload(value.model_dump(mode="json"))
        return str(value)


class OpenAIAgentsSdkRuntimeAdapter(AgentsSdkRuntimeAdapterBase):
    """Provider-neutral runtime built on the OpenAI Agents SDK contract.

    Provider model/client construction is delegated to the LLM module so the
    agent runtime owns only agent definitions, sessions, runs, tools,
    capabilities, and trace persistence. The class name is retained for public
    compatibility; OpenAI, Microsoft Foundry, Bedrock, and LiteLLM-backed
    providers are selected by :class:`LlmServiceManager`.
    """

    def __init__(self, llm_service_manager: LlmServiceManager | None = None) -> None:
        self._llm_service_manager = llm_service_manager

    def _build_agent(
        self,
        runtime_spec: AgentRuntimeSpec,
        execution_context: AgentExecutionContext,
        tools: list[object] | None = None,
    ) -> tuple[Any, Any]:
        if self._llm_service_manager is None:
            raise ServiceError("Agent runtime is not configured with an LLM service manager.")
        model = self._llm_service_manager.build_agent_chat_model(
            organization_id=execution_context.runtime.organization_id,
            model_name=runtime_spec.model,
        )
        agent = Agent(
            name=runtime_spec.name,
            instructions=runtime_spec.instructions,
            model=model,
            tools=list(tools or []),
            model_settings=ModelSettings(temperature=runtime_spec.temperature),
        )
        return agent, model
