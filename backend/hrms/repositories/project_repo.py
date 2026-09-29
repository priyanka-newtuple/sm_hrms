from __future__ import annotations

import uuid

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from hrms.models.enums import CustomerStatus, ProjectStatus
from hrms.models.project import Customer, Project, ProjectApprovalRequest


def customers_base_query() -> Select:
    return select(Customer).options(selectinload(Customer.account_owner))


def projects_base_query() -> Select:
    return select(Project).options(
        selectinload(Project.customer),
        selectinload(Project.project_manager),
        selectinload(Project.delivery_manager),
        selectinload(Project.approval_requests).selectinload(ProjectApprovalRequest.requester),
        selectinload(Project.approval_requests).selectinload(ProjectApprovalRequest.reviewer),
    )


def apply_customer_filters(stmt: Select, *, search: str | None = None, include_archived: bool = False) -> Select:
    if not include_archived:
        stmt = stmt.where(Customer.status != CustomerStatus.ARCHIVED)
    if search:
        pattern = f"%{search.lower()}%"
        stmt = stmt.where(or_(func.lower(Customer.name).like(pattern), func.lower(Customer.code).like(pattern)))
    return stmt


def apply_project_filters(
    stmt: Select,
    *,
    search: str | None = None,
    status: ProjectStatus | None = None,
    customer_id: uuid.UUID | None = None,
    include_archived: bool = False,
) -> Select:
    if not include_archived:
        stmt = stmt.where(Project.status != ProjectStatus.ARCHIVED)
    if status:
        stmt = stmt.where(Project.status == status)
    if customer_id:
        stmt = stmt.where(Project.customer_id == customer_id)
    if search:
        pattern = f"%{search.lower()}%"
        stmt = stmt.where(or_(func.lower(Project.name).like(pattern), func.lower(Project.code).like(pattern)))
    return stmt


async def list_paginated(db: AsyncSession, stmt: Select, *, offset: int, limit: int, order_by):
    count_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = count_result.scalar_one()
    result = await db.execute(stmt.order_by(order_by).offset(offset).limit(limit))
    return list(result.scalars().all()), total


async def get_customer(db: AsyncSession, customer_id: uuid.UUID) -> Customer | None:
    result = await db.execute(customers_base_query().where(Customer.id == customer_id))
    return result.scalar_one_or_none()


async def get_project(db: AsyncSession, project_id: uuid.UUID) -> Project | None:
    result = await db.execute(projects_base_query().where(Project.id == project_id).execution_options(populate_existing=True))
    return result.scalar_one_or_none()


async def open_projects_for_customer(db: AsyncSession, customer_id: uuid.UUID) -> list[Project]:
    """Projects that still block the customer from being archived."""
    from hrms.models.enums import OPEN_PROJECT_STATUSES

    result = await db.execute(
        select(Project).where(Project.customer_id == customer_id, Project.status.in_(OPEN_PROJECT_STATUSES))
    )
    return list(result.scalars().all())


async def next_customer_code(db: AsyncSession) -> str:
    result = await db.execute(select(func.count()).select_from(Customer))
    return f"CUS-{result.scalar_one() + 1:04d}"


async def next_project_code(db: AsyncSession) -> str:
    result = await db.execute(select(func.count()).select_from(Project))
    return f"PRJ-{result.scalar_one() + 1:04d}"
