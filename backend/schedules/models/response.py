"""Response models for recurring entity schedules."""

from __future__ import annotations

from datetime import date

from pydantic import Field

from common.data_model import BaseModel
from schedules.models.interface import ScheduleRecord, ScheduleTargetRecord


class SchedulesStatusResponse(BaseModel):
    module: str
    status: str
    started: bool


class ScheduleListResponse(BaseModel):
    items: list[ScheduleRecord] = Field(default_factory=list)
    total: int = 0


class ScheduleTargetListResponse(BaseModel):
    items: list[ScheduleTargetRecord] = Field(default_factory=list)
    total: int = 0


class SchedulePreviewItem(BaseModel):
    due_date: date
    materialization_date: date


class SchedulePreviewResponse(BaseModel):
    items: list[SchedulePreviewItem] = Field(default_factory=list)


class ScheduleRunPreviewItem(BaseModel):
    target_id: str
    anchor_entity_id: str
    anchor_identifier: str
    due_date: date
    due_dates: list[date] = Field(default_factory=list)
    status: str
    reason: str | None = None


class ScheduleRunPreviewResponse(BaseModel):
    schedule_id: str
    schedule_name: str
    invocation_id: str
    eligible: int = 0
    skipped: int = 0
    items: list[ScheduleRunPreviewItem] = Field(default_factory=list)


class ScheduleRunNowResponse(BaseModel):
    schedule_id: str
    invocation_id: str
    queued: int = 0
    skipped: int = 0
    run_ids: list[str] = Field(default_factory=list)
