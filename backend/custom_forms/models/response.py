"""API response contracts for custom forms."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from common.data_model import BaseModel as PydanticBaseModel


class ConnectorFormPreviewResponse(PydanticBaseModel):
    """A connector's form, with cell values stripped for display only."""

    form: dict[str, Any] = Field(default_factory=dict)
