"""Azure Communication Services (ACS) email provider strategy.

Owns credential resolution, validation, and delivery for the
`azure_communication` provider. Credentials are read from the
`organization_integrations` table (config keys: endpoint, from_email,
from_name, reply_to_email; secret key: connection_string).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from azure.communication.email import EmailClient
from azure.core.exceptions import ClientAuthenticationError, HttpResponseError, ServiceRequestError

from common.logger import logger
from mail.models.response import EmailSendResult
from mail.services.base import EmailMessage, EmailServiceBase, load_org_integration

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@dataclass
class AcsCreds:
    """Resolved Azure Communication Services credentials for an organization."""

    endpoint: str
    connection_string: str
    from_email: str
    from_name: str | None
    reply_to: str | None


class AcsEmailService(EmailServiceBase):
    """Strategy for the Azure Communication Services email provider."""

    name = "azure_communication"

    def resolve_credentials(self, db: Session | None, org_id: str) -> AcsCreds | None:
        """Return ACS credentials from organization_integrations, or None if unconfigured."""
        loaded = load_org_integration(db, org_id, "azure_communication")
        if loaded is None:
            return None
        config, secrets = loaded
        return self.credentials_from_payload(config, secrets)

    def credentials_from_payload(self, config: dict, secrets: dict) -> AcsCreds | None:
        """Build ACS credentials from a raw config/secrets payload, or None."""
        endpoint = config.get("endpoint") or ""
        from_email = config.get("from_email") or ""
        from_name = config.get("from_name") or None
        reply_to = config.get("reply_to_email") or None
        if not endpoint or not from_email:
            return None
        connection_string = secrets.get("connection_string") or ""
        if not connection_string:
            return None
        return AcsCreds(
            endpoint=endpoint,
            connection_string=connection_string,
            from_email=from_email,
            from_name=from_name,
            reply_to=reply_to,
        )

    def validate(self, **params) -> tuple[bool, str]:
        """Validate raw ACS credentials without persisting. Returns (is_valid, message)."""
        endpoint = params.get("endpoint")
        connection_string = params.get("connection_string")
        if not endpoint:
            return False, "Endpoint is required for azure_communication"
        if not connection_string:
            return False, "Connection string is required for azure_communication"
        try:
            connection_endpoint = ""
            for part in connection_string.split(";"):
                if part.lower().startswith("endpoint="):
                    connection_endpoint = part.split("=", 1)[1].strip()
                    break
            if (
                endpoint
                and connection_endpoint
                and endpoint.rstrip("/") != connection_endpoint.rstrip("/")
            ):
                logger.warning(
                    "Azure Communication endpoint mismatch between config and connection string",
                    extra={"config_endpoint": endpoint, "connection_endpoint": connection_endpoint},
                )
            _ = EmailClient.from_connection_string(connection_string)
            logger.info("Azure Communication Email credentials validated successfully")
            return True, ""
        except ClientAuthenticationError:
            return False, "Authentication failed - check Azure Communication connection string"
        except ValueError as exc:
            return False, str(exc)
        except (HttpResponseError, ServiceRequestError) as exc:
            return False, str(exc)
        except Exception as exc:
            return False, str(exc)

    def send(self, creds: AcsCreds, message: EmailMessage) -> EmailSendResult:
        """Send outbound email via Azure Communication Services Email API."""
        endpoint = creds.endpoint
        connection_string = creds.connection_string
        sender_email = message.from_email
        sender_name = message.from_name
        recipients = message.recipients
        subject = message.subject
        body_html = message.body_html
        body_text = message.body_text
        reply_to = message.reply_to
        try:
            if not sender_email:
                raise ValueError("Sender email is required for Azure Communication email")
            if not recipients:
                raise ValueError("At least one recipient is required for Azure Communication email")

            connection_endpoint = ""
            for part in connection_string.split(";"):
                if part.lower().startswith("endpoint="):
                    connection_endpoint = part.split("=", 1)[1].strip()
                    break
            if (
                endpoint
                and connection_endpoint
                and endpoint.rstrip("/") != connection_endpoint.rstrip("/")
            ):
                logger.warning(
                    "Azure Communication endpoint mismatch between config and connection string",
                    extra={"config_endpoint": endpoint, "connection_endpoint": connection_endpoint},
                )

            client = EmailClient.from_connection_string(connection_string)
            message_payload: dict[str, Any] = {
                "senderAddress": sender_email,
                "content": {"subject": subject, "html": body_html},
                "recipients": {"to": [{"address": email} for email in recipients]},
            }
            if body_text:
                message_payload["content"]["plainText"] = body_text
            if sender_name:
                message_payload["senderDisplayName"] = sender_name
            if reply_to:
                message_payload["replyTo"] = [{"address": reply_to}]

            logger.info(
                "Sending email via Azure Communication",
                extra={
                    "endpoint": endpoint,
                    "sender_email": sender_email,
                    "recipient_count": len(recipients),
                },
            )
            poller = client.begin_send(message_payload)
            result = poller.result()
            if isinstance(result, dict):
                status = str(result.get("status", "")).lower()
                message_id = result.get("id")
            else:
                status = str(getattr(result, "status", "")).lower()
                message_id = getattr(result, "id", None)
            if status == "succeeded":
                return EmailSendResult(
                    success=True, message="Email sent successfully", message_id=message_id
                )
            return EmailSendResult(
                success=False,
                message=f"Azure Communication send failed with status: {status or 'unknown'}",
                message_id=message_id,
            )
        except ValueError as exc:
            return EmailSendResult(success=False, message=f"Invalid payload: {exc}")
        except ClientAuthenticationError as exc:
            return EmailSendResult(success=False, message=f"Authentication failed: {exc}")
        except (HttpResponseError, ServiceRequestError) as exc:
            return EmailSendResult(success=False, message=f"Azure Communication error: {exc}")
        except Exception as exc:
            logger.exception(
                "Unexpected Azure Communication send error", extra={"endpoint": endpoint}
            )
            return EmailSendResult(success=False, message=f"Unexpected error: {exc}")


acs_service = AcsEmailService()
