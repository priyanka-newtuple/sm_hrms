"""Request models for executor runtime operations."""

from __future__ import annotations

from pydantic import Field, model_validator

from common.data_model import BaseModel as PydanticBaseModel
from executor.models.interface import ExecutorBinding, ExecutorInput


class ExecutorExecutionRequest(PydanticBaseModel):
    """Request contract for executing one registered executor."""

    executor_name: str = Field(..., min_length=1)
    execution_input: ExecutorInput
    binding: ExecutorBinding | None = None

    @model_validator(mode="after")
    def normalize_fields(self) -> ExecutorExecutionRequest:
        """Normalize execution request names and optional binding."""
        self.executor_name = str(self.executor_name).strip()
        if not self.executor_name:
            raise ValueError("executor_name must not be blank")
        if self.binding is not None and self.binding.executor_name != self.executor_name:
            raise ValueError("binding executor_name must match request executor_name")
        return self
