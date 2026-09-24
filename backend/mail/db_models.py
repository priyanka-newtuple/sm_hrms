"""Persistence models for the mail module."""

from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Any

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.sql import func
from sqlalchemy.types import JSON

from database.manager import Base


class EmailProvider(StrEnum):
    """Supported email providers."""

    SES = "ses"
    SMTP = "smtp"
    AZURE_COMMUNICATION = "azure_communication"


class InboundEmail(Base):
    """Tracks inbound email processing for ATS intake."""

    __tablename__ = "inbound_emails"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    message_id = Column(String(128), nullable=True, unique=True, index=True)
    s3_bucket = Column(String(255), nullable=True)
    s3_key = Column(String(1024), nullable=True)
    sender_email = Column(String(255), nullable=True)
    sender_name = Column(String(255), nullable=True)
    recipient_emails = Column(JSON, nullable=True)
    subject = Column(String(512), nullable=True)
    body_text = Column(Text, nullable=True)
    body_html = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="received", index=True)
    error_message = Column(Text, nullable=True)
    candidate_id = Column(String(36), nullable=True)
    application_id = Column(String(36), nullable=True)
    attachments = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (Index("ix_inbound_emails_org_status", "organization_id", "status"),)


class EmailTemplateModel(Base):
    """Stored HTML email template, optionally linked to a public form schema."""

    __tablename__ = "email_templates"
    __table_args__ = (
        {
            "schema": f"{__import__('os').environ.get('POSTGRES_APP_SCHEMA', 'public')}_definitions",
            "extend_existing": True,
        },
    )

    template_id = Column(String(36), primary_key=True)
    organization_id = Column(String(36), nullable=True)
    name = Column(String(128), nullable=False)
    subject = Column(Text, nullable=False)
    body_html = Column(Text, nullable=False)
    form_id = Column(String(36), nullable=True)
    action_kind = Column(String(64), nullable=True)
    entity_type = Column(String(128), nullable=True)
    is_system = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class MailModelService:
    """Persistence adapter helpers for the mail module."""

    def __init__(self, database_service_manager: Any = None) -> None:
        """Store the shared database service manager for mail persistence helpers."""
        self.database_service_manager = database_service_manager
        self.module_name = "mail"

    def list_email_templates(self, db, organization_id: str, action_kind: str | None = None) -> list[dict[str, Any]]:
        """List system and organization-owned email templates visible to one organization."""
        query = (
            db.query(EmailTemplateModel)
            .filter(
                (EmailTemplateModel.organization_id == organization_id)
                | (EmailTemplateModel.is_system.is_(True))
            )
        )
        if action_kind:
            query = query.filter(
                (EmailTemplateModel.action_kind == action_kind)
                | (EmailTemplateModel.action_kind.is_(None))
            )
        rows = query.order_by(EmailTemplateModel.created_at.desc()).all()
        return [self._to_template_dict(row) for row in rows]

    def get_email_template(
        self, db, organization_id: str, template_id: str
    ) -> dict[str, Any] | None:
        """Fetch one email template if it is system-owned or belongs to the organization."""
        row = (
            db.query(EmailTemplateModel)
            .filter(EmailTemplateModel.template_id == template_id)
            .filter(
                (EmailTemplateModel.organization_id == organization_id)
                | (EmailTemplateModel.is_system.is_(True))
            )
            .first()
        )
        return self._to_template_dict(row) if row else None

    def get_default_email_template_for_kind(
        self, db, organization_id: str, action_kind: str
    ) -> dict[str, Any] | None:
        """Fetch the org's override template for a system action_kind, or the
        system default if the org hasn't customized it. Prefers the org's own
        template (is_system=False) when both exist."""
        row = (
            db.query(EmailTemplateModel)
            .filter(EmailTemplateModel.action_kind == action_kind)
            .filter(
                (EmailTemplateModel.organization_id == organization_id)
                | (EmailTemplateModel.is_system.is_(True))
            )
            .order_by(EmailTemplateModel.is_system.asc())
            .first()
        )
        return self._to_template_dict(row) if row else None

    def create_email_template(self, db, organization_id: str, payload: dict[str, Any]) -> str:
        """Insert a new organization-owned email template and return its identifier."""
        template_id = str(payload.get("template_id") or uuid.uuid4())
        model = EmailTemplateModel(
            template_id=template_id,
            organization_id=organization_id,
            name=str(payload.get("name") or ""),
            subject=str(payload.get("subject") or ""),
            body_html=str(payload.get("body_html") or ""),
            form_id=payload.get("form_id"),
            action_kind=payload.get("action_kind") or None,
            entity_type=payload.get("entity_type") or None,
            is_system=False,
        )
        db.add(model)
        db.commit()
        return template_id

    def update_email_template(self, db, template_id: str, payload: dict[str, Any]) -> None:
        """Update mutable fields on an existing email template."""
        row = (
            db.query(EmailTemplateModel)
            .filter(EmailTemplateModel.template_id == template_id)
            .first()
        )
        if row is None:
            return
        row.name = str(payload.get("name") or "")
        row.subject = str(payload.get("subject") or "")
        row.body_html = str(payload.get("body_html") or "")
        row.form_id = payload.get("form_id")
        if "action_kind" in payload:
            row.action_kind = payload["action_kind"] or None
        row.entity_type = payload.get("entity_type") or None
        db.commit()

    def delete_email_template(self, db, template_id: str) -> None:
        """Delete an email template by identifier if it exists."""
        row = (
            db.query(EmailTemplateModel)
            .filter(EmailTemplateModel.template_id == template_id)
            .first()
        )
        if row is not None:
            db.delete(row)
        db.commit()

    @staticmethod
    def _to_template_dict(row: EmailTemplateModel) -> dict[str, Any]:
        """Convert an email template ORM row into a plain response dictionary."""
        return {
            "template_id": row.template_id,
            "organization_id": row.organization_id,
            "name": row.name,
            "subject": row.subject,
            "body_html": row.body_html,
            "form_id": row.form_id,
            "action_kind": row.action_kind,
            "entity_type": row.entity_type,
            "is_system": row.is_system,
            "created_at": row.created_at,
        }
