"""Request models for tenants."""

from __future__ import annotations

try:
    from common.data_model import BaseModel as PydanticBaseModel
except Exception:  # pragma: no cover - package/runtime compatibility fallback
    from pydantic import BaseModel as PydanticBaseModel


class OrganizationsStatusRequest(PydanticBaseModel):
    """Typed request model for tenants status operations."""

