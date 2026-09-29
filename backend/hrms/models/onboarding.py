from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hrms.database import Base
from hrms.models.base import TimestampMixin, UUIDPkMixin
from hrms.models.enums import OnboardingStatus, OnboardingType, TaskActionType, TaskStatus


class OnboardingRecord(UUIDPkMixin, TimestampMixin, Base):
    """
    Tracks an employee's onboarding/offboarding lifecycle. Where Flowtuple is
    reachable, `flowtuple_workflow_id` links to the workflow driving progress and
    the frontend renders it via WorkflowProvider.embed_url(); the native
    OnboardingTask checklist below is always kept as a fallback / lightweight
    progress record regardless of provider.
    """

    __tablename__ = "onboarding_records"

    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
    workflow_type: Mapped[OnboardingType] = mapped_column(Enum(OnboardingType, name="onboarding_type"))
    status: Mapped[OnboardingStatus] = mapped_column(
        Enum(OnboardingStatus, name="onboarding_status"), default=OnboardingStatus.NOT_STARTED
    )
    flowtuple_workflow_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    employee: Mapped[Employee] = relationship("Employee")  # noqa: F821
    tasks: Mapped[list[OnboardingTask]] = relationship(
        back_populates="onboarding_record",
        cascade="all, delete-orphan",
        order_by="OnboardingTask.seq",
    )


class OnboardingTask(UUIDPkMixin, Base):
    """
    One step of an onboarding/offboarding workflow, stamped from an
    OnboardingTemplateStep (for template-driven onboarding) or created bare
    (legacy offboarding checklist). `is_complete` is kept in sync with `status`
    for backward compatibility with pre-template records and UI.
    """

    __tablename__ = "onboarding_tasks"
    __table_args__ = (Index("ix_onboarding_tasks_assignee_status", "assignee_employee_id", "status"),)

    onboarding_record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("onboarding_records.id", ondelete="CASCADE"), nullable=False
    )
    template_step_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("onboarding_template_steps.id", ondelete="SET NULL"),
        nullable=True,
    )
    seq: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    step_key: Mapped[str | None] = mapped_column(String(50), nullable=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus, name="task_status"), default=TaskStatus.READY)
    is_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    action_type: Mapped[TaskActionType] = mapped_column(
        Enum(TaskActionType, name="task_action_type"), default=TaskActionType.MANUAL
    )

    # Who is on the hook — resolved from the template's assignee_rule at stamp time.
    assignee_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    assignee_role: Mapped[str | None] = mapped_column(String(100), nullable=True)

    depends_on_seqs: Mapped[list[int] | None] = mapped_column(ARRAY(Integer), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    completion_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # The real record this step produced (asset_assignment / allocation /
    # employee_invitation id) — onboarding points at module data, never copies it.
    linked_entity_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    linked_entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    onboarding_record: Mapped[OnboardingRecord] = relationship(back_populates="tasks")
    assignee: Mapped[Employee | None] = relationship(  # noqa: F821
        "Employee", foreign_keys=[assignee_employee_id]
    )
    completed_by: Mapped[Employee | None] = relationship(  # noqa: F821
        "Employee", foreign_keys=[completed_by_id]
    )
