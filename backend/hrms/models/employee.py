from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Boolean, Date, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hrms.database import Base
from hrms.models.base import TimestampMixin, UUIDPkMixin
from hrms.models.enums import EmploymentStatus, EmploymentType, ExitType


class Employee(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "employees"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    role_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("roles.id"))
    reports_to_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=True)

    employee_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    work_email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    department: Mapped[str] = mapped_column(String(100), ForeignKey("departments.name", ondelete="RESTRICT"), nullable=False)
    designation: Mapped[str] = mapped_column(String(100), ForeignKey("designations.name", ondelete="RESTRICT"), nullable=False)
    employment_status: Mapped[EmploymentStatus] = mapped_column(
        Enum(EmploymentStatus, name="employment_status"), default=EmploymentStatus.ACTIVE
    )
    date_joined: Mapped[date] = mapped_column(Date, nullable=False)
    employment_type: Mapped[EmploymentType] = mapped_column(
        Enum(EmploymentType, name="employment_type"),
        default=EmploymentType.FULL_TIME,
        nullable=False,
    )
    work_location: Mapped[str | None] = mapped_column(String(100), nullable=True)
    probation_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    confirmation_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notice_period_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Offboarding — populated by employee_service.offboard_employee()
    last_working_day: Mapped[date | None] = mapped_column(Date, nullable=True)
    exit_type: Mapped[ExitType | None] = mapped_column(Enum(ExitType, name="exit_type"), nullable=True)
    exit_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    rehire_eligible: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # Basic / non-sensitive profile fields
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    skills: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # PII — gated behind DataProfile != BASIC/NONE
    personal_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Compensation / payroll — gated behind PermissionKey.VIEW_EMPLOYEE_COMPENSATION /
    # VIEW_BANK_PAYROLL_DATA in addition to DataProfile.
    salary_ctc: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    bank_account_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    bank_ifsc: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # External payroll provider id (Razorpay contact), captured during onboarding.
    payroll_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Cost to company for delivery/finance margin calculations — VIEW_EMPLOYEE_COST
    employee_cost_rate: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)

    user: Mapped[User] = relationship("User", back_populates="employee")  # noqa: F821
    role: Mapped[Role] = relationship("Role")  # noqa: F821
    reports_to: Mapped[Employee | None] = relationship("Employee", remote_side="Employee.id")

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"
