from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hrms.database import Base
from hrms.models.base import TimestampMixin, UUIDPkMixin
from hrms.models.enums import CustomerStatus, EngagementType, ProjectHealth, ProjectStatus


class Customer(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "customers"

    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    status: Mapped[CustomerStatus] = mapped_column(
        Enum(CustomerStatus, name="customer_status"), default=CustomerStatus.ACTIVE, nullable=False
    )
    industry: Mapped[str | None] = mapped_column(String(100), nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # The employee who owns this account commercially (usually a Delivery Manager).
    account_owner_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=True)
    contract_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    contract_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    payment_terms_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    billing_address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Commercial — gated behind PermissionKey.VIEW_CUSTOMER_CONTRACT_VALUE
    contract_value: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)

    projects: Mapped[list[Project]] = relationship(back_populates="customer")
    account_owner: Mapped[Employee | None] = relationship(  # noqa: F821
        "Employee", foreign_keys=[account_owner_id]
    )


class Project(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint(
            "approval_status IN ('draft', 'pending', 'changes_requested', 'rejected', 'approved')",
            name="ck_project_approval_status",
        ),
    )

    # Existing/seeded operational projects are grandfathered as approved.
    # API creation explicitly chooses draft or Super Admin direct approval.
    approval_status: Mapped[str] = mapped_column(String(30), default="approved", server_default="approved", nullable=False)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=True)

    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)
    project_manager_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=False)
    delivery_manager_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=True)
    status: Mapped[ProjectStatus] = mapped_column(Enum(ProjectStatus, name="project_status"), default=ProjectStatus.ACTIVE)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    engagement_type: Mapped[EngagementType] = mapped_column(
        Enum(EngagementType, name="engagement_type"),
        default=EngagementType.TIME_AND_MATERIALS,
        nullable=False,
    )
    health: Mapped[ProjectHealth] = mapped_column(
        Enum(ProjectHealth, name="project_health"), default=ProjectHealth.GREEN, nullable=False
    )
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    practice: Mapped[str | None] = mapped_column(String(100), nullable=True)
    budgeted_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Commercial/financial — gated behind VIEW_BILLING_RATE / VIEW_PROJECT_REVENUE / VIEW_PROJECT_MARGIN
    budget_amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    billing_rate: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    revenue: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    margin_percent: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)

    customer: Mapped[Customer] = relationship(back_populates="projects")
    project_manager: Mapped[Employee] = relationship(  # noqa: F821
        "Employee", foreign_keys=[project_manager_id]
    )
    delivery_manager: Mapped[Employee | None] = relationship(  # noqa: F821
        "Employee", foreign_keys=[delivery_manager_id]
    )
    approval_requests: Mapped[list[ProjectApprovalRequest]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ProjectApprovalRequest.created_at",
    )


class ProjectApprovalRequest(UUIDPkMixin, TimestampMixin, Base):
    """Initial approval or a staged amendment. Live approved values stay unchanged until approved."""

    __tablename__ = "project_approval_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'pending', 'changes_requested', 'rejected', 'approved')", name="ck_project_request_status"
        ),
        CheckConstraint("kind IN ('initial', 'amendment')", name="ck_project_request_kind"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    requested_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"))
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="draft", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    proposed: Mapped[dict] = mapped_column(JSONB, nullable=False)
    history: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    project: Mapped[Project] = relationship(back_populates="approval_requests")
    requester: Mapped[Employee] = relationship("Employee", foreign_keys=[requested_by_id])  # noqa: F821
    reviewer: Mapped[Employee | None] = relationship("Employee", foreign_keys=[reviewed_by_id])  # noqa: F821
