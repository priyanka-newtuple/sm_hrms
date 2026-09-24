"""Provider-strategy contracts for outbound email.

Each email provider (SMTP, SES, Azure Communication, Microsoft Graph) implements
`EmailProviderBackend`: it owns how its credentials are resolved, validated, and
how a message is delivered. The mail manager stays a thin facade that selects a
backend and delegates.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

from common.encryption import get_encryption_service
from common.logger import logger
from integrations.db_models import OrganizationIntegrationModel

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from mail.models.response import EmailSendResult


@dataclass
class EmailMessage:
    """A provider-agnostic outbound message."""

    from_email: str
    from_name: str | None
    recipients: list[str]
    subject: str
    body_html: str
    body_text: str | None = None
    reply_to: str | None = None

    @property
    def sender(self) -> str:
        """RFC-5322 sender string, e.g. 'Name <addr>' or just 'addr'."""
        return f"{self.from_name} <{self.from_email}>" if self.from_name else self.from_email


def load_org_integration(
    db: Session | None, org_id: str, provider_name: str
) -> tuple[dict, dict] | None:
    """Return `(config, secrets)` for a provider from organization_integrations.

    `config` is the plaintext config JSON; `secrets` is the decrypted secret blob.
    Returns None when there is no row (or no DB session).
    """
    if db is None:
        return None
    try:
        row = (
            db.query(OrganizationIntegrationModel)
            .filter(
                OrganizationIntegrationModel.organization_id == org_id,
                OrganizationIntegrationModel.provider == provider_name,
            )
            .first()
        )
        if row is None:
            return None
        config = dict(row.config or {})
        secrets: dict = {}
        if row.encrypted_secret_config:
            raw = get_encryption_service().decrypt(row.encrypted_secret_config)
            secrets = json.loads(raw) if isinstance(raw, str) else (raw or {})
        return config, dict(secrets)
    except Exception as exc:
        logger.error("Failed to load %s integration for org=%s: %s", provider_name, org_id, exc)
        return None


class EmailServiceBase(ABC):
    """Strategy for one email provider.

    Credential objects returned by `resolve_credentials` must expose
    `from_email`, `from_name`, and `reply_to` (the manager builds the
    `EmailMessage` from those).
    """

    #: Provider identifier — matches the `organization_integrations.provider`
    #: value (and the EmailProvider enum value where one exists).
    name: str

    @abstractmethod
    def resolve_credentials(self, db: Session | None, org_id: str):
        """Return this provider's credentials for the org, or None if unconfigured."""

    @abstractmethod
    def credentials_from_payload(self, config: dict, secrets: dict):
        """Build this provider's credentials from a raw config/secrets payload
        (e.g. an unsaved form), or None if incomplete."""

    @abstractmethod
    def validate(self, **params) -> tuple[bool, str]:
        """Validate raw credentials without persisting. Returns (is_valid, message)."""

    @abstractmethod
    def send(self, creds, message: EmailMessage) -> EmailSendResult:
        """Deliver `message` using `creds`."""
