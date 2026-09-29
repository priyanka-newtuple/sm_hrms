from __future__ import annotations

import uuid

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from hrms.models.employee import Employee


def base_query() -> Select:
    return select(Employee).options(selectinload(Employee.role), selectinload(Employee.reports_to))


def apply_filters(
    stmt: Select,
    *,
    search: str | None = None,
    department: str | None = None,
    status: str | None = None,
) -> Select:
    if search:
        pattern = f"%{search.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Employee.first_name).like(pattern),
                func.lower(Employee.last_name).like(pattern),
                func.lower(Employee.work_email).like(pattern),
                func.lower(Employee.employee_code).like(pattern),
            )
        )
    if department:
        stmt = stmt.where(Employee.department == department)
    if status:
        stmt = stmt.where(Employee.employment_status == status)
    return stmt


async def get_by_id(db: AsyncSession, employee_id: uuid.UUID) -> Employee | None:
    result = await db.execute(base_query().where(Employee.id == employee_id))
    return result.scalar_one_or_none()


async def list_paginated(db: AsyncSession, stmt: Select, *, offset: int, limit: int) -> tuple[list[Employee], int]:
    count_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = count_result.scalar_one()
    result = await db.execute(stmt.order_by(Employee.first_name).offset(offset).limit(limit))
    return list(result.scalars().all()), total


async def next_employee_code(db: AsyncSession) -> str:
    result = await db.execute(select(func.count()).select_from(Employee))
    return f"NT{result.scalar_one() + 1:04d}"


async def direct_reports(db: AsyncSession, employee_id: uuid.UUID) -> list[Employee]:
    result = await db.execute(select(Employee).where(Employee.reports_to_id == employee_id))
    return list(result.scalars().all())


async def would_create_reporting_cycle(db: AsyncSession, employee_id: uuid.UUID, new_manager_id: uuid.UUID) -> bool:
    """
    True if pointing `employee_id` at `new_manager_id` would close a loop —
    i.e. the proposed manager already reports (directly or transitively) to
    this employee. Walks up from the manager rather than using a recursive CTE
    so the guard stays readable and terminates on a pre-existing bad chain.
    """
    if employee_id == new_manager_id:
        return True
    seen: set[uuid.UUID] = set()
    cursor: uuid.UUID | None = new_manager_id
    while cursor is not None and cursor not in seen:
        seen.add(cursor)
        if cursor == employee_id:
            return True
        result = await db.execute(select(Employee.reports_to_id).where(Employee.id == cursor))
        cursor = result.scalar_one_or_none()
    return False
