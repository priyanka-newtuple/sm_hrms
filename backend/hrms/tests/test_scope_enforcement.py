"""
Regression tests for the record-scope gaps found during the CRUD pass.

Before app/authz/scope_guard.py existed, only the employee endpoints re-checked
RecordScope on single-record access. Projects and allocations did not, so
`GET /projects/{id}` was a live IDOR and a Project Manager could edit — or
allocate people onto — projects belonging to another manager.
"""

import pytest

from hrms.tests.conftest import EMPLOYEE, PM_A, PM_B, login_as

pytestmark = pytest.mark.asyncio


async def test_employee_cannot_read_unassigned_project_by_id(client, seeded):
    """The IDOR: list was correctly scoped, but get-by-id was not."""
    await login_as(client, EMPLOYEE)  # eng_9 — allocated to project_a only

    visible = await client.get("/api/v1/projects")
    assert visible.status_code == 200
    ids = {p["id"] for p in visible.json()["items"]}
    assert str(seeded["project_untouched_id"]) not in ids

    leaked = await client.get(f"/api/v1/projects/{seeded['project_untouched_id']}")
    assert leaked.status_code == 404


async def test_employee_can_read_their_own_project_by_id(client, seeded):
    await login_as(client, EMPLOYEE)
    resp = await client.get(f"/api/v1/projects/{seeded['project_a_id']}")
    assert resp.status_code == 200
    # Commercial fields still stripped — Employee holds no VIEW_* permission keys.
    assert "billing_rate" not in resp.json()


async def test_pm_cannot_edit_another_managers_project(client, seeded):
    await login_as(client, PM_A)
    resp = await client.patch(
        f"/api/v1/projects/{seeded['project_untouched_id']}", json={"name": "Hijacked"}
    )
    assert resp.status_code == 404


async def test_pm_can_edit_their_own_project(client, seeded):
    await login_as(client, PM_A)
    resp = await client.patch(
        f"/api/v1/projects/{seeded['project_a_id']}", json={"health": "amber"}
    )
    assert resp.status_code == 200
    assert resp.json()["health"] == "amber"


async def test_pm_cannot_allocate_onto_unmanaged_project(client, seeded):
    """Write-scope: RecordScope can't gate CREATE, so the FK is checked instead."""
    await login_as(client, PM_A)
    resp = await client.post(
        "/api/v1/allocations",
        json={
            "employee_id": str(seeded["employee_ids"]["eng_10"]),
            "project_id": str(seeded["project_untouched_id"]),  # pm2's project
            "allocation_percent": 50,
            "role_on_project": "Developer",
            "start_date": str(seeded["today"]),
        },
    )
    assert resp.status_code == 404


async def test_pm_can_allocate_onto_their_own_project(client, seeded):
    await login_as(client, PM_B)
    resp = await client.post(
        "/api/v1/allocations",
        json={
            "employee_id": str(seeded["employee_ids"]["eng_11"]),
            "project_id": str(seeded["project_b_id"]),
            "allocation_percent": 50,
            "role_on_project": "Developer",
            "start_date": str(seeded["today"]),
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["allocation"]["allocation_percent"] == 50


async def test_delivery_manager_sees_all_projects(client, seeded):
    from hrms.tests.conftest import DELIVERY_MANAGER

    await login_as(client, DELIVERY_MANAGER)
    resp = await client.get("/api/v1/projects")
    assert resp.status_code == 200
    ids = {p["id"] for p in resp.json()["items"]}
    assert {str(seeded["project_a_id"]), str(seeded["project_b_id"])} <= ids
