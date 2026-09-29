from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from hrms.authz.engine import AuthzEngine
from hrms.authz.enums import Action, FeatureKey
from hrms.authz.scope_filters import apply_onboarding_scope
from hrms.core.audit import record_audit
from hrms.core.exceptions import Conflict, NotFound, PermissionDenied
from hrms.models.document import EmployeeDocument
from hrms.models.employee import Employee
from hrms.models.enums import (
    TERMINAL_TASK_STATUSES,
    InvitationStatus,
    OnboardingStatus,
    OnboardingType,
    TaskActionType,
    TaskStatus,
)
from hrms.models.invitation import EmployeeInvitation
from hrms.models.onboarding import OnboardingRecord, OnboardingTask
from hrms.repositories import onboarding_repo
from hrms.schemas.onboarding import (
    EmployeeDocumentOut,
    InvitationOut,
    MyActionOut,
    OnboardingDetailOut,
    OnboardingEmployeeOut,
    OnboardingRecordOut,
    OnboardingStart,
    OnboardingTaskOut,
    TaskCompleteIn,
    TaskSkipIn,
    WizardProfileIn,
)
from hrms.services import onboarding_flow_service
from hrms.workflows.base import WorkflowProvider
from hrms.workflows.flowtuple import get_workflow_provider

FEATURE_BY_TYPE = {
    OnboardingType.ONBOARDING: FeatureKey.EMPLOYEE_ONBOARDING,
    OnboardingType.OFFBOARDING: FeatureKey.EMPLOYEE_OFFBOARDING,
}


# ------------------------------------------------------------- serialization


def _task_out(task: OnboardingTask) -> OnboardingTaskOut:
    out = OnboardingTaskOut.model_validate(task)
    if task.assignee is not None:
        out.assignee_name = task.assignee.full_name
    if task.completed_by is not None:
        out.completed_by_name = task.completed_by.full_name
    return out


def _employee_out(employee: Employee) -> OnboardingEmployeeOut:
    return OnboardingEmployeeOut(
        id=employee.id,
        full_name=employee.full_name,
        department=employee.department,
        designation=employee.designation,
        work_email=employee.work_email,
        date_joined=employee.date_joined,
    )


def _record_out(
    record: OnboardingRecord, provider: WorkflowProvider, *, detail: bool = False
) -> OnboardingRecordOut | OnboardingDetailOut:
    cls = OnboardingDetailOut if detail else OnboardingRecordOut
    out = cls.model_validate(record)
    out.embed_url = provider.embed_url(record)
    out.tasks = [_task_out(t) for t in record.tasks]
    if record.employee is not None:
        out.employee = _employee_out(record.employee)
    out.progress_total = len(record.tasks)
    out.progress_done = sum(1 for t in record.tasks if t.status in TERMINAL_TASK_STATUSES)
    current = next((t for t in record.tasks if t.status == TaskStatus.READY), None)
    if current is not None:
        out.current_task_title = current.title
        out.current_assignee_name = current.assignee.full_name if current.assignee else (current.assignee_role or None)
        out.current_due_date = current.due_date
    return out


def _serialize(record: OnboardingRecord, provider: WorkflowProvider) -> dict:
    return _record_out(record, provider).model_dump(mode="json")


# --------------------------------------------------------------------- lists


async def list_onboarding(
    db: AsyncSession,
    engine: AuthzEngine,
    current_employee: Employee,
    workflow_type: OnboardingType,
    *,
    offset: int,
    limit: int,
):
    feature = FEATURE_BY_TYPE[workflow_type]
    scope = await engine.get_scope(current_employee, feature)
    stmt = apply_onboarding_scope(onboarding_repo.base_query(), scope, current_employee).where(
        OnboardingRecord.workflow_type == workflow_type
    )
    records, total = await onboarding_repo.list_paginated(db, stmt, offset=offset, limit=limit)
    provider = get_workflow_provider()
    items = [_serialize(r, provider) for r in records]
    return items, total


# --------------------------------------------------------------------- start


async def start_onboarding(db: AsyncSession, actor: Employee, payload: OnboardingStart) -> dict:
    employee = await db.get(Employee, payload.employee_id)
    if employee is None:
        raise NotFound("Employee not found")

    existing = await db.execute(
        select(OnboardingRecord).where(
            OnboardingRecord.employee_id == payload.employee_id,
            OnboardingRecord.workflow_type == payload.workflow_type,
            OnboardingRecord.status != OnboardingStatus.COMPLETED,
        )
    )
    if existing.scalars().first() is not None:
        raise Conflict(f"{employee.full_name} already has an open {payload.workflow_type.value} workflow.")

    record = OnboardingRecord(employee_id=payload.employee_id, workflow_type=payload.workflow_type)
    db.add(record)
    await db.flush()

    await start_workflow(db, record, employee)

    await record_audit(
        db,
        actor_id=actor.user_id,
        action="start",
        entity_type="onboarding_record",
        entity_id=str(record.id),
    )
    await db.commit()
    saved = await onboarding_repo.get(db, record.id)
    return _serialize(saved, get_workflow_provider())


async def start_workflow(db: AsyncSession, record: OnboardingRecord, employee: Employee) -> None:
    """
    Template-driven flow for onboarding (assignees, dependencies, emails);
    falls back to the legacy provider checklist when no template exists or
    Flowtuple is enabled. Shared by the API route and employee creation.
    """
    from hrms.workflows.native import NativeWorkflowProvider

    provider = get_workflow_provider()
    use_template = record.workflow_type == OnboardingType.ONBOARDING and isinstance(provider, NativeWorkflowProvider)
    if use_template and await onboarding_flow_service.stamp_template(db, record, employee):
        return
    await provider.start(record, record.workflow_type)


# --------------------------------------------------------------- task actions


async def _load_record_and_task(
    db: AsyncSession, record_id: uuid.UUID, task_id: uuid.UUID
) -> tuple[OnboardingRecord, OnboardingTask]:
    # Serialize transitions for a workflow, including dependency handoffs.
    await db.execute(select(OnboardingRecord.id).where(OnboardingRecord.id == record_id).with_for_update())
    record = await onboarding_repo.get(db, record_id)
    if record is None:
        raise NotFound("Onboarding record not found")
    task = next((t for t in record.tasks if t.id == task_id), None)
    if task is None:
        raise NotFound("Task not found")
    return record, task


async def _assert_can_act(engine: AuthzEngine, actor: Employee, record: OnboardingRecord, task: OnboardingTask) -> None:
    feature = FEATURE_BY_TYPE[record.workflow_type]
    if task.assignee_employee_id == actor.id:
        return
    if await engine.has_permission(actor, feature, Action.MANAGE):
        await assert_can_manage_record(db=engine.db, engine=engine, actor=actor, record=record)
        return
    raise PermissionDenied("Only the step's assignee or a role that manages onboarding can update this step.")


async def assert_can_manage_record(db, engine, actor, record):
    feature = FEATURE_BY_TYPE[record.workflow_type]
    if not await engine.has_permission(actor, feature, Action.MANAGE):
        raise PermissionDenied("Workflow management is restricted to process owners. Use My Work for assigned tasks.")
    scope = await engine.get_scope(actor, feature)
    result = await db.execute(
        apply_onboarding_scope(select(OnboardingRecord.id).where(OnboardingRecord.id == record.id), scope, actor)
    )
    if result.scalar_one_or_none() is None:
        raise PermissionDenied("This workflow is outside your scope.")


async def complete_task(
    db: AsyncSession,
    engine: AuthzEngine,
    actor: Employee,
    record_id: uuid.UUID,
    task_id: uuid.UUID,
    payload: TaskCompleteIn | None = None,
) -> dict:
    record, task = await _load_record_and_task(db, record_id, task_id)
    await _assert_can_act(engine, actor, record, task)
    payload = payload or TaskCompleteIn()

    await onboarding_flow_service.complete_task(
        db,
        record,
        task,
        actor=actor,
        note=payload.note,
        payroll_reference=payload.payroll_reference,
    )
    await record_audit(
        db,
        actor_id=actor.user_id,
        action="complete_task",
        entity_type="onboarding_task",
        entity_id=str(task.id),
        diff={"title": task.title, "note": payload.note},
    )
    await db.commit()
    saved = await onboarding_repo.get(db, record_id)
    return _task_out(next(t for t in saved.tasks if t.id == task_id)).model_dump(mode="json")


async def skip_task(
    db: AsyncSession,
    engine: AuthzEngine,
    actor: Employee,
    record_id: uuid.UUID,
    task_id: uuid.UUID,
    payload: TaskSkipIn | None = None,
) -> dict:
    record, task = await _load_record_and_task(db, record_id, task_id)
    # Skipping is a process decision — assignees can't skip their own work.
    await assert_can_manage_record(db, engine, actor, record)
    if not payload or not payload.note or not payload.note.strip():
        from hrms.core.exceptions import ValidationFailed

        raise ValidationFailed("A reason is required to skip a step.")

    await onboarding_flow_service.skip_task(db, record, task, actor=actor, note=(payload.note if payload else None))
    await record_audit(
        db,
        actor_id=actor.user_id,
        action="skip_task",
        entity_type="onboarding_task",
        entity_id=str(task.id),
        diff={"title": task.title, "note": payload.note if payload else None},
    )
    await db.commit()
    saved = await onboarding_repo.get(db, record_id)
    return _serialize(saved, get_workflow_provider())


# --------------------------------------------------------------------- detail


async def _latest_invitation(db: AsyncSession, employee_id: uuid.UUID) -> EmployeeInvitation | None:
    result = await db.execute(
        select(EmployeeInvitation)
        .where(EmployeeInvitation.employee_id == employee_id)
        .order_by(EmployeeInvitation.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _documents_out(db: AsyncSession, employee_id: uuid.UUID) -> list[EmployeeDocumentOut]:
    result = await db.execute(
        select(EmployeeDocument)
        .options(selectinload(EmployeeDocument.verified_by))
        .where(EmployeeDocument.employee_id == employee_id)
        .order_by(EmployeeDocument.created_at)
    )
    out = []
    for doc in result.scalars().all():
        item = EmployeeDocumentOut.model_validate(doc)
        if doc.verified_by is not None:
            item.verified_by_name = doc.verified_by.full_name
        out.append(item)
    return out


async def get_detail(
    db: AsyncSession,
    engine: AuthzEngine,
    current_employee: Employee,
    record_id: uuid.UUID,
) -> dict:
    record = await onboarding_repo.get(db, record_id)
    if record is None:
        raise NotFound("Onboarding record not found")
    await assert_can_manage_record(db, engine, current_employee, record)

    out = _record_out(record, get_workflow_provider(), detail=True)
    out.documents = await _documents_out(db, record.employee_id)
    invitation = await _latest_invitation(db, record.employee_id)
    if invitation is not None:
        out.invitation = InvitationOut.model_validate(invitation)
    return out.model_dump(mode="json")


# ----------------------------------------------------------------- my actions


async def my_actions(db: AsyncSession, current_employee: Employee) -> list[dict]:
    result = await db.execute(
        select(OnboardingTask)
        .options(
            selectinload(OnboardingTask.assignee),
            selectinload(OnboardingTask.completed_by),
            selectinload(OnboardingTask.onboarding_record).selectinload(OnboardingRecord.employee),
        )
        .where(
            OnboardingTask.assignee_employee_id == current_employee.id,
            OnboardingTask.status == TaskStatus.READY,
        )
        .order_by(OnboardingTask.due_date.asc().nulls_last())
    )
    today = date.today()
    actions = []
    for task in result.scalars().all():
        record = task.onboarding_record
        if record.employee is None:
            continue
        actions.append(
            MyActionOut(
                record_id=record.id,
                task=_task_out(task),
                employee=_employee_out(record.employee),
                workflow_type=record.workflow_type,
                overdue=bool(task.due_date and task.due_date < today),
            ).model_dump(mode="json")
        )
    return actions


# --------------------------------------------------------------------- wizard


async def my_onboarding(db: AsyncSession, current_employee: Employee) -> dict | None:
    """The current user's own onboarding (any status) — powers /welcome."""
    result = await db.execute(
        onboarding_repo.base_query()
        .where(
            OnboardingRecord.employee_id == current_employee.id,
            OnboardingRecord.workflow_type == OnboardingType.ONBOARDING,
        )
        .order_by(OnboardingRecord.created_at.desc())
        .limit(1)
    )
    record = result.scalars().first()
    if record is None:
        return None
    out = _record_out(record, get_workflow_provider(), detail=True)
    # Self-service exposes the employee's tasks, never other assignees' notes or links.
    out.tasks = [t for t in out.tasks if t.assignee_employee_id == current_employee.id]
    out.current_task_title = next((t.title for t in out.tasks if t.status == TaskStatus.READY), None)
    out.current_assignee_name = None
    out.current_due_date = None
    out.embed_url = None
    out.documents = await _documents_out(db, current_employee.id)
    invitation = await _latest_invitation(db, current_employee.id)
    if invitation is not None:
        out.invitation = InvitationOut.model_validate(invitation)
    return out.model_dump(mode="json")


async def submit_wizard_profile(db: AsyncSession, current_employee: Employee, payload: WizardProfileIn) -> dict | None:
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    for field, value in changes.items():
        setattr(current_employee, field, value)

    await onboarding_flow_service.auto_complete(
        db,
        employee_id=current_employee.id,
        action_type=TaskActionType.EMPLOYEE_PROFILE,
        actor=current_employee,
        entity_type="employee",
        entity_id=current_employee.id,
    )
    await record_audit(
        db,
        actor_id=current_employee.user_id,
        action="wizard_profile_submit",
        entity_type="employee",
        entity_id=str(current_employee.id),
        diff={k: "***" if "bank" in k else v for k, v in changes.items()},
    )
    await db.commit()
    return await my_onboarding(db, current_employee)


async def accept_invitation(db: AsyncSession, current_employee: Employee, token: str) -> bool:
    accepted = await onboarding_flow_service.accept_invitation(db, current_employee, token)
    if accepted:
        await db.commit()
    return accepted


async def flag_expired_invitations(db: AsyncSession) -> None:
    """Housekeeping used by the outbox loop: expire stale invitations."""
    result = await db.execute(
        select(EmployeeInvitation).where(
            EmployeeInvitation.status == InvitationStatus.PENDING,
            EmployeeInvitation.expires_at <= datetime.now(UTC),
        )
    )
    for invitation in result.scalars().all():
        invitation.status = InvitationStatus.EXPIRED
    await db.commit()
