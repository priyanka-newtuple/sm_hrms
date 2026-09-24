"""Interface models and contracts for the mail module."""

from __future__ import annotations

from typing import Protocol, Self

from pydantic import ConfigDict, Field, model_validator

from common.data_model import BaseModel as PydanticBaseModel, ExtendedStrEnum


class EmailActionKind(ExtendedStrEnum):
    """`email_templates.action_kind` values the platform sends system emails for.

    Names the known kinds; the column stays free-form because custom and form
    templates carry none.
    """

    MENTION = "notification.mention"
    ASSIGNMENT = "notification.assignment"
    COMMENT = "notification.comment"
    REPLY = "notification.reply"
    LIKE = "notification.like"
    NEW_USER = "notification.new_user"
    NEW_ORG = "notification.new_org"
    ACTION_FAILED = "notification.action_failed"
    PASSWORD_RESET = "auth.password_reset"
    CALENDAR_INVITE = "calendar.invite"
    INVITATION = "user.invitation"


def validate_provider_secret(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized


def validate_optional_display_name(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def validate_optional_region(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def validate_optional_smtp_host(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


class EmailAttachment(PydanticBaseModel):
    """Frozen attachment payload parsed from inbound email."""

    model_config = ConfigDict(frozen=True, from_attributes=True)

    filename: str = Field(..., min_length=1)
    content_type: str = Field(..., min_length=1)
    content_bytes: bytes

    @property
    def size_bytes(self) -> int:
        return len(self.content_bytes)


class ParsedEmail(PydanticBaseModel):
    """Frozen parsed inbound email payload."""

    model_config = ConfigDict(frozen=True, from_attributes=True)

    subject: str = ""
    sender_email: str | None = None
    sender_name: str | None = None
    recipients: list[str] = Field(default_factory=list)
    body_text: str = ""
    body_html: str = ""
    attachments: list[EmailAttachment] = Field(default_factory=list)


class MailConfigLookupService(Protocol):
    """Contract for mail configuration persistence lookups."""

    def get_config(self, db: object, org_id: str, provider: object) -> object | None:
        """Return the active mail configuration when available."""
        ...


class EmailCredentialPayload(PydanticBaseModel):
    """Reusable credential contract for provider validation."""

    provider: str = Field(..., min_length=1)
    access_key_id: str = Field(..., min_length=1)
    secret_access_key: str = Field(..., min_length=1)
    region: str | None = None
    smtp_host: str | None = None
    smtp_port: int | None = None
    from_name: str | None = None

    @model_validator(mode="after")
    def normalize_fields(self) -> Self:
        self.provider = validate_provider_secret(str(self.provider), "provider")
        self.access_key_id = validate_provider_secret(str(self.access_key_id), "access_key_id")
        self.secret_access_key = validate_provider_secret(
            str(self.secret_access_key), "secret_access_key"
        )
        self.region = validate_optional_region(self.region)
        self.smtp_host = validate_optional_smtp_host(self.smtp_host)
        self.from_name = validate_optional_display_name(self.from_name)
        return self
