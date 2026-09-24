"""Provider-neutral trace payload serialization."""

from __future__ import annotations

from typing import Any


def _redact_data_url(text: str) -> str:
    """Strip base64 payloads from ``data:`` URLs so they are never persisted.

    Multimodal image inputs reach the model as ``data:<mime>;base64,<...>`` URLs.
    Those are large and sensitive and must not land in the run record / trace, so
    the base64 body is replaced with a short marker while the MIME header is kept
    for debugging. Only the captured/persisted copy is redacted — the live request
    sent to the model is unaffected.
    """
    if text.startswith("data:") and ";base64," in text:
        header = text.split(";base64,", 1)[0]
        return f"{header};base64,<redacted>"
    return text


def json_safe_payload(value: Any) -> Any:
    """Convert SDK request values into persistable trace data."""
    try:
        from openai import NotGiven
    except ImportError:  # pragma: no cover - provider services report SDK failures
        NotGiven = ()  # type: ignore[assignment]

    if isinstance(value, NotGiven):
        return None
    if value is None or isinstance(value, int | float | bool):
        return value
    if isinstance(value, str):
        return _redact_data_url(value)
    if isinstance(value, dict):
        payload: dict[str, Any] = {}
        for key, item in value.items():
            if key in {"extra_headers", "extra_query"}:
                continue
            cleaned = json_safe_payload(item)
            if cleaned is not None:
                payload[str(key)] = cleaned
        return payload
    if isinstance(value, list | tuple):
        return [
            cleaned
            for item in value
            if (cleaned := json_safe_payload(item)) is not None
        ]
    if hasattr(value, "model_dump"):
        return json_safe_payload(value.model_dump(mode="json"))
    return str(value)
