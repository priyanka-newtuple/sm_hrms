"""Cross-entity business rules: allocation capacity, archive guards, offboarding."""

from datetime import timedelta

import pytest

from hrms.tests.conftest import (
    DELIVERY_MANAGER,
    EMPLOYEE,
    FINANCE,
    HR_BASIC,
    HR_FULL,
    SUPER_ADMIN,
    login_as,
)

pytestmark = pytest.mark.asyncio


# ------------------------------------------------------------------ allocations


async def test_over_allocation_warns_but_still_saves(client, seeded):
    """User-chosen policy: exceeding 100% is reported, not refused."""
    await login_as(client, DELIVERY_MANAGER)
    # eng_9 already sits at 60% on project_a. Adding 60% on project_b => 120%.
    resp = await client.post(
        "/api/v1/allocations",
        json={
            "employee_id": str(seeded["employee_ids"]["eng_9"]),
            "project_id": str(seeded["project_b_id"]),
            "allocation_percent": 60,
            "confirm_overallocation": True,
            "overallocation_reason": "Approved transition overlap",
            "role_on_project": "Developer",
            "start_date": str(seeded["today"]),
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["over_allocated"] is True
    assert body["total_allocation_percent"] == 120
    assert len(body["conflicts"]) >= 1


async def test_within_capacity_reports_no_warning(client, seeded):
    await login_as(client, DELIVERY_MANAGER)
    resp = await client.post(
        "/api/v1/allocations",
        json={
            "employee_id": str(seeded["employee_ids"]["eng_12"]),
            "project_id": str(seeded["project_a_id"]),
            "allocation_percent": 40,
            "role_on_project": "QA",
            "start_date": str(seeded["today"]),
        },
    )
    assert resp.status_code == 201
    assert resp.json()["over_allocated"] is False


async def test_duplicate_allocation_on_same_project_is_rejected(client, seeded):
    """Distinct from over-allocation: double-booking one project is a data error."""
    await login_as(client, DELIVERY_MANAGER)
    resp = await client.post(
        "/api/v1/allocations",
        json={
            "employee_id": str(seeded["employee_ids"]["eng_9"]),
            "project_id": str(seeded["project_a_id"]),  # already allocated here
            "allocation_percent": 20,
            "role_on_project": "Developer",
            "start_date": str(seeded["today"]),
        },
    )
    assert resp.status_code == 409
    assert "conflicts" in resp.json()["detail"]


async def test_allocation_before_project_start_is_rejected(client, seeded):
    await login_as(client, DELIVERY_MANAGER)
    resp = await client.post(
        "/api/v1/allocations",
        json={
            "employee_id": str(seeded["employee_ids"]["eng_13"]),
            "project_id": str(seeded["project_a_id"]),
            "allocation_percent": 50,
            "role_on_project": "Developer",
            "start_date": str(seeded["today"] - timedelta(days=365)),
        },
    )
    assert resp.status_code == 422
    assert "project_start_date" in resp.json()["detail"]


async def test_capacity_endpoint_reports_committed_and_free(client, seeded):
    await login_as(client, DELIVERY_MANAGER)
    resp = await client.get(
        f"/api/v1/employees/{seeded['employee_ids']['eng_12']}/capacity",
        params={"on": str(seeded["today"])},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_allocation_percent"] + body["available_percent"] == 100


async def test_allocation_is_cancelled_not_deleted(client, seeded):
    """Archive-only: the row survives, flipped to CANCELLED."""
    await login_as(client, DELIVERY_MANAGER)
    created = await client.post(
        "/api/v1/allocations",
        json={
            "employee_id": str(seeded["employee_ids"]["eng_14"]),
            "project_id": str(seeded["project_a_id"]),
            "allocation_percent": 30,
            "role_on_project": "QA",
            "start_date": str(seeded["today"]),
        },
    )
    allocation_id = created.json()["allocation"]["id"]

    cancelled = await client.post(f"/api/v1/allocations/{allocation_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    # Still retrievable — history is preserved, not erased.
    assert (await client.get(f"/api/v1/allocations/{allocation_id}")).status_code == 200


async def test_allocation_nests_employee_and_project(client, seeded):
    """Responses carry related records so the UI needn't resolve ids client-side."""
    await login_as(client, DELIVERY_MANAGER)
    resp = await client.get(f"/api/v1/allocations/{seeded['allocation_id']}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["employee"]["full_name"]
    assert body["project"]["code"] == "PRJ-0001"
    assert body["project"]["customer"]["name"] == "Acme Industries"


# -------------------------------------------------------------------- customers


async def test_finance_can_create_customer(client, seeded):
    await login_as(client, FINANCE)
    resp = await client.post(
        "/api/v1/customers", json={"name": "Northwind Trading", "industry": "Logistics"}
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["code"].startswith("CUS-")


async def test_hr_basic_cannot_touch_customers(client, seeded):
    """The matrix gives HR-Basic no access to Customers at all."""
    await login_as(client, HR_BASIC)
    assert (await client.get("/api/v1/customers")).status_code == 403
    assert (
        await client.post("/api/v1/customers", json={"name": "Nope"})
    ).status_code == 403


async def test_archiving_customer_with_open_projects_is_blocked(client, seeded):
    await login_as(client, SUPER_ADMIN)
    resp = await client.post(f"/api/v1/customers/{seeded['customer_id']}/archive")
    assert resp.status_code == 409
    assert resp.json()["detail"]["projects"]


async def test_contract_value_hidden_without_permission_key(client, seeded):
    await login_as(client, HR_FULL)  # View-All on customers, but no commercial keys
    resp = await client.get(f"/api/v1/customers/{seeded['customer_id']}")
    assert resp.status_code == 200
    assert "contract_value" not in resp.json()

    await login_as(client, FINANCE)  # holds VIEW_CUSTOMER_CONTRACT_VALUE
    resp = await client.get(f"/api/v1/customers/{seeded['customer_id']}")
    assert resp.json()["contract_value"] is not None


# ------------------------------------------------------------------- offboarding


async def test_offboarding_readiness_lists_blockers(client, seeded):
    """pm1 manages a project and has direct reports — both must be resolved."""
    await login_as(client, HR_FULL)
    resp = await client.get(
        f"/api/v1/employees/{seeded['employee_ids']['pm1']}/offboarding-readiness"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ready"] is False
    assert "managed_projects" in {b["kind"] for b in body["blockers"]}


async def test_offboarding_is_refused_while_blocked(client, seeded):
    await login_as(client, HR_FULL)
    resp = await client.post(
        f"/api/v1/employees/{seeded['employee_ids']['pm1']}/offboard",
        json={"last_working_day": str(seeded["today"]), "exit_type": "resignation"},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["blockers"]


async def test_offboarding_a_clear_employee_cascades(client, seeded):
    """eng_20 has no reports, no managed projects, no assets, no timesheets."""
    employee_id = seeded["employee_ids"]["eng_20"]
    await login_as(client, HR_FULL)

    readiness = await client.get(f"/api/v1/employees/{employee_id}/offboarding-readiness")
    assert readiness.json()["ready"] is True

    resp = await client.post(
        f"/api/v1/employees/{employee_id}/offboard",
        json={
            "last_working_day": str(seeded["today"]),
            "exit_type": "resignation",
            "exit_reason": "Moving on",
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["employment_status"] == "offboarded"

    # The login must be revoked — this is the security-critical half.
    from sqlalchemy import select

    from hrms.database import AsyncSessionLocal
    from hrms.models.user import User

    async with AsyncSessionLocal() as db:
        user = (
            await db.execute(select(User).where(User.id == seeded["user_ids"]["eng_20"]))
        ).scalar_one()
        assert user.is_active is False


async def test_offboarded_employee_cannot_be_allocated(client, seeded):
    await login_as(client, DELIVERY_MANAGER)
    resp = await client.post(
        "/api/v1/allocations",
        json={
            "employee_id": str(seeded["employee_ids"]["eng_20"]),  # offboarded above
            "project_id": str(seeded["project_a_id"]),
            "allocation_percent": 50,
            "role_on_project": "Developer",
            "start_date": str(seeded["today"]),
        },
    )
    assert resp.status_code == 422
    assert "offboarded" in resp.json()["detail"]["message"]


# --------------------------------------------------------------------- employees


async def test_reporting_cycle_is_rejected(client, seeded):
    """pm1 reports to the delivery manager; pointing the DM at pm1 closes a loop."""
    await login_as(client, HR_FULL)
    resp = await client.patch(
        f"/api/v1/employees/{seeded['employee_ids']['delivery_manager']}",
        json={"reports_to_id": str(seeded["employee_ids"]["pm1"])},
    )
    assert resp.status_code == 422
    assert "cycle" in resp.json()["detail"]["message"]


async def test_employee_cannot_be_own_manager(client, seeded):
    await login_as(client, HR_FULL)
    employee_id = seeded["employee_ids"]["eng_9"]
    resp = await client.patch(
        f"/api/v1/employees/{employee_id}", json={"reports_to_id": str(employee_id)}
    )
    assert resp.status_code == 422


async def test_new_employee_must_use_company_domain(client, seeded):
    await login_as(client, HR_FULL)
    resp = await client.post(
        "/api/v1/employees",
        json={
            "email": "outsider@gmail.com",
            "first_name": "Out", "last_name": "Sider",
            "department": "Engineering", "designation": "Engineer",
            "role_id": str(seeded["employee_ids"]["eng_9"]),  # any uuid; domain fails first
            "date_joined": str(seeded["today"]),
        },
    )
    assert resp.status_code == 422
    assert "newtuple.com" in resp.json()["detail"]["message"]


async def test_creating_employee_starts_onboarding(client, seeded):
    await login_as(client, HR_FULL)
    roles = (await client.get("/api/v1/roles")).json()
    employee_role = next(r for r in roles if r["name"] == "Employee")

    created = await client.post(
        "/api/v1/employees",
        json={
            "email": "new.joiner@newtuple.com",
            "first_name": "New", "last_name": "Joiner",
            "department": "Engineering", "designation": "Software Engineer",
            "role_id": employee_role["id"],
            "date_joined": str(seeded["today"]),
        },
    )
    assert created.status_code == 201, created.text

    onboarding = await client.get("/api/v1/onboarding", params={"workflow_type": "onboarding"})
    records = [r for r in onboarding.json()["items"] if r["employee_id"] == created.json()["id"]]
    assert records, "new employee should appear on the onboarding pipeline"
    assert len(records[0]["tasks"]) == 8
    assert {t["seq"]: t["status"] for t in records[0]["tasks"] if t["seq"] in (1, 2)} == {
        1: "ready",
        2: "ready",
    }


async def test_employee_self_service_still_blocks_privileged_fields(client, seeded):
    """Guard from the earlier pass must survive the refactor."""
    await login_as(client, EMPLOYEE)
    employee_id = seeded["employee_ids"]["eng_9"]

    blocked = await client.patch(
        f"/api/v1/employees/{employee_id}", json={"department": "Leadership"}
    )
    assert blocked.status_code == 403

    allowed = await client.patch(
        f"/api/v1/employees/{employee_id}", json={"phone": "+91-9000000001"}
    )
    assert allowed.status_code == 200
