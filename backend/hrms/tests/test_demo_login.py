from __future__ import annotations

import pytest
from sqlalchemy import delete, select

from hrms.authz.enums import RoleName
from hrms.config import get_settings
from hrms.database import AsyncSessionLocal
from hrms.models.role import Role
from hrms.models.user import User
from hrms.seed.production_demo_data import DEMO_EMAILS, ensure_production_demo_employees


@pytest.mark.asyncio
async def test_demo_login_lists_and_authenticates_only_fixed_personas(client, seeded, monkeypatch):
    monkeypatch.setattr(get_settings(), "SEED_PRODUCTION_DEMO_DATA", True)
    async with AsyncSessionLocal() as db:
        role_rows = (await db.execute(select(Role))).scalars().all()
        roles = {RoleName(role.name): role for role in role_rows}
        await ensure_production_demo_employees(db, roles)
        await db.commit()

    try:
        personas = await client.get("/api/v1/auth/demo-users")
        assert personas.status_code == 200
        assert {persona["email"] for persona in personas.json()} == DEMO_EMAILS

        login = await client.post("/api/v1/auth/demo-login", json={"email": "demo.recruiter@newtuple.com"})
        assert login.status_code == 200
        me = await client.get("/api/v1/auth/me")
        assert me.status_code == 200
        assert me.json()["role_name"] == "Recruiter"

        arbitrary = await client.post("/api/v1/auth/demo-login", json={"email": "sanjay.bhat@newtuple.com"})
        assert arbitrary.status_code == 401
    finally:
        await client.post("/api/v1/auth/logout")
        async with AsyncSessionLocal() as db:
            await db.execute(delete(User).where(User.email.in_(DEMO_EMAILS)))
            await db.commit()
