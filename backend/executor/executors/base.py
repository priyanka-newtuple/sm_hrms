"""Shared utilities for built-in executor implementations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from exceptions import ServiceError
from executor.models.interface import ExecutorData, ExecutorResponse

if TYPE_CHECKING:
    from common.configuration import Configuration


def get_frontend_url(config: Configuration) -> str:
    """Read frontend_url from config._configuration.runtime_configuration."""
    try:
        url = config._configuration.runtime_configuration.frontend_url
    except AttributeError:
        raise ServiceError("FRONTEND_URL is not configured. Set it in the runtime configuration before deploying.")
    return url.rstrip("/")


def apply_template_placeholders(text: str, fields: dict) -> str:
    """Replace {{field_name}} placeholders in text using executor fields."""
    for key, val in fields.items():
        value = str(val.value) if hasattr(val, "value") else str(val)
        text = text.replace(f"{{{{{key}}}}}", value)
    return text


def get_field(fields: dict, key: str) -> str | None:
    """Extract a string value from an executor fields dict by key."""
    v = fields.get(key)
    if v is None:
        return None
    return str(v.value) if hasattr(v, "value") else str(v)


def fail(reason: str) -> ExecutorResponse:
    """Return a failed ExecutorResponse with the given reason."""
    return ExecutorResponse(
        success=False,
        message=reason,
        data=ExecutorData(outcome="failed", fields={}, meta={"reason": reason}),
    )
