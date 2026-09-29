from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from hrms.models.allocation import Allocation
from hrms.models.enums import COMMITTED_ALLOCATION_STATUSES
from hrms.models.project import Project


def base_query() -> Select:
    return select(Allocation).options(
        selectinload(Allocation.employee),
        selectinload(Allocation.project).selectinload(Project.customer),
    )


def apply_filters(
    stmt: Select,
    *,
    employee_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    active_on: date | None = None,
    include_cancelled: bool = False,
) -> Select:
    if not include_cancelled:
        stmt = stmt.where(Allocation.status.in_(COMMITTED_ALLOCATION_STATUSES))
    if employee_id:
        stmt = stmt.where(Allocation.employee_id == employee_id)
    if project_id:
        stmt = stmt.where(Allocation.project_id == project_id)
    if active_on:
        stmt = stmt.where(
            Allocation.start_date <= active_on,
            or_(Allocation.end_date.is_(None), Allocation.end_date >= active_on),
        )
    return stmt


async def list_paginated(db: AsyncSession, stmt: Select, *, offset: int, limit: int):
    count_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = count_result.scalar_one()
    result = await db.execute(stmt.order_by(Allocation.start_date.desc()).offset(offset).limit(limit))
    return list(result.scalars().all()), total


async def get(db: AsyncSession, allocation_id: uuid.UUID) -> Allocation | None:
    result = await db.execute(base_query().where(Allocation.id == allocation_id))
    return result.scalar_one_or_none()


async def overlapping_allocations(
    db: AsyncSession,
    *,
    employee_id: uuid.UUID,
    start_date: date,
    end_date: date | None,
    exclude_allocation_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
) -> list[Allocation]:
    """
    Every committed allocation for this employee whose date window intersects
    [start_date, end_date].

    Two ranges overlap iff `start_a <= end_b AND start_b <= end_a`. A NULL
    end_date means "ongoing", so it is treated as +infinity — expressed here as
    `end_date IS NULL OR end_date >= other_start`.
    """
    conditions = [
        Allocation.employee_id == employee_id,
        Allocation.status.in_(COMMITTED_ALLOCATION_STATUSES),
        # existing.end >= new.start  (existing.end NULL => ongoing, always true)
        or_(Allocation.end_date.is_(None), Allocation.end_date >= start_date),
    ]
    if end_date is not None:
        # existing.start <= new.end  (new.end NULL => unbounded, so no constraint)
        conditions.append(Allocation.start_date <= end_date)
    stmt = base_query().where(*conditions)
    if exclude_allocation_id:
        stmt = stmt.where(Allocation.id != exclude_allocation_id)
    if project_id:
        stmt = stmt.where(Allocation.project_id == project_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def open_allocations_for_employee(db: AsyncSession, employee_id: uuid.UUID) -> list[Allocation]:
    """Committed allocations with no end date, or an end date in the future."""
    result = await db.execute(
        base_query().where(
            Allocation.employee_id == employee_id,
            Allocation.status.in_(COMMITTED_ALLOCATION_STATUSES),
        )
    )
    return list(result.scalars().all())
