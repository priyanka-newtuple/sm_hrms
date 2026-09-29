from __future__ import annotations

import calendar
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from hrms.authz.engine import AuthzEngine
from hrms.authz.enums import FeatureKey, RoleName
from hrms.authz.scope_filters import apply_timesheet_scope
from hrms.core.audit import record_audit
from hrms.core.exceptions import Conflict, NotFound, PermissionDenied, ValidationFailed
from hrms.models.allocation import Allocation
from hrms.models.employee import Employee
from hrms.models.enums import ALLOCATABLE_PROJECT_STATUSES, COMMITTED_ALLOCATION_STATUSES, ApprovalAction, TimesheetStatus
from hrms.models.timesheet import Holiday, LeaveRequest, Timesheet, TimesheetApproval
from hrms.repositories import timesheet_repo
from hrms.schemas.timesheet import (
    TimesheetApprovalIn,
    TimesheetCreate,
    TimesheetOut,
    TimesheetUpdate,
    WeekSaveIn,
)

FEATURE = FeatureKey.TIMESHEETS
HR_ROLES = {RoleName.HR_BASIC.value, RoleName.HR_FULL.value, RoleName.SUPER_ADMIN.value}


def _monday(value: date) -> date:
    return value - timedelta(days=value.weekday())


def _leave_out(row: LeaveRequest) -> dict:
    return {
        "id": row.id,
        "employee_id": row.employee_id,
        "employee_name": row.employee.full_name if row.employee else None,
        "manager_id": row.manager_id,
        "start_date": row.start_date,
        "end_date": row.end_date,
        "leave_type": row.leave_type,
        "reason": row.reason,
        "status": row.status,
        "decision_comment": row.decision_comment,
        "decided_at": row.decided_at,
    }


async def _holidays(db, start: date, end: date):
    return list(
        (
            await db.execute(
                select(Holiday)
                .where(Holiday.is_active.is_(True), Holiday.status == "published", Holiday.holiday_date.between(start, end))
                .order_by(Holiday.holiday_date)
            )
        ).scalars()
    )


async def _approved_leave_dates(db, employee_id, start, end):
    rows = (
        await db.execute(
            select(LeaveRequest).where(
                LeaveRequest.employee_id == employee_id,
                LeaveRequest.status == "approved",
                LeaveRequest.start_date <= end,
                LeaveRequest.end_date >= start,
            )
        )
    ).scalars()
    dates = set()
    for row in rows:
        current = max(start, row.start_date)
        while current <= min(end, row.end_date):
            dates.add(current)
            current += timedelta(days=1)
    return dates


async def _assigned_projects(db, employee_id, start, end):
    rows = (
        await db.execute(
            select(Allocation)
            .options(selectinload(Allocation.project))
            .where(
                Allocation.employee_id == employee_id,
                Allocation.status.in_(COMMITTED_ALLOCATION_STATUSES),
                Allocation.start_date <= end,
                or_(Allocation.end_date.is_(None), Allocation.end_date >= start),
            )
        )
    ).scalars()
    return {
        row.project_id: row
        for row in rows
        if row.project.approval_status == "approved" and row.project.status in ALLOCATABLE_PROJECT_STATUSES
    }


def _entry_out(row: Timesheet) -> dict:
    data = TimesheetOut.model_validate(row).model_dump(mode="json")
    data["project_name"] = row.project.name if row.project else "Unknown project"
    data["employee_name"] = row.employee.full_name if row.employee else None
    return data


def _submission_summary(rows: list[Timesheet], manager: Employee | None) -> dict | None:
    tracked = [
        row for row in rows if row.status in (TimesheetStatus.SUBMITTED, TimesheetStatus.APPROVED, TimesheetStatus.REJECTED)
    ]
    if not tracked:
        return None
    statuses = {row.status for row in tracked}
    if TimesheetStatus.SUBMITTED in statuses:
        status = TimesheetStatus.SUBMITTED.value
    elif TimesheetStatus.REJECTED in statuses:
        status = TimesheetStatus.REJECTED.value
    elif statuses == {TimesheetStatus.APPROVED}:
        status = TimesheetStatus.APPROVED.value
    else:
        status = "partially_reviewed"
    decisions = [approval for row in tracked for approval in row.approvals]
    latest = max(decisions, key=lambda item: item.created_at) if decisions else None
    submitted_dates = [row.submitted_at for row in tracked if row.submitted_at]
    return {
        "week_start_date": tracked[0].week_start_date,
        "status": status,
        "total_hours": sum(float(row.hours) for row in tracked),
        "submitted_at": max(submitted_dates) if submitted_dates else None,
        "pending_with_id": manager.id if status == TimesheetStatus.SUBMITTED.value and manager else None,
        "pending_with_name": manager.full_name if status == TimesheetStatus.SUBMITTED.value and manager else None,
        "decision_comment": latest.comment if latest else None,
        "decided_by_name": latest.approver.full_name if latest and latest.approver else None,
        "decided_at": latest.created_at if latest else None,
    }


async def _reporting_manager(db: AsyncSession, actor: Employee) -> Employee | None:
    return await db.get(Employee, actor.reports_to_id) if actor.reports_to_id else None


async def list_timesheets(db: AsyncSession, engine: AuthzEngine, current_employee: Employee, *, offset: int, limit: int):
    scope = await engine.get_scope(current_employee, FEATURE)
    stmt = apply_timesheet_scope(timesheet_repo.base_query(), scope, current_employee)
    # "View - Approved" for Finance is a status filter, not a RecordScope value —
    # applied here in the service layer (see seed/permission_matrix.py docstring).
    if current_employee.role.name == RoleName.FINANCE.value:
        stmt = stmt.where(Timesheet.status == TimesheetStatus.APPROVED)
    timesheets, total = await timesheet_repo.list_paginated(db, stmt, offset=offset, limit=limit)
    items = [TimesheetOut.model_validate(t).model_dump(mode="json") for t in timesheets]
    return items, total


async def create_timesheet(db: AsyncSession, actor: Employee, payload: TimesheetCreate) -> Timesheet:
    from hrms.services.project_approval_service import assert_operational

    await assert_operational(db, payload.project_id)
    if payload.work_date:
        if payload.work_date in {row.holiday_date for row in await _holidays(db, payload.work_date, payload.work_date)}:
            raise ValidationFailed("Time cannot be entered on a company holiday.")
        if payload.work_date in await _approved_leave_dates(db, actor.id, payload.work_date, payload.work_date):
            raise ValidationFailed("Time cannot be entered on an approved leave day.")
        projects = await _assigned_projects(db, actor.id, payload.work_date, payload.work_date)
        if payload.project_id not in projects:
            raise ValidationFailed("The project is not allocated to you on that date.")
    timesheet = Timesheet(employee_id=actor.id, **payload.model_dump())
    db.add(timesheet)
    await db.flush()
    await record_audit(db, actor_id=actor.user_id, action="create", entity_type="timesheet", entity_id=str(timesheet.id))
    await db.commit()
    await db.refresh(timesheet, attribute_names=["approvals"])
    return timesheet


async def update_timesheet(db: AsyncSession, actor: Employee, timesheet_id: uuid.UUID, payload: TimesheetUpdate) -> Timesheet:
    timesheet = await timesheet_repo.get(db, timesheet_id)
    if timesheet is None:
        raise NotFound("Timesheet not found")
    if timesheet.employee_id != actor.id:
        raise PermissionDenied("You can only edit your own timesheets")
    if timesheet.status != TimesheetStatus.DRAFT:
        raise PermissionDenied("Only draft timesheets can be edited")
    from hrms.services.project_approval_service import assert_operational

    await assert_operational(db, timesheet.project_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(timesheet, field, value)
    await db.commit()
    await db.refresh(timesheet, attribute_names=["approvals"])
    return timesheet


async def submit_timesheet(db: AsyncSession, actor: Employee, timesheet_id: uuid.UUID) -> Timesheet:
    timesheet = await timesheet_repo.get(db, timesheet_id)
    if timesheet is None:
        raise NotFound("Timesheet not found")
    if timesheet.employee_id != actor.id:
        raise PermissionDenied("You can only submit your own timesheets")
    from hrms.services.project_approval_service import assert_operational

    await assert_operational(db, timesheet.project_id)
    timesheet.status = TimesheetStatus.SUBMITTED
    timesheet.submitted_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(timesheet, attribute_names=["approvals"])
    return timesheet


async def decide_timesheet(
    db: AsyncSession,
    engine: AuthzEngine,
    approver: Employee,
    timesheet_id: uuid.UUID,
    payload: TimesheetApprovalIn,
) -> Timesheet:
    timesheet = await timesheet_repo.get(db, timesheet_id)
    if timesheet is None:
        raise NotFound("Timesheet not found")
    if timesheet.status != TimesheetStatus.SUBMITTED:
        raise PermissionDenied("Only submitted timesheets can be approved or rejected")

    # Confirm this specific timesheet falls within the approver's granted scope.
    scope = await engine.get_scope(approver, FEATURE)
    check_stmt = apply_timesheet_scope(select(Timesheet.id).where(Timesheet.id == timesheet_id), scope, approver)
    result = await db.execute(check_stmt)
    if result.scalar_one_or_none() is None:
        raise PermissionDenied("This timesheet is outside your approval scope")

    timesheet.status = TimesheetStatus.APPROVED if payload.action == ApprovalAction.APPROVE else TimesheetStatus.REJECTED
    db.add(
        TimesheetApproval(
            timesheet_id=timesheet.id,
            approver_id=approver.id,
            action=payload.action,
            comment=payload.comment,
        )
    )
    await record_audit(
        db,
        actor_id=approver.user_id,
        action=f"timesheet_{payload.action.value}",
        entity_type="timesheet",
        entity_id=str(timesheet.id),
    )
    await db.commit()
    await db.refresh(timesheet, attribute_names=["approvals"])
    return timesheet


async def week_view(db: AsyncSession, actor: Employee, week_start: date) -> dict:
    week_start = _monday(week_start)
    week_end = week_start + timedelta(days=6)
    projects = await _assigned_projects(db, actor.id, week_start, week_end)
    entries = list(
        (
            await db.execute(
                timesheet_repo.base_query().where(
                    Timesheet.employee_id == actor.id,
                    Timesheet.work_date.between(week_start, week_end),
                )
            )
        ).scalars()
    )
    holidays = await _holidays(db, week_start, week_end)
    leaves = list(
        (
            await db.execute(
                select(LeaveRequest)
                .options(selectinload(LeaveRequest.employee))
                .where(
                    LeaveRequest.employee_id == actor.id,
                    LeaveRequest.status.in_(["pending", "approved"]),
                    LeaveRequest.start_date <= week_end,
                    LeaveRequest.end_date >= week_start,
                )
            )
        ).scalars()
    )
    manager = await _reporting_manager(db, actor)
    return {
        "week_start_date": week_start,
        "days": [week_start + timedelta(days=index) for index in range(7)],
        "projects": [
            {"id": project_id, "name": allocation.project.name}
            for project_id, allocation in sorted(projects.items(), key=lambda pair: pair[1].project.name)
        ],
        "entries": [_entry_out(row) for row in entries],
        "holidays": holidays,
        "leaves": [_leave_out(row) for row in leaves],
        "total_hours": sum(float(row.hours) for row in entries),
        "submission": _submission_summary(entries, manager),
    }


async def my_submissions(db: AsyncSession, actor: Employee) -> list[dict]:
    rows = list(
        (
            await db.execute(
                timesheet_repo.base_query()
                .where(
                    Timesheet.employee_id == actor.id,
                    Timesheet.work_date.is_not(None),
                    Timesheet.status.in_([TimesheetStatus.SUBMITTED, TimesheetStatus.APPROVED, TimesheetStatus.REJECTED]),
                )
                .order_by(Timesheet.week_start_date.desc())
            )
        ).scalars()
    )
    manager = await _reporting_manager(db, actor)
    grouped: dict[date, list[Timesheet]] = {}
    for row in rows:
        grouped.setdefault(row.week_start_date, []).append(row)
    return [summary for week_rows in grouped.values() if (summary := _submission_summary(week_rows, manager))]


async def save_week(db: AsyncSession, actor: Employee, payload: WeekSaveIn) -> dict:
    week_start = _monday(payload.week_start_date)
    if week_start != payload.week_start_date:
        raise ValidationFailed("week_start_date must be a Monday.")
    week_end = week_start + timedelta(days=6)
    holiday_dates = {row.holiday_date for row in await _holidays(db, week_start, week_end)}
    leave_dates = await _approved_leave_dates(db, actor.id, week_start, week_end)
    projects = await _assigned_projects(db, actor.id, week_start, week_end)
    existing = list(
        (
            await db.execute(
                select(Timesheet)
                .where(
                    Timesheet.employee_id == actor.id,
                    Timesheet.work_date.between(week_start, week_end),
                )
                .with_for_update()
            )
        ).scalars()
    )
    if any(row.status in (TimesheetStatus.SUBMITTED, TimesheetStatus.APPROVED) for row in existing):
        raise Conflict("A submitted or approved week is locked until it is rejected.")
    by_key = {(row.project_id, row.work_date): row for row in existing}
    incoming_keys = set()
    totals: dict[date, float] = {}
    for row in existing:
        totals[row.work_date] = totals.get(row.work_date, 0) + float(row.hours)

    for entry in payload.entries:
        if not week_start <= entry.work_date <= week_end:
            raise ValidationFailed("Every entry must fall inside the selected week.")
        if entry.work_date in holiday_dates:
            raise ValidationFailed("Time cannot be entered on a company holiday.")
        if entry.work_date in leave_dates:
            raise ValidationFailed("Time cannot be entered on an approved leave day.")
        allocation = projects.get(entry.project_id)
        if (
            allocation is None
            or entry.work_date < allocation.start_date
            or (allocation.end_date and entry.work_date > allocation.end_date)
        ):
            raise ValidationFailed("The project is not allocated to you on that date.")
        key = (entry.project_id, entry.work_date)
        if key in incoming_keys:
            raise ValidationFailed("Only one entry per project and day is allowed.")
        incoming_keys.add(key)
        current = by_key.get(key)
        previous = float(current.hours) if current else 0
        totals[entry.work_date] = totals.get(entry.work_date, 0) - previous + entry.hours
        if totals[entry.work_date] > 24:
            raise ValidationFailed("Daily time across projects cannot exceed 24 hours.")
        if current and current.status not in (TimesheetStatus.DRAFT, TimesheetStatus.REJECTED):
            if entry.hours != previous or (entry.task_details or None) != current.task_details:
                raise Conflict("Submitted or approved entries cannot be changed.")
            continue
        if entry.hours == 0:
            if current:
                await db.delete(current)
            continue
        if current:
            current.hours = entry.hours
            current.task_details = entry.task_details
            current.notes = entry.task_details
            current.status = TimesheetStatus.DRAFT
            current.submitted_at = None
        else:
            db.add(
                Timesheet(
                    employee_id=actor.id,
                    project_id=entry.project_id,
                    week_start_date=week_start,
                    work_date=entry.work_date,
                    hours=entry.hours,
                    task_details=entry.task_details,
                    notes=entry.task_details,
                    status=TimesheetStatus.DRAFT,
                )
            )
    await record_audit(
        db,
        actor_id=actor.user_id,
        action="save_week",
        entity_type="timesheet_week",
        entity_id=f"{actor.id}:{week_start}",
        diff={"entry_count": len(payload.entries)},
    )
    await db.commit()
    return await week_view(db, actor, week_start)


async def submit_week(db: AsyncSession, actor: Employee, week_start: date) -> dict:
    week_start = _monday(week_start)
    week_end = week_start + timedelta(days=6)
    rows = list(
        (
            await db.execute(
                select(Timesheet)
                .where(
                    Timesheet.employee_id == actor.id,
                    Timesheet.work_date.between(week_start, week_end),
                    Timesheet.status.in_([TimesheetStatus.DRAFT, TimesheetStatus.REJECTED]),
                )
                .with_for_update()
            )
        ).scalars()
    )
    if not rows:
        raise ValidationFailed("There are no draft entries to submit for this week.")
    holidays = {row.holiday_date for row in await _holidays(db, week_start, week_end)}
    leave_dates = await _approved_leave_dates(db, actor.id, week_start, week_end)
    if any(row.work_date in holidays or row.work_date in leave_dates for row in rows):
        raise Conflict("This week contains time on a holiday or approved leave day. Update it before submitting.")
    submitted_at = datetime.now(UTC)
    for row in rows:
        row.status = TimesheetStatus.SUBMITTED
        row.submitted_at = submitted_at
    await db.commit()
    return await week_view(db, actor, week_start)


async def monthly_view(db: AsyncSession, actor: Employee, month: date) -> dict:
    start = month.replace(day=1)
    end = month.replace(day=calendar.monthrange(month.year, month.month)[1])
    entries = list(
        (
            await db.execute(
                timesheet_repo.base_query().where(
                    Timesheet.employee_id == actor.id,
                    Timesheet.work_date.between(start, end),
                )
            )
        ).scalars()
    )
    leaves = list(
        (
            await db.execute(
                select(LeaveRequest)
                .options(selectinload(LeaveRequest.employee))
                .where(
                    LeaveRequest.employee_id == actor.id,
                    LeaveRequest.start_date <= end,
                    LeaveRequest.end_date >= start,
                )
            )
        ).scalars()
    )
    return {
        "month": start.strftime("%Y-%m"),
        "entries": [_entry_out(row) for row in entries],
        "holidays": await _holidays(db, start, end),
        "leaves": [_leave_out(row) for row in leaves],
        "total_hours": sum(float(row.hours) for row in entries),
    }


async def approval_queue(db: AsyncSession, actor: Employee) -> list[dict]:
    query = timesheet_repo.base_query().where(Timesheet.status == TimesheetStatus.SUBMITTED, Timesheet.work_date.is_not(None))
    if actor.role.name != RoleName.SUPER_ADMIN.value:
        query = query.join(Employee, Timesheet.employee_id == Employee.id).where(Employee.reports_to_id == actor.id)
    rows = list((await db.execute(query.order_by(Timesheet.week_start_date, Timesheet.employee_id))).scalars())
    grouped = {}
    for row in rows:
        key = (row.employee_id, row.week_start_date)
        group = grouped.setdefault(
            key,
            {
                "employee_id": row.employee_id,
                "employee_name": row.employee.full_name,
                "week_start_date": row.week_start_date,
                "total_hours": 0,
                "entries": [],
            },
        )
        group["total_hours"] += float(row.hours)
        group["entries"].append(_entry_out(row))
    return list(grouped.values())


async def decide_week(db, actor, employee_id, week_start, payload):
    employee = await db.get(Employee, employee_id)
    if employee is None:
        raise NotFound("Employee not found")
    if actor.role.name != RoleName.SUPER_ADMIN.value and employee.reports_to_id != actor.id:
        raise PermissionDenied("Only the employee's reporting manager can review this week.")
    week_start = _monday(week_start)
    rows = list(
        (
            await db.execute(
                select(Timesheet)
                .where(
                    Timesheet.employee_id == employee_id,
                    Timesheet.week_start_date == week_start,
                    Timesheet.status == TimesheetStatus.SUBMITTED,
                    Timesheet.work_date.is_not(None),
                )
                .with_for_update()
            )
        ).scalars()
    )
    if not rows:
        raise Conflict("This week is no longer waiting for approval.")
    action = ApprovalAction.APPROVE if payload.action == ApprovalAction.APPROVE else ApprovalAction.REJECT
    for row in rows:
        row.status = TimesheetStatus.APPROVED if action == ApprovalAction.APPROVE else TimesheetStatus.REJECTED
        db.add(TimesheetApproval(timesheet_id=row.id, approver_id=actor.id, action=action, comment=payload.comment))
    await db.commit()
    return {"employee_id": employee_id, "week_start_date": week_start, "status": rows[0].status.value}


async def list_holidays(db, year: int) -> list[Holiday]:
    return list(
        (
            await db.execute(
                select(Holiday)
                .where(
                    Holiday.is_active.is_(True),
                    Holiday.status == "published",
                    Holiday.holiday_date >= date(year, 1, 1),
                    Holiday.holiday_date <= date(year, 12, 31),
                )
                .order_by(Holiday.holiday_date)
            )
        ).scalars()
    )


def _assert_hr(actor: Employee) -> None:
    if actor.role.name not in HR_ROLES:
        raise PermissionDenied("Only HR or Super Admin can manage the holiday calendar.")


async def create_holiday(db, actor: Employee, payload) -> Holiday:
    _assert_hr(actor)
    existing = (
        await db.execute(select(Holiday).where(Holiday.holiday_date == payload.holiday_date).with_for_update())
    ).scalar_one_or_none()
    if existing and existing.is_active:
        raise Conflict("A holiday already exists on this date.")
    if existing:
        existing.name = payload.name
        existing.description = payload.description
        existing.is_optional = payload.is_optional
        existing.is_active = True
        existing.created_by_id = actor.id
        holiday = existing
    else:
        holiday = Holiday(**payload.model_dump(), created_by_id=actor.id)
        db.add(holiday)
    await db.commit()
    await db.refresh(holiday)
    return holiday


async def update_holiday(db, actor: Employee, holiday_id, payload) -> Holiday:
    _assert_hr(actor)
    holiday = (await db.execute(select(Holiday).where(Holiday.id == holiday_id).with_for_update())).scalar_one_or_none()
    if holiday is None or not holiday.is_active:
        raise NotFound("Holiday not found")
    duplicate = (
        await db.execute(
            select(Holiday.id).where(
                Holiday.holiday_date == payload.holiday_date,
                Holiday.id != holiday.id,
                Holiday.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if duplicate:
        raise Conflict("A holiday already exists on this date.")
    for field, value in payload.model_dump().items():
        setattr(holiday, field, value)
    await db.commit()
    await db.refresh(holiday)
    return holiday


async def deactivate_holiday(db, actor: Employee, holiday_id) -> dict:
    _assert_hr(actor)
    holiday = (await db.execute(select(Holiday).where(Holiday.id == holiday_id).with_for_update())).scalar_one_or_none()
    if holiday is None or not holiday.is_active:
        raise NotFound("Holiday not found")
    holiday.is_active = False
    await db.commit()
    return {"id": holiday.id, "status": "inactive"}


async def list_leave_requests(db, actor: Employee, approvals: bool = False) -> list[dict]:
    query = select(LeaveRequest).options(selectinload(LeaveRequest.employee))
    if approvals:
        if actor.role.name != RoleName.SUPER_ADMIN.value:
            query = query.where(LeaveRequest.manager_id == actor.id)
        query = query.where(LeaveRequest.status == "pending")
    else:
        query = query.where(LeaveRequest.employee_id == actor.id)
    rows = (await db.execute(query.order_by(LeaveRequest.created_at.desc()))).scalars()
    return [_leave_out(row) for row in rows]


async def create_leave_request(db, actor: Employee, payload) -> dict:
    overlap = (
        await db.execute(
            select(LeaveRequest.id).where(
                LeaveRequest.employee_id == actor.id,
                LeaveRequest.status.in_(["pending", "approved"]),
                LeaveRequest.start_date <= payload.end_date,
                LeaveRequest.end_date >= payload.start_date,
            )
        )
    ).scalar_one_or_none()
    if overlap:
        raise Conflict("A pending or approved leave request already overlaps these dates.")
    time_exists = (
        await db.execute(
            select(Timesheet.id).where(
                Timesheet.employee_id == actor.id,
                Timesheet.work_date.between(payload.start_date, payload.end_date),
                Timesheet.status.in_([TimesheetStatus.SUBMITTED, TimesheetStatus.APPROVED]),
            )
        )
    ).scalar_one_or_none()
    if time_exists:
        raise Conflict("Submitted or approved time exists in this leave period.")
    row = LeaveRequest(employee_id=actor.id, manager_id=actor.reports_to_id, **payload.model_dump())
    db.add(row)
    await db.commit()
    saved = (
        await db.execute(select(LeaveRequest).options(selectinload(LeaveRequest.employee)).where(LeaveRequest.id == row.id))
    ).scalar_one()
    return _leave_out(saved)


async def decide_leave_request(db, actor: Employee, leave_id, payload) -> dict:
    row = (
        await db.execute(
            select(LeaveRequest).options(selectinload(LeaveRequest.employee)).where(LeaveRequest.id == leave_id).with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFound("Leave request not found")
    if actor.role.name != RoleName.SUPER_ADMIN.value and row.manager_id != actor.id:
        raise PermissionDenied("Only the employee's reporting manager can review this leave request.")
    if row.status != "pending":
        raise Conflict("This leave request is no longer pending.")
    if payload.decision == "approve":
        conflict = (
            await db.execute(
                select(Timesheet.id).where(
                    Timesheet.employee_id == row.employee_id,
                    Timesheet.work_date.between(row.start_date, row.end_date),
                    Timesheet.status.in_([TimesheetStatus.SUBMITTED, TimesheetStatus.APPROVED]),
                )
            )
        ).scalar_one_or_none()
        if conflict:
            raise Conflict("Submitted or approved time exists in this leave period.")
        drafts = (
            await db.execute(
                select(Timesheet).where(
                    Timesheet.employee_id == row.employee_id,
                    Timesheet.work_date.between(row.start_date, row.end_date),
                    Timesheet.status.in_([TimesheetStatus.DRAFT, TimesheetStatus.REJECTED]),
                )
            )
        ).scalars()
        for draft in drafts:
            await db.delete(draft)
        row.status = "approved"
    else:
        if not (payload.comment or "").strip():
            raise ValidationFailed("A comment is required when rejecting leave.")
        row.status = "rejected"
    row.decision_comment = payload.comment
    row.decided_by_id = actor.id
    row.decided_at = datetime.now(UTC)
    await db.commit()
    return _leave_out(row)


async def cancel_leave_request(db, actor: Employee, leave_id) -> dict:
    row = (await db.execute(select(LeaveRequest).where(LeaveRequest.id == leave_id).with_for_update())).scalar_one_or_none()
    if row is None or row.employee_id != actor.id:
        raise NotFound("Leave request not found")
    if row.status != "pending":
        raise Conflict("Only pending leave requests can be cancelled.")
    row.status = "cancelled"
    await db.commit()
    return {"id": row.id, "status": row.status}
