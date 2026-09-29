"""
Notification outbox: flow logic queues rows (transactionally, alongside the
state change that caused them); a background loop in app.main drains the queue
and actually sends. One generic "you have an onboarding action" template plus
a few event-specific ones — no step-specific email code anywhere else.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hrms.config import get_settings
from hrms.core.mailer import send_email
from hrms.models.enums import OutboxStatus
from hrms.models.notification import NotificationOutbox

logger = logging.getLogger("hrms.notifications")
settings = get_settings()

# template_key -> (subject template, body template). Formatted with **payload.
TEMPLATES: dict[str, tuple[str, str]] = {
    "allocation_overcapacity": (
        "Overallocation alert: {employee_name}",
        "{actor_name} confirmed overallocation for {employee_name}.\n\n"
        "Affected periods:\n{periods}\n\nReason: {reason}\n\n"
        "Committed allocations across projects:\n{breakdown}\n\nAllocation reference: {allocation_id}",
    ),
    "project_review": (
        "Project {status}: {project_name}",
        "Hi {recipient_name},\n\nProject '{project_name}' is {status}.\n\n"
        "Open the request in My Work:\n{link}\n\n— Newtuple HRMS",
    ),
    "task_ready": (
        "Onboarding action for {new_hire_name}: {task_title}",
        "Hi {assignee_name},\n\n"
        "An onboarding step for {new_hire_name} ({department}, joining {date_joined}) "
        "is now waiting on you:\n\n"
        "    {task_title}\n"
        "    Due: {due_date}\n\n"
        "Open your onboarding queue to act on it:\n"
        "    {link}\n\n"
        "— Newtuple HRMS",
    ),
    "invitation": (
        "Welcome to Newtuple — complete your onboarding",
        "Hi {new_hire_name},\n\n"
        "Welcome aboard! Your Newtuple HRMS account is ready.\n\n"
        "Sign in with your Google work account ({work_email}) and complete your "
        "onboarding — personal details, bank details for payroll, and document "
        "uploads (ID proof, PAN, education & experience certificates, signed "
        "offer letter):\n\n"
        "    {link}\n\n"
        "This invitation expires on {expires_at}.\n\n"
        "— Newtuple HRMS",
    ),
    "documents_submitted": (
        "Documents ready for verification: {new_hire_name}",
        "Hi {assignee_name},\n\n"
        "{new_hire_name} has uploaded their onboarding documents. Please review "
        "and verify them:\n\n"
        "    {link}\n\n"
        "— Newtuple HRMS",
    ),
    "document_rejected": (
        "Action needed: re-upload your {doc_type}",
        "Hi {new_hire_name},\n\n"
        "Your {doc_type} could not be verified:\n\n"
        "    {note}\n\n"
        "Please upload a corrected copy here:\n"
        "    {link}\n\n"
        "— Newtuple HRMS",
    ),
    "onboarding_complete": (
        "Onboarding complete: {new_hire_name}",
        "Hi {recipient_name},\n\n"
        "All onboarding steps for {new_hire_name} are complete. They're fully "
        "set up — accounts, payroll, documents, assets, and project allocation.\n\n"
        "    {link}\n\n"
        "— Newtuple HRMS",
    ),
}


def queue_email(
    db: AsyncSession,
    *,
    email_to: str,
    template_key: str,
    payload: dict,
    recipient_employee_id: uuid.UUID | None = None,
    related_task_id: uuid.UUID | None = None,
) -> None:
    """Adds an outbox row to the current transaction. Never sends inline."""
    subject_tpl, body_tpl = TEMPLATES[template_key]
    db.add(
        NotificationOutbox(
            recipient_employee_id=recipient_employee_id,
            email_to=email_to,
            template_key=template_key,
            subject=subject_tpl.format(**payload),
            body_text=body_tpl.format(**payload),
            payload=payload,
            related_task_id=related_task_id,
        )
    )


async def drain_outbox(db: AsyncSession, *, limit: int = 50) -> int:
    """Sends queued emails; marks each row sent/failed. Returns count attempted."""
    result = await db.execute(
        select(NotificationOutbox)
        .where(NotificationOutbox.status == OutboxStatus.QUEUED)
        .order_by(NotificationOutbox.created_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    rows = list(result.scalars().all())
    for row in rows:
        try:
            await send_email(row.email_to, row.subject, row.body_text)
            row.status = OutboxStatus.SENT
            row.sent_at = datetime.now(UTC)
            row.error = None
        except Exception as exc:  # noqa: BLE001 — record and move on; retried next drain
            logger.warning("Email to %s failed: %s", row.email_to, exc)
            row.status = OutboxStatus.FAILED
            row.error = str(exc)[:2000]
    await db.commit()
    return len(rows)


async def retry_failed(db: AsyncSession) -> None:
    """Re-queue failed sends (called by the periodic loop, cheap idempotent)."""
    result = await db.execute(select(NotificationOutbox).where(NotificationOutbox.status == OutboxStatus.FAILED).limit(50))
    for row in result.scalars().all():
        row.status = OutboxStatus.QUEUED
    await db.commit()
