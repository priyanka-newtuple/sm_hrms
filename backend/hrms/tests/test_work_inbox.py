"""End-to-end authorization and workflow transitions through the task inbox."""

import asyncio
from datetime import date
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from hrms.main import app
from hrms.tests.conftest import DELIVERY_MANAGER, EMPLOYEE, FINANCE, HR_BASIC, HR_FULL, OFFICE_ADMIN, PM_A, login_as
from hrms.tests.test_onboarding_flow import PNG, _hire, _task

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("email", [OFFICE_ADMIN, FINANCE, PM_A, EMPLOYEE])
async def test_participants_cannot_browse_or_start_workflows(client, seeded, email):
    data = await _hire(client, seeded)
    rid = data["record"]["id"]
    await login_as(client, email)
    assert (await client.get("/api/v1/onboarding")).status_code == 403
    assert (await client.get(f"/api/v1/onboarding/{rid}")).status_code == 403
    assert (
        await client.post(
            "/api/v1/onboarding/start",
            json={
                "employee_id": data["employee"]["id"],
                "workflow_type": "onboarding",
            },
        )
    ).status_code == 403
    assert (await client.get(f"/api/v1/onboarding/employees/{data['employee']['id']}/documents")).status_code == 403
    grants = (await client.get("/api/v1/auth/me")).json()["permissions"]
    assert next(p for p in grants if p["feature_key"] == "employee_onboarding")["actions"] == ["none"]


async def test_inbox_contains_only_assigned_ready_work_and_minimal_context(client, seeded):
    data = await _hire(client, seeded)
    t1, t2, t6 = (_task(data["record"], n) for n in (1, 2, 6))
    await login_as(client, OFFICE_ADMIN)
    response = await client.get(f"/api/v1/work/tasks/{t1['id']}")
    assert response.status_code == 200, response.text
    item = response.json()
    assert item["can_act"]
    assert item["record_id"] is None
    assert not {"tasks", "documents", "invitation", "employee_id", "bank_account_number", "embed_url"} & item.keys()
    assert (await client.get(f"/api/v1/work/tasks/{t2['id']}")).status_code == 404
    assert (await client.post(f"/api/v1/work/tasks/{t2['id']}/complete", json={})).status_code == 404
    waiting = await client.get("/api/v1/work", params={"view": "waiting", "page_size": 100})
    assert any(i["id"] == t6["id"] for i in waiting.json()["items"])
    before = (await client.get("/api/v1/work/summary")).json()["total"]
    completed = await client.post(f"/api/v1/work/tasks/{t1['id']}/complete", json={"note": "Workspace ready"})
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "done"
    assert "tasks" not in completed.json()
    assert (await client.get(f"/api/v1/work/tasks/{t6['id']}")).json()["can_act"]
    assert (await client.get("/api/v1/work/summary")).json()["total"] == before  # next task replaced it
    done = (await client.get("/api/v1/work", params={"view": "completed", "page_size": 100})).json()
    assert any(i["id"] == t1["id"] for i in done["items"])
    assert (await client.post(f"/api/v1/work/tasks/{t1['id']}/complete", json={})).status_code == 409


async def test_state_and_action_rules_cannot_be_bypassed(client, seeded):
    data = await _hire(client, seeded)
    rid = data["record"]["id"]
    t1, t2, t6 = (_task(data["record"], n) for n in (1, 2, 6))
    await login_as(client, OFFICE_ADMIN)
    assert (await client.post(f"/api/v1/work/tasks/{t6['id']}/complete", json={})).status_code == 409
    assert (await client.post(f"/api/v1/work/tasks/{t1['id']}/complete", json={"payroll_reference": "bad"})).status_code == 422
    result = await client.post(f"/api/v1/onboarding/{rid}/tasks/{t1['id']}/complete", json={})
    assert result.status_code == 200
    assert "tasks" not in result.json()  # legacy endpoint also returns only the changed task
    assert (await client.post(f"/api/v1/work/tasks/{t6['id']}/complete", json={})).status_code == 422
    await login_as(client, data["employee"]["work_email"])
    assert (await client.post(f"/api/v1/onboarding/{rid}/tasks/{t2['id']}/complete", json={})).status_code == 403
    own = (await client.get("/api/v1/onboarding/me")).json()
    assert all(t["assignee_employee_id"] == data["employee"]["id"] for t in own["tasks"])
    await login_as(client, FINANCE)
    assert (await client.post(f"/api/v1/work/tasks/{t2['id']}/complete", json={})).status_code == 422
    assert (
        await client.post(f"/api/v1/work/tasks/{t2['id']}/complete", json={"payroll_reference": "cont_work"})
    ).status_code == 200


async def test_task_asset_assignment_is_fixed_to_employee_and_creates_real_record(client, seeded):
    data = await _hire(client, seeded)
    t1, t6 = (_task(data["record"], n) for n in (1, 6))
    await login_as(client, OFFICE_ADMIN)
    await client.post(f"/api/v1/work/tasks/{t1['id']}/complete", json={})
    asset = (
        await client.post(
            "/api/v1/assets",
            json={
                "asset_tag": f"WORK-{uuid4().hex[:8]}",
                "name": "Inbox Laptop",
                "asset_type": "Laptop",
            },
        )
    ).json()
    options = (await client.get(f"/api/v1/work/tasks/{t6['id']}/assets")).json()
    assert any(o["id"] == asset["id"] for o in options)
    payload = {"asset_id": asset["id"], "assigned_date": str(date.today())}
    bad = await client.post(
        f"/api/v1/work/tasks/{t6['id']}/assets", json={**payload, "employee_id": str(seeded["employee_ids"]["eng_9"])}
    )
    assert bad.status_code == 422
    saved = await client.post(f"/api/v1/work/tasks/{t6['id']}/assets", json=payload)
    assert saved.status_code == 200, saved.text
    assert saved.json()["status"] == "done"
    assert (await client.post(f"/api/v1/work/tasks/{t6['id']}/assets", json=payload)).status_code == 409
    await login_as(client, HR_FULL)
    record = (await client.get(f"/api/v1/onboarding/{data['record']['id']}")).json()
    assert _task(record, 6)["linked_entity_type"] == "asset_assignment"


async def test_reassignment_revokes_former_assignee_and_records_reason(client, seeded):
    data = await _hire(client, seeded)
    task = _task(data["record"], 1)
    result = await client.post(
        f"/api/v1/work/tasks/{task['id']}/reassign",
        json={
            "employee_id": str(seeded["employee_ids"]["pm1"]),
            "reason": "Covering for office admin",
        },
    )
    assert result.status_code == 200, result.text
    await login_as(client, OFFICE_ADMIN)
    assert (await client.get(f"/api/v1/work/tasks/{task['id']}")).status_code == 404
    assert (await client.post(f"/api/v1/work/tasks/{task['id']}/complete", json={})).status_code == 404
    await login_as(client, PM_A)
    assert (await client.get(f"/api/v1/work/tasks/{task['id']}")).json()["can_act"]
    assert (await client.get("/api/v1/onboarding")).status_code == 403
    assert (await client.post(f"/api/v1/work/tasks/{task['id']}/complete", json={})).status_code == 200


async def test_document_approval_waiting_rejection_and_reupload(client, seeded):
    data = await _hire(client, seeded)
    eid = data["employee"]["id"]
    await login_as(client, data["employee"]["work_email"])
    doc = (
        await client.post(
            f"/api/v1/onboarding/employees/{eid}/documents",
            data={"doc_type": "pan"},
            files={"file": ("pan.png", PNG, "image/png")},
        )
    ).json()
    waiting = (await client.get("/api/v1/work", params={"view": "waiting"})).json()["items"]
    assert any(i["id"] == doc["id"] for i in waiting)
    await login_as(client, OFFICE_ADMIN)
    assert (await client.get(f"/api/v1/work/documents/{doc['id']}")).status_code == 404
    assert (await client.get(f"/api/v1/onboarding/documents/{doc['id']}/download")).status_code == 403
    await login_as(client, HR_FULL)
    assert (await client.get(f"/api/v1/work/documents/{doc['id']}")).json()["can_act"]
    assert (await client.get("/api/v1/work/summary")).json()["approvals"] >= 1
    url = f"/api/v1/onboarding/documents/{doc['id']}/review"
    assert (await client.post(url, json={"status": "rejected"})).status_code == 422
    assert (await client.post(url, json={"status": "rejected", "note": "Please upload a legible scan"})).status_code == 200
    assert (await client.post(url, json={"status": "verified"})).status_code == 409
    await login_as(client, data["employee"]["work_email"])
    second = (
        await client.post(
            f"/api/v1/onboarding/employees/{eid}/documents",
            data={"doc_type": "pan"},
            files={"file": ("pan2.png", PNG, "image/png")},
        )
    ).json()
    third = (
        await client.post(
            f"/api/v1/onboarding/employees/{eid}/documents",
            data={"doc_type": "pan"},
            files={"file": ("pan3.png", PNG, "image/png")},
        )
    ).json()
    await login_as(client, HR_FULL)
    assert not (await client.get(f"/api/v1/work/documents/{second['id']}")).json()["can_act"]
    assert (
        await client.post(f"/api/v1/onboarding/documents/{second['id']}/review", json={"status": "verified"})
    ).status_code == 409
    assert (
        await client.post(f"/api/v1/onboarding/documents/{third['id']}/review", json={"status": "verified"})
    ).status_code == 200


async def test_simultaneous_completion_has_one_winner(client, seeded):
    data = await _hire(client, seeded)
    task = _task(data["record"], 1)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as other:
        await login_as(client, OFFICE_ADMIN)
        await login_as(other, OFFICE_ADMIN)
        url = f"/api/v1/work/tasks/{task['id']}/complete"
        responses = await asyncio.gather(client.post(url, json={}), other.post(url, json={}))
        assert sorted(r.status_code for r in responses) == [200, 409]


async def test_project_allocation_from_task_respects_project_scope(client, seeded):
    data = await _hire(client, seeded)
    task = _task(data["record"], 8)
    await client.post(f"/api/v1/work/tasks/{_task(data['record'], 1)['id']}/complete", json={})
    await login_as(client, data["employee"]["work_email"])
    await client.post("/api/v1/onboarding/me/profile", json={"phone": "9000000011"})
    await login_as(client, HR_FULL)
    response = await client.post(f"/api/v1/work/tasks/{task['id']}/reassign", json={
        "employee_id": str(seeded["employee_ids"]["pm1"]), "reason": "Project manager owns the allocation",
    })
    assert response.status_code == 200, response.text
    await login_as(client, DELIVERY_MANAGER)
    assert (await client.get(f"/api/v1/work/tasks/{task['id']}")).status_code == 404
    await login_as(client, PM_A)
    options = (await client.get(f"/api/v1/work/tasks/{task['id']}/projects")).json()
    assert any(o["id"] == str(seeded["project_a_id"]) for o in options)
    assert all(o["id"] != str(seeded["project_b_id"]) for o in options)
    payload = {"project_id": str(seeded["project_b_id"]), "allocation_percent": 25,
               "role_on_project": "Developer", "start_date": str(date.today())}
    assert (await client.post(f"/api/v1/work/tasks/{task['id']}/allocation", json=payload)).status_code == 404
    payload["project_id"] = str(seeded["project_a_id"])
    result = await client.post(f"/api/v1/work/tasks/{task['id']}/allocation", json=payload)
    assert result.status_code == 200, result.text
    assert result.json()["item"]["status"] == "done"
    assert "allocation" not in result.json()  # only task context and capacity warning


async def test_review_self_approval_and_competing_reviewers(client, seeded):
    data = await _hire(client, seeded)
    eid = data["employee"]["id"]
    uploaded_by_hr = (await client.post(f"/api/v1/onboarding/employees/{eid}/documents",
        data={"doc_type": "pan"}, files={"file": ("pan.png", PNG, "image/png")})).json()
    url = f"/api/v1/onboarding/documents/{uploaded_by_hr['id']}/review"
    assert (await client.post(url, json={"status": "verified"})).status_code == 403
    assert not (await client.get(f"/api/v1/work/documents/{uploaded_by_hr['id']}")).json()["can_act"]
    await login_as(client, data["employee"]["work_email"])
    doc = (await client.post(f"/api/v1/onboarding/employees/{eid}/documents",
        data={"doc_type": "id_proof"}, files={"file": ("id.png", PNG, "image/png")})).json()
    url = f"/api/v1/onboarding/documents/{doc['id']}/review"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as other:
        await login_as(client, HR_FULL)
        await login_as(other, HR_BASIC)
        results = await asyncio.gather(client.post(url, json={"status": "verified"}),
            other.post(url, json={"status": "rejected", "note": "Please resubmit"}))
        assert sorted(r.status_code for r in results) == [200, 409]


async def test_pagination_filters_and_unauthenticated_access(client, seeded):
    assert (await client.get("/api/v1/work")).status_code == 401
    assert (await client.get("/api/v1/work/summary")).status_code == 401
    await _hire(client, seeded)
    await _hire(client, seeded)
    await login_as(client, OFFICE_ADMIN)
    first = (await client.get("/api/v1/work", params={"page_size": 1, "page": 1})).json()
    second = (await client.get("/api/v1/work", params={"page_size": 1, "page": 2})).json()
    assert first["total"] == second["total"] and first["total"] >= 2
    assert first["items"][0]["id"] != second["items"][0]["id"]
    assert (await client.get("/api/v1/work", params={"kind": "approval"})).json()["total"] == 0
