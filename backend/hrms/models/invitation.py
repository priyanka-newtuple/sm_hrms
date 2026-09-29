from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hrms.database import Base
from hrms.models.base import TimestampMixin, UUIDPkMixin
from hrms.models.enums import InvitationStatus


class EmployeeInvitation(UUIDPkMixin, TimestampMixin, Base):
    """
    Invitation sent to a new hire (usually to their personal email — the work
    account may be minutes old) asking them to sign in to HRMS and complete
    their profile. Only the SHA-256 hash of the token is stored.
    """

    __tablename__ = "employee_invitations"

    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    status: Mapped[InvitationStatus] = mapped_column(
        Enum(InvitationStatus, name="invitation_status"), default=InvitationStatus.PENDING
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    employee: Mapped[Employee] = relationship("Employee")  # noqa: F821
