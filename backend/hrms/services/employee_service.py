from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hrms.authz.engine import AuthzEngine
from hrms.authz.enums import FeatureKey, RecordScope
from hrms.authz.scope_filters import apply_employee_scope
from hrms.authz.scope_guard import assert_in_scope
from hrms.authz.serializers import strip_employee_fields
from hrms.config import get_settings
from hrms.core.audit import record_audit
from hrms.core.exceptions import Conflict, NotFound, PermissionDenied, ValidationFailed
from hrms.models.asset import AssetAssignment
from hrms.models.employee import Employee
from hrms.models.enums import (
    AllocationStatus,
    EmploymentStatus,
    OnboardingStatus,
    OnboardingType,
    TimesheetStatus,
)
from hrms.models.onboarding import OnboardingRecord, OnboardingTask
from hrms.models.project import Project
from hrms.models.role import Role
from hrms.models.timesheet import Timesheet
from hrms.models.user import User
from hrms.repositories import allocation_repo, employee_repo
from hrms.schemas.employee import (
    EmployeeCreate,
    EmployeeOut,
    EmployeeUpdate,
    OffboardingBlocker,
    OffboardingReadiness,
    OffboardRequest,
)

FEATURE = FeatureKey.EMPLOYEE_DIRECTORY
settings = get_settings()

# Fields a caller may only change on someone else's record (or their own, if
# their EMPLOYEE_DIRECTORY scope is broader than SELF) — never on their own
# record when their grant is scoped to SELF, so self-service editing (phone,
# personal email, address...) can never be used to self-promote a role,
# reassign a manager, or alter compensation.
_PRIVILEGED_FIELDS = {
    "role_id",
    "reports_to_id",
    "department",
    "designation",
    "employment_status",
    "employment_type",
    "salary_ctc",
    "bank_account_number",
    "bank_ifsc",
    "employee_cost_rate",
    "probation_end_date",
    "confirmation_date",
    "notice_period_days",
}


def _serialize(employee: Employee, profile, permission_keys, *, is_self: bool) -> dict:
    data = EmployeeOut.model_validate(employee).model_dump(mode="json")
    return strip_employee_fields(data, profile, permission_keys, is_self=is_self)


async def list_employees(
    db: AsyncSession,
    engine: AuthzEngine,
    current_employee: Employee,
    *,
    offset: int,
    limit: int,
    search: str | None = None,
    department: str | None = None,
    status: str | None = None,
) -> tuple[list[dict], int]:
    scope = await engine.get_scope(current_employee, FEATURE)
    profile = await engine.get_data_profile(current_employee, FEATURE)
    permission_keys = await engine.get_all_permission_keys(current_employee)

    stmt = apply_employee_scope(employee_repo.base_query(), scope, current_employee)
    stmt = employee_repo.apply_filters(stmt, search=search, department=department, status=status)
    employees, total = await employee_repo.list_paginated(db, stmt, offset=offset, limit=limit)

    items = [_serialize(e, profile, permission_keys, is_self=(e.id == current_employee.id)) for e in employees]
    return items, total


async def get_employee(db: AsyncSession, engine: AuthzEngine, current_employee: Employee, employee_id: uuid.UUID) -> dict:
    is_self = employee_id == current_employee.id
    if not is_self:
        await assert_in_scope(
            db,
            engine,
            current_employee,
            feature=FEATURE,
            model=Employee,
            record_id=employee_id,
            scope_filter=apply_employee_scope,
            entity_label="Employee",
        )
    employee = await employee_repo.get_by_id(db, employee_id)
    if employee is None:
        raise NotFound("Employee not found")

    profile = await engine.get_data_profile(current_employee, FEATURE)
    permission_keys = await engine.get_all_permission_keys(current_employee)
    return _serialize(employee, profile, permission_keys, is_self=is_self)


async def _assert_valid_manager(db: AsyncSession, employee_id: uuid.UUID | None, manager_id: uuid.UUID) -> None:
    manager = await employee_repo.get_by_id(db, manager_id)
    if manager is None:
        raise NotFound("Reporting manager not found")
    if manager.employment_status == EmploymentStatus.OFFBOARDED:
        raise ValidationFailed(f"{manager.full_name} has been offboarded and cannot be a manager.")
    if employee_id and await employee_repo.would_create_reporting_cycle(db, employee_id, manager_id):
        raise ValidationFailed(
            "That reporting line would create a cycle — the chosen manager already reports up through this employee."
        )


async def create_employee(db: AsyncSession, engine: AuthzEngine, actor: Employee, payload: EmployeeCreate) -> dict:
    from hrms.services.reference_data_service import validate_employee_values

    await validate_employee_values(db, department=payload.department, designation=payload.designation)
    domain = payload.email.rsplit("@", 1)[-1].lower()
    if domain != settings.ALLOWED_EMAIL_DOMAIN.lower():
        raise ValidationFailed(f"Work email must be on @{settings.ALLOWED_EMAIL_DOMAIN} to match Google SSO.")
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none() is not None:
        raise Conflict(f"{payload.email} already exists.")

    if await db.get(Role, payload.role_id) is None:
        raise NotFound("Role not found")
    if payload.reports_to_id:
        await _assert_valid_manager(db, None, payload.reports_to_id)

    user = User(email=payload.email)
    db.add(user)
    await db.flush()

    data = payload.model_dump(exclude={"email"})
    employee = Employee(
        user_id=user.id,
        work_email=payload.email,
        employee_code=await employee_repo.next_employee_code(db),
        **data,
    )
    db.add(employee)
    await db.flush()

    # Every new hire starts an onboarding workflow automatically — the record is
    # what the Onboarding module lists, so creating an employee without one would
    # leave them invisible to HR's onboarding view. start_workflow stamps the
    # template (assignees, dependencies, handoff emails) when one exists.
    from hrms.services.onboarding_service import start_workflow

    record = OnboardingRecord(employee_id=employee.id, workflow_type=OnboardingType.ONBOARDING)
    db.add(record)
    await db.flush()
    await start_workflow(db, record, employee)

    await record_audit(
        db,
        actor_id=actor.user_id,
        action="create",
        entity_type="employee",
        entity_id=str(employee.id),
    )
    await db.commit()

    saved = await employee_repo.get_by_id(db, employee.id)
    profile = await engine.get_data_profile(actor, FEATURE)
    return _serialize(saved, profile, await engine.get_all_permission_keys(actor), is_self=False)


async def update_employee(
    db: AsyncSession,
    engine: AuthzEngine,
    actor: Employee,
    employee_id: uuid.UUID,
    payload: EmployeeUpdate,
) -> dict:
    is_self = employee_id == actor.id
    if not is_self:
        await assert_in_scope(
            db,
            engine,
            actor,
            feature=FEATURE,
            model=Employee,
            record_id=employee_id,
            scope_filter=apply_employee_scope,
            entity_label="Employee",
        )
    employee = await employee_repo.get_by_id(db, employee_id)
    if employee is None:
        raise NotFound("Employee not found")

    changes = payload.model_dump(exclude_unset=True)

    if "department" in changes or "designation" in changes:
        from hrms.services.reference_data_service import validate_employee_values

        await validate_employee_values(
            db,
            department=changes.get("department", employee.department),
            designation=changes.get("designation", employee.designation),
        )

    if is_self:
        scope = await engine.get_scope(actor, FEATURE)
        if scope == RecordScope.SELF:
            attempted = _PRIVILEGED_FIELDS & changes.keys()
            if attempted:
                raise PermissionDenied(f"Self-service edits cannot change: {', '.join(sorted(attempted))}")

    if changes.get("role_id") and await db.get(Role, changes["role_id"]) is None:
        raise NotFound("Role not found")
    if changes.get("reports_to_id"):
        await _assert_valid_manager(db, employee_id, changes["reports_to_id"])

    for field, value in changes.items():
        setattr(employee, field, value)
    await record_audit(
        db,
        actor_id=actor.user_id,
        action="update",
        entity_type="employee",
        entity_id=str(employee.id),
        diff=changes,
    )
    await db.commit()

    saved = await employee_repo.get_by_id(db, employee_id)
    profile = await engine.get_data_profile(actor, FEATURE)
    return _serialize(saved, profile, await engine.get_all_permission_keys(actor), is_self=is_self)


# --------------------------------------------------------------------- offboarding


async def offboarding_readiness(db: AsyncSession, employee_id: uuid.UUID) -> OffboardingReadiness:
    """
    Everything that must be resolved by a human before this employee can exit.

    Active allocations are deliberately absent: offboard_employee() end-dates
    those automatically, because nobody has to decide anything about them.
    """
    employee = await employee_repo.get_by_id(db, employee_id)
    if employee is None:
        raise NotFound("Employee not found")

    blockers: list[OffboardingBlocker] = []

    from hrms.models.enums import OPEN_PROJECT_STATUSES

    managed = await db.execute(
        select(Project).where(
            (Project.project_manager_id == employee_id) | (Project.delivery_manager_id == employee_id),
            Project.status.in_(OPEN_PROJECT_STATUSES),
        )
    )
    managed_projects = list(managed.scalars().all())
    if managed_projects:
        blockers.append(
            OffboardingBlocker(
                kind="managed_projects",
                message=f"Still manages {len(managed_projects)} open project(s). Reassign the project/delivery manager first.",
                items=[{"id": str(p.id), "code": p.code, "name": p.name} for p in managed_projects],
            )
        )

    reports = await employee_repo.direct_reports(db, employee_id)
    if reports:
        blockers.append(
            OffboardingBlocker(
                kind="direct_reports",
                message=f"Has {len(reports)} direct report(s). Reassign them to a new manager.",
                items=[{"id": str(r.id), "employee_code": r.employee_code, "name": r.full_name} for r in reports],
            )
        )

    assets = await db.execute(
        select(AssetAssignment).where(
            AssetAssignment.employee_id == employee_id,
            AssetAssignment.returned_date.is_(None),
        )
    )
    open_assets = list(assets.scalars().all())
    if open_assets:
        blockers.append(
            OffboardingBlocker(
                kind="unreturned_assets",
                message=f"Holds {len(open_assets)} unreturned asset(s).",
                items=[
                    {"id": str(a.id), "asset_id": str(a.asset_id), "assigned_date": str(a.assigned_date)} for a in open_assets
                ],
            )
        )

    timesheets = await db.execute(
        select(Timesheet).where(
            Timesheet.employee_id == employee_id,
            Timesheet.status.in_((TimesheetStatus.DRAFT, TimesheetStatus.SUBMITTED)),
        )
    )
    open_timesheets = list(timesheets.scalars().all())
    if open_timesheets:
        blockers.append(
            OffboardingBlocker(
                kind="open_timesheets",
                message=f"Has {len(open_timesheets)} unapproved timesheet(s).",
                items=[
                    {"id": str(t.id), "week_start_date": str(t.week_start_date), "status": t.status.value}
                    for t in open_timesheets
                ],
            )
        )

    return OffboardingReadiness(employee_id=employee_id, ready=not blockers, blockers=blockers)


async def offboard_employee(
    db: AsyncSession,
    engine: AuthzEngine,
    actor: Employee,
    employee_id: uuid.UUID,
    payload: OffboardRequest,
) -> dict:
    employee = await employee_repo.get_by_id(db, employee_id)
    if employee is None:
        raise NotFound("Employee not found")
    if employee.employment_status == EmploymentStatus.OFFBOARDED:
        raise Conflict(f"{employee.full_name} is already offboarded.")

    readiness = await offboarding_readiness(db, employee_id)
    if not readiness.ready:
        raise Conflict(
            f"{employee.full_name} cannot be offboarded yet.",
            {"blockers": [b.model_dump(mode="json") for b in readiness.blockers]},
        )

    # Cascade: close out open allocations at the last working day.
    for allocation in await allocation_repo.open_allocations_for_employee(db, employee_id):
        allocation.status = AllocationStatus.COMPLETED
        if allocation.end_date is None or allocation.end_date > payload.last_working_day:
            allocation.end_date = payload.last_working_day

    employee.employment_status = EmploymentStatus.OFFBOARDED
    employee.last_working_day = payload.last_working_day
    employee.exit_type = payload.exit_type
    employee.exit_reason = payload.exit_reason
    employee.rehire_eligible = payload.rehire_eligible

    # Revoke the login. This is the security-critical half of offboarding —
    # get_current_user() rejects inactive users, so their session dies too.
    user = await db.get(User, employee.user_id)
    if user is not None:
        user.is_active = False

    record = OnboardingRecord(
        employee_id=employee_id,
        workflow_type=OnboardingType.OFFBOARDING,
        status=OnboardingStatus.IN_PROGRESS,
        started_at=datetime.now(UTC),
    )
    db.add(record)
    await db.flush()
    from hrms.workflows.native import DEFAULT_OFFBOARDING_TASKS

    for title in DEFAULT_OFFBOARDING_TASKS:
        db.add(OnboardingTask(onboarding_record_id=record.id, title=title))

    await record_audit(
        db,
        actor_id=actor.user_id,
        action="offboard",
        entity_type="employee",
        entity_id=str(employee.id),
        diff={
            "last_working_day": str(payload.last_working_day),
            "exit_type": payload.exit_type.value,
        },
    )
    await db.commit()

    saved = await employee_repo.get_by_id(db, employee_id)
    profile = await engine.get_data_profile(actor, FEATURE)
    return _serialize(saved, profile, await engine.get_all_permission_keys(actor), is_self=False)


async def reactivate_employee(db: AsyncSession, engine: AuthzEngine, actor: Employee, employee_id: uuid.UUID) -> dict:
    """Reverse an offboarding (rehire, or an exit entered in error)."""
    employee = await employee_repo.get_by_id(db, employee_id)
    if employee is None:
        raise NotFound("Employee not found")
    if employee.employment_status == EmploymentStatus.ACTIVE:
        raise Conflict(f"{employee.full_name} is already active.")
    if employee.rehire_eligible is False:
        raise Conflict(f"{employee.full_name} is marked not eligible for rehire.")

    employee.employment_status = EmploymentStatus.ACTIVE
    employee.last_working_day = None
    employee.exit_type = None
    employee.exit_reason = None

    user = await db.get(User, employee.user_id)
    if user is not None:
        user.is_active = True

    await record_audit(
        db,
        actor_id=actor.user_id,
        action="reactivate",
        entity_type="employee",
        entity_id=str(employee.id),
    )
    await db.commit()

    saved = await employee_repo.get_by_id(db, employee_id)
    profile = await engine.get_data_profile(actor, FEATURE)
    return _serialize(saved, profile, await engine.get_all_permission_keys(actor), is_self=False)
