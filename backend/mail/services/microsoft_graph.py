"""Microsoft Graph email provider strategy.

Implements `EmailServiceBase` for Microsoft Graph (`microsoft_graph_email`):
resolves credentials from `organization_integrations`, and sends mail via the
Graph `sendMail` endpoint using the OAuth2 client-credentials flow.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx

from common.logger import logger
from mail.models.response import EmailSendResult
from mail.services.base import (
    EmailMessage,
    EmailServiceBase,
    load_org_integration,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

GRAPH_API_TIMEOUT_SECONDS = 15


@dataclass
class GraphCreds:
    """Resolved Microsoft Graph email credentials for an organization."""

    tenant_id: str
    client_id: str
    client_secret: str
    from_email: str
    from_name: str | None = None
    reply_to: str | None = None


def _get_graph_access_token(tenant_id: str, client_id: str, client_secret: str) -> str:
    """Obtain an OAuth2 access token from Microsoft using client credentials flow."""
    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    token_response = httpx.post(
        token_url,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "https://graph.microsoft.com/.default",
        },
        timeout=GRAPH_API_TIMEOUT_SECONDS,
    )
    token_response.raise_for_status()
    access_token = token_response.json().get("access_token")
    if not access_token:
        raise ValueError("Failed to obtain Microsoft Graph access token")
    return access_token


def _build_graph_email_payload(
    from_email: str,
    from_name: str | None,
    recipients: list[str],
    subject: str,
    body_html: str,
    reply_to: str | None = None,
) -> dict:
    """Build the Graph API message payload."""
    sender_address: dict = {"emailAddress": {"address": from_email}}
    if from_name:
        sender_address["emailAddress"]["name"] = from_name

    message: dict = {
        "subject": subject,
        "body": {"contentType": "HTML", "content": body_html},
        "from": sender_address,
        "toRecipients": [{"emailAddress": {"address": r}} for r in recipients],
    }
    if reply_to:
        message["replyTo"] = [{"emailAddress": {"address": reply_to}}]
    return message


class MicrosoftGraphEmailService(EmailServiceBase):
    """Strategy for the Microsoft Graph email provider."""

    name = "microsoft_graph_email"

    def resolve_credentials(self, db: Session | None, org_id: str) -> GraphCreds | None:
        """Read Microsoft Graph email credentials from organization_integrations."""
        loaded = load_org_integration(db, org_id, "microsoft_graph_email")
        if loaded is None:
            return None
        config, secrets = loaded
        return self.credentials_from_payload(config, secrets)

    def credentials_from_payload(self, config: dict, secrets: dict) -> GraphCreds | None:
        """Build Microsoft Graph credentials from a raw config/secrets payload, or None."""
        tenant_id = config.get("tenant_id") or ""
        client_id = config.get("client_id") or ""
        from_email = config.get("from_email") or ""
        from_name = config.get("from_name") or None
        reply_to = config.get("reply_to_email") or None
        if not tenant_id or not client_id or not from_email:
            return None
        client_secret = secrets.get("client_secret") or ""
        if not client_secret:
            return None
        return GraphCreds(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
            from_email=from_email,
            from_name=from_name,
            reply_to=reply_to,
        )

    def validate(self, **params) -> tuple[bool, str]:
        """Microsoft Graph validation is not supported; report success without network calls."""
        return True, "Validation not supported for Microsoft Graph"

    def send(self, creds: GraphCreds, message: EmailMessage) -> EmailSendResult:
        """Send email via Microsoft Graph API using client credentials flow."""
        try:
            access_token = _get_graph_access_token(
                creds.tenant_id, creds.client_id, creds.client_secret
            )
            graph_message = _build_graph_email_payload(
                message.from_email,
                message.from_name,
                message.recipients,
                message.subject,
                message.body_html,
                message.reply_to,
            )
            send_url = f"https://graph.microsoft.com/v1.0/users/{message.from_email}/sendMail"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }
            response = httpx.post(
                send_url,
                json={"message": graph_message},
                headers=headers,
                timeout=GRAPH_API_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return EmailSendResult(success=True, message="Email sent successfully")
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Microsoft Graph HTTP error: %s",
                exc.response.status_code if exc.response else exc,
            )
            return EmailSendResult(success=False, message="Microsoft Graph HTTP error")
        except Exception as exc:
            logger.error("Microsoft Graph send failed: %s", exc)
            return EmailSendResult(success=False, message="Microsoft Graph send failed")


graph_service = MicrosoftGraphEmailService()
