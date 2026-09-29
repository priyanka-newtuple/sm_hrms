from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Boolean, Date, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hrms.database import Base
from hrms.models.base import TimestampMixin, UUIDPkMixin
from hrms.models.enums import AllocationStatus


class Allocation(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "allocations"

    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    allocation_percent: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    role_on_project: Mapped[str] = mapped_column(
        String(100), ForeignKey("project_roles.name", ondelete="RESTRICT"), nullable=False
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    # NULL end_date means "ongoing" — treated as infinity by the capacity overlap check.
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[AllocationStatus] = mapped_column(
        Enum(AllocationStatus, name="allocation_status"),
        default=AllocationStatus.ACTIVE,
        nullable=False,
    )
    billable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Who made this allocation — audit trail distinct from the generic audit_logs table.
    allocated_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=True)
    # Commercial — gated behind PermissionKey.VIEW_BILLING_RATE
    billing_rate_override: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)

    employee: Mapped[Employee] = relationship(  # noqa: F821
        "Employee", foreign_keys=[employee_id]
    )
    allocated_by: Mapped[Employee | None] = relationship(  # noqa: F821
        "Employee", foreign_keys=[allocated_by_id]
    )
    project: Mapped[Project] = relationship("Project")  # noqa: F821
