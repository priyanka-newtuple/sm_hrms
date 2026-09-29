from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from hrms.database import Base
from hrms.models.base import TimestampMixin, UUIDPkMixin
from hrms.models.enums import OutboxStatus


class NotificationOutbox(UUIDPkMixin, TimestampMixin, Base):
    """
    Transactional email queue. Flow logic only ever *writes* rows here (in the
    same transaction as the state change that caused them), and a background
    drain loop actually sends — so a slow or broken SMTP server can never fail
    or delay an onboarding action, and every notification is auditable.
    """

    __tablename__ = "notifications_outbox"

    recipient_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    email_to: Mapped[str] = mapped_column(String(255), nullable=False)
    template_key: Mapped[str] = mapped_column(String(50), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    related_task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("onboarding_tasks.id", ondelete="SET NULL"), nullable=True
    )

    status: Mapped[OutboxStatus] = mapped_column(Enum(OutboxStatus, name="outbox_status"), default=OutboxStatus.QUEUED)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
