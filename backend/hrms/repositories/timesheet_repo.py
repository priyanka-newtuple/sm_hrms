from __future__ import annotations

import uuid

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from hrms.models.timesheet import Timesheet, TimesheetApproval


def base_query() -> Select:
    return select(Timesheet).options(
        selectinload(Timesheet.approvals).selectinload(TimesheetApproval.approver),
        selectinload(Timesheet.employee),
        selectinload(Timesheet.project),
    )


async def list_paginated(db: AsyncSession, stmt: Select, *, offset: int, limit: int):
    count_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = count_result.scalar_one()
    result = await db.execute(stmt.order_by(Timesheet.week_start_date.desc()).offset(offset).limit(limit))
    return list(result.scalars().all()), total


async def get(db: AsyncSession, timesheet_id: uuid.UUID) -> Timesheet | None:
    result = await db.execute(base_query().where(Timesheet.id == timesheet_id))
    return result.scalar_one_or_none()
