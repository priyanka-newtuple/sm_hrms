from __future__ import annotations

import uuid

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from hrms.models.helpdesk import HelpdeskCategory, HelpdeskTicket


def tickets_base_query() -> Select:
    return select(HelpdeskTicket)


async def list_paginated(db: AsyncSession, stmt: Select, *, offset: int, limit: int):
    count_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = count_result.scalar_one()
    result = await db.execute(stmt.order_by(HelpdeskTicket.created_at.desc()).offset(offset).limit(limit))
    return list(result.scalars().all()), total


async def get_ticket(db: AsyncSession, ticket_id: uuid.UUID) -> HelpdeskTicket | None:
    return await db.get(HelpdeskTicket, ticket_id)


async def list_categories(db: AsyncSession) -> list[HelpdeskCategory]:
    result = await db.execute(select(HelpdeskCategory).order_by(HelpdeskCategory.name))
    return list(result.scalars().all())


async def next_ticket_number(db: AsyncSession) -> str:
    result = await db.execute(select(func.count()).select_from(HelpdeskTicket))
    n = result.scalar_one() + 1
    return f"HD-{n:05d}"
