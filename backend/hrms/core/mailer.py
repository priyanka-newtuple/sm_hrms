"""
Minimal SMTP transport using only the standard library (no new dependencies,
so the Docker image is unchanged). The blocking smtplib call runs in a worker
thread via asyncio.to_thread.

When EMAIL_ENABLED is false or SMTP_HOST is unset, messages are logged to the
backend console instead — the outbox row is still marked sent, so the whole
onboarding flow is exercisable in local dev without a mail server.
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
from email.message import EmailMessage

from hrms.config import get_settings

logger = logging.getLogger("hrms.mailer")
settings = get_settings()


def _send_sync(to: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"] = settings.EMAIL_FROM
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
        server.starttls()
        if settings.SMTP_USERNAME:
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        server.send_message(msg)


async def send_email(to: str, subject: str, body: str) -> None:
    """Raises on failure — the caller (outbox drain) records the error."""
    if not settings.EMAIL_ENABLED or not settings.SMTP_HOST:
        logger.info("EMAIL (dev log, not sent)\n  To: %s\n  Subject: %s\n%s", to, subject, body)
        # Also print for the docker-compose console where log config may be quiet.
        print(f"[email:dev] to={to!r} subject={subject!r}\n{body}\n", flush=True)
        return
    await asyncio.to_thread(_send_sync, to, subject, body)
