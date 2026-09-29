from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hrms.database import Base
from hrms.models.base import TimestampMixin, UUIDPkMixin

CONTENT_STATUS = "status IN ('draft', 'pending_approval', 'published', 'archived')"


class OrganizationPolicy(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "organization_policies"
    __table_args__ = (CheckConstraint(CONTENT_STATUS, name="ck_policy_status"),)

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    owner: Mapped[str] = mapped_column(String(100), nullable=False, default="People")
    version: Mapped[str] = mapped_column(String(30), nullable=False, default="1.0")
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    review_date: Mapped[date | None] = mapped_column(Date)
    visibility: Mapped[str] = mapped_column(String(20), nullable=False, default="public")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft", server_default="draft")
    created_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=False)
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_by: Mapped[Employee] = relationship("Employee", foreign_keys=[created_by_id])  # noqa: F821
    approved_by: Mapped[Employee | None] = relationship("Employee", foreign_keys=[approved_by_id])  # noqa: F821


class LearningEvent(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "learning_events"
    __table_args__ = (CheckConstraint(CONTENT_STATUS, name="ck_learning_event_status"),)

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    location: Mapped[str] = mapped_column(String(200), nullable=False)
    audience: Mapped[str] = mapped_column(String(200), nullable=False, default="All employees")
    capacity: Mapped[int | None] = mapped_column(Integer)
    registration_url: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft", server_default="draft")
    created_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=False)
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_by: Mapped[Employee] = relationship("Employee", foreign_keys=[created_by_id])  # noqa: F821
    approved_by: Mapped[Employee | None] = relationship("Employee", foreign_keys=[approved_by_id])  # noqa: F821


class JobDescription(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "job_descriptions"

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    department: Mapped[str] = mapped_column(String(100), nullable=False)
    level: Mapped[str] = mapped_column(String(60), nullable=False)
    responsibilities: Mapped[str] = mapped_column(Text, nullable=False)
    requirements: Mapped[str] = mapped_column(Text, nullable=False)
    preferred_skills: Mapped[str | None] = mapped_column(Text)
    experience: Mapped[str | None] = mapped_column(String(100))
    employment_type: Mapped[str] = mapped_column(String(50), nullable=False, default="Full-time")
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True, server_default="true")
    created_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=False)

    created_by: Mapped[Employee] = relationship("Employee")  # noqa: F821


class JobOpening(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "job_openings"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'pending_approval', 'approved', 'published', 'paused', 'closed', 'archived')",
            name="ck_job_opening_status",
        ),
    )

    job_description_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("job_descriptions.id"), nullable=False)
    requisition_code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    hiring_manager_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=False)
    openings: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    location: Mapped[str] = mapped_column(String(150), nullable=False)
    work_mode: Mapped[str] = mapped_column(String(30), nullable=False)
    application_deadline: Mapped[date] = mapped_column(Date, nullable=False)
    referral_bonus: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft", server_default="draft")
    created_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=False)
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"))
    published_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    job_description: Mapped[JobDescription] = relationship()
    hiring_manager: Mapped[Employee] = relationship("Employee", foreign_keys=[hiring_manager_id])  # noqa: F821
    created_by: Mapped[Employee] = relationship("Employee", foreign_keys=[created_by_id])  # noqa: F821


class EmployeeReferral(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "employee_referrals"

    job_opening_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("job_openings.id"), nullable=False)
    referred_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=False)
    candidate_name: Mapped[str] = mapped_column(String(200), nullable=False)
    candidate_email: Mapped[str] = mapped_column(String(255), nullable=False)
    candidate_phone: Mapped[str | None] = mapped_column(String(50))
    message: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="submitted", server_default="submitted")

    job_opening: Mapped[JobOpening] = relationship()
    referred_by: Mapped[Employee] = relationship("Employee")  # noqa: F821
