"""API request contracts for custom forms."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from common.data_model import BaseModel as PydanticBaseModel


class ConnectorFormPreviewRequest(PydanticBaseModel):
    """Sample field values to preview a connector-backed form with."""

    entity_values: dict[str, Any] = Field(default_factory=dict)
