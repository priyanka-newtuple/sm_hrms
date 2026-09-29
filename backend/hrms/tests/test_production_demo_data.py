from __future__ import annotations

import pytest
from sqlalchemy import select

from hrms.authz.enums import RoleName
from hrms.database import AsyncSessionLocal
from hrms.models.role import Role
from hrms.seed.production_demo_data import DEMO_PERSONAS, ensure_production_demo_employees


@pytest.mark.asyncio
async def test_production_demo_personas_cover_every_role_and_are_idempotent(seeded):
    async with AsyncSessionLocal() as db:
        role_rows = (await db.execute(select(Role))).scalars().all()
        roles = {RoleName(role.name): role for role in role_rows}

        first = await ensure_production_demo_employees(db, roles)
        first_ids = {employee.id for employee in first}
        second = await ensure_production_demo_employees(db, roles)

        assert {persona.role for persona in DEMO_PERSONAS} == set(RoleName)
        assert {employee.id for employee in second} == first_ids
        assert len(first_ids) == len(RoleName)
        assert len({employee.employee_code for employee in second}) == len(RoleName)
        assert all(employee.work_email.startswith("demo.") for employee in second)

        await db.rollback()
