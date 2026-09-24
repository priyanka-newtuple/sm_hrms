"""Response models for background_jobs."""

from __future__ import annotations

from pydantic import Field

from common.data_model import BaseModel as PydanticBaseModel


class IntakeOrchestrationStatusResponse(PydanticBaseModel):
    """Response model for background_jobs module status."""

    module: str = Field(..., description="Module name")
    status: str = Field(..., description="Operational status")
    started: bool = Field(..., description="Whether the sweep loop is running")


class IntakeJobResponse(PydanticBaseModel):
    """Response model for a single intake job."""

    job_id: str = Field(..., description="Intake job identifier")
    organization_id: str = Field(..., description="Organization identifier")
    status: str = Field(..., description="Job processing state")
    source_type: str = Field(..., description="Source type label")
    file_count: int = Field(..., description="Total number of source files")
    processed_count: int = Field(default=0, description="Number of processed files")
    failed_count: int = Field(default=0, description="Number of failed files")
    subject_entity_type: str | None = Field(default=None, description="Target entity type")
    created_at: str | None = Field(default=None, description="Creation timestamp")
    updated_at: str | None = Field(default=None, description="Update timestamp")
    context: dict[str, object] = Field(default_factory=dict, description="Contextual payload")


class IntakeJobListResponse(PydanticBaseModel):
    """Response model for a list of intake jobs."""

    items: list[IntakeJobResponse] = Field(default_factory=list, description="List of intake jobs")
