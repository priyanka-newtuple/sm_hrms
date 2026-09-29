"""
Integration tests run against a real Postgres (ARRAY(Enum) columns aren't
portable to SQLite). Point DATABASE_URL at a disposable test database before
running pytest, e.g.:

    DATABASE_URL=postgresql+asyncpg://hrms:hrms@localhost:5432/hrms_test pytest

CI does this automatically via a postgres service container (see
.github/workflows/ci.yml). Tables are created and dropped per test session;
never point this at a database with data you care about.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from hrms.database import AsyncSessionLocal, Base, engine
from hrms.config import get_settings
from hrms.main import app
from hrms.models.allocation import Allocation
from hrms.models.enums import AllocationStatus, CustomerStatus, ProjectStatus
from hrms.models.project import Customer, Project
from hrms.seed.seed_data import seed_employees, seed_roles_and_permissions


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _prepare_schema():
    if engine.url.database != "sm_hrms_test" or get_settings().ENV != "test":
        raise RuntimeError("Destructive fixtures require ENV=test and database sm_hrms_test")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="session")
async def seeded(_prepare_schema):
    """
    A minimal but fully-related fixture graph:

        Acme (CUS-0001) ─┬─ PM-A's project  (PRJ-0001, pm1)  ── eng_9 @ 60%
                         └─ PM-B's project  (PRJ-0002, pm2)

    Two project managers on two different projects is what makes the
    cross-manager scope tests meaningful.
    """
    async with AsyncSessionLocal() as db:
        roles = await seed_roles_and_permissions(db)
        emp = await seed_employees(db, roles)

        from hrms.services import onboarding_flow_service

        await onboarding_flow_service.ensure_default_template(db)

        customer = Customer(
            code="CUS-0001", name="Acme Industries", status=CustomerStatus.ACTIVE,
            currency="INR", contract_value=1_000_000,
        )
        db.add(customer)
        await db.flush()

        today = date.today()
        project_a = Project(
            code="PRJ-0001", name="PM-A Project", customer_id=customer.id,
            project_manager_id=emp["pm1"].id, delivery_manager_id=emp["delivery_manager"].id,
            status=ProjectStatus.ACTIVE, start_date=today - timedelta(days=90),
            billing_rate=12000, revenue=500000, margin_percent=25,
        )
        project_b = Project(
            code="PRJ-0002", name="PM-B Project", customer_id=customer.id,
            project_manager_id=emp["pm2"].id, delivery_manager_id=emp["delivery_manager"].id,
            status=ProjectStatus.ACTIVE, start_date=today - timedelta(days=60),
            billing_rate=14000, revenue=400000, margin_percent=30,
        )
        # Deliberately never allocated to by any test, so scope assertions about
        # "a project this employee cannot see" can't be invalidated by another
        # test allocating someone onto it first.
        project_untouched = Project(
            code="PRJ-0003", name="Untouched Project", customer_id=customer.id,
            project_manager_id=emp["pm2"].id, delivery_manager_id=emp["delivery_manager"].id,
            status=ProjectStatus.ACTIVE, start_date=today - timedelta(days=45),
            billing_rate=15000, revenue=300000, margin_percent=22,
        )
        db.add_all([project_a, project_b, project_untouched])
        await db.flush()

        allocation = Allocation(
            employee_id=emp["eng_9"].id, project_id=project_a.id,
            allocation_percent=60, role_on_project="Developer",
            start_date=today - timedelta(days=30), status=AllocationStatus.ACTIVE,
        )
        db.add(allocation)
        await db.commit()

        return {
            "employee_ids": {k: v.id for k, v in emp.items()},
            "user_ids": {k: v.user_id for k, v in emp.items()},
            "customer_id": customer.id,
            "project_a_id": project_a.id,   # managed by pm1
            "project_b_id": project_b.id,   # managed by pm2
            "project_untouched_id": project_untouched.id,  # managed by pm2, no allocations
            "allocation_id": allocation.id,
            "today": today,
        }


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def login_as(client: AsyncClient, email: str) -> None:
    resp = await client.post("/api/v1/auth/dev-login", json={"email": email})
    assert resp.status_code == 200, resp.text


# Convenience handles for the seeded personas.
SUPER_ADMIN = "ananya.rao@newtuple.com"
HR_FULL = "kavya.menon@newtuple.com"
HR_BASIC = "rohit.sharma@newtuple.com"
DELIVERY_MANAGER = "vikram.iyer@newtuple.com"
FINANCE = "neha.gupta@newtuple.com"
OFFICE_ADMIN = "suresh.nair@newtuple.com"
PM_A = "priya.desai@newtuple.com"     # manages project_a
PM_B = "arjun.kulkarni@newtuple.com"  # manages project_b
EMPLOYEE = "sanjay.bhat@newtuple.com"  # eng_9, allocated to project_a
