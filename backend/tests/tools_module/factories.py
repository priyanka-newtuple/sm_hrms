from __future__ import annotations

from typing import Any


PLATFORM_RUNTIME_TOOL_ARGUMENTS: dict[str, dict[str, Any]] = {
    "read_document": {"storage_key": "documents/resume.pdf"},
    "get_form_schema": {"entity_type": "ATS.Candidate"},
    "get_picklist_values": {"picklist_id": "candidate_source"},
    "list_events": {"entity_id": "entity-1"},
}


def build_platform_runtime_arguments(tool_name: str) -> dict[str, Any]:
    """Return a deterministic argument payload for one platform-runtime-backed tool.

    Args:
        tool_name: Public tool name that should use the platform runtime path in tests.

    Returns:
        A deterministic argument payload for the requested tool.
    """
    return dict(PLATFORM_RUNTIME_TOOL_ARGUMENTS[tool_name])


def build_platform_runtime_output(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Return a deterministic normalized output payload for a platform-runtime-backed tool.

    Args:
        tool_name: Public tool name executed through the platform runtime path.
        arguments: Tool arguments received by the runtime path.

    Returns:
        A deterministic normalized output payload.
    """
    return {"tool_name": tool_name, "arguments": dict(arguments), "path": "platform_runtime"}
