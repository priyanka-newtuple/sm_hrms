import asyncio
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from hrms.database import AsyncSessionLocal
from hrms.main import app
from hrms.models.allocation import Allocation
from hrms.models.enums import AllocationStatus
from hrms.models.notification import NotificationOutbox
from hrms.services.allocation_capacity_service import timeline
from hrms.tests.conftest import DELIVERY_MANAGER, EMPLOYEE, HR_BASIC, HR_FULL, PM_A, SUPER_ADMIN, login_as


def test_capacity_splits_non_simultaneous_bookings_and_inclusive_boundaries():
    def row(start, end, pct, status=AllocationStatus.ACTIVE):
        return SimpleNamespace(
            start_date=date(2030, 1, start), end_date=date(2030, 1, end), allocation_percent=pct, status=status
        )

    result = timeline(
        [row(1, 5, 60), row(6, 10, 60), row(1, 10, 100, AllocationStatus.CANCELLED)], date(2030, 1, 1), date(2030, 1, 10), 40
    )
    assert len(result) == 1 and result[0]["total_allocation_percent"] == 100
    result = timeline([row(1, 5, 60), row(5, 10, 60)], date(2030, 1, 1), date(2030, 1, 10), 40)
    over = [p for p in result if p["excess_percent"] > 0]
    assert over == [dict(start_date="2030-01-05", end_date="2030-01-05", total_allocation_percent=160, excess_percent=60)]


@pytest.mark.asyncio
async def test_reference_values_are_seeded_and_enforced(client, seeded):
    await login_as(client, SUPER_ADMIN)
    employee_options = await client.get("/api/v1/employees/form-options")
    assert employee_options.status_code == 200
    assert "Engineering" in {item["value"] for item in employee_options.json()["departments"]}
    assert "Software Engineer" in {item["value"] for item in employee_options.json()["designations"]}

    allocation_options = await client.get("/api/v1/allocations/options")
    assert allocation_options.status_code == 200
    assert "Developer" in {item["value"] for item in allocation_options.json()["project_roles"]}

    bad_employee = await client.patch(
        f"/api/v1/employees/{seeded['employee_ids']['eng_12']}",
        json={"department": "Invented Department"},
    )
    assert bad_employee.status_code == 422

    bad_allocation = await client.post(
        "/api/v1/allocations",
        json={
            "employee_id": str(seeded["employee_ids"]["eng_12"]),
            "project_id": str(seeded["project_a_id"]),
            "allocation_percent": 10,
            "role_on_project": "Invented Role",
            "start_date": str(seeded["today"]),
        },
    )
    assert bad_allocation.status_code == 422


@pytest.mark.asyncio
async def test_preview_confirmation_notifications_highlighting_and_reduction(client, seeded):
    employee = seeded["employee_ids"]["eng_24"]
    start = seeded["today"] + timedelta(days=1000)
    async with AsyncSessionLocal() as db:
        existing = Allocation(
            employee_id=employee,
            project_id=seeded["project_b_id"],
            allocation_percent=60,
            role_on_project="Engineer",
            start_date=start,
            end_date=start + timedelta(days=10),
            status=AllocationStatus.ACTIVE,
        )
        db.add(existing)
        await db.commit()
    payload = dict(
        employee_id=str(employee),
        project_id=str(seeded["project_a_id"]),
        allocation_percent=60,
        start_date=str(start),
        end_date=str(start + timedelta(days=20)),
        role_on_project="Engineer",
    )
    await login_as(client, PM_A)
    preview_payload = {k: v for k, v in payload.items() if k != "role_on_project"}
    preview = await client.post("/api/v1/allocations/preview", json=preview_payload)
    assert preview.status_code == 200, preview.text
    data = preview.json()
    assert data["total_allocation_percent"] == 120
    assert data["overallocated_periods"][0]["end_date"] == str(start + timedelta(days=10))
    assert data["allocations"][0]["project_name"] == "PM-B Project"
    assert data["allocations"][0]["manager_name"]
    assert not {"billing_rate", "billing_rate_override", "notes", "salary"} & data["allocations"][0].keys()
    assert (await client.post("/api/v1/allocations", json=payload)).status_code == 409
    assert (
        await client.post("/api/v1/allocations", json={**payload, "confirm_overallocation": True, "overallocation_reason": " "})
    ).status_code == 409
    saved = await client.post(
        "/api/v1/allocations", json={**payload, "confirm_overallocation": True, "overallocation_reason": "Client handover"}
    )
    assert saved.status_code == 201, saved.text
    allocation_id = saved.json()["allocation"]["id"]
    assert saved.json()["allocation"]["over_allocated"]

    async def notifications():
        async with AsyncSessionLocal() as db:
            return list(
                (
                    await db.execute(
                        select(NotificationOutbox).where(
                            NotificationOutbox.template_key == "allocation_overcapacity",
                            NotificationOutbox.payload["allocation_id"].astext == allocation_id,
                        )
                    )
                ).scalars()
            )

    messages = await notifications()
    assert {m.email_to for m in messages} == {PM_A, HR_FULL, HR_BASIC, SUPER_ADMIN}
    assert len(messages) == 4 and all("Client handover" in m.body_text and "120%" in m.body_text for m in messages)
    listed = await client.get("/api/v1/allocations", params={"employee_id": str(employee), "overallocated_only": True})
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["total_allocation_percent"] == 120
    # Metadata and reductions do not resend alerts; extension alone outside an overlap does not either.
    assert (await client.patch(f"/api/v1/allocations/{allocation_id}", json={"notes": "Routine note"})).status_code == 200
    assert (await client.patch(f"/api/v1/allocations/{allocation_id}", json={"allocation_percent": 55})).status_code == 200
    assert len(await notifications()) == 4
    assert (await client.patch(f"/api/v1/allocations/{allocation_id}", json={"allocation_percent": 70})).status_code == 409
    increased = await client.patch(
        f"/api/v1/allocations/{allocation_id}",
        json={"allocation_percent": 70, "confirm_overallocation": True, "overallocation_reason": "Longer handover"},
    )
    assert increased.status_code == 200
    assert len(await notifications()) == 8
    cancelled = await client.post(f"/api/v1/allocations/{allocation_id}/cancel")
    assert cancelled.status_code == 200
    assert (await client.get("/api/v1/allocations", params={"employee_id": str(employee), "overallocated_only": True})).json()[
        "total"
    ] == 0
    await login_as(client, EMPLOYEE)
    assert (await client.post("/api/v1/allocations/preview", json=preview_payload)).status_code == 403
    await login_as(client, PM_A)
    assert (
        await client.post("/api/v1/allocations/preview", json={**preview_payload, "project_id": str(seeded["project_b_id"])})
    ).status_code == 404
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Allocation).where(Allocation.employee_id == employee))
        await db.commit()


@pytest.mark.asyncio
async def test_concurrent_allocations_recheck_capacity_under_employee_lock(client, seeded):
    employee = seeded["employee_ids"]["eng_25"]
    start = seeded["today"] + timedelta(days=1400)
    payload = dict(
        employee_id=str(employee),
        allocation_percent=60,
        start_date=str(start),
        end_date=str(start + timedelta(days=5)),
        role_on_project="Engineer",
    )
    await login_as(client, DELIVERY_MANAGER)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as other:
        await login_as(other, DELIVERY_MANAGER)
        responses = await asyncio.gather(
            client.post("/api/v1/allocations", json={**payload, "project_id": str(seeded["project_a_id"])}),
            other.post("/api/v1/allocations", json={**payload, "project_id": str(seeded["project_b_id"])}),
        )
    assert sorted(r.status_code for r in responses) == [201, 409]
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Allocation).where(Allocation.employee_id == employee))
        await db.commit()
