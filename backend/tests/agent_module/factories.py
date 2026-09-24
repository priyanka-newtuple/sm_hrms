from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

TOOL_ID = "11111111-1111-1111-1111-111111111111"


def build_definition_create_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": "custom_agent",
        "display_name": "Custom Agent",
        "description": "Custom agent for testing.",
        "system_prompt": "You are a helpful testing agent.",
        "allowed_tools": [TOOL_ID],
        "constraints": {"max_iterations": 5, "require_approval": []},
        "suggestions": [],
        "is_active": True,
    }
    payload.update(overrides)
    return payload


def build_definition_update_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "display_name": "Updated Agent",
        "description": "Updated description for the agent.",
        "system_prompt": "You are an updated testing agent.",
        "allowed_tools": [TOOL_ID],
        "constraints": {"max_iterations": 4, "require_approval": []},
        "suggestions": [],
        "is_active": True,
    }
    payload.update(overrides)
    return payload


def build_chat_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "agent": "recruitment_assistant",
        "message": "Summarize the pipeline",
    }
    payload.update(overrides)
    return payload


def build_tool_call(name: str, arguments: dict[str, Any] | None = None, tool_call_id: str = "tool-call-1") -> dict[str, Any]:
    return {
        "id": tool_call_id,
        "function": {
            "name": name,
            "arguments": arguments or {},
        },
    }


def build_completion_response(
    *,
    content: str,
    tool_calls: list[dict[str, Any]] | None = None,
    tokens: int = 0,
) -> dict[str, Any]:
    return {
        "choices": [{"message": {"content": content, "tool_calls": tool_calls or []}}],
        "usage": {"total_tokens": tokens},
    }


def build_trace_run_payload(**overrides: object) -> dict[str, object]:
    now = datetime.now(timezone.utc)
    payload: dict[str, object] = {
        "organization_id": "org-1",
        "user_id": "admin-user",
        "agent_name": "recruitment_assistant",
        "run_type": "persistent",
        "status": "success",
        "model": "fake-model",
        "input_message": "Summarize the pipeline",
        "session_id": "session-1",
        "message_id": "message-1",
        "context": {"entity_id": "entity-1"},
        "tokens_used": 7,
        "iterations": 1,
        "duration_ms": 42,
        "started_at": now,
        "completed_at": now + timedelta(milliseconds=42),
        "expires_at": now + timedelta(days=30),
    }
    payload.update(overrides)
    return payload


def build_trace_events() -> list[dict[str, object]]:
    return [
        {"seq": 1, "kind": "system_prompt", "payload": {"model": "fake-model"}},
        {"seq": 2, "kind": "assistant_message", "payload": {"content": "hello"}},
    ]
