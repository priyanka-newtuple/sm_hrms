"""SMTP email provider strategy.

Implements `EmailServiceBase` for plain SMTP delivery: credentials are
resolved from `organization_integrations` (provider "smtp"), validated without
persisting, and used to deliver a message. STARTTLS is applied opportunistically
whenever the server offers it, so AUTH credentials are never sent over a
plaintext channel.
"""

from __future__ import annotations

import smtplib
import ssl
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import TYPE_CHECKING

from common.logger import logger
from mail.models.response import EmailSendResult
from mail.services.base import EmailMessage, EmailServiceBase, load_org_integration

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@dataclass
class SmtpCreds:
    """Resolved SMTP credentials and sender identity."""

    username: str
    password: str
    host: str
    port: int
    use_tls: bool
    from_email: str
    from_name: str | None = None
    reply_to: str | None = None


class SmtpEmailService(EmailServiceBase):
    """Strategy for the plain SMTP email provider."""

    name = "smtp"

    def resolve_credentials(self, db: Session | None, org_id: str) -> SmtpCreds | None:
        """Return SMTP credentials from organization_integrations, or None."""
        loaded = load_org_integration(db, org_id, self.name)
        if loaded is None:
            return None
        config, secrets = loaded
        return self.credentials_from_payload(config, secrets)

    def credentials_from_payload(self, config: dict, secrets: dict) -> SmtpCreds | None:
        """Build SMTP credentials from a raw config/secrets payload, or None."""
        smtp_host = config.get("smtp_host") or ""
        smtp_port = config.get("smtp_port")
        from_email = config.get("from_email") or ""
        username = secrets.get("username") or ""
        password = secrets.get("password") or ""
        if not (smtp_host and smtp_port and from_email and username and password):
            return None
        smtp_use_tls = config.get("smtp_use_tls")
        if smtp_use_tls is None:
            smtp_use_tls = True
        return SmtpCreds(
            username=username,
            password=password,
            host=smtp_host,
            port=int(smtp_port),
            use_tls=bool(smtp_use_tls),
            from_email=from_email,
            from_name=config.get("from_name") or None,
            reply_to=config.get("reply_to_email") or None,
        )

    def validate(self, **params) -> tuple[bool, str]:
        """Validate raw SMTP credentials without persisting. Returns (is_valid, message)."""
        username = params.get("access_key_id")
        password = params.get("secret_access_key")
        host = params.get("smtp_host")
        port = params.get("smtp_port")
        use_tls = params.get("smtp_use_tls", True)

        if not host or not port:
            return False, "SMTP host and port are required"

        try:
            if port == 465:
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(host, port, context=context, timeout=10) as server:
                    server.login(username, password)
            else:
                with smtplib.SMTP(host, port, timeout=10) as server:
                    server.ehlo()
                    # Upgrade to TLS whenever the server offers it (SES requires it
                    # on 587), never send AUTH credentials over a plaintext channel.
                    if use_tls or server.has_extn("starttls"):
                        context = ssl.create_default_context()
                        server.starttls(context=context)
                        server.ehlo()
                    server.login(username, password)
            logger.info("SMTP credentials validated successfully")
            return True, ""
        except smtplib.SMTPAuthenticationError as exc:
            logger.warning("SMTP authentication failed: %s", exc)
            return False, "Authentication failed - check username and password"
        except smtplib.SMTPConnectError as exc:
            logger.warning("SMTP connection failed: %s", exc)
            return False, f"Could not connect to SMTP server: {host}:{port}"
        except smtplib.SMTPException as exc:
            logger.warning("SMTP error: %s", exc)
            return False, f"SMTP error: {exc!s}"
        except ConnectionRefusedError:
            return False, f"Connection refused to {host}:{port}"
        except TimeoutError:
            return False, f"Connection timed out to {host}:{port}"
        except Exception as exc:
            logger.warning("SMTP validation failed: %s", exc)
            return False, str(exc)

    def send(self, creds: SmtpCreds, message: EmailMessage) -> EmailSendResult:
        """Deliver `message` over SMTP using `creds`."""
        username = creds.username
        password = creds.password
        host = creds.host
        port = creds.port
        use_tls = creds.use_tls
        sender = message.sender
        from_email = message.from_email
        recipients = message.recipients
        subject = message.subject
        body_html = message.body_html
        body_text = message.body_text
        reply_to = message.reply_to

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = sender
            msg["To"] = ", ".join(recipients)
            if reply_to:
                msg["Reply-To"] = reply_to
            if body_text:
                msg.attach(MIMEText(body_text, "plain", "utf-8"))
            msg.attach(MIMEText(body_html, "html", "utf-8"))
            if port == 465:
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(host, port, context=context) as server:
                    server.login(username, password)
                    server.sendmail(from_email, recipients, msg.as_string())
            else:
                with smtplib.SMTP(host, port) as server:
                    server.ehlo()
                    # Upgrade to TLS whenever the server offers it (SES requires it
                    # on 587), never send AUTH credentials over a plaintext channel.
                    if use_tls or server.has_extn("starttls"):
                        context = ssl.create_default_context()
                        server.starttls(context=context)
                        server.ehlo()
                    server.login(username, password)
                    server.sendmail(from_email, recipients, msg.as_string())
            logger.info(
                "Email sent successfully via SMTP",
                extra={
                    "host": host,
                    "port": port,
                    "recipients": recipients,
                    "subject": subject[:50],
                },
            )
            return EmailSendResult(success=True, message="Email sent successfully", message_id=None)
        except smtplib.SMTPAuthenticationError as exc:
            logger.error("SMTP authentication failed: %s", exc)
            return EmailSendResult(
                success=False, message="SMTP authentication failed. Please check your credentials."
            )
        except smtplib.SMTPRecipientsRefused as exc:
            logger.error("SMTP recipients refused: %s", exc)
            return EmailSendResult(
                success=False, message=f"Recipients refused: {', '.join(exc.recipients.keys())}"
            )
        except smtplib.SMTPSenderRefused as exc:
            logger.error("SMTP sender refused: %s", exc)
            return EmailSendResult(
                success=False,
                message="Sender email rejected. Please verify your sender email is allowed.",
            )
        except smtplib.SMTPException as exc:
            logger.error("SMTP error: %s", exc)
            return EmailSendResult(success=False, message=f"SMTP error: {exc!s}")
        except Exception as exc:
            logger.exception("Unexpected error sending email via SMTP: %s", exc)
            return EmailSendResult(success=False, message=f"Failed to send email: {exc!s}")


smtp_service = SmtpEmailService()
