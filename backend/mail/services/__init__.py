"""Email service strategy registry.

The mail manager selects a service (explicitly or via the auto-resolution order)
and delegates credential resolution, validation, and delivery to it. Mirrors the
per-provider service layout used by `llm/services`.
"""

from __future__ import annotations

from mail.services.acs import acs_service
from mail.services.base import EmailMessage, EmailServiceBase, load_org_integration
from mail.services.microsoft_graph import graph_service
from mail.services.ses import ses_service
from mail.services.smtp import smtp_service

_SERVICES: dict[str, EmailServiceBase] = {
    service.name: service
    for service in (smtp_service, ses_service, acs_service, graph_service)
}

# Order used when no provider is specified — mirrors historical behavior:
# Microsoft Graph, then Azure Communication, then SES, then SMTP.
AUTO_ORDER: tuple[str, ...] = ("microsoft_graph_email", "azure_communication", "ses", "smtp")


def get_service(provider: object) -> EmailServiceBase | None:
    """Return the email service for a provider name or EmailProvider enum, or None."""
    if provider is None:
        return None
    key = getattr(provider, "value", provider)
    return _SERVICES.get(key)


def auto_services() -> list[EmailServiceBase]:
    """Services to try, in priority order, when no provider is specified."""
    return [_SERVICES[name] for name in AUTO_ORDER]


__all__ = [
    "AUTO_ORDER",
    "EmailMessage",
    "EmailServiceBase",
    "auto_services",
    "get_service",
    "load_org_integration",
]
