from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hrms.authz.engine import AuthzEngine
from hrms.authz.enums import FeatureKey, PermissionKey
from hrms.authz.scope_filters import apply_allocation_scope
from hrms.authz.scope_guard import assert_in_scope, assert_project_writable
from hrms.core.audit import record_audit
from hrms.core.exceptions import Conflict, NotFound, ValidationFailed
from hrms.models.allocation import Allocation
from hrms.models.employee import Employee
from hrms.models.enums import (
    ALLOCATABLE_PROJECT_STATUSES,
    COMMITTED_ALLOCATION_STATUSES,
    AllocationStatus,
    EmploymentStatus,
)
from hrms.repositories import allocation_repo, employee_repo, project_repo
from hrms.schemas.allocation import (
    AllocationCreate,
    AllocationOut,
    AllocationUpdate,
    AllocationWriteResult,
    CapacityConflict,
    CapacityOut,
)
from hrms.services import allocation_capacity_service as capacity_service

FEATURE = FeatureKey.ALLOCATIONS
CONFIRM_FIELDS = {"confirm_overallocation", "overallocation_reason"}


async def lock_employee(db, employee_id):
    employee = (await db.execute(select(Employee).where(Employee.id == employee_id).with_for_update())).scalar_one_or_none()
    if employee is None:
        raise NotFound("Employee not found")


def require_confirmation(payload, capacity):
    if capacity["over_allocated"] and (not payload.confirm_overallocation or not (payload.overallocation_reason or "").strip()):
        raise Conflict("Confirm overallocation and provide a reason before saving.", capacity)


def _serialize(allocation: Allocation, permission_keys: set[PermissionKey]) -> dict:
    data = AllocationOut.model_validate(allocation).model_dump(mode="json")
    if PermissionKey.VIEW_BILLING_RATE not in permission_keys:
        data.pop("billing_rate_override", None)
    return data


def _to_conflict(allocation: Allocation) -> CapacityConflict:
    return CapacityConflict(
        allocation_id=allocation.id,
        project_name=allocation.project.name if allocation.project else "Unknown project",
        allocation_percent=float(allocation.allocation_percent),
        start_date=allocation.start_date,
        end_date=allocation.end_date,
    )


async def _validate_against_related_records(
    db: AsyncSession,
    *,
    employee_id: uuid.UUID,
    project_id: uuid.UUID,
    start_date: date,
    end_date: date | None,
    exclude_allocation_id: uuid.UUID | None = None,
) -> None:
    """Cross-entity rules: the employee must be employable, the project open, and
    the allocation window must sit inside the project window."""
    employee = await employee_repo.get_by_id(db, employee_id)
    if employee is None:
        raise NotFound("Employee not found")
    if employee.employment_status in (EmploymentStatus.OFFBOARDING, EmploymentStatus.OFFBOARDED):
        raise ValidationFailed(f"{employee.full_name} is {employee.employment_status.value} and cannot be allocated.")

    project = await project_repo.get_project(db, project_id)
    if project is None:
        raise NotFound("Project not found")
    from hrms.services.project_approval_service import assert_operational

    project = await assert_operational(db, project_id)
    if project.status not in ALLOCATABLE_PROJECT_STATUSES:
        raise ValidationFailed(
            f"Project '{project.name}' is {project.status.value}; only planned or active projects can take allocations."
        )

    if start_date < project.start_date:
        raise ValidationFailed(
            "Allocation starts before the project does.",
            {"project_start_date": str(project.start_date)},
        )
    if project.end_date is not None:
        if end_date is None:
            raise ValidationFailed(
                "This project has an end date, so the allocation needs one too.",
                {"project_end_date": str(project.end_date)},
            )
        if end_date > project.end_date:
            raise ValidationFailed(
                "Allocation ends after the project does.",
                {"project_end_date": str(project.end_date)},
            )

    # Double-booking the same person onto the same project for overlapping days is a
    # data-quality error (unlike total over-allocation, which is only a warning).
    duplicates = await allocation_repo.overlapping_allocations(
        db,
        employee_id=employee_id,
        start_date=start_date,
        end_date=end_date,
        exclude_allocation_id=exclude_allocation_id,
        project_id=project_id,
    )
    if duplicates:
        raise Conflict(
            f"{employee.full_name} already has an overlapping allocation on this project.",
            {"conflicts": [_to_conflict(a).model_dump(mode="json") for a in duplicates]},
        )


async def _capacity_verdict(
    db: AsyncSession,
    *,
    employee_id: uuid.UUID,
    start_date: date,
    end_date: date | None,
    new_percent: float,
    exclude_allocation_id: uuid.UUID | None = None,
) -> tuple[bool, float, list[CapacityConflict]]:
    """Total committed % across the overlapping window, including the row being saved."""
    overlapping = await allocation_repo.overlapping_allocations(
        db,
        employee_id=employee_id,
        start_date=start_date,
        end_date=end_date,
        exclude_allocation_id=exclude_allocation_id,
    )
    total = capacity_service.summary(overlapping, start_date, end_date, new_percent)["total_allocation_percent"]
    return total > 100, total, [_to_conflict(a) for a in overlapping]


async def list_allocations(
    db: AsyncSession,
    engine: AuthzEngine,
    current_employee: Employee,
    *,
    offset: int,
    limit: int,
    employee_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    active_on: date | None = None,
    include_cancelled: bool = False,
    overallocated_only: bool = False,
):
    scope = await engine.get_scope(current_employee, FEATURE)
    permission_keys = await engine.get_all_permission_keys(current_employee)
    stmt = apply_allocation_scope(allocation_repo.base_query(), scope, current_employee)
    stmt = allocation_repo.apply_filters(
        stmt,
        employee_id=employee_id,
        project_id=project_id,
        active_on=active_on,
        include_cancelled=include_cancelled,
    )
    if overallocated_only:
        allocations = list((await db.execute(stmt.order_by(Allocation.start_date.desc(), Allocation.id))).scalars())
        items = await capacity_service.annotate(db, allocations, lambda a: _serialize(a, permission_keys))
        items = [item for item in items if item["over_allocated"]]
        return items[offset : offset + limit], len(items)
    allocations, total = await allocation_repo.list_paginated(db, stmt, offset=offset, limit=limit)
    return await capacity_service.annotate(db, allocations, lambda a: _serialize(a, permission_keys)), total


async def get_allocation(db: AsyncSession, engine: AuthzEngine, current_employee: Employee, allocation_id: uuid.UUID) -> dict:
    await assert_in_scope(
        db,
        engine,
        current_employee,
        feature=FEATURE,
        model=Allocation,
        record_id=allocation_id,
        scope_filter=apply_allocation_scope,
        entity_label="Allocation",
    )
    allocation = await allocation_repo.get(db, allocation_id)
    if allocation is None:
        raise NotFound("Allocation not found")
    permission_keys = await engine.get_all_permission_keys(current_employee)
    return (await capacity_service.annotate(db, [allocation], lambda a: _serialize(a, permission_keys)))[0]


async def create_allocation(
    db: AsyncSession, engine: AuthzEngine, actor: Employee, payload: AllocationCreate
) -> AllocationWriteResult:
    from hrms.services.reference_data_service import validate_project_role

    await validate_project_role(db, payload.role_on_project)
    # A PM holding Manage-Assigned may only allocate onto projects they manage.
    await assert_project_writable(db, engine, actor, feature=FEATURE, project_id=payload.project_id)
    await lock_employee(db, payload.employee_id)
    await _validate_against_related_records(
        db,
        employee_id=payload.employee_id,
        project_id=payload.project_id,
        start_date=payload.start_date,
        end_date=payload.end_date,
    )
    over, total, conflicts = await _capacity_verdict(
        db,
        employee_id=payload.employee_id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        new_percent=payload.allocation_percent,
    )

    rows = await capacity_service.employee_rows(db, payload.employee_id)
    capacity = capacity_service.summary(rows, payload.start_date, payload.end_date, payload.allocation_percent)
    if payload.status not in COMMITTED_ALLOCATION_STATUSES:
        capacity = dict(over_allocated=False, total_allocation_percent=0, overallocated_periods=[])
        over, total = False, 0
    require_confirmation(payload, capacity)
    allocation = Allocation(**payload.model_dump(exclude=CONFIRM_FIELDS), allocated_by_id=actor.id)
    db.add(allocation)
    await db.flush()

    if capacity["over_allocated"]:
        await capacity_service.notify_overallocation(db, actor, allocation, payload.overallocation_reason.strip(), capacity)

    # If this employee has an open onboarding with a PM-allocation step, this
    # allocation completes it (and emails the next assignee). No-op otherwise.
    from hrms.models.enums import TaskActionType
    from hrms.services import onboarding_flow_service

    await onboarding_flow_service.auto_complete(
        db,
        employee_id=payload.employee_id,
        action_type=TaskActionType.PROJECT_ALLOCATION,
        actor=actor,
        entity_type="allocation",
        entity_id=allocation.id,
    )

    await record_audit(
        db,
        actor_id=actor.user_id,
        action="create",
        entity_type="allocation",
        entity_id=str(allocation.id),
        diff={
            "over_allocated": over,
            "total_allocation_percent": total,
            "overallocation_reason": payload.overallocation_reason,
            "periods": capacity["overallocated_periods"],
        },
    )
    await db.commit()

    saved = await allocation_repo.get(db, allocation.id)
    permission_keys = await engine.get_all_permission_keys(actor)
    return AllocationWriteResult(
        allocation=(await capacity_service.annotate(db, [saved], lambda a: _serialize(a, permission_keys)))[0],
        over_allocated=over,
        total_allocation_percent=total,
        conflicts=conflicts,
    )


async def update_allocation(
    db: AsyncSession,
    engine: AuthzEngine,
    actor: Employee,
    allocation_id: uuid.UUID,
    payload: AllocationUpdate,
) -> AllocationWriteResult:
    await assert_in_scope(
        db,
        engine,
        actor,
        feature=FEATURE,
        model=Allocation,
        record_id=allocation_id,
        scope_filter=apply_allocation_scope,
        entity_label="Allocation",
    )
    allocation = await allocation_repo.get(db, allocation_id)
    if allocation is None:
        raise NotFound("Allocation not found")

    await lock_employee(db, allocation.employee_id)
    await db.refresh(allocation)
    await assert_project_writable(db, engine, actor, feature=FEATURE, project_id=allocation.project_id)
    changes = payload.model_dump(exclude_unset=True, exclude=CONFIRM_FIELDS)
    if "role_on_project" in changes:
        from hrms.services.reference_data_service import validate_project_role

        await validate_project_role(db, changes["role_on_project"])
    if any(
        changes.get(field, True) is None
        for field in ("start_date", "allocation_percent", "status", "role_on_project", "billable")
    ):
        raise ValidationFailed("Required allocation fields cannot be null.")
    start_date = changes.get("start_date", allocation.start_date)
    end_date = changes.get("end_date", allocation.end_date)
    percent = changes.get("allocation_percent", float(allocation.allocation_percent))

    if end_date is not None and end_date < start_date:
        raise ValidationFailed("end_date cannot be before start_date")

    await _validate_against_related_records(
        db,
        employee_id=allocation.employee_id,
        project_id=allocation.project_id,
        start_date=start_date,
        end_date=end_date,
        exclude_allocation_id=allocation_id,
    )
    over, total, conflicts = await _capacity_verdict(
        db,
        employee_id=allocation.employee_id,
        start_date=start_date,
        end_date=end_date,
        new_percent=percent,
        exclude_allocation_id=allocation_id,
    )

    rows = await capacity_service.employee_rows(db, allocation.employee_id)
    others = [r for r in rows if r.id != allocation.id]
    capacity = capacity_service.summary(others, start_date, end_date, percent)
    effective_status = changes.get("status", allocation.status)
    if effective_status not in COMMITTED_ALLOCATION_STATUSES:
        capacity = dict(over_allocated=False, total_allocation_percent=0, overallocated_periods=[])
        over, total = False, 0
    # A change worsens capacity if any affected day has more committed load than before.
    before = capacity_service.timeline(rows, start_date, end_date)
    worsens = False
    for period in capacity["overallocated_periods"]:
        for old in before:
            if old["start_date"] <= (period["end_date"] or "9999-12-31") and period["start_date"] <= (
                old["end_date"] or "9999-12-31"
            ):
                if period["total_allocation_percent"] > old["total_allocation_percent"]:
                    worsens = True
    if worsens:
        require_confirmation(payload, capacity)
    for field, value in changes.items():
        setattr(allocation, field, value)
    await db.flush()
    if worsens:
        await capacity_service.notify_overallocation(db, actor, allocation, payload.overallocation_reason.strip(), capacity)
    await record_audit(
        db,
        actor_id=actor.user_id,
        action="update",
        entity_type="allocation",
        entity_id=str(allocation.id),
        diff={
            **changes,
            "overallocation_reason": payload.overallocation_reason,
            "overallocated_periods": capacity["overallocated_periods"],
        },
    )
    await db.commit()

    saved = await allocation_repo.get(db, allocation_id)
    permission_keys = await engine.get_all_permission_keys(actor)
    return AllocationWriteResult(
        allocation=(await capacity_service.annotate(db, [saved], lambda a: _serialize(a, permission_keys)))[0],
        over_allocated=over,
        total_allocation_percent=total,
        conflicts=conflicts,
    )


async def cancel_allocation(db: AsyncSession, engine: AuthzEngine, actor: Employee, allocation_id: uuid.UUID) -> dict:
    """
    Archive-only policy: allocations are cancelled, never deleted, so the
    historical record of who was booked on what survives.
    """
    await assert_in_scope(
        db,
        engine,
        actor,
        feature=FEATURE,
        model=Allocation,
        record_id=allocation_id,
        scope_filter=apply_allocation_scope,
        entity_label="Allocation",
    )
    allocation = await allocation_repo.get(db, allocation_id)
    if allocation is None:
        raise NotFound("Allocation not found")
    await lock_employee(db, allocation.employee_id)
    await db.refresh(allocation)
    await assert_project_writable(db, engine, actor, feature=FEATURE, project_id=allocation.project_id)
    if allocation.status == AllocationStatus.CANCELLED:
        raise Conflict("Allocation is already cancelled.")

    allocation.status = AllocationStatus.CANCELLED
    await record_audit(
        db,
        actor_id=actor.user_id,
        action="cancel",
        entity_type="allocation",
        entity_id=str(allocation.id),
    )
    await db.commit()

    saved = await allocation_repo.get(db, allocation_id)
    permission_keys = await engine.get_all_permission_keys(actor)
    return _serialize(saved, permission_keys)


async def employee_capacity(db: AsyncSession, employee_id: uuid.UUID, on_date: date) -> CapacityOut:
    """Committed vs free capacity for one employee on a given day."""
    overlapping = await allocation_repo.overlapping_allocations(db, employee_id=employee_id, start_date=on_date, end_date=on_date)
    total = sum(float(a.allocation_percent) for a in overlapping)
    return CapacityOut(
        employee_id=employee_id,
        on_date=on_date,
        total_allocation_percent=total,
        available_percent=max(0.0, 100.0 - total),
        over_allocated=total > 100,
        allocations=[_to_conflict(a) for a in overlapping],
    )


async def preview_allocation(db, engine, actor, payload):
    await assert_project_writable(db, engine, actor, feature=FEATURE, project_id=payload.project_id)
    if await db.get(Employee, payload.employee_id) is None:
        raise NotFound("Employee not found")
    rows = await capacity_service.employee_rows(db, payload.employee_id)
    if payload.exclude_allocation_id:
        existing = next((r for r in rows if r.id == payload.exclude_allocation_id), None)
        if existing is None or existing.project_id != payload.project_id:
            raise NotFound("Allocation not found")
    others = [r for r in rows if r.id != payload.exclude_allocation_id]
    result = capacity_service.summary(others, payload.start_date, payload.end_date, payload.allocation_percent)
    result["allocations"] = [capacity_service.staffing_row(r, rows) for r in rows]
    return result
