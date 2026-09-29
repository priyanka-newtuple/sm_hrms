from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hrms.database import Base
from hrms.models.base import TimestampMixin, UUIDPkMixin


class PerformanceCycle(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "performance_cycles"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'pending_approval', 'open', 'review', 'calibration', 'published', 'closed')",
            name="ck_performance_cycle_status",
        ),
    )

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    goal_due_date: Mapped[date] = mapped_column(Date, nullable=False)
    self_review_due_date: Mapped[date] = mapped_column(Date, nullable=False)
    manager_review_due_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft", server_default="draft")
    created_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=False)
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_by: Mapped[Employee] = relationship("Employee", foreign_keys=[created_by_id])  # noqa: F821
    approved_by: Mapped[Employee | None] = relationship("Employee", foreign_keys=[approved_by_id])  # noqa: F821


class PerformanceGoal(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "performance_goals"
    __table_args__ = (
        CheckConstraint("weight > 0 AND weight <= 100", name="ck_performance_goal_weight"),
        CheckConstraint("progress >= 0 AND progress <= 100", name="ck_performance_goal_progress"),
        CheckConstraint(
            "status IN ('draft', 'pending_approval', 'approved', 'changes_requested')",
            name="ck_performance_goal_status",
        ),
    )

    cycle_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("performance_cycles.id", ondelete="CASCADE"), index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    measurement: Mapped[str] = mapped_column(Text, nullable=False)
    weight: Mapped[int] = mapped_column(Integer, nullable=False)
    target_date: Mapped[date] = mapped_column(Date, nullable=False)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    evidence: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft", server_default="draft")
    manager_comment: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")

    cycle: Mapped[PerformanceCycle] = relationship()
    employee: Mapped[Employee] = relationship("Employee")  # noqa: F821


class PerformanceReview(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "performance_reviews"
    __table_args__ = (
        UniqueConstraint("cycle_id", "employee_id", name="uq_performance_review_cycle_employee"),
        CheckConstraint(
            "status IN ('not_started', 'self_draft', 'submitted_to_manager', "
            "'manager_submitted', 'calibrated', 'published', 'acknowledged')",
            name="ck_performance_review_status",
        ),
    )

    cycle_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("performance_cycles.id", ondelete="CASCADE"), index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    manager_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="not_started", server_default="not_started")
    self_summary: Mapped[str | None] = mapped_column(Text)
    self_rating: Mapped[int | None] = mapped_column(Integer)
    manager_summary: Mapped[str | None] = mapped_column(Text)
    manager_rating: Mapped[int | None] = mapped_column(Integer)
    calibration_comment: Mapped[str | None] = mapped_column(Text)
    calibrated_rating: Mapped[int | None] = mapped_column(Integer)
    calibrated_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"))
    final_rating: Mapped[int | None] = mapped_column(Integer)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    employee_comment: Mapped[str | None] = mapped_column(Text)

    cycle: Mapped[PerformanceCycle] = relationship()
    employee: Mapped[Employee] = relationship("Employee", foreign_keys=[employee_id])  # noqa: F821
    manager: Mapped[Employee | None] = relationship("Employee", foreign_keys=[manager_id])  # noqa: F821
    calibrated_by: Mapped[Employee | None] = relationship("Employee", foreign_keys=[calibrated_by_id])  # noqa: F821
    feedback: Mapped[list[ProjectFeedback]] = relationship(back_populates="review", cascade="all, delete-orphan")


class ProjectFeedback(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "project_feedback"
    __table_args__ = (
        UniqueConstraint("review_id", "project_id", "reviewer_id", name="uq_project_feedback_reviewer"),
        CheckConstraint("status IN ('pending', 'submitted')", name="ck_project_feedback_status"),
    )

    review_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("performance_reviews.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"))
    reviewer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", server_default="pending")
    rating: Mapped[int | None] = mapped_column(Integer)
    contribution: Mapped[str | None] = mapped_column(Text)
    collaboration: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    review: Mapped[PerformanceReview] = relationship(back_populates="feedback")
    project: Mapped[Project] = relationship("Project")  # noqa: F821
    reviewer: Mapped[Employee] = relationship("Employee")  # noqa: F821
