"""AWS SES email provider strategy.

Resolves SES credentials from `organization_integrations`, validates raw
credentials against the SES API, and delivers messages via boto3.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

from common.logger import logger
from mail.models.response import EmailSendResult
from mail.services.base import EmailMessage, EmailServiceBase, load_org_integration

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@dataclass
class SesCreds:
    """Resolved AWS SES credentials for an organization."""

    access_key_id: str
    secret_key: str
    region: str
    from_email: str
    from_name: str | None
    reply_to: str | None


class SesEmailService(EmailServiceBase):
    """Email delivery via AWS SES."""

    name = "ses"

    def resolve_credentials(self, db: Session | None, org_id: str) -> SesCreds | None:
        loaded = load_org_integration(db, org_id, "ses")
        if loaded is None:
            return None
        config, secrets = loaded
        return self.credentials_from_payload(config, secrets)

    def credentials_from_payload(self, config: dict, secrets: dict) -> SesCreds | None:
        region = config.get("region") or ""
        from_email = config.get("from_email") or ""
        if not region or not from_email:
            return None
        from_name = config.get("from_name") or None
        reply_to = config.get("reply_to_email") or None
        access_key_id = secrets.get("aws_access_key_id") or ""
        secret_key = secrets.get("aws_secret_access_key") or ""
        if not access_key_id or not secret_key:
            return None
        return SesCreds(
            access_key_id=access_key_id,
            secret_key=secret_key,
            region=region,
            from_email=from_email,
            from_name=from_name,
            reply_to=reply_to,
        )

    def validate(self, **params) -> tuple[bool, str]:
        access_key_id = params.get("access_key_id")
        secret_access_key = params.get("secret_access_key")
        region = params.get("region")
        from_email = params.get("from_email")
        if not region:
            return False, "Region is required for SES"
        try:
            client = boto3.client(
                "ses",
                aws_access_key_id=access_key_id,
                aws_secret_access_key=secret_access_key,
                region_name=region,
            )

            quota = client.get_send_quota()
            max_send_rate = quota.get("MaxSendRate", 0)
            if max_send_rate <= 0:
                return False, "SES account has no sending quota - check account status"

            try:
                identities = client.list_verified_email_addresses()
                verified = identities.get("VerifiedEmailAddresses", [])
                if from_email not in verified:
                    domain = from_email.split("@")[1]
                    domain_identities = client.list_identities(IdentityType="Domain")
                    domains = domain_identities.get("Identities", [])
                    if domain not in domains:
                        logger.warning(
                            "Email %s not verified in SES - emails may fail until verified",
                            from_email,
                        )
            except ClientError as exc:
                logger.warning("Could not verify email identity: %s", exc)

            logger.info("SES credentials validated successfully")
            return True, ""
        except NoCredentialsError:
            return False, "Invalid credentials - access key or secret key is missing"
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            error_msg = exc.response.get("Error", {}).get("Message", str(exc))
            if error_code in ("InvalidClientTokenId", "SignatureDoesNotMatch"):
                return False, "Invalid credentials - check access key and secret"
            if error_code == "AccessDenied":
                return False, "Access denied - IAM user needs SES permissions"
            if error_code == "InvalidParameterValue":
                return False, f"Invalid parameter: {error_msg}"
            logger.warning("SES validation failed: %s - %s", error_code, error_msg)
            return False, error_msg
        except Exception as exc:
            logger.warning("SES validation failed: %s", exc)
            return False, str(exc)

    def send(self, creds: SesCreds, message: EmailMessage) -> EmailSendResult:
        recipients = message.recipients
        subject = message.subject
        try:
            client = boto3.client(
                "ses",
                aws_access_key_id=creds.access_key_id,
                aws_secret_access_key=creds.secret_key,
                region_name=creds.region,
            )
            body = {"Html": {"Charset": "UTF-8", "Data": message.body_html}}
            if message.body_text:
                body["Text"] = {"Charset": "UTF-8", "Data": message.body_text}
            kwargs = {
                "Source": message.sender,
                "Destination": {"ToAddresses": recipients},
                "Message": {
                    "Subject": {"Charset": "UTF-8", "Data": subject},
                    "Body": body,
                },
            }
            if message.reply_to:
                kwargs["ReplyToAddresses"] = [message.reply_to]
            response = client.send_email(**kwargs)
            message_id = response.get("MessageId")
            logger.info(
                "Email sent successfully via SES",
                extra={"message_id": message_id, "recipients": recipients, "subject": subject[:50]},
            )
            return EmailSendResult(
                success=True, message="Email sent successfully", message_id=message_id
            )
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            error_msg = exc.response.get("Error", {}).get("Message", str(exc))
            logger.error(
                "Failed to send email via SES: %s - %s",
                error_code,
                error_msg,
                extra={"recipients": recipients, "subject": subject[:50]},
            )
            if error_code == "MessageRejected":
                if "not verified" in error_msg.lower():
                    return EmailSendResult(
                        success=False,
                        message="Sender email is not verified in AWS SES. Please verify your email identity.",
                    )
                return EmailSendResult(success=False, message=f"Email rejected: {error_msg}")
            if error_code == "Throttling":
                return EmailSendResult(
                    success=False,
                    message="Email sending rate exceeded. Please try again later.",
                )
            if error_code == "InvalidParameterValue":
                return EmailSendResult(
                    success=False, message=f"Invalid email parameter: {error_msg}"
                )
            return EmailSendResult(success=False, message=error_msg)
        except Exception as exc:
            logger.exception("Unexpected error sending email: %s", exc)
            return EmailSendResult(success=False, message=f"Failed to send email: {exc!s}")


ses_service = SesEmailService()
