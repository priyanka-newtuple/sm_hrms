from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict

from hrms.models.enums import AssetStatus


class AssetCreate(BaseModel):
    asset_tag: str
    name: str
    asset_type: str
    serial_number: str | None = None
    purchase_date: date | None = None
    notes: str | None = None


class AssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    asset_tag: str
    name: str
    asset_type: str
    serial_number: str | None
    status: AssetStatus
    purchase_date: date | None
    notes: str | None


class AssetAssignIn(BaseModel):
    employee_id: uuid.UUID
    assigned_date: date
    condition_notes: str | None = None


class AssetReturnIn(BaseModel):
    returned_date: date
    condition_notes: str | None = None


class AssetAssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    asset_id: uuid.UUID
    employee_id: uuid.UUID
    assigned_date: date
    returned_date: date | None
    condition_notes: str | None
