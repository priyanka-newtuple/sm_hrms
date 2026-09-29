from __future__ import annotations

import uuid

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from hrms.models.asset import Asset, AssetAssignment


def assets_base_query() -> Select:
    return select(Asset).options(selectinload(Asset.assignments))


async def list_paginated(db: AsyncSession, stmt: Select, *, offset: int, limit: int, order_by):
    count_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = count_result.scalar_one()
    result = await db.execute(stmt.order_by(order_by).offset(offset).limit(limit))
    return list(result.scalars().all()), total


async def get_asset(db: AsyncSession, asset_id: uuid.UUID) -> Asset | None:
    return await db.get(Asset, asset_id)


def assignments_base_query() -> Select:
    return select(AssetAssignment)
