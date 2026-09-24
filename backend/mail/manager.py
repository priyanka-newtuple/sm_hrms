"""Business logic manager for mail configuration and delivery."""

from __future__ import annotations

import html
import json
import uuid
from datetime import datetime
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses, parseaddr
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote_plus

import boto3
import httpx
from bs4 import BeautifulSoup
from icalendar import Calendar, Event, vCalAddress, vText

from common.calendar import CalendarEvent, CalendarEventResult, FreeBusySlot
from common.configuration import get_configuration
from common.enums import DefaultRole
from common.logger import logger as structured_logger
from exceptions import NotFoundError, ValidationError
from mail.db_models import InboundEmail, MailModelService
from mail.models.interface import EmailActionKind, EmailAttachment, ParsedEmail
from mail.models.response import (
    EmailSendResult,
    EmailTestResponse,
)
from mail.services import EmailMessage, auto_services, get_service
from user.db_models import Organization

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from mail.db_models import EmailProvider

TEMPLATE_VARIABLES: dict[str, list[dict[str, str]]] = {
    "mail.send_email": [
        {"key": "form_link", "label": "Form Link", "type": "link", "description": "Link to the public form for this entity"},
    ],
}

config = get_configuration()
logger = structured_logger

# Action kind of the system template seeded for calendar-invite emails. Keep in
# sync with 2026_08_09_0002_seed_remaining_system_email_templates.
EMAIL_KIND_CALENDAR_INVITE = EmailActionKind.CALENDAR_INVITE.value



class MailServiceManager:
    """Manager for mail configuration and delivery."""

    def __init__(
        self,
        email_config_model_service: MailModelService | None = None,
        database_service_manager: Any = None,
        config: Any = None,
        auth_service_manager: Any = None,
    ) -> None:
        """Initialize the mail manager with persistence, config, and auth dependencies."""
        self.email_config_model_service = email_config_model_service
        self.database_service_manager = database_service_manager
        self.config = config
        self.auth_service_manager = auth_service_manager
        self.module_name = "mail"
        self._started = False

    def start(self) -> None:
        """Mark the mail module as started."""
        self._started = True

    def stop(self) -> None:
        """Mark the mail module as stopped."""
        self._started = False

    def list_email_templates(self, db: Session, org_id: str, action_kind: str | None = None) -> dict[str, Any]:
        """List email templates available to the given organization."""
        return {"items": self.email_config_model_service.list_email_templates(db, org_id, action_kind=action_kind)}

    def get_template_variables(self, action_kind: str) -> dict[str, Any]:
        """Return available template variables for a given action kind."""
        variables = TEMPLATE_VARIABLES.get(action_kind, [])
        return {"action_kind": action_kind, "variables": variables}

    def get_email_template(self, db: Session, org_id: str, template_id: str) -> dict[str, Any]:
        """Fetch a single email template visible to the given organization."""
        row = self.email_config_model_service.get_email_template(db, org_id, template_id)
        if row is None:
            raise NotFoundError("email template not found")
        return row

    def get_default_email_template_for_kind(
        self, db: Session, org_id: str, action_kind: str
    ) -> dict[str, Any] | None:
        """Fetch the system-notification template for an action kind (e.g.
        "notification.mention", "notification.assignment"), or None if unseeded."""
        return self.email_config_model_service.get_default_email_template_for_kind(
            db, org_id, action_kind
        )

    def create_email_template(
        self,
        db: Session,
        org_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Create an organization-scoped email template and return the saved record."""
        template_id = self.email_config_model_service.create_email_template(db, org_id, payload)
        return self.get_email_template(db, org_id, template_id)

    def update_email_template(
        self,
        db: Session,
        org_id: str,
        template_id: str,
        payload: dict[str, Any],
        actor: dict[str, Any],
    ) -> dict[str, Any]:
        """Update an email template. System templates are shared by every org,
        so only a superadmin may edit one."""
        current = self.get_email_template(db, org_id, template_id)
        actor_roles = actor.get("roles") or []
        if current.get("is_system") and DefaultRole.SUPERADMIN.value not in actor_roles:
            raise ValidationError("only a superadmin can update system templates")
        merged = {
            "name": str(payload.get("name") or current.get("name") or ""),
            "subject": str(payload.get("subject") or current.get("subject") or ""),
            "body_html": str(payload.get("body_html") or current.get("body_html") or ""),
            "form_id": payload.get("form_id", current.get("form_id")),
            "entity_type": payload.get("entity_type", current.get("entity_type")),
        }
        self.email_config_model_service.update_email_template(db, template_id, merged)
        return self.get_email_template(db, org_id, template_id)

    def delete_email_template(
        self,
        db: Session,
        org_id: str,
        template_id: str,
    ) -> None:
        """Delete a non-system email template visible to the given organization."""
        current = self.get_email_template(db, org_id, template_id)
        if current.get("is_system"):
            raise ValidationError("system templates cannot be deleted")
        self.email_config_model_service.delete_email_template(db, template_id)

    def validate_credentials_only(
        self,
        provider: EmailProvider,
        access_key_id: str | None,
        secret_access_key: str | None,
        from_email: str,
        region: str | None = None,
        smtp_host: str | None = None,
        smtp_port: int | None = None,
        smtp_use_tls: bool | None = True,
        endpoint: str | None = None,
        connection_string: str | None = None,
    ) -> tuple[bool, str]:
        service = get_service(provider)
        if service is None:
            return False, f"Unknown provider: {provider}"
        return service.validate(
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            from_email=from_email,
            region=region,
            smtp_host=smtp_host,
            smtp_port=smtp_port,
            smtp_use_tls=smtp_use_tls,
            endpoint=endpoint,
            connection_string=connection_string,
        )

    def send_email(
        self,
        db: Session,
        org_id: str,
        to: str | list[str],
        subject: str,
        body_html: str,
        body_text: str | None = None,
        reply_to: str | None = None,
        provider: EmailProvider | str | None = None,
    ) -> EmailSendResult:
        recipients = [to] if isinstance(to, str) else to
        services = [get_service(provider)] if provider else auto_services()
        for service in services:
            if service is None:
                continue
            creds = service.resolve_credentials(db, org_id)
            if not creds:
                continue
            message = EmailMessage(
                from_email=creds.from_email,
                from_name=creds.from_name,
                recipients=recipients,
                subject=subject,
                body_html=body_html,
                body_text=body_text,
                reply_to=reply_to or creds.reply_to,
            )
            return service.send(creds, message)
        return EmailSendResult(
            success=False,
            message="Email service not configured. Please configure email settings in Settings.",
        )

    _TEST_EMAIL_SUBJECT = "Test Email from State Machine"
    _TEST_EMAIL_HTML = """
        <html>
        <head></head>
        <body>
            <h2>Email Configuration Test</h2>
            <p>This is a test email to verify your email configuration is working correctly.</p>
            <p>If you received this email, your email integration is properly configured.</p>
            <hr>
            <p style="color: #666; font-size: 12px;">
                Sent from State Machine Platform
            </p>
        </body>
        </html>
        """
    _TEST_EMAIL_TEXT = (
        "Email Configuration Test\n\n"
        "This is a test email to verify your email configuration is working correctly.\n\n"
        "If you received this email, your email integration is properly configured.\n\n"
        "---\nSent from State Machine Platform"
    )

    def send_test_email(
        self,
        db: Session,
        org_id: str,
        to_email: str,
        provider: EmailProvider | str | None = None,
        config: dict | None = None,
        secrets: dict | None = None,
    ) -> EmailTestResponse:
        """Send a test email.

        When `config`/`secrets` are supplied, the message is sent ad-hoc using
        those credentials (so a provider can be tested before it is saved).
        Otherwise the org's saved configuration is used.
        """
        if config is not None or secrets is not None:
            service = get_service(provider)
            if service is None:
                return EmailTestResponse(success=False, message=f"Unknown provider: {provider}")
            creds = service.credentials_from_payload(dict(config or {}), dict(secrets or {}))
            if not creds:
                return EmailTestResponse(
                    success=False, message="Provided email credentials are incomplete."
                )
            result = service.send(
                creds,
                EmailMessage(
                    from_email=creds.from_email,
                    from_name=creds.from_name,
                    recipients=[to_email],
                    subject=self._TEST_EMAIL_SUBJECT,
                    body_html=self._TEST_EMAIL_HTML,
                    body_text=self._TEST_EMAIL_TEXT,
                    reply_to=creds.reply_to,
                ),
            )
        else:
            result = self.send_email(
                db=db,
                org_id=org_id,
                to=to_email,
                provider=provider,
                subject=self._TEST_EMAIL_SUBJECT,
                body_html=self._TEST_EMAIL_HTML,
                body_text=self._TEST_EMAIL_TEXT,
            )
        return EmailTestResponse(
            success=result.success,
            message=result.message,
            message_id=result.message_id,
        )

    def _generate_ics(
        self, event: CalendarEvent, organizer_email: str, organizer_name: str = ""
    ) -> str:
        cal = Calendar()
        cal.add("prodid", "-//State Machine//Calendar Invite//EN")
        cal.add("version", "2.0")
        cal.add("calscale", "GREGORIAN")
        cal.add("method", "REQUEST")

        ics_event = Event()
        ics_event.add("summary", event.title)
        ics_event.add("dtstart", event.start_time)
        ics_event.add("dtend", event.end_time)
        ics_event.add("dtstamp", datetime.utcnow())
        ics_event.add("uid", f"{uuid.uuid4()}@newtuple.com")

        if event.description:
            ics_event.add("description", event.description)
        if event.location:
            ics_event.add("location", event.location)

        organizer = vCalAddress(f"MAILTO:{organizer_email}")
        organizer.params["cn"] = vText(organizer_name or organizer_email)
        organizer.params["role"] = vText("REQ-PARTICIPANT")
        ics_event.add("organizer", organizer)

        for attendee_email in event.attendees:
            attendee = vCalAddress(f"MAILTO:{attendee_email}")
            attendee.params["cn"] = vText(attendee_email)
            attendee.params["rsvp"] = vText("TRUE")
            attendee.params["role"] = vText("REQ-PARTICIPANT")
            attendee.params["partstat"] = vText("NEEDS-ACTION")
            ics_event.add("attendee", attendee)

        cal.add_component(ics_event)
        return cal.to_ical().decode("utf-8")

    async def create_ics_event(
        self,
        db: Session,
        org_id: str,
        organizer_email: str,
        organizer_name: str,
        event: CalendarEvent,
        send_invites: bool = True,
    ) -> CalendarEventResult:
        try:
            ics_content = self._generate_ics(
                event, organizer_email=organizer_email, organizer_name=organizer_name
            )
            if send_invites and event.attendees:
                sent = await self._send_ics_email(
                    db=db,
                    org_id=org_id,
                    organizer_email=organizer_email,
                    organizer_name=organizer_name,
                    event=event,
                )
                if not sent:
                    return CalendarEventResult(
                        success=False,
                        message="Failed to send calendar invite email",
                        ics_content=ics_content,
                        method="ics_email",
                    )
            return CalendarEventResult(
                success=True,
                message="Calendar invite sent via email" if send_invites else "ICS file generated",
                ics_content=ics_content,
                method="ics_email",
                metadata={"attendees": event.attendees, "organizer": organizer_email},
            )
        except Exception as exc:
            logger.error("Error generating ICS: %s", exc)
            return CalendarEventResult(
                success=False,
                message=f"Failed to generate calendar invite: {exc!s}",
                method="ics_email",
            )

    async def _send_ics_email(
        self,
        db: Session,
        org_id: str,
        organizer_email: str,
        organizer_name: str,
        event: CalendarEvent,
    ) -> bool:
        try:
            start_str = event.start_time.strftime("%B %d, %Y at %I:%M %p")
            end_str = event.end_time.strftime("%I:%M %p")
            location_block = (
                f"<p><strong>Where:</strong> {html.escape(event.location)}</p>"
                if event.location
                else ""
            )
            description_block = (
                f"<p><strong>Description:</strong><br>{html.escape(event.description)}</p>"
                if event.description
                else ""
            )
            values = {
                "title": html.escape(event.title),
                "when": f"{start_str} - {end_str}",
                "location_block": location_block,
                "description_block": description_block,
                "organizer": html.escape(organizer_name or organizer_email),
            }

            template = self.get_default_email_template_for_kind(
                db, org_id, EMAIL_KIND_CALENDAR_INVITE
            )
            if template:
                subject = self._render_template(template["subject"], values)
                body_html = self._render_template(template["body_html"], values)
            else:
                logger.warning(
                    "calendar invite template '%s' not found; using minimal fallback",
                    EMAIL_KIND_CALENDAR_INVITE,
                )
                subject = f"Calendar Invite: {values['title']}"
                body_html = (
                    f"<h2>{values['title']}</h2>"
                    f"<p><strong>When:</strong> {values['when']}</p>"
                    f"{location_block}{description_block}"
                    f"<p>You have been invited to this event. Please add it to your calendar.</p>"
                )

            result = self.send_email(
                db=db,
                org_id=org_id,
                to=event.attendees,
                subject=subject,
                body_html=body_html,
                reply_to=organizer_email,
            )
            return result.success
        except Exception as exc:
            logger.error("Error sending ICS email: %s", exc)
            return False

    @staticmethod
    def _render_template(text: str, values: dict[str, str]) -> str:
        """Replace {{key}} placeholders in a stored email template."""
        for key, value in values.items():
            text = text.replace(f"{{{{{key}}}}}", value)
        return text

    def _build_s3_client(self) -> Any:
        inbound_email_s3_access_key_id = config.runtime_configuration.inbound_email_s3_access_key_id
        inbound_email_s3_secret_access_key = (
            config.runtime_configuration.inbound_email_s3_secret_access_key
        )
        inbound_email_s3_region = config.runtime_configuration.inbound_email_s3_region
        if inbound_email_s3_access_key_id and inbound_email_s3_secret_access_key:
            return boto3.client(
                "s3",
                region_name=inbound_email_s3_region or None,
                aws_access_key_id=inbound_email_s3_access_key_id,
                aws_secret_access_key=inbound_email_s3_secret_access_key,
            )
        return boto3.client("s3", region_name=inbound_email_s3_region or None)

    def _confirm_sns_subscription(self, subscribe_url: str) -> None:
        try:
            response = httpx.get(subscribe_url, timeout=10)
            response.raise_for_status()
            structured_logger.info("Confirmed SNS subscription for inbound email")
        except Exception as exc:
            structured_logger.warning(f"Failed to confirm SNS subscription: {exc}")

    def _parse_sns_envelope(
        self, payload: dict[str, Any]
    ) -> tuple[str, dict[str, Any], str | None]:
        sns_type = payload.get("Type", "")
        if "Message" not in payload:
            return "", payload, None
        message = payload.get("Message", "")
        if isinstance(message, str):
            try:
                message_payload = json.loads(message)
            except json.JSONDecodeError:
                message_payload = {"raw": message}
        else:
            message_payload = message
        return sns_type, message_payload, payload.get("SubscribeURL")

    def _extract_s3_location(
        self, message_payload: dict[str, Any]
    ) -> tuple[str | None, str | None, str | None, list[str]]:
        bucket = None
        key = None
        message_id = None
        recipients: list[str] = []
        if "Records" in message_payload:
            records = message_payload.get("Records") or []
            if records:
                record = records[0]
                s3_info = record.get("s3", {})
                bucket = s3_info.get("bucket", {}).get("name")
                raw_key = s3_info.get("object", {}).get("key")
                key = unquote_plus(raw_key) if raw_key else None
        elif "mail" in message_payload and "receipt" in message_payload:
            mail = message_payload.get("mail") or {}
            receipt = message_payload.get("receipt") or {}
            action = receipt.get("action") or {}
            bucket = action.get("bucketName")
            raw_key = action.get("objectKey")
            key = unquote_plus(raw_key) if raw_key else None
            message_id = mail.get("messageId")
            recipients = mail.get("destination") or []
        return bucket, key, message_id, recipients

    def _fetch_raw_email(self, bucket: str, key: str) -> bytes:
        client = self._build_s3_client()
        response = client.get_object(Bucket=bucket, Key=key)
        return response["Body"].read()

    def _decode_part(self, part: Any) -> str:
        payload = part.get_payload(decode=True) or b""
        charset = part.get_content_charset() or "utf-8"
        try:
            return payload.decode(charset, errors="replace")
        except LookupError:
            return payload.decode("utf-8", errors="replace")

    def _parse_email(self, raw_bytes: bytes) -> ParsedEmail:
        message = BytesParser(policy=policy.default).parsebytes(raw_bytes)
        subject = message.get("Subject") or ""
        sender_name, sender_email = parseaddr(message.get("From") or "")
        recipients = [email for _, email in getaddresses(message.get_all("To", [])) if email]
        recipients += [email for _, email in getaddresses(message.get_all("Cc", [])) if email]
        text_parts: list[str] = []
        html_parts: list[str] = []
        attachments: list[EmailAttachment] = []
        for part in message.walk():
            if part.is_multipart():
                continue
            content_disposition = (part.get("Content-Disposition") or "").lower()
            filename = part.get_filename()
            if "attachment" in content_disposition or filename:
                if not filename:
                    filename = f"attachment-{uuid.uuid4().hex[:8]}"
                attachments.append(
                    EmailAttachment(
                        filename=filename,
                        content_type=part.get_content_type(),
                        content_bytes=part.get_payload(decode=True) or b"",
                    )
                )
                continue
            content_type = part.get_content_type()
            if content_type == "text/plain":
                text_parts.append(self._decode_part(part))
            elif content_type == "text/html":
                html_parts.append(self._decode_part(part))
        body_text = "\n\n".join([t.strip() for t in text_parts if t.strip()])
        body_html = "\n\n".join([h.strip() for h in html_parts if h.strip()])
        if not body_text and body_html:
            soup = BeautifulSoup(body_html, "html.parser")
            body_text = soup.get_text("\n").strip()
        return ParsedEmail(
            subject=subject,
            sender_email=sender_email or None,
            sender_name=sender_name or None,
            recipients=recipients,
            body_text=body_text,
            body_html=body_html,
            attachments=attachments,
        )

    async def process_inbound_email(self, db: Session, payload: dict[str, Any]) -> dict[str, Any]:
        sns_type, message_payload, subscribe_url = self._parse_sns_envelope(payload)
        if sns_type == "SubscriptionConfirmation" and subscribe_url:
            self._confirm_sns_subscription(subscribe_url)
            return {"status": "subscription_confirmed"}
        bucket, key, message_id, _recipients = self._extract_s3_location(message_payload)
        if not bucket or not key:
            return {"status": "ignored", "reason": "No S3 email payload"}
        inbound_email_allowed_bucket = config.runtime_configuration.inbound_email_allowed_bucket
        if inbound_email_allowed_bucket and bucket != inbound_email_allowed_bucket:
            structured_logger.warning(
                "Inbound email bucket mismatch",
                extra={"bucket": bucket, "allowed": inbound_email_allowed_bucket},
            )
            return {"status": "ignored", "reason": "Bucket not allowed"}
        if message_id:
            existing = db.query(InboundEmail).filter(InboundEmail.message_id == message_id).first()
            if existing:
                return {"status": "duplicate", "inbound_email_id": existing.id}
        raw_bytes = self._fetch_raw_email(bucket, key)
        parsed_email = self._parse_email(raw_bytes)
        inbound_record = InboundEmail(
            organization_id="",
            message_id=message_id,
            s3_bucket=bucket,
            s3_key=key,
            sender_email=parsed_email.sender_email,
            sender_name=parsed_email.sender_name,
            recipient_emails=parsed_email.recipients,
            subject=parsed_email.subject,
            body_text=parsed_email.body_text,
            body_html=parsed_email.body_html,
            status="received",
        )
        org = self._resolve_org_from_recipients(db, parsed_email.recipients)
        if not org:
            inbound_record.status = "failed"
            inbound_record.error_message = "Unable to resolve organization from recipients"
            db.add(inbound_record)
            db.commit()
            db.refresh(inbound_record)
            return {"status": "failed", "inbound_email_id": inbound_record.id}
        inbound_record.organization_id = org.id
        db.add(inbound_record)
        db.commit()
        db.refresh(inbound_record)
        return {"status": "processed", "inbound_email_id": inbound_record.id}

    def _resolve_org_from_recipients(
        self, db: Session, recipients: list[str]
    ) -> Organization | None:
        domain = config.runtime_configuration.inbound_email_domain.lower()
        for recipient in recipients:
            recipient = recipient.lower().strip()
            if not recipient or "@" not in recipient:
                continue
            local, recipient_domain = recipient.split("@", 1)
            if recipient_domain != domain or not local.startswith("intake-"):
                continue
            slug = local.replace("intake-", "", 1)
            if not slug:
                continue
            org = db.query(Organization).filter(Organization.slug == slug).first()
            if org:
                return org
        return None


mail_service = MailServiceManager(
    email_config_model_service=MailModelService(),
    config=config,
)
email_service = mail_service
inbound_email_service = mail_service


class ICSFallbackProvider:
    """Generates .ics files and sends via email when Google Calendar is not available."""

    def __init__(self, db: Session, org_id: str, organizer_email: str, organizer_name: str = ""):
        self.db = db
        self.org_id = org_id
        self.organizer_email = organizer_email
        self.organizer_name = organizer_name

    async def create_event(
        self, event: CalendarEvent, send_invites: bool = True
    ) -> CalendarEventResult:
        return await mail_service.create_ics_event(
            db=self.db,
            org_id=self.org_id,
            organizer_email=self.organizer_email,
            organizer_name=self.organizer_name,
            event=event,
            send_invites=send_invites,
        )

    async def update_event(
        self, event_id: str, event: CalendarEvent, send_updates: bool = True
    ) -> CalendarEventResult:
        return await self.create_event(event, send_updates)

    async def cancel_event(
        self, event_id: str, send_cancellation: bool = True
    ) -> CalendarEventResult:
        return CalendarEventResult(
            success=False,
            message="Event cancellation not supported for email-based invites. Please notify attendees manually.",
            method="ics_email",
        )

    async def check_availability(
        self,
        attendees: list[str],
        start_time: datetime,
        end_time: datetime,
    ) -> dict[str, list[FreeBusySlot]]:
        return {}
