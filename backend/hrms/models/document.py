from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hrms.database import Base
from hrms.models.base import TimestampMixin, UUIDPkMixin
from hrms.models.enums import DocumentStatus, DocumentType


class EmployeeDocument(UUIDPkMixin, TimestampMixin, Base):
    """
    A file the employee (or HR on their behalf) uploaded — ID proofs, education
    and experience certificates, the signed offer letter. Collected during
    onboarding but kept for the employee's whole tenure. Files live on disk
    under settings.DOCUMENT_STORAGE_DIR; this row is the metadata + verification
    state HR works with.
    """

    __tablename__ = "employee_documents"

    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
    doc_type: Mapped[DocumentType] = mapped_column(Enum(DocumentType, name="document_type"))
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    status: Mapped[DocumentStatus] = mapped_column(Enum(DocumentStatus, name="document_status"), default=DocumentStatus.SUBMITTED)
    # Rejection reason / verification note, shown to the employee.
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=True)
    verified_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    employee: Mapped[Employee] = relationship("Employee", foreign_keys=[employee_id])  # noqa: F821
    verified_by: Mapped[Employee | None] = relationship(  # noqa: F821
        "Employee", foreign_keys=[verified_by_id]
    )
