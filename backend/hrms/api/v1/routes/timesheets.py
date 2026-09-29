from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from hrms.authz.deps import get_authz_engine, get_current_employee, require_permission
from hrms.authz.engine import AuthzEngine
from hrms.authz.enums import Action, FeatureKey
from hrms.core.pagination import Page
from hrms.database import get_db
from hrms.models.employee import Employee
from hrms.schemas.timesheet import (
    HolidayIn,
    HolidayOut,
    LeaveCreate,
    LeaveDecisionIn,
    TimesheetApprovalIn,
    TimesheetCreate,
    TimesheetOut,
    TimesheetUpdate,
    WeekSaveIn,
)
from hrms.services import timesheet_service

router = APIRouter(prefix="/timesheets", tags=["timesheets"])
FEATURE = FeatureKey.TIMESHEETS


@router.get("", response_model=Page)
async def list_timesheets(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    current_employee: Employee = Depends(require_permission(FEATURE, Action.VIEW)),
):
    items, total = await timesheet_service.list_timesheets(
        db, engine, current_employee, offset=(page - 1) * page_size, limit=page_size
    )
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/week")
async def week_view(
    week_start: date = Query(...),
    db: AsyncSession = Depends(get_db),
    actor: Employee = Depends(get_current_employee),
):
    return await timesheet_service.week_view(db, actor, week_start)


@router.put("/week")
async def save_week(
    payload: WeekSaveIn,
    db: AsyncSession = Depends(get_db),
    actor: Employee = Depends(get_current_employee),
):
    return await timesheet_service.save_week(db, actor, payload)


@router.post("/week/submit")
async def submit_week(
    week_start: date = Query(...),
    db: AsyncSession = Depends(get_db),
    actor: Employee = Depends(get_current_employee),
):
    return await timesheet_service.submit_week(db, actor, week_start)


@router.get("/month")
async def month_view(
    month: date = Query(...),
    db: AsyncSession = Depends(get_db),
    actor: Employee = Depends(get_current_employee),
):
    return await timesheet_service.monthly_view(db, actor, month)


@router.get("/submissions")
async def my_submissions(
    db: AsyncSession = Depends(get_db),
    actor: Employee = Depends(get_current_employee),
):
    return await timesheet_service.my_submissions(db, actor)


@router.get("/approvals")
async def approval_queue(
    db: AsyncSession = Depends(get_db),
    actor: Employee = Depends(require_permission(FEATURE, Action.APPROVE)),
):
    return await timesheet_service.approval_queue(db, actor)


@router.post("/approvals/{employee_id}/{week_start}/decision")
async def decide_week(
    employee_id: uuid.UUID,
    week_start: date,
    payload: TimesheetApprovalIn,
    db: AsyncSession = Depends(get_db),
    actor: Employee = Depends(require_permission(FEATURE, Action.APPROVE)),
):
    return await timesheet_service.decide_week(db, actor, employee_id, week_start, payload)


@router.get("/holidays", response_model=list[HolidayOut])
async def list_holidays(
    year: int = Query(..., ge=2000, le=2200),
    db: AsyncSession = Depends(get_db),
    _actor: Employee = Depends(get_current_employee),
):
    return await timesheet_service.list_holidays(db, year)


@router.post("/holidays", response_model=HolidayOut, status_code=201)
async def create_holiday(
    payload: HolidayIn,
    db: AsyncSession = Depends(get_db),
    actor: Employee = Depends(get_current_employee),
):
    return await timesheet_service.create_holiday(db, actor, payload)


@router.put("/holidays/{holiday_id}", response_model=HolidayOut)
async def update_holiday(
    holiday_id: uuid.UUID,
    payload: HolidayIn,
    db: AsyncSession = Depends(get_db),
    actor: Employee = Depends(get_current_employee),
):
    return await timesheet_service.update_holiday(db, actor, holiday_id, payload)


@router.delete("/holidays/{holiday_id}")
async def deactivate_holiday(
    holiday_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: Employee = Depends(get_current_employee),
):
    return await timesheet_service.deactivate_holiday(db, actor, holiday_id)


@router.get("/leave-requests")
async def list_leave_requests(
    approvals: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    actor: Employee = Depends(get_current_employee),
):
    return await timesheet_service.list_leave_requests(db, actor, approvals)


@router.post("/leave-requests", status_code=201)
async def create_leave_request(
    payload: LeaveCreate,
    db: AsyncSession = Depends(get_db),
    actor: Employee = Depends(get_current_employee),
):
    return await timesheet_service.create_leave_request(db, actor, payload)


@router.post("/leave-requests/{leave_id}/decision")
async def decide_leave_request(
    leave_id: uuid.UUID,
    payload: LeaveDecisionIn,
    db: AsyncSession = Depends(get_db),
    actor: Employee = Depends(get_current_employee),
):
    return await timesheet_service.decide_leave_request(db, actor, leave_id, payload)


@router.post("/leave-requests/{leave_id}/cancel")
async def cancel_leave_request(
    leave_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: Employee = Depends(get_current_employee),
):
    return await timesheet_service.cancel_leave_request(db, actor, leave_id)


@router.post("", response_model=TimesheetOut, status_code=201)
async def create_timesheet(
    payload: TimesheetCreate,
    db: AsyncSession = Depends(get_db),
    current_employee: Employee = Depends(require_permission(FEATURE, Action.CREATE)),
):
    return await timesheet_service.create_timesheet(db, current_employee, payload)


@router.patch("/{timesheet_id}", response_model=TimesheetOut)
async def update_timesheet(
    timesheet_id: uuid.UUID,
    payload: TimesheetUpdate,
    db: AsyncSession = Depends(get_db),
    current_employee: Employee = Depends(require_permission(FEATURE, Action.EDIT)),
):
    return await timesheet_service.update_timesheet(db, current_employee, timesheet_id, payload)


@router.post("/{timesheet_id}/submit", response_model=TimesheetOut)
async def submit_timesheet(
    timesheet_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_employee: Employee = Depends(require_permission(FEATURE, Action.EDIT)),
):
    return await timesheet_service.submit_timesheet(db, current_employee, timesheet_id)


@router.post("/{timesheet_id}/decide", response_model=TimesheetOut)
async def decide_timesheet(
    timesheet_id: uuid.UUID,
    payload: TimesheetApprovalIn,
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    current_employee: Employee = Depends(require_permission(FEATURE, Action.APPROVE)),
):
    return await timesheet_service.decide_timesheet(db, engine, current_employee, timesheet_id, payload)
