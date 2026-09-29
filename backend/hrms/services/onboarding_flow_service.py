"""
Template-driven onboarding flow engine.

One rule drives all handoffs: whenever a task reaches a terminal state, every
PENDING task whose dependencies are now satisfied flips to READY, and its
assignee gets an email (queued transactionally via the notifications outbox).

Steps whose action_type maps to a real module (assets, allocations, profile,
documents) are auto-completed by those modules calling `auto_complete()` /
the document hooks — onboarding never duplicates their state, it links to it.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import set_committed_value

from hrms.config import get_settings
from hrms.core.exceptions import Conflict, ValidationFailed
from hrms.models.document import EmployeeDocument
from hrms.models.employee import Employee
from hrms.models.enums import (
    REQUIRED_DOCUMENT_TYPES,
    TERMINAL_TASK_STATUSES,
    DocumentStatus,
    EmploymentStatus,
    InvitationStatus,
    OnboardingStatus,
    OnboardingType,
    TaskActionType,
    TaskStatus,
)
from hrms.models.invitation import EmployeeInvitation
from hrms.models.onboarding import OnboardingRecord, OnboardingTask
from hrms.models.onboarding_template import OnboardingTemplate
from hrms.models.role import Role
from hrms.services import notification_service

settings = get_settings()

# Fallback chain when a step's assignee role has no active employee.
_ROLE_FALLBACKS = ["HR - Full", "Super Admin"]

DEFAULT_TEMPLATE_NAME = "Default onboarding"

# seq, step_key, title, description, assignee_rule, assignee_role, action_type, due_days, depends
# (The migration inserts the same template for existing databases; this copy is
# used by ensure_default_template() for freshly-seeded ones.)
DEFAULT_TEMPLATE_STEPS: list[tuple] = [
    (
        1,
        "newtuple_id",
        "Create Newtuple ID (Google Workspace account)",
        "Create the Google Workspace account and confirm the work email is active.",
        "ROLE",
        "Office Admin",
        TaskActionType.MANUAL,
        2,
        None,
    ),
    (
        2,
        "razorpay_account",
        "Create Razorpay payroll account",
        "Create the payroll contact in Razorpay and record the reference ID on this step.",
        "ROLE",
        "Finance",
        TaskActionType.MANUAL,
        3,
        None,
    ),
    (
        3,
        "hrms_invitation",
        "Invite employee to HRMS",
        "System sends the HRMS invitation email automatically once the Newtuple ID exists.",
        "ROLE",
        "HR - Full",
        TaskActionType.INVITE_EMPLOYEE,
        3,
        [1],
    ),
    (
        4,
        "employee_profile",
        "Employee fills personal & bank details",
        "The new hire completes the self-service wizard: personal info and payroll bank account.",
        "NEW_HIRE",
        None,
        TaskActionType.EMPLOYEE_PROFILE,
        6,
        [3],
    ),
    (
        5,
        "documents",
        "Upload documents & experience certificates",
        "ID proof, PAN, education certificates, experience certificates and signed offer "
        "letter — uploaded by the employee, verified by HR.",
        "NEW_HIRE",
        None,
        TaskActionType.DOCUMENT_COLLECTION,
        8,
        [3],
    ),
    (
        6,
        "asset_allocation",
        "Allocate laptop and access badge",
        "Assign assets in the Assets module; the step completes automatically.",
        "ROLE",
        "Office Admin",
        TaskActionType.ASSET_ASSIGNMENT,
        8,
        [1],
    ),
    (
        7,
        "hr_orientation",
        "HR orientation session",
        "Run the orientation session and mark this step done with the date in the note.",
        "ROLE",
        "HR - Basic",
        TaskActionType.MANUAL,
        10,
        [4],
    ),
    (
        8,
        "pm_allocation",
        "Allocate to project & project manager",
        "Create the allocation in the Allocations module; the step completes automatically.",
        "ROLE",
        "Delivery Manager",
        TaskActionType.PROJECT_ALLOCATION,
        12,
        [4],
    ),
]


async def ensure_default_template(db: AsyncSession) -> OnboardingTemplate:
    """Creates the default onboarding template if missing (used by seed_data;
    migrations handle already-deployed databases)."""
    from hrms.models.enums import AssigneeRule
    from hrms.models.onboarding_template import OnboardingTemplateStep

    existing = await get_default_template(db, OnboardingType.ONBOARDING)
    if existing is not None:
        return existing
    template = OnboardingTemplate(
        name=DEFAULT_TEMPLATE_NAME,
        workflow_type=OnboardingType.ONBOARDING,
        is_default=True,
        active=True,
    )
    db.add(template)
    await db.flush()
    for seq, key, title, desc, rule, role, action, due, deps in DEFAULT_TEMPLATE_STEPS:
        db.add(
            OnboardingTemplateStep(
                template_id=template.id,
                seq=seq,
                step_key=key,
                title=title,
                description=desc,
                assignee_rule=AssigneeRule(rule.lower()),
                assignee_role=role,
                action_type=action,
                due_days=due,
                depends_on_seqs=deps,
            )
        )
    await db.flush()
    return await get_default_template(db, OnboardingType.ONBOARDING)


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


async def _first_active_with_role(db: AsyncSession, role_name: str) -> Employee | None:
    result = await db.execute(
        select(Employee)
        .join(Role, Employee.role_id == Role.id)
        .where(Role.name == role_name, Employee.employment_status == EmploymentStatus.ACTIVE)
        .order_by(Employee.employee_code)
        .limit(1)
    )
    return result.scalar_one_or_none()


async def resolve_assignee(db: AsyncSession, *, rule, role_name: str | None, new_hire: Employee) -> Employee | None:
    from hrms.models.enums import AssigneeRule

    if rule == AssigneeRule.NEW_HIRE:
        return new_hire
    if rule == AssigneeRule.REPORTING_MANAGER and new_hire.reports_to_id:
        return await db.get(Employee, new_hire.reports_to_id)
    candidates = ([role_name] if role_name else []) + _ROLE_FALLBACKS
    for name in candidates:
        found = await _first_active_with_role(db, name)
        if found is not None and found.id != new_hire.id:
            return found
    return None


async def get_default_template(db: AsyncSession, workflow_type: OnboardingType) -> OnboardingTemplate | None:
    result = await db.execute(
        select(OnboardingTemplate)
        .options(selectinload(OnboardingTemplate.steps))
        .where(
            OnboardingTemplate.workflow_type == workflow_type,
            OnboardingTemplate.is_default.is_(True),
            OnboardingTemplate.active.is_(True),
        )
        .limit(1)
    )
    return result.scalar_one_or_none()


async def stamp_template(db: AsyncSession, record: OnboardingRecord, new_hire: Employee) -> bool:
    """
    Creates concrete tasks from the default template. Returns False when no
    template exists (caller falls back to the legacy static checklist).
    Emails for immediately-READY steps are queued here too.
    """
    template = await get_default_template(db, record.workflow_type)
    if template is None or not template.steps:
        return False

    record.status = OnboardingStatus.IN_PROGRESS
    record.started_at = record.started_at or datetime.now(UTC)
    start_date = record.started_at.date()

    tasks: list[OnboardingTask] = []
    for step in template.steps:
        assignee = await resolve_assignee(db, rule=step.assignee_rule, role_name=step.assignee_role, new_hire=new_hire)
        deps = list(step.depends_on_seqs or [])
        task = OnboardingTask(
            onboarding_record_id=record.id,
            template_step_id=step.id,
            seq=step.seq,
            step_key=step.step_key,
            title=step.title,
            description=step.description,
            status=TaskStatus.PENDING if deps else TaskStatus.READY,
            action_type=step.action_type,
            assignee_employee_id=assignee.id if assignee else None,
            assignee_role=step.assignee_role,
            depends_on_seqs=deps or None,
            due_date=start_date + timedelta(days=step.due_days) if step.due_days else None,
        )
        db.add(task)
        tasks.append(task)
    await db.flush()
    # Populate the relationship without a lazy SELECT (illegal in async).
    set_committed_value(record, "tasks", tasks)
    for task in tasks:
        if task.status == TaskStatus.READY:
            await _on_task_ready(db, record, task, new_hire)
    return True


def _frontend_link(record: OnboardingRecord, *, for_new_hire: bool) -> str:
    if for_new_hire:
        return f"{settings.FRONTEND_URL}/welcome"
    return f"{settings.FRONTEND_URL}/onboarding/{record.id}"


async def _on_task_ready(
    db: AsyncSession,
    record: OnboardingRecord,
    task: OnboardingTask,
    new_hire: Employee,
) -> None:
    """Emails the assignee; system-executed steps (invitation) run and complete."""
    if task.action_type == TaskActionType.INVITE_EMPLOYEE:
        await _execute_invitation(db, record, task, new_hire)
        return

    assignee = await db.get(Employee, task.assignee_employee_id) if task.assignee_employee_id else None
    if assignee is None:
        return
    is_new_hire = assignee.id == new_hire.id
    email_to = (new_hire.personal_email or new_hire.work_email) if is_new_hire else assignee.work_email
    notification_service.queue_email(
        db,
        email_to=email_to,
        template_key="task_ready",
        payload={
            "assignee_name": assignee.first_name,
            "new_hire_name": new_hire.full_name,
            "department": new_hire.department,
            "date_joined": str(new_hire.date_joined),
            "task_title": task.title,
            "due_date": str(task.due_date) if task.due_date else "—",
            "link": f"{settings.FRONTEND_URL}/my-work/tasks/{task.id}",
        },
        recipient_employee_id=assignee.id,
        related_task_id=task.id,
    )


async def _execute_invitation(
    db: AsyncSession,
    record: OnboardingRecord,
    task: OnboardingTask,
    new_hire: Employee,
) -> None:
    """System step: create the invitation, email the new hire, mark task done."""
    raw_token = secrets.token_urlsafe(32)
    invitation = EmployeeInvitation(
        employee_id=new_hire.id,
        email=new_hire.personal_email or new_hire.work_email,
        token_hash=_hash_token(raw_token),
        expires_at=datetime.now(UTC) + timedelta(days=settings.INVITATION_EXPIRE_DAYS),
    )
    db.add(invitation)
    await db.flush()

    notification_service.queue_email(
        db,
        email_to=invitation.email,
        template_key="invitation",
        payload={
            "new_hire_name": new_hire.first_name,
            "work_email": new_hire.work_email,
            "link": f"{settings.FRONTEND_URL}/welcome?token={raw_token}",
            "expires_at": str(invitation.expires_at.date()),
        },
        recipient_employee_id=new_hire.id,
        related_task_id=task.id,
    )

    _mark_done(task, completed_by_id=None, note="Invitation sent automatically")
    task.linked_entity_type = "employee_invitation"
    task.linked_entity_id = invitation.id
    await advance(db, record)


def _mark_done(task: OnboardingTask, *, completed_by_id: uuid.UUID | None, note: str | None = None) -> None:
    task.status = TaskStatus.DONE
    task.is_complete = True
    task.completed_at = datetime.now(UTC)
    task.completed_by_id = completed_by_id
    if note:
        task.completion_note = note


async def advance(db: AsyncSession, record: OnboardingRecord) -> None:
    """
    The handoff rule. Flips PENDING tasks whose dependencies are all terminal
    to READY (queueing their emails), and completes the record when every task
    is terminal. Idempotent; call after any task state change. Does not commit.
    """
    done_seqs = {t.seq for t in record.tasks if t.status in TERMINAL_TASK_STATUSES}

    new_hire = await db.get(Employee, record.employee_id)
    # Invitation execution inside _on_task_ready can recurse back here; loop
    # until stable instead.
    changed = True
    while changed:
        changed = False
        for task in record.tasks:
            if task.status != TaskStatus.PENDING:
                continue
            if all(dep in done_seqs for dep in (task.depends_on_seqs or [])):
                task.status = TaskStatus.READY
                changed = True
                if task.action_type == TaskActionType.INVITE_EMPLOYEE:
                    # Executes + completes + recurses; refresh terminal set after.
                    await _execute_invitation(db, record, task, new_hire)
                    return
                await _on_task_ready(db, record, task, new_hire)

    if record.status != OnboardingStatus.COMPLETED and all(t.status in TERMINAL_TASK_STATUSES for t in record.tasks):
        record.status = OnboardingStatus.COMPLETED
        record.completed_at = datetime.now(UTC)
        await _notify_completion(db, record, new_hire)


async def _notify_completion(db: AsyncSession, record: OnboardingRecord, new_hire: Employee) -> None:
    recipients: list[Employee] = []
    hr = await _first_active_with_role(db, "HR - Full")
    if hr:
        recipients.append(hr)
    if new_hire.reports_to_id:
        manager = await db.get(Employee, new_hire.reports_to_id)
        if manager and all(manager.id != r.id for r in recipients):
            recipients.append(manager)
    for recipient in recipients:
        from hrms.authz.engine import AuthzEngine
        from hrms.authz.enums import Action, FeatureKey

        can_manage = await AuthzEngine(db).has_permission(recipient, FeatureKey.EMPLOYEE_ONBOARDING, Action.MANAGE)
        notification_service.queue_email(
            db,
            email_to=recipient.work_email,
            template_key="onboarding_complete",
            payload={
                "recipient_name": recipient.first_name,
                "new_hire_name": new_hire.full_name,
                "link": _frontend_link(record, for_new_hire=False) if can_manage else f"{settings.FRONTEND_URL}/my-work",
            },
            recipient_employee_id=recipient.id,
        )


async def complete_task(
    db: AsyncSession,
    record: OnboardingRecord,
    task: OnboardingTask,
    *,
    actor: Employee,
    note: str | None = None,
    payroll_reference: str | None = None,
) -> None:
    """Manual completion by the assignee / HR. Does not commit."""
    if task.status != TaskStatus.READY:
        raise Conflict("This task is no longer actionable. Refresh My Work.")
    if task.action_type != TaskActionType.MANUAL:
        raise ValidationFailed("Complete the required action; this task cannot be marked done manually.")
    if payroll_reference and task.step_key != "razorpay_account":
        raise ValidationFailed("A payroll reference can only be supplied for payroll setup.")
    if task.step_key == "razorpay_account" and not (payroll_reference and payroll_reference.strip()):
        raise ValidationFailed("Enter the payroll reference to complete payroll setup.")
    _mark_done(task, completed_by_id=actor.id, note=note)

    # Razorpay step: the payroll reference lands on the employee record itself,
    # where Finance and future payroll views read it.
    if payroll_reference:
        employee = await db.get(Employee, record.employee_id)
        employee.payroll_reference = payroll_reference

    await advance(db, record)


async def skip_task(
    db: AsyncSession,
    record: OnboardingRecord,
    task: OnboardingTask,
    *,
    actor: Employee,
    note: str | None = None,
) -> None:
    if task.status in TERMINAL_TASK_STATUSES:
        raise Conflict("This task is already complete. Refresh the workflow.")
    task.status = TaskStatus.SKIPPED
    task.is_complete = True
    task.completed_at = datetime.now(UTC)
    task.completed_by_id = actor.id
    task.completion_note = note or "Skipped"
    await advance(db, record)


async def _open_onboarding_record(db: AsyncSession, employee_id: uuid.UUID) -> OnboardingRecord | None:
    result = await db.execute(
        select(OnboardingRecord)
        .options(selectinload(OnboardingRecord.tasks), selectinload(OnboardingRecord.employee))
        .where(
            OnboardingRecord.employee_id == employee_id,
            OnboardingRecord.workflow_type == OnboardingType.ONBOARDING,
            OnboardingRecord.status != OnboardingStatus.COMPLETED,
        )
        .order_by(OnboardingRecord.created_at.desc())
        .limit(1)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def auto_complete(
    db: AsyncSession,
    *,
    employee_id: uuid.UUID,
    action_type: TaskActionType,
    actor: Employee | None,
    entity_type: str,
    entity_id: uuid.UUID,
) -> None:
    """
    Called by other modules (assets, allocations, wizard) when a real record is
    created: closes the matching onboarding step and links the record. A no-op
    when the employee has no open onboarding or no such step — so the modules
    behave exactly as before outside onboarding. Does not commit.
    """
    record = await _open_onboarding_record(db, employee_id)
    if record is None:
        return
    task = next(
        (t for t in record.tasks if t.action_type == action_type and t.status == TaskStatus.READY),
        None,
    )
    if task is None:
        return
    _mark_done(task, completed_by_id=actor.id if actor else None)
    task.linked_entity_type = entity_type
    task.linked_entity_id = entity_id
    await advance(db, record)


# ------------------------------------------------------------------ documents


async def documents_for_employee(db: AsyncSession, employee_id: uuid.UUID) -> list[EmployeeDocument]:
    result = await db.execute(
        select(EmployeeDocument).where(EmployeeDocument.employee_id == employee_id).order_by(EmployeeDocument.created_at)
    )
    return list(result.scalars().all())


def _required_docs_all(docs: list[EmployeeDocument], status: DocumentStatus) -> bool:
    by_type: dict = {}
    for doc in docs:
        # Latest upload per type wins (re-uploads supersede rejected ones).
        current = by_type.get(doc.doc_type)
        if current is None or doc.created_at >= current.created_at:
            by_type[doc.doc_type] = doc
    return all(
        by_type.get(t) is not None
        and (by_type[t].status == status or (status == DocumentStatus.SUBMITTED and by_type[t].status == DocumentStatus.VERIFIED))
        for t in REQUIRED_DOCUMENT_TYPES
    )


async def on_document_uploaded(db: AsyncSession, employee: Employee) -> None:
    """When all required docs are in, nudge HR to verify. Does not commit."""
    record = await _open_onboarding_record(db, employee.id)
    if record is None:
        return
    docs = await documents_for_employee(db, employee.id)
    if not _required_docs_all(docs, DocumentStatus.SUBMITTED):
        return
    hr = await _first_active_with_role(db, "HR - Full")
    if hr is None:
        return
    notification_service.queue_email(
        db,
        email_to=hr.work_email,
        template_key="documents_submitted",
        payload={
            "assignee_name": hr.first_name,
            "new_hire_name": employee.full_name,
            "link": _frontend_link(record, for_new_hire=False),
        },
        recipient_employee_id=hr.id,
    )


async def on_document_reviewed(db: AsyncSession, employee: Employee, document: EmployeeDocument, actor: Employee) -> None:
    """
    Rejection → email the new hire to re-upload. All required docs verified →
    auto-complete the document-collection step. Does not commit.
    """
    record = await _open_onboarding_record(db, employee.id)
    if document.status == DocumentStatus.REJECTED:
        link = f"{settings.FRONTEND_URL}/welcome"
        notification_service.queue_email(
            db,
            email_to=employee.personal_email or employee.work_email,
            template_key="document_rejected",
            payload={
                "new_hire_name": employee.first_name,
                "doc_type": document.doc_type.value.replace("_", " "),
                "note": document.note or "No reason given.",
                "link": link,
            },
            recipient_employee_id=employee.id,
        )
        return

    if record is None:
        return
    docs = await documents_for_employee(db, employee.id)
    if _required_docs_all(docs, DocumentStatus.VERIFIED):
        await auto_complete(
            db,
            employee_id=employee.id,
            action_type=TaskActionType.DOCUMENT_COLLECTION,
            actor=actor,
            entity_type="employee_document",
            entity_id=document.id,
        )


# ------------------------------------------------------------------ invitations


async def accept_invitation(db: AsyncSession, employee: Employee, raw_token: str) -> bool:
    """Marks the invitation accepted on first wizard visit. Does not commit."""
    result = await db.execute(
        select(EmployeeInvitation).where(
            EmployeeInvitation.token_hash == _hash_token(raw_token),
            EmployeeInvitation.employee_id == employee.id,
        )
    )
    invitation = result.scalar_one_or_none()
    if invitation is None or invitation.status == InvitationStatus.EXPIRED:
        return False
    if invitation.status == InvitationStatus.PENDING:
        if invitation.expires_at <= datetime.now(UTC):
            invitation.status = InvitationStatus.EXPIRED
            return False
        invitation.status = InvitationStatus.ACCEPTED
        invitation.accepted_at = datetime.now(UTC)
    return True
