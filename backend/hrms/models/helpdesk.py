from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hrms.database import Base
from hrms.models.base import TimestampMixin, UUIDPkMixin
from hrms.models.enums import TicketPriority, TicketStatus


class HelpdeskCategory(UUIDPkMixin, Base):
    __tablename__ = "helpdesk_categories"

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    department: Mapped[str] = mapped_column(String(50), nullable=False)  # HR, Admin, IT...


class HelpdeskTicket(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "helpdesk_tickets"

    ticket_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    category_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("helpdesk_categories.id"), nullable=False)
    raised_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=False)
    assigned_to_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=True)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[TicketPriority] = mapped_column(Enum(TicketPriority, name="ticket_priority"), default=TicketPriority.MEDIUM)
    status: Mapped[TicketStatus] = mapped_column(Enum(TicketStatus, name="ticket_status"), default=TicketStatus.OPEN)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    category: Mapped[HelpdeskCategory] = relationship("HelpdeskCategory")
    raised_by: Mapped[Employee] = relationship("Employee", foreign_keys=[raised_by_id])  # noqa: F821
    assigned_to: Mapped[Employee | None] = relationship(  # noqa: F821
        "Employee", foreign_keys=[assigned_to_id]
    )
