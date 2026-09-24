"""Request models for tools."""

from __future__ import annotations

from pydantic import Field, model_validator

from common.data_model import BaseModel as PydanticBaseModel


class ToolExecutionRequest(PydanticBaseModel):
    """Request contract for direct tool execution."""

    tool_name: str = Field(..., min_length=1)
    arguments: dict[str, object] = Field(default_factory=dict)
    run_id: str | None = None
    session_id: str | None = None
    entity_id: str | None = None
    entity_type: str | None = None
    source: str = "tools-api"
    metadata: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def normalize_fields(self) -> "ToolExecutionRequest":
        """Normalize the direct tool-execution request.

        Args:
            None.

        Returns:
            The normalized request instance.
        """
        self.tool_name = str(self.tool_name).strip()
        self.arguments = dict(self.arguments or {})
        self.source = str(self.source or "tools-api").strip() or "tools-api"
        self.metadata = dict(self.metadata or {})
        return self


class ToolExecutionLogListRequest(PydanticBaseModel):
    """Request contract for tool execution history queries."""

    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    tool_name: str | None = None
    source: str | None = None
    success: bool | None = None
    execution_backend: str | None = None

    @model_validator(mode="after")
    def normalize_fields(self) -> "ToolExecutionLogListRequest":
        """Normalize optional execution-history filters.

        Args:
            None.

        Returns:
            The normalized list request instance.
        """
        self.tool_name = str(self.tool_name).strip() or None if self.tool_name is not None else None
        self.source = str(self.source).strip() or None if self.source is not None else None
        self.execution_backend = (
            str(self.execution_backend).strip() or None if self.execution_backend is not None else None
        )
        return self
