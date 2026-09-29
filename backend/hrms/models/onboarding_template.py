from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hrms.database import Base
from hrms.models.base import TimestampMixin, UUIDPkMixin
from hrms.models.enums import AssigneeRule, OnboardingType, TaskActionType


class OnboardingTemplate(UUIDPkMixin, TimestampMixin, Base):
    """
    An editable checklist definition. Starting onboarding stamps the template's
    steps into concrete OnboardingTasks with resolved assignees and due dates,
    so HR can change the template without touching in-flight records.
    """

    __tablename__ = "onboarding_templates"

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    workflow_type: Mapped[OnboardingType] = mapped_column(Enum(OnboardingType, name="onboarding_type", create_type=False))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    steps: Mapped[list[OnboardingTemplateStep]] = relationship(
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="OnboardingTemplateStep.seq",
    )


class OnboardingTemplateStep(UUIDPkMixin, Base):
    __tablename__ = "onboarding_template_steps"
    __table_args__ = (UniqueConstraint("template_id", "seq", name="uq_template_step_seq"),)

    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("onboarding_templates.id", ondelete="CASCADE"),
        nullable=False,
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    # Stable machine key ("newtuple_id", "razorpay_account"...) the UI uses for
    # step-specific affordances (e.g. the payroll-reference input on Razorpay).
    step_key: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    assignee_rule: Mapped[AssigneeRule] = mapped_column(Enum(AssigneeRule, name="assignee_rule"), default=AssigneeRule.ROLE)
    # Role *name* (RoleName value), resolved to a person at stamp time. A string
    # rather than an FK so templates can be created before roles are seeded.
    assignee_role: Mapped[str | None] = mapped_column(String(100), nullable=True)

    action_type: Mapped[TaskActionType] = mapped_column(
        Enum(TaskActionType, name="task_action_type"), default=TaskActionType.MANUAL
    )
    # Due-date offset in days from when onboarding starts.
    due_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Seq numbers of steps that must be DONE/SKIPPED before this one becomes READY.
    depends_on_seqs: Mapped[list[int] | None] = mapped_column(ARRAY(Integer), nullable=True)

    template: Mapped[OnboardingTemplate] = relationship(back_populates="steps")
