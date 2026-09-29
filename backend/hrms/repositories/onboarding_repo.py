from __future__ import annotations

import uuid

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from hrms.models.onboarding import OnboardingRecord, OnboardingTask


def base_query() -> Select:
    return select(OnboardingRecord).options(
        selectinload(OnboardingRecord.tasks).selectinload(OnboardingTask.assignee),
        selectinload(OnboardingRecord.tasks).selectinload(OnboardingTask.completed_by),
        selectinload(OnboardingRecord.employee),
    )


async def list_paginated(db: AsyncSession, stmt: Select, *, offset: int, limit: int):
    count_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = count_result.scalar_one()
    result = await db.execute(stmt.order_by(OnboardingRecord.created_at.desc()).offset(offset).limit(limit))
    return list(result.scalars().all()), total


async def get(db: AsyncSession, record_id: uuid.UUID) -> OnboardingRecord | None:
    result = await db.execute(base_query().where(OnboardingRecord.id == record_id).execution_options(populate_existing=True))
    return result.scalar_one_or_none()
