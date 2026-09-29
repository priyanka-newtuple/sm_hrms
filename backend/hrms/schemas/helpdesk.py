from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from hrms.models.enums import TicketPriority, TicketStatus


class HelpdeskCategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    department: str


class TicketCreate(BaseModel):
    category_id: uuid.UUID
    subject: str
    description: str
    priority: TicketPriority = TicketPriority.MEDIUM


class TicketUpdate(BaseModel):
    assigned_to_id: uuid.UUID | None = None
    priority: TicketPriority | None = None
    status: TicketStatus | None = None


class TicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    ticket_number: str
    category_id: uuid.UUID
    raised_by_id: uuid.UUID
    assigned_to_id: uuid.UUID | None
    subject: str
    description: str
    priority: TicketPriority
    status: TicketStatus
    resolved_at: datetime | None
