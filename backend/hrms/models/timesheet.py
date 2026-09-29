from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Enum, ForeignKey, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hrms.database import Base
from hrms.models.base import TimestampMixin, UUIDPkMixin
from hrms.models.enums import ApprovalAction, TimesheetStatus


class Timesheet(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "timesheets"
    __table_args__ = (UniqueConstraint("employee_id", "project_id", "work_date", name="uq_timesheet_employee_project_day"),)

    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    week_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    work_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    hours: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    status: Mapped[TimesheetStatus] = mapped_column(Enum(TimesheetStatus, name="timesheet_status"), default=TimesheetStatus.DRAFT)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    task_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    employee: Mapped[Employee] = relationship("Employee")  # noqa: F821
    project: Mapped[Project] = relationship("Project")  # noqa: F821
    approvals: Mapped[list[TimesheetApproval]] = relationship(back_populates="timesheet", cascade="all, delete-orphan")


class TimesheetApproval(UUIDPkMixin, Base):
    __tablename__ = "timesheet_approvals"

    timesheet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("timesheets.id", ondelete="CASCADE"), nullable=False
    )
    approver_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=False)
    action: Mapped[ApprovalAction] = mapped_column(Enum(ApprovalAction, name="approval_action"))
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    timesheet: Mapped[Timesheet] = relationship(back_populates="approvals")
    approver: Mapped[Employee] = relationship("Employee")  # noqa: F821


class Holiday(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "holidays"

    holiday_date: Mapped[date] = mapped_column(Date, unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_optional: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="published", server_default="published")
    location: Mapped[str] = mapped_column(String(100), nullable=False, default="All locations", server_default="All locations")
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=True)
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LeaveRequest(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "leave_requests"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'approved', 'rejected', 'cancelled')", name="ck_leave_status"),
        CheckConstraint("leave_type IN ('annual', 'sick', 'casual', 'unpaid', 'other')", name="ck_leave_type"),
    )

    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    manager_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    leave_type: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending", server_default="pending")
    decision_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    employee: Mapped[Employee] = relationship("Employee", foreign_keys=[employee_id])  # noqa: F821
    manager: Mapped[Employee | None] = relationship("Employee", foreign_keys=[manager_id])  # noqa: F821
    decided_by: Mapped[Employee | None] = relationship("Employee", foreign_keys=[decided_by_id])  # noqa: F821
