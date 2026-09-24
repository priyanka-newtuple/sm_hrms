"""Request models for playbooks."""

from __future__ import annotations

try:
    from common.data_model import BaseModel as PydanticBaseModel
except Exception:  # pragma: no cover - package/runtime compatibility fallback
    from pydantic import BaseModel as PydanticBaseModel


class PlaybooksRuntimeStatusRequest(PydanticBaseModel):
    """Typed request model for playbooks status operations."""

