"""Response models for tenants."""

from __future__ import annotations

try:
    from common.data_model import BaseModel as PydanticBaseModel
except Exception:  # pragma: no cover - package/runtime compatibility fallback
    from pydantic import BaseModel as PydanticBaseModel

from pydantic import Field


class OrganizationsStatusResponse(PydanticBaseModel):
    """Module health status response."""

    module: str = Field(..., min_length=1, description="Module name")
    status: str = Field(..., min_length=1, description="Health status")
    started: bool = Field(..., description="Whether manager startup ran")

    def to_dict(self) -> dict[str, object]:
        return self.model_dump()
