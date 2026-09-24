"""Response schemas for the projections module."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from common.data_model import BaseModel as PydanticBaseModel


class PipelineViewRead(PydanticBaseModel):
    """Single pipeline board card (denormalized application entry)."""

    application_id: str
    candidate_id: Optional[str] = None
    candidate_name: Optional[str] = None
    candidate_email: Optional[str] = None
    job_id: Optional[str] = None
    job_title: Optional[str] = None
    job_department: Optional[str] = None
    machine_name: Optional[str] = None
    machine_version: Optional[int] = None
    current_state: str
    state_entered_at: datetime
    sla_due_at: Optional[datetime] = None
    sla_risk: Optional[str] = None
    applied_at: datetime
    updated_at: datetime


class HeatmapRead(PydanticBaseModel):
    """SLA heatmap entry aggregated by job + state."""

    job_id: str
    state: str
    application_count: int
    breached_count: int
    avg_time_in_state_seconds: Optional[float] = None
    updated_at: datetime


class HeatmapRefreshResponse(PydanticBaseModel):
    rows_updated: int
    message: str


class FunnelInUse(PydanticBaseModel):
    machine_name: str
    machine_version: Optional[int] = None
    application_count: int


class FunnelsInUseResponse(PydanticBaseModel):
    funnels: list[FunnelInUse]
    total_applications: int
    is_multi_funnel: bool


class RebuildProjectionsResponse(PydanticBaseModel):
    deleted: int
    created: int
    message: str


class ProjectionsStatusResponse(PydanticBaseModel):
    module: str
    status: str
    started: bool
