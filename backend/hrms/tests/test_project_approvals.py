import asyncio
from datetime import timedelta
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from hrms.main import app
from hrms.tests.conftest import DELIVERY_MANAGER, EMPLOYEE, FINANCE, HR_FULL, PM_A, PM_B, SUPER_ADMIN, login_as

pytestmark = pytest.mark.asyncio


def payload(seeded, **changes):
    return {
        "name": f"Approval test {uuid4().hex[:8]}",
        "customer_id": str(seeded["customer_id"]),
        "project_manager_id": str(seeded["employee_ids"]["pm1"]),
        "delivery_manager_id": str(seeded["employee_ids"]["delivery_manager"]),
        "start_date": str(seeded["today"]),
        "budget_amount": 100000,
        **changes,
    }


async def create(client, seeded, email=PM_A, **changes):
    await login_as(client, email)
    response = await client.post("/api/v1/projects", json=payload(seeded, **changes))
    assert response.status_code == 201, response.text
    return response.json()


async def submit(client, project):
    request = project["approval_request"]
    response = await client.post(f"/api/v1/project-approvals/{request['id']}/submit", json={"version": request["version"]})
    assert response.status_code == 200, response.text
    return response.json()


async def decide(client, request, decision="approve", note=None):
    return await client.post(
        f"/api/v1/project-approvals/{request['id']}/decision",
        json={"decision": decision, "version": request["version"], "note": note},
    )


async def test_superadmin_direct_creation_is_approved_and_audited(client, seeded):
    project = await create(client, seeded, SUPER_ADMIN)
    assert project["approval_status"] == "approved"
    assert project["status"] == "planned"
    request = project["approval_request"]
    assert request["status"] == "approved"
    assert request["note"] == "Created and approved by Super Admin"
    assert request["history"][0]["action"] == "created_and_approved"
    assert request["history"][0]["snapshot"]["budget_amount"] == 100000
    completed = (await client.get("/api/v1/work", params={"view": "completed", "page_size": 100})).json()["items"]
    assert any(i["id"] == request["id"] for i in completed)


@pytest.mark.parametrize("creator", [PM_A, DELIVERY_MANAGER])
async def test_project_drafts_submit_to_superadmin_inbox(client, seeded, creator):
    project = await create(client, seeded, creator)
    assert project["approval_status"] == "draft"
    pending = await submit(client, project)
    assert pending["status"] == "pending"
    waiting = (await client.get("/api/v1/work", params={"view": "waiting", "page_size": 100})).json()["items"]
    assert any(i["id"] == pending["id"] and i["source"] == "projects" for i in waiting)
    assert (await decide(client, pending)).status_code == 403
    await login_as(client, SUPER_ADMIN)
    approvals = (await client.get("/api/v1/work", params={"kind": "approval", "page_size": 100})).json()["items"]
    assert any(i["id"] == pending["id"] for i in approvals)
    approved = await decide(client, pending)
    assert approved.status_code == 200, approved.text
    saved = (await client.get(f"/api/v1/projects/{project['id']}")).json()
    assert saved["approval_status"] == "approved"
    assert saved["status"] == "planned"
    assert saved["approval_request"]["reviewer_name"]


@pytest.mark.parametrize("reader", [EMPLOYEE, HR_FULL, FINANCE, PM_B])
async def test_unapproved_projects_are_not_visible_to_unrelated_roles(client, seeded, reader):
    project = await create(client, seeded)
    await login_as(client, reader)
    assert (await client.get(f"/api/v1/projects/{project['id']}")).status_code == 404
    assert (await client.get(f"/api/v1/project-approvals/{project['approval_request']['id']}")).status_code == 404
    items = (await client.get("/api/v1/projects", params={"search": project["name"]})).json()["items"]
    assert not items


async def test_unapproved_projects_cannot_be_used_or_promoted(client, seeded):
    project = await create(client, seeded)
    pid = project["id"]
    assert (await client.patch(f"/api/v1/projects/{pid}", json={"status": "active"})).status_code == 422
    assert (await client.patch(f"/api/v1/projects/{pid}", json={"approval_status": "approved"})).status_code == 422
    allocation = await client.post(
        "/api/v1/allocations",
        json={
            "employee_id": str(seeded["employee_ids"]["eng_9"]),
            "project_id": pid,
            "allocation_percent": 20,
            "role_on_project": "Engineer",
            "start_date": str(seeded["today"]),
        },
    )
    assert allocation.status_code == 422, allocation.text
    await login_as(client, EMPLOYEE)
    result = await client.post(
        "/api/v1/timesheets", json={"project_id": pid, "week_start_date": str(seeded["today"]), "hours": 8}
    )
    assert result.status_code == 422
    await login_as(client, SUPER_ADMIN)
    assert (await client.post("/api/v1/projects", json=payload(seeded, status="active"))).status_code == 422


async def test_changes_requested_resubmission_and_stale_decision(client, seeded):
    project = await create(client, seeded)
    pending = await submit(client, project)
    assert (await client.patch(f"/api/v1/projects/{project['id']}", json={"budget_amount": 50000})).status_code == 409
    await login_as(client, SUPER_ADMIN)
    assert (await decide(client, pending, "changes_requested")).status_code == 422
    changes = await decide(client, pending, "changes_requested", "Reduce the budget")
    assert changes.status_code == 200, changes.text
    await login_as(client, PM_A)
    edited = await client.patch(f"/api/v1/projects/{project['id']}", json={"budget_amount": 50000})
    assert edited.status_code == 200, edited.text
    resubmitted = await submit(client, edited.json())
    assert resubmitted["version"] > pending["version"]
    await login_as(client, SUPER_ADMIN)
    assert (await decide(client, pending)).status_code == 409
    done = await decide(client, resubmitted)
    assert done.status_code == 200, done.text
    assert done.json()["proposed"]["budget_amount"] == 50000
    snapshots = [e["snapshot"]["budget_amount"] for e in done.json()["history"] if e["action"] == "submitted"]
    assert snapshots == [100000, 50000]


async def test_withdraw_invalidates_old_review_and_rejection_is_terminal(client, seeded):
    project = await create(client, seeded)
    pending = await submit(client, project)
    result = await client.post(f"/api/v1/project-approvals/{pending['id']}/withdraw", json={"version": pending["version"]})
    assert result.status_code == 200, result.text
    await login_as(client, SUPER_ADMIN)
    assert (await decide(client, pending)).status_code == 409
    await login_as(client, PM_A)
    project = (await client.get(f"/api/v1/projects/{project['id']}")).json()
    again = await submit(client, project)
    await login_as(client, SUPER_ADMIN)
    assert (await decide(client, again, "reject", "Not proceeding")).status_code == 200
    await login_as(client, PM_A)
    assert (
        await client.post(f"/api/v1/project-approvals/{again['id']}/submit", json={"version": again["version"]})
    ).status_code == 409


async def test_amendments_preserve_live_values_until_approved(client, seeded):
    project = await create(client, seeded, SUPER_ADMIN)
    await login_as(client, PM_A)
    edited = await client.patch(f"/api/v1/projects/{project['id']}", json={"budget_amount": 200000})
    assert edited.status_code == 200, edited.text
    assert edited.json()["budget_amount"] == 100000
    assert edited.json()["approval_status"] == "approved"
    assert edited.json()["approval_request"]["kind"] == "amendment"
    pending = await submit(client, edited.json())
    await login_as(client, SUPER_ADMIN)
    assert (await decide(client, pending)).status_code == 200
    saved = (await client.get(f"/api/v1/projects/{project['id']}")).json()
    assert saved["budget_amount"] == 200000
    assert len(saved["approval_history"]) == 2


async def test_amendment_dates_cannot_exclude_existing_allocations(client, seeded):
    project = await create(client, seeded, SUPER_ADMIN)
    created = await client.post(
        "/api/v1/allocations",
        json={
            "employee_id": str(seeded["employee_ids"]["eng_9"]),
            "project_id": project["id"],
            "allocation_percent": 10,
            "confirm_overallocation": True,
            "overallocation_reason": "Allocation constraint test",
            "role_on_project": "Engineer",
            "start_date": str(seeded["today"]),
        },
    )
    assert created.status_code == 201, created.text
    await login_as(client, PM_A)
    edited = await client.patch(f"/api/v1/projects/{project['id']}", json={"end_date": str(seeded["today"] + timedelta(days=5))})
    pending = await submit(client, edited.json())
    await login_as(client, SUPER_ADMIN)
    result = await decide(client, pending)
    assert result.status_code == 422, result.text


async def test_concurrent_review_decisions_have_one_winner(client, seeded):
    pending = await submit(client, await create(client, seeded))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as other:
        await login_as(client, SUPER_ADMIN)
        await login_as(other, SUPER_ADMIN)
        results = await asyncio.gather(decide(client, pending), decide(other, pending, "reject", "Not approved"))
    assert sorted(r.status_code for r in results) == [200, 409]


async def test_pm_assignment_limits_and_creation_picker(client, seeded):
    await login_as(client, PM_A)
    result = await client.post("/api/v1/projects", json=payload(seeded, project_manager_id=str(seeded["employee_ids"]["pm2"])))
    assert result.status_code == 422
    options = (await client.get("/api/v1/project-creation-options")).json()
    assert options["customers"] and set(options["customers"][0]) == {"id", "label"}
    assert options["employees"] and set(options["employees"][0]) == {"id", "label"}
    await login_as(client, EMPLOYEE)
    assert (await client.get("/api/v1/project-creation-options")).status_code == 403


async def test_self_approval_exception_only_applies_to_superadmin_creation(client, seeded):
    project = await create(client, seeded, SUPER_ADMIN)
    edited = await client.patch(f"/api/v1/projects/{project['id']}", json={"budget_amount": 500000})
    pending = await submit(client, edited.json())
    assert (await decide(client, pending)).status_code == 403
