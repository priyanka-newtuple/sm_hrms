"""Template-driven onboarding: assignees, handoffs, auto-complete from real modules."""

from datetime import date
from uuid import uuid4

import pytest

from hrms.tests.conftest import (
    DELIVERY_MANAGER,
    EMPLOYEE,
    FINANCE,
    HR_BASIC,
    HR_FULL,
    OFFICE_ADMIN,
    login_as,
)

pytestmark = pytest.mark.asyncio

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 80


def _task(record: dict, seq: int) -> dict:
    return next(t for t in record["tasks"] if t["seq"] == seq)


async def _hire(client, seeded) -> dict:
    await login_as(client, HR_FULL)
    roles = (await client.get("/api/v1/roles")).json()
    employee_role = next(r for r in roles if r["name"] == "Employee")
    created = await client.post(
        "/api/v1/employees",
        json={
            "email": f"flow.hire.{uuid4().hex[:8]}@newtuple.com",
            "first_name": "Flow",
            "last_name": "Hire",
            "department": "Engineering",
            "designation": "Software Engineer",
            "role_id": employee_role["id"],
            "date_joined": str(seeded["today"]),
        },
    )
    assert created.status_code == 201, created.text
    records = (
        await client.get(
            "/api/v1/onboarding",
            params={"workflow_type": "onboarding", "page_size": 200},
        )
    ).json()["items"]
    record = next(r for r in records if r["employee_id"] == created.json()["id"])
    return {"employee": created.json(), "record": record}


async def test_onboarding_pipeline_stamps_assignees_and_parallel_ready_steps(client, seeded):
    data = await _hire(client, seeded)
    record = data["record"]
    assert len(record["tasks"]) == 8
    assert _task(record, 1)["status"] == "ready"
    assert _task(record, 2)["status"] == "ready"
    assert all(_task(record, s)["status"] == "pending" for s in (3, 4, 5, 7, 8))
    assert all(t["assignee_name"] for t in record["tasks"])
    assert record["current_task_title"]
    assert record["progress_total"] == 8
    assert record["progress_done"] == 0

    dup = await client.post(
        "/api/v1/onboarding/start",
        json={"employee_id": data["employee"]["id"], "workflow_type": "onboarding"},
    )
    assert dup.status_code == 409


async def test_onboarding_handoffs_invitation_wizard_docs_assets_allocations(client, seeded):
    data = await _hire(client, seeded)
    rid = data["record"]["id"]
    hire_id = data["employee"]["id"]

    await login_as(client, FINANCE)
    t2 = _task(data["record"], 2)
    done = await client.post(
        f"/api/v1/onboarding/{rid}/tasks/{t2['id']}/complete",
        json={"note": "Payroll contact created", "payroll_reference": "cont_TEST123"},
    )
    assert done.status_code == 200, done.text

    await login_as(client, OFFICE_ADMIN)
    t1 = _task(data["record"], 1)
    done = await client.post(
        f"/api/v1/onboarding/{rid}/tasks/{t1['id']}/complete",
        json={"note": "Workspace account live"},
    )
    assert done.status_code == 200, done.text
    await login_as(client, HR_FULL)
    record = (await client.get(f"/api/v1/onboarding/{rid}")).json()
    assert _task(record, 3)["status"] == "done"
    assert _task(record, 4)["status"] == "ready"
    assert _task(record, 5)["status"] == "ready"
    assert _task(record, 6)["status"] == "ready"

    await login_as(client, EMPLOYEE)
    blocked = await client.post(
        f"/api/v1/onboarding/{rid}/tasks/{_task(record, 7)['id']}/complete", json={}
    )
    assert blocked.status_code == 403

    await login_as(client, OFFICE_ADMIN)
    actions = (await client.get("/api/v1/onboarding/my-actions")).json()
    assert any(a["task"]["step_key"] == "asset_allocation" and a["record_id"] == rid for a in actions)

    await login_as(client, data["employee"]["work_email"])
    me = (await client.get("/api/v1/onboarding/me")).json()
    assert me["id"] == rid
    assert me.get("invitation")

    submitted = await client.post(
        "/api/v1/onboarding/me/profile",
        json={
            "phone": "+91-9000000001",
            "personal_email": "flow.hire@gmail.com",
            "address": "12 Test Lane, Bengaluru",
            "bank_account_number": "50210001112223",
            "bank_ifsc": "HDFC0009999",
        },
    )
    assert submitted.status_code == 200, submitted.text
    me = submitted.json()
    assert _task(me, 4)["status"] == "done"
    assert all(t["assignee_employee_id"] == hire_id for t in me["tasks"])

    for doc_type in ("id_proof", "pan", "education_certificate", "signed_offer_letter"):
        r = await client.post(
            f"/api/v1/onboarding/employees/{hire_id}/documents",
            data={"doc_type": doc_type},
            files={"file": (f"{doc_type}.png", PNG, "image/png")},
        )
        assert r.status_code == 200, r.text

    await login_as(client, HR_FULL)
    detail = (await client.get(f"/api/v1/onboarding/{rid}")).json()
    pan = next(d for d in detail["documents"] if d["doc_type"] == "pan")
    rejected = await client.post(
        f"/api/v1/onboarding/documents/{pan['id']}/review",
        json={"status": "rejected", "note": "Photo is blurry"},
    )
    assert rejected.status_code == 200

    await login_as(client, data["employee"]["work_email"])
    reup = await client.post(
        f"/api/v1/onboarding/employees/{hire_id}/documents",
        data={"doc_type": "pan"},
        files={"file": ("pan_v2.png", PNG, "image/png")},
    )
    assert reup.status_code == 200

    await login_as(client, HR_FULL)
    detail = (await client.get(f"/api/v1/onboarding/{rid}")).json()
    for doc in detail["documents"]:
        if doc["status"] == "submitted":
            r = await client.post(
                f"/api/v1/onboarding/documents/{doc['id']}/review",
                json={"status": "verified"},
            )
            assert r.status_code == 200, r.text
    detail = (await client.get(f"/api/v1/onboarding/{rid}")).json()
    assert _task(detail, 5)["status"] == "done"

    await login_as(client, HR_FULL)
    profile = (await client.get(f"/api/v1/employees/{hire_id}")).json()
    assert profile.get("payroll_reference") == "cont_TEST123"
    docs = (await client.get(f"/api/v1/onboarding/employees/{hire_id}/documents")).json()
    assert len(docs) >= 4

    await login_as(client, OFFICE_ADMIN)
    asset = await client.post(
        "/api/v1/assets",
        json={"asset_tag": "NT-TEST-1", "name": "Test Laptop", "asset_type": "Laptop"},
    )
    assert asset.status_code == 201, asset.text
    assigned = await client.post(
        f"/api/v1/assets/{asset.json()['id']}/assign",
        json={"employee_id": hire_id, "assigned_date": str(date.today())},
    )
    assert assigned.status_code == 201, assigned.text
    await login_as(client, HR_FULL)
    detail = (await client.get(f"/api/v1/onboarding/{rid}")).json()
    t6 = _task(detail, 6)
    assert t6["status"] == "done"
    assert t6["linked_entity_type"] == "asset_assignment"

    await login_as(client, HR_BASIC)
    t7 = _task(detail, 7)
    oriented = await client.post(
        f"/api/v1/onboarding/{rid}/tasks/{t7['id']}/complete",
        json={"note": "Orientation held"},
    )
    assert oriented.status_code == 200, oriented.text

    await login_as(client, DELIVERY_MANAGER)
    alloc = await client.post(
        "/api/v1/allocations",
        json={
            "employee_id": hire_id,
            "project_id": str(seeded["project_a_id"]),
            "allocation_percent": 10,
            "role_on_project": "Developer",
            "start_date": str(date.today()),
        },
    )
    assert alloc.status_code == 201, alloc.text

    await login_as(client, HR_FULL)
    final = (await client.get(f"/api/v1/onboarding/{rid}")).json()
    t8 = _task(final, 8)
    assert t8["status"] == "done"
    assert t8["linked_entity_type"] == "allocation"
    assert final["status"] == "completed"
    assert final["progress_done"] == 8
    assert final["progress_total"] == 8
