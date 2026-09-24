"""Shared normalization for untrusted structured bulk-agent output."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from exceptions import ValidationError

MULTIPLE_JSON_OBJECTS_WARNING = (
    "agent output contained multiple JSON objects; using last complete object"
)

JSON_CODE_FENCE_PATTERN = re.compile(
    r"```(?:json)?\s*(.*?)```",
    flags=re.IGNORECASE | re.DOTALL,
)


@dataclass(frozen=True)
class ParsedAgentPayload:
    """Parsed agent output with non-fatal normalization warnings."""

    payload: dict[str, Any]
    warnings: list[str]


def parse_agent_payload(text: str) -> dict[str, Any]:
    """Parse an object from plain JSON or a fenced JSON block with surrounding prose."""
    return parse_agent_payload_with_metadata(text).payload


def parse_agent_payload_with_metadata(text: str) -> ParsedAgentPayload:
    """Parse an object from agent output and report tolerated output-shape issues."""
    fenced_blocks = JSON_CODE_FENCE_PATTERN.findall(text)
    candidates = [*reversed(fenced_blocks), text]
    parsed_non_object = False
    for candidate in candidates:
        parsed = _parse_candidate(candidate)
        if parsed is None:
            continue
        payloads, warnings = parsed
        if all(isinstance(payload, dict) for payload in payloads):
            return ParsedAgentPayload(payload=payloads[-1], warnings=warnings)
        parsed_non_object = True
    if parsed_non_object:
        raise ValidationError("extractor returned a non-object result")
    raise ValidationError("extractor returned invalid JSON")


def _parse_candidate(candidate: str) -> tuple[list[Any], list[str]] | None:
    """Parse one complete JSON value, or adjacent complete JSON values."""
    text = candidate.strip()
    if not text:
        return None
    try:
        return [json.loads(text)], []
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    values: list[Any] = []
    index = 0
    while index < len(text):
        while index < len(text) and text[index].isspace():
            index += 1
        if index >= len(text):
            break
        try:
            value, index = decoder.raw_decode(text, index)
        except json.JSONDecodeError:
            return None
        values.append(value)
    if not values:
        return None
    warnings = [MULTIPLE_JSON_OBJECTS_WARNING] if len(values) > 1 else []
    return values, warnings
